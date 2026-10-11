import os
import uuid
import time
import asyncio
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, status, BackgroundTasks, UploadFile, File, Response
from sqlalchemy.orm import Session
from pydantic import BaseModel, ConfigDict
from typing import List, Optional

from app.core.database import get_db
from app.models.project import Project
from app.models.task import Task, TaskStatus, RunnerType
from app.models.message import Message, MessageRole
from app.services.git_service import GitWorktreeService
from app.services.runner_service import RunnerService
from app.services.refiner_service import PromptRefinerService
from app.services.assistant_service import assistant_service
from app.services.terminal_service import terminal_service
from app.services.run_registry import run_registry
from app.services.artifact_service import artifact_service
from app.websockets.manager import ws_manager

router = APIRouter(prefix="/api/tasks", tags=["tasks"])
git_service = GitWorktreeService()
runner_service = RunnerService()
refiner_service = PromptRefinerService()


class TaskCreate(BaseModel):
    project_id: str
    title: str
    raw_prompt: str
    runner_type: Optional[str] = "SUBPROCESS_CLI"
    runner_config: Optional[dict] = None


class MessageCreate(BaseModel):
    content: str
    auto_run: Optional[bool] = False
    attachments: Optional[List[dict]] = None


class TaskResponse(BaseModel):
    id: str
    project_id: str
    title: str
    raw_prompt: str
    refined_spec: Optional[str] = None
    status: str
    runner_type: str
    runner_config: dict = {}
    worktree_path: Optional[str] = None
    git_branch: Optional[str] = None
    awaiting_you: bool = False
    project_name: Optional[str] = None
    # Apurados pelo processo real, não pelo status gravado no banco
    is_alive: bool = False
    stalled: bool = False
    started_at: Optional[float] = None
    # Estado único e explícito do card — o que vai escrito na tela
    card_state: str = "NA_FILA"
    changed_files: int = 0
    lines_added: int = 0
    lines_removed: int = 0

    model_config = ConfigDict(from_attributes=True)


class MessageResponse(BaseModel):
    id: str
    task_id: str
    role: str
    content: str
    attachments: Optional[List[dict]] = None
    created_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)


class AntigravityConversationItem(BaseModel):
    conversation_id: str
    title: str
    preview: str
    step_count: int
    last_modified: str
    workspace: str
    status: str
    already_imported: bool = False


class ImportAntigravityTaskRequest(BaseModel):
    project_id: str
    conversation_id: str
    title: Optional[str] = None


@router.get("/antigravity/conversations", response_model=List[AntigravityConversationItem])
def list_antigravity_conversations(project_id: Optional[str] = None, db: Session = Depends(get_db)):
    raw_convs = assistant_service.list_antigravity_conversations()
    existing_tasks = db.query(Task).all()
    imported_ids = set()
    for t in existing_tasks:
        if t.runner_config and isinstance(t.runner_config, dict):
            cid = t.runner_config.get("antigravity_conversation_id")
            if cid:
                imported_ids.add(cid)

    result = []
    for c in raw_convs:
        c_copy = dict(c)
        c_copy["already_imported"] = c["conversation_id"] in imported_ids
        result.append(AntigravityConversationItem(**c_copy))
    return result


def _importar_conversa(
    db: Session, project_id: str, conversation_id: str, title_override: Optional[str] = None
) -> Task:
    """Transforma uma conversa do Antigravity numa tarefa com todo o histórico."""
    conv_info = assistant_service.get_antigravity_conversation_info(conversation_id)
    transcript_msgs = assistant_service.get_conversation_transcript(conversation_id)

    title = (
        title_override
        or (conv_info.get("title") if conv_info else None)
        or f"Conversa {conversation_id[:8]}"
    ).strip()

    raw_prompt = ""
    for m in transcript_msgs:
        if m.get("role") == "USER":
            raw_prompt = m.get("content", "").strip()
            break
    if not raw_prompt:
        raw_prompt = (conv_info.get("preview") if conv_info else "") or title

    task = Task(
        project_id=project_id,
        title=title,
        raw_prompt=raw_prompt,
        status=TaskStatus.RUNNING,
        runner_type=RunnerType.SUBPROCESS_CLI,
        runner_config={
            "antigravity_conversation_id": conversation_id,
            "direct_mode": True
        }
    )
    db.add(task)
    db.commit()
    db.refresh(task)

    for m in transcript_msgs:
        role_enum = MessageRole.USER if m.get("role") == "USER" else MessageRole.ASSISTANT
        db.add(Message(task_id=task.id, role=role_enum, content=m.get("content", "")))
    db.commit()

    assistant_service.set_task_conversation_id(task.id, conversation_id)
    return task


def _ids_ja_importados(db: Session) -> set:
    ids = set()
    for t in db.query(Task).all():
        if isinstance(t.runner_config, dict):
            cid = t.runner_config.get("antigravity_conversation_id")
            if cid:
                ids.add(cid)
    return ids


@router.post("/import-antigravity", response_model=TaskResponse, status_code=status.HTTP_201_CREATED)
async def import_antigravity_task(data: ImportAntigravityTaskRequest, db: Session = Depends(get_db)):
    proj = db.query(Project).filter(Project.id == data.project_id).first()
    if not proj:
        raise HTTPException(status_code=404, detail="Projeto não encontrado")

    task = _importar_conversa(db, data.project_id, data.conversation_id, data.title)

    await ws_manager.broadcast_dashboard({
        "type": "TASK_CREATED",
        "task_id": task.id,
        "project_id": task.project_id
    })

    return task


class ImportBulkRequest(BaseModel):
    project_id: str
    # Vazio ou ausente = todas as que ainda não foram importadas
    conversation_ids: Optional[List[str]] = None


@router.post("/import-antigravity-bulk")
async def import_antigravity_bulk(data: ImportBulkRequest, db: Session = Depends(get_db)):
    """
    Importa várias conversas de uma vez. Pula as já importadas e segue em frente
    quando uma falha — perder o lote inteiro por causa de uma seria pior.
    """
    proj = db.query(Project).filter(Project.id == data.project_id).first()
    if not proj:
        raise HTTPException(status_code=404, detail="Projeto não encontrado")

    disponiveis = assistant_service.list_antigravity_conversations()
    alvos = data.conversation_ids or [c["conversation_id"] for c in disponiveis]
    ja_importados = _ids_ja_importados(db)

    importadas, puladas, falhas = [], 0, []
    for conv_id in alvos:
        if conv_id in ja_importados:
            puladas += 1
            continue
        try:
            task = _importar_conversa(db, data.project_id, conv_id)
            importadas.append(task.id)
        except Exception as e:
            db.rollback()
            falhas.append({"conversation_id": conv_id, "error": str(e)})

    if importadas:
        await ws_manager.broadcast_dashboard({
            "type": "TASKS_IMPORTED",
            "project_id": data.project_id,
            "count": len(importadas)
        })

    return {
        "imported": len(importadas),
        "skipped": puladas,
        "failed": falhas,
        "task_ids": importadas,
    }


@router.post("/{task_id}/sync-antigravity")
async def sync_task_with_antigravity(task_id: str, db: Session = Depends(get_db)):
    task = db.query(Task).filter(Task.id == task_id).first()
    if not task:
        raise HTTPException(status_code=404, detail="Tarefa não encontrada")

    conv_id = None
    if task.runner_config and isinstance(task.runner_config, dict):
        conv_id = task.runner_config.get("antigravity_conversation_id")

    if not conv_id:
        raise HTTPException(status_code=400, detail="Esta tarefa não possui uma sessão do Antigravity vinculada")

    transcript_msgs = assistant_service.get_conversation_transcript(conv_id)
    if not transcript_msgs:
        return {"synced": 0, "total_messages": len(task.messages)}

    existing_msgs = db.query(Message).filter(Message.task_id == task_id).order_by(Message.created_at.asc()).all()
    existing_contents = {m.content.strip() for m in existing_msgs}

    added_count = 0
    for m in transcript_msgs:
        c_text = (m.get("content") or "").strip()
        if not c_text:
            continue

        if c_text not in existing_contents:
            role_enum = MessageRole.USER if m.get("role") == "USER" else MessageRole.ASSISTANT
            new_msg = Message(
                task_id=task.id,
                role=role_enum,
                content=c_text
            )
            db.add(new_msg)
            db.commit()
            db.refresh(new_msg)
            existing_contents.add(c_text)
            added_count += 1

            await ws_manager.broadcast_task(task.id, {
                "type": "MESSAGE",
                "message": {
                    "id": new_msg.id,
                    "task_id": new_msg.task_id,
                    "role": new_msg.role.value,
                    "content": new_msg.content,
                    "created_at": new_msg.created_at.isoformat()
                }
            })

    return {"synced": added_count, "task_id": task.id, "total_antigravity": len(transcript_msgs)}


@router.post("/antigravity/{conversation_id}/sync")
async def sync_antigravity_conversation_endpoint(conversation_id: str, db: Session = Depends(get_db)):
    all_tasks = db.query(Task).all()
    target_task = None
    for t in all_tasks:
        if t.runner_config and isinstance(t.runner_config, dict):
            if t.runner_config.get("antigravity_conversation_id") == conversation_id:
                target_task = t
                break

    if not target_task:
        raise HTTPException(status_code=404, detail="Nenhuma tarefa vinculada a esta conversa do Antigravity")

    return await sync_task_with_antigravity(target_task.id, db)


@router.post("/sync-all")
async def sync_all_tasks_endpoint(project_id: Optional[str] = None, db: Session = Depends(get_db)):
    query = db.query(Task)
    if project_id:
        query = query.filter(Task.project_id == project_id)

    tasks = query.all()
    tasks_checked = 0
    tasks_updated = 0
    total_messages_synced = 0
    details = []

    for task in tasks:
        if task.runner_config and isinstance(task.runner_config, dict):
            conv_id = task.runner_config.get("antigravity_conversation_id")
            if conv_id:
                tasks_checked += 1
                res = await sync_task_with_antigravity(task.id, db)
                synced_count = res.get("synced", 0)
                if synced_count > 0:
                    tasks_updated += 1
                    total_messages_synced += synced_count
                details.append({
                    "task_id": task.id,
                    "title": task.title,
                    "synced": synced_count
                })

    return {
        "tasks_checked": tasks_checked,
        "tasks_updated": tasks_updated,
        "total_messages_synced": total_messages_synced,
        "details": details
    }


def _is_awaiting_you(task: Task, db: Session, is_alive: bool = False) -> bool:
    """
    A bola está com o usuário quando:
      - há diff para revisar ou falha para tratar, ou
      - o agente falou por último e a tarefa ainda não acabou.
    Derivado do que já existe — não é um status novo no banco.
    """
    # Agente trabalhando agora não espera ninguém: ter uma conversa que terminou
    # com fala dele não significa que a bola voltou para o usuário.
    if is_alive:
        return False
    if task.status == TaskStatus.DONE:
        return False
    if task.status in (TaskStatus.REVIEW_READY, TaskStatus.FAILED):
        return True

    last = (
        db.query(Message)
        .filter(Message.task_id == task.id)
        .order_by(Message.created_at.desc(), Message.id.desc())
        .first()
    )
    return bool(last and last.role == MessageRole.ASSISTANT)


# Conversa que passa disto sem terminar foi interrompida (servidor caiu, por
# exemplo). Sem expirar, o card diria "executando" para sempre.
CHAT_BUSY_TIMEOUT = 15 * 60


def _marcar_chat_ocupado(db: Session, task: Task, ocupado: bool) -> None:
    """Liga/desliga o sinal de que o chat está processando esta tarefa."""
    cfg = dict(task.runner_config or {})
    if ocupado:
        cfg["chat_busy_since"] = time.time()
    else:
        cfg.pop("chat_busy_since", None)
    task.runner_config = cfg
    db.commit()


async def _responder_e_desmarcar(db: Session, task: Task, coro):
    """
    Garante que a marca saia mesmo se o agente falhar — senão o card ficaria
    dizendo "executando" para sempre por causa de um erro.

    Avisa o painel ao terminar: é o sinal de que a bola voltou para o usuário.
    Sem o aviso, o card só mudaria no próximo ciclo de 20s.
    """
    try:
        return await coro
    finally:
        _marcar_chat_ocupado(db, task, ocupado=False)
        await ws_manager.broadcast_dashboard({
            "type": "TASK_UPDATED",
            "task_id": task.id,
            "project_id": task.project_id,
        })


def _to_response(task: Task, db: Session) -> TaskResponse:
    data = TaskResponse.model_validate(task)

    # O estado real vem do trabalho em curso, não do campo status — que é um
    # registro gravado algum dia e pode estar velho.
    is_alive = False
    run = None
    if task.worktree_path:
        is_alive = run_registry.esta_vivo(task.worktree_path)
        run = run_registry.ler(task.worktree_path)

    # Trabalho feito pelo chat também conta: é assim que o usuário mais opera.
    cfg = task.runner_config if isinstance(task.runner_config, dict) else {}
    chat_desde = cfg.get("chat_busy_since")
    chat_ativo = False
    chat_preso = False
    if chat_desde:
        if (time.time() - chat_desde) < CHAT_BUSY_TIMEOUT:
            chat_ativo = True
        else:
            chat_preso = True

    is_alive = is_alive or chat_ativo

    data.is_alive = is_alive
    data.started_at = (run.get("started_at") if run else None) or chat_desde
    # "Parou sem concluir": havia trabalho em curso e não há mais nada vivo.
    data.stalled = bool(
        not is_alive
        and (chat_preso or (task.status == TaskStatus.RUNNING and run is not None))
    )
    data.awaiting_you = _is_awaiting_you(task, db, is_alive=is_alive)
    data.project_name = task.project.name if task.project else None
    data.card_state = _card_state(task, db, is_alive=is_alive, stalled=data.stalled)

    if task.worktree_path:
        stats = git_service.change_stats(task.worktree_path)
        data.changed_files = stats["files"]
        data.lines_added = stats["added"]
        data.lines_removed = stats["removed"]

    return data


def _card_state(task: Task, db: Session, is_alive: bool, stalled: bool) -> str:
    """
    Um estado só por card, escrito por extenso na tela.

    A ordem importa: trabalhando agora tem precedência sobre tudo, e
    "te perguntou" é separado de "entregou" porque custam tempos
    muito diferentes do usuário — segundos contra minutos.
    """
    if is_alive:
        return "EXECUTANDO"
    if task.status == TaskStatus.DONE:
        return "CONCLUIDO"
    if stalled:
        return "PAROU"
    if task.status in (TaskStatus.REVIEW_READY, TaskStatus.FAILED):
        return "ENTREGOU" if task.status == TaskStatus.REVIEW_READY else "PAROU"

    ultima = (
        db.query(Message)
        .filter(Message.task_id == task.id)
        .order_by(Message.created_at.desc(), Message.id.desc())
        .first()
    )
    if ultima and ultima.role == MessageRole.ASSISTANT:
        return "TE_PERGUNTOU"

    return "NA_FILA"


@router.get("/{task_id}/artifacts")
def list_task_artifacts(task_id: str, db: Session = Depends(get_db)):
    """
    Artefatos visíveis desta tarefa.

    Antes do merge eles vivem no worktree; depois, no projeto. É o mesmo
    arquivo — não há cópia nem sincronização.
    """
    task = db.query(Task).filter(Task.id == task_id).first()
    if not task:
        raise HTTPException(status_code=404, detail="Tarefa não encontrada")

    base = task.worktree_path if (task.worktree_path and os.path.isdir(task.worktree_path)) \
        else (task.project.root_path if task.project else None)
    if not base:
        return {"base": None, "artifacts": []}

    return {"base": base, "artifacts": artifact_service.listar(base)}


@router.get("/{task_id}/artifacts/{nome}")
def read_task_artifact(task_id: str, nome: str, db: Session = Depends(get_db)):
    task = db.query(Task).filter(Task.id == task_id).first()
    if not task:
        raise HTTPException(status_code=404, detail="Tarefa não encontrada")

    base = task.worktree_path if (task.worktree_path and os.path.isdir(task.worktree_path)) \
        else (task.project.root_path if task.project else None)
    if not base:
        raise HTTPException(status_code=404, detail="Artefato não encontrado")

    try:
        conteudo = artifact_service.ler(base, nome)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    if conteudo is None:
        raise HTTPException(status_code=404, detail="Artefato não encontrado")

    return {"name": nome, "content": conteudo}


class KnowledgeApproval(BaseModel):
    lines: List[str]


@router.get("/{task_id}/knowledge-proposals")
def list_knowledge_proposals(task_id: str, db: Session = Depends(get_db)):
    """O que o agente propôs registrar nesta tarefa. Vazio é o normal."""
    task = db.query(Task).filter(Task.id == task_id).first()
    if not task:
        raise HTTPException(status_code=404, detail="Tarefa não encontrada")
    if not task.worktree_path:
        return {"proposals": []}
    return {"proposals": artifact_service.ler_propostas(task.worktree_path)}


@router.post("/{task_id}/knowledge-proposals")
def approve_knowledge_proposals(
    task_id: str, data: KnowledgeApproval, db: Session = Depends(get_db)
):
    """
    Grava as linhas que o usuário aprovou no índice do projeto e limpa o
    rascunho. Lista vazia = descartar tudo, que é o caminho esperado.
    """
    task = db.query(Task).filter(Task.id == task_id).first()
    if not task:
        raise HTTPException(status_code=404, detail="Tarefa não encontrada")

    if data.lines:
        artifact_service.registrar_conhecimento(task.project.root_path, data.lines)
    if task.worktree_path:
        artifact_service.limpar_propostas(task.worktree_path)

    return {"registered": len(data.lines)}


@router.get("/{task_id}/artifacts/{nome}/raw")
def serve_task_artifact(task_id: str, nome: str, db: Session = Depends(get_db)):
    """
    Serve o artefato pelo próprio servidor.

    O navegador bloqueia links `file://` vindos de uma página http — por isso
    não dava para abrir um mockup ou um mapa mental sem ir na pasta à mão.
    Servindo daqui, com o content-type certo, ele abre normalmente.
    """
    task = db.query(Task).filter(Task.id == task_id).first()
    if not task:
        raise HTTPException(status_code=404, detail="Tarefa não encontrada")

    base = task.worktree_path if (task.worktree_path and os.path.isdir(task.worktree_path)) \
        else (task.project.root_path if task.project else None)
    if not base:
        raise HTTPException(status_code=404, detail="Artefato não encontrado")

    try:
        dados = artifact_service.ler_bytes(base, nome)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    if dados is None:
        raise HTTPException(status_code=404, detail="Artefato não encontrado")

    return Response(content=dados, media_type=artifact_service.content_type(nome))


@router.post("/{task_id}/terminal")
def open_task_terminal(task_id: str, db: Session = Depends(get_db)):
    """
    Abre um terminal no worktree da tarefa — onde o agente está mexendo.
    Tarefa ainda não executada não tem worktree: cai na pasta do projeto,
    que é mais útil do que recusar.
    """
    task = db.query(Task).filter(Task.id == task_id).first()
    if not task:
        raise HTTPException(status_code=404, detail="Tarefa não encontrada")

    alvo = task.worktree_path or (task.project.root_path if task.project else None)
    try:
        caminho = terminal_service.open_at(alvo)
    except FileNotFoundError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except RuntimeError as e:
        raise HTTPException(status_code=500, detail=str(e))
    return {"opened_at": caminho}


@router.post("/refresh-states")
def refresh_states(db: Session = Depends(get_db)):
    """
    Confere TODOS os agentes neste instante e corrige o que estiver errado.

    Existe para quando a detecção automática falhar ou atrasar: em vez de
    reiniciar o servidor ou esperar o ciclo, o usuário clica e tem a verdade
    do momento.
    """
    corrigidas = []
    tarefas = db.query(Task).all()

    # Corrige o ramo base gravado errado: "main" é só o padrão do formulário
    # e nunca foi conferido. Num repo que usa master, isso quebra o merge.
    projetos = db.query(Project).all()
    for p in projetos:
        real = git_service.branch_base(p.root_path)
        if real and real != p.default_branch:
            antigo = p.default_branch
            p.default_branch = real
            corrigidas.append({
                "id": p.id, "title": p.name,
                "novo_status": f"ramo base {antigo} → {real}",
            })

    # Religa worktrees órfãs: a pasta existe no disco mas a tarefa não a
    # conhece, então tudo que o agente produziu fica invisível no painel.
    # O nome é previsível (task-<id>), então dá para reencontrar.
    for t in tarefas:
        if t.worktree_path or not t.project:
            continue
        candidato = git_service.get_worktree_path(t.project.root_path, t.id)
        if os.path.isdir(candidato):
            t.worktree_path = candidato
            if not t.git_branch:
                t.git_branch = f"task/{t.id}"
            corrigidas.append({"id": t.id, "title": t.title, "novo_status": "worktree religada"})

    for t in tarefas:
        if t.status != TaskStatus.RUNNING or not t.worktree_path:
            continue
        novo = runner_service.reconcile(t.worktree_path)
        if novo and novo != "RUNNING":
            t.status = TaskStatus(novo)
            corrigidas.append({"id": t.id, "title": t.title, "novo_status": novo})

    # Marca de chat presa (servidor caiu no meio da conversa) também é corrigida
    for t in tarefas:
        cfg = t.runner_config if isinstance(t.runner_config, dict) else {}
        desde = cfg.get("chat_busy_since")
        if desde and (time.time() - desde) >= CHAT_BUSY_TIMEOUT:
            t.runner_config = {k: v for k, v in cfg.items() if k != "chat_busy_since"}
            corrigidas.append({"id": t.id, "title": t.title, "novo_status": "chat destravado"})

    db.commit()

    return {
        "checked": len(tarefas),
        "fixed": corrigidas,
        "tasks": [_to_response(t, db) for t in tarefas],
    }


@router.get("/all", response_model=List[TaskResponse])
def list_all_tasks(db: Session = Depends(get_db)):
    """Todas as tarefas, de todos os projetos — a visão cross-projeto."""
    tasks = db.query(Task).all()
    return [_to_response(t, db) for t in tasks]


@router.get("/project/{project_id}", response_model=List[TaskResponse])
def list_tasks_by_project(project_id: str, db: Session = Depends(get_db)):
    tasks = db.query(Task).filter(Task.project_id == project_id).all()
    return [_to_response(t, db) for t in tasks]


@router.post("", response_model=TaskResponse, status_code=status.HTTP_201_CREATED)
def create_task(data: TaskCreate, db: Session = Depends(get_db)):
    proj = db.query(Project).filter(Project.id == data.project_id).first()
    if not proj:
        raise HTTPException(status_code=404, detail="Projeto não encontrado")

    task = Task(
        project_id=data.project_id,
        title=data.title,
        raw_prompt=data.raw_prompt,
        status=TaskStatus.DRAFT,
        runner_type=RunnerType(data.runner_type) if data.runner_type in RunnerType._value2member_map_ else RunnerType.SUBPROCESS_CLI,
        runner_config=data.runner_config or {}
    )
    db.add(task)
    db.commit()
    db.refresh(task)
    return task


@router.post("/{task_id}/refine", response_model=TaskResponse)
def refine_task(task_id: str, db: Session = Depends(get_db)):
    task = db.query(Task).filter(Task.id == task_id).first()
    if not task:
        raise HTTPException(status_code=404, detail="Tarefa não encontrada")

    # Mapeia arquivos existentes no projeto para context pruning
    available_files = []
    if os.path.exists(task.project.root_path):
        for root, _, files in os.walk(task.project.root_path):
            if ".git" in root or "node_modules" in root or ".worktrees" in root:
                continue
            for f in files:
                rel = os.path.relpath(os.path.join(root, f), task.project.root_path)
                available_files.append(rel.replace("\\", "/"))

    spec = refiner_service.refine(task.raw_prompt, available_files=available_files)
    task.refined_spec = refiner_service.to_markdown(spec)
    task.status = TaskStatus.SPEC_READY
    db.commit()
    db.refresh(task)
    return task


async def _run_task_background(task_id: str, project_path: str, command: list[str], db_session_factory, is_assistant: bool = False, prompt: str = ""):
    worktree_path = git_service.get_worktree_path(project_path, task_id)
    conv_id = None
    try:
        await ws_manager.broadcast_task(task_id, {
            "type": "LOG",
            "content": f"[Orchestrator] Inicializando worktree em {worktree_path}"
        })
        git_service.create_worktree(project_path, task_id)

        await ws_manager.broadcast_task(task_id, {
            "type": "STATUS",
            "status": "RUNNING"
        })

        if is_assistant or (command and command[0] == "assistant"):
            async def log_cb(msg: str):
                await ws_manager.broadcast_task(task_id, {"type": "LOG", "content": msg})

            db_tmp = db_session_factory()
            t_obj = db_tmp.query(Task).filter(Task.id == task_id).first()
            title = t_obj.title if t_obj else "Tarefa"
            db_tmp.close()

            await assistant_service.execute_task_direct(
                task_id=task_id,
                task_title=title,
                prompt=prompt,
                worktree_path=worktree_path,
                log_callback=log_cb
            )
            final_status = TaskStatus.REVIEW_READY
        else:
            # Desacoplado: o agente sobrevive a reinícios do servidor e só para
            # quando o usuário mandar (ver artefato agentes-sobrevivem-ao-servidor).
            pid = runner_service.launch_detached(task_id, command, cwd=worktree_path)
            if pid:
                await ws_manager.broadcast_task(task_id, {
                    "type": "LOG",
                    "content": f"[Orchestrator] Agente iniciado (PID {pid}), desacoplado do servidor."
                })

            collected = []
            async for line in runner_service.follow_log(task_id, worktree_path):
                collected.append(line)
                await ws_manager.broadcast_task(task_id, {
                    "type": "LOG",
                    "content": line.rstrip()
                })

            if runner_service.was_stopped(task_id):
                return

            # O agentapi devolve o conversationId na saída; sem guardá-lo, o chat
            # depois conversaria com um agente que nunca viu esta tarefa.
            conv_id = runner_service.extract_conversation_id("".join(collected))

            rc = runner_service.get_last_returncode(task_id)
            final_status = TaskStatus.REVIEW_READY if rc == 0 else TaskStatus.FAILED

        db = db_session_factory()
        t = db.query(Task).filter(Task.id == task_id).first()
        if t:
            t.status = final_status
            if conv_id and isinstance(t.runner_config, dict) \
                    and not t.runner_config.get("antigravity_conversation_id"):
                t.runner_config = {**t.runner_config, "antigravity_conversation_id": conv_id}
            db.commit()
        db.close()

        await ws_manager.broadcast_task(task_id, {
            "type": "STATUS",
            "status": final_status.value
        })
        await ws_manager.broadcast_dashboard({
            "type": "TASK_UPDATED",
            "task_id": task_id,
            "status": final_status.value
        })

    except Exception as e:
        await ws_manager.broadcast_task(task_id, {
            "type": "LOG",
            "content": f"[Erro na execução] {str(e)}"
        })
        db = db_session_factory()
        t = db.query(Task).filter(Task.id == task_id).first()
        if t:
            t.status = TaskStatus.FAILED
            db.commit()
        db.close()
        await ws_manager.broadcast_task(task_id, {"type": "STATUS", "status": "FAILED"})
        await ws_manager.broadcast_dashboard({"type": "TASK_UPDATED", "task_id": task_id, "status": "FAILED"})


@router.post("/{task_id}/run", response_model=TaskResponse)
def run_task(task_id: str, background_tasks: BackgroundTasks, db: Session = Depends(get_db)):
    task = db.query(Task).filter(Task.id == task_id).first()
    if not task:
        raise HTTPException(status_code=404, detail="Tarefa não encontrada")

    prompt = task.refined_spec or task.raw_prompt

    # Cola o índice de conhecimento do projeto no começo do prompt. Vale para
    # qualquer CLI — não depende do que cada um lê sozinho. Só o índice entra;
    # os artefatos o agente abre sob demanda.
    contexto = artifact_service.contexto_para_prompt(task.project.root_path)
    if contexto:
        prompt = f"{contexto}\n---\n\n{prompt}"

    # Convida o agente a registrar o que aprendeu — com o padrão em "nada".
    prompt = f"{prompt}\n\n---\n{artifact_service.instrucao_de_conhecimento()}"

    is_assistant = (
        task.runner_type == RunnerType.DIRECT_API
        or (task.runner_config and task.runner_config.get("cli") in ["assistant", "integrated"])
    )

    cmd = []
    if not is_assistant:
        cfg = dict(task.runner_config or {})
        # Nomeia a sessão ANTES de executar, para que o chat possa retomar depois
        # o mesmo agente que fez o trabalho (ver artefato gestao-multi-agente).
        if "claude" in str(cfg.get("cli", "")).lower() and not cfg.get("claude_session_id"):
            cfg["claude_session_id"] = str(uuid.uuid4())
            task.runner_config = cfg
        cmd = runner_service.resolve_cli_command(task.runner_type.value, prompt, cfg)

    task.status = TaskStatus.RUNNING
    task.worktree_path = git_service.get_worktree_path(task.project.root_path, task.id)
    task.git_branch = f"task/{task.id}"
    db.commit()
    db.refresh(task)

    from app.core.database import SessionLocal
    background_tasks.add_task(
        _run_task_background,
        task.id,
        task.project.root_path,
        cmd,
        SessionLocal,
        is_assistant,
        prompt
    )
    return task



@router.post("/{task_id}/stop")
def stop_task(task_id: str, db: Session = Depends(get_db)):
    task = db.query(Task).filter(Task.id == task_id).first()
    if not task:
        raise HTTPException(status_code=404, detail="Tarefa não encontrada")

    # O agente desacoplado não está mais em memória: encerra pela árvore de
    # processos registrada em disco. O stop_task cobre execuções legadas.
    stopped = runner_service.stop_task(task_id)
    if task.worktree_path:
        stopped = runner_service.stop_detached(task.worktree_path) or stopped
    runner_service.stopped_tasks.add(task_id)

    task.status = TaskStatus.SPEC_READY
    db.commit()
    return {"stopped": stopped, "status": task.status}


@router.get("/{task_id}/diff")
def get_task_diff(task_id: str, db: Session = Depends(get_db)):
    task = db.query(Task).filter(Task.id == task_id).first()
    if not task:
        raise HTTPException(status_code=404, detail="Tarefa não encontrada")

    diff = git_service.get_diff(task.project.root_path, task.id, base_branch=task.project.default_branch)
    return {"diff": diff}


@router.post("/{task_id}/merge")
def merge_task(task_id: str, db: Session = Depends(get_db)):
    task = db.query(Task).filter(Task.id == task_id).first()
    if not task:
        raise HTTPException(status_code=404, detail="Tarefa não encontrada")

    # Antes do merge a worktree ainda existe: é a última chance de saber
    # quais artefatos esta tarefa trouxe.
    novos = [a["name"] for a in artifact_service.listar(task.worktree_path)] \
        if task.worktree_path else []

    merged = git_service.merge_task(task.project.root_path, task.id, target_branch=task.project.default_branch)
    if not merged:
        raise HTTPException(status_code=409, detail="Conflito de merge detectado")

    # O merge é a promoção: o artefato deixa de ser da tarefa e passa a ser
    # documentação do projeto. Registrar no índice custa zero — usa o título.
    registrados = []
    if novos:
        try:
            artifact_service.registrar_no_indice(
                task.project.root_path, novos, titulo_tarefa=task.title
            )
            registrados = novos
        except Exception as e:
            logging.getLogger("orchestrator").warning(f"Falha ao indexar artefatos: {e}")

    git_service.remove_worktree(task.project.root_path, task.id)
    task.status = TaskStatus.DONE
    db.commit()
    return {"merged": True, "status": "DONE", "artifacts_indexed": registrados}


@router.post("/{task_id}/upload")
async def upload_task_attachment(task_id: str, file: UploadFile = File(...), db: Session = Depends(get_db)):
    task = db.query(Task).filter(Task.id == task_id).first()
    if not task:
        raise HTTPException(status_code=404, detail="Tarefa não encontrada")

    task_upload_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..", "uploads", "tasks", task_id))
    os.makedirs(task_upload_dir, exist_ok=True)

    raw_filename = file.filename or "arquivo"
    safe_name = f"{uuid.uuid4().hex[:8]}_{raw_filename.replace(' ', '_')}"
    file_path = os.path.join(task_upload_dir, safe_name)

    content = await file.read()
    with open(file_path, "wb") as f:
        f.write(content)

    return {
        "filename": safe_name,
        "original_name": raw_filename,
        "file_path": file_path.replace("\\", "/"),
        "file_url": f"/api/uploads/tasks/{task_id}/{safe_name}",
        "content_type": file.content_type or "application/octet-stream",
        "size": len(content)
    }


@router.get("/{task_id}/messages", response_model=List[MessageResponse])
def get_task_messages(task_id: str, db: Session = Depends(get_db)):
    return db.query(Message).filter(Message.task_id == task_id).order_by(Message.created_at.asc()).all()


@router.post("/{task_id}/messages", response_model=MessageResponse, status_code=status.HTTP_201_CREATED)
async def send_task_message(task_id: str, data: MessageCreate, background_tasks: BackgroundTasks, db: Session = Depends(get_db)):
    task = db.query(Task).filter(Task.id == task_id).first()
    if not task:
        raise HTTPException(status_code=404, detail="Tarefa não encontrada")

    # Recupera histórico anterior
    prev_messages = db.query(Message).filter(Message.task_id == task_id).order_by(Message.created_at.asc()).all()
    history = [{"role": m.role.value, "content": m.content} for m in prev_messages]

    user_msg = Message(
        task_id=task.id,
        role=MessageRole.USER,
        content=data.content,
        attachments=data.attachments or []
    )
    db.add(user_msg)
    db.commit()
    db.refresh(user_msg)

    # Notifica via WebSocket sobre a nova mensagem do usuário
    await ws_manager.broadcast_task(task.id, {
        "type": "MESSAGE",
        "message": {
            "id": user_msg.id,
            "task_id": user_msg.task_id,
            "role": user_msg.role.value,
            "content": user_msg.content,
            "attachments": user_msg.attachments or [],
            "created_at": user_msg.created_at.isoformat()
        }
    })

    # Gera resposta do Assistente
    conv_id = None
    cli_preference = None
    if task.runner_config and isinstance(task.runner_config, dict):
        conv_id = task.runner_config.get("antigravity_conversation_id")
        cli_preference = task.runner_config.get("cli")
        # Restaura a sessão do Claude desta tarefa (sobrevive a reinícios do servidor)
        claude_session = task.runner_config.get("claude_session_id")
        if claude_session:
            assistant_service._claude_sessions[task.id] = claude_session

    # Marca a tarefa como ocupada ANTES de chamar o agente: é esse sinal que
    # faz o card mostrar "Executando" enquanto o usuário está em outra tarefa.
    _marcar_chat_ocupado(db, task, ocupado=True)
    await ws_manager.broadcast_dashboard({
        "type": "TASK_BUSY",
        "task_id": task.id,
        "project_id": task.project_id,
    })

    reply_text = await _responder_e_desmarcar(
        db, task,
        assistant_service.generate_chat_reply(
        task_id=task.id,
        task_title=task.title,
        task_prompt=task.raw_prompt,
        history=history,
        project_root=task.project.root_path,
        user_message=data.content,
        project_name=task.project.name,
        git_branch=task.git_branch,
        conversation_id=conv_id,
        attachments=data.attachments,
            cli_preference=cli_preference,
            worktree_path=task.worktree_path
        )
    )

    # Persiste a sessão do Claude criada nesta troca, para retomá-la depois
    new_session = assistant_service._claude_sessions.get(task.id)
    if new_session and isinstance(task.runner_config, dict) \
            and task.runner_config.get("claude_session_id") != new_session:
        task.runner_config = {**task.runner_config, "claude_session_id": new_session}

    assistant_msg = Message(
        task_id=task.id,
        role=MessageRole.ASSISTANT,
        content=reply_text
    )
    db.add(assistant_msg)
    db.commit()
    db.refresh(assistant_msg)

    # Notifica via WebSocket sobre a resposta do assistente
    await ws_manager.broadcast_task(task.id, {
        "type": "MESSAGE",
        "message": {
            "id": assistant_msg.id,
            "task_id": assistant_msg.task_id,
            "role": assistant_msg.role.value,
            "content": assistant_msg.content,
            "created_at": assistant_msg.created_at.isoformat()
        }
    })

    # Atualiza conversa Antigravity no runner_config se criada
    conv_id = assistant_service.get_task_conversation_id(task.id)
    if conv_id and (not task.runner_config or task.runner_config.get("antigravity_conversation_id") != conv_id):
        cfg = dict(task.runner_config or {})
        cfg["antigravity_conversation_id"] = conv_id
        task.runner_config = cfg
        db.commit()

    # Se a tarefa estiver em revisão ou auto_run solicitado, re-executa o agente com o feedback
    if data.auto_run or task.status == TaskStatus.REVIEW_READY:
        task.status = TaskStatus.RUNNING
        cmd = runner_service.resolve_cli_command(task.runner_type.value, data.content, task.runner_config)
        from app.core.database import SessionLocal
        background_tasks.add_task(
            _run_task_background,
            task.id,
            task.project.root_path,
            cmd,
            SessionLocal
        )

    return assistant_msg


@router.delete("/{task_id}")
async def delete_task(task_id: str, db: Session = Depends(get_db)):
    task = db.query(Task).filter(Task.id == task_id).first()
    if not task:
        raise HTTPException(status_code=404, detail="Tarefa não encontrada")

    project_id = task.project_id
    project_root = task.project.root_path if task.project else None

    # 1. Interrompe execução se estiver ativa
    try:
        runner_service.stop_task(task_id)
    except Exception:
        pass

    # 2. Localiza e exclui a conversa vinculada do Antigravity
    conv_id = None
    if task.runner_config and isinstance(task.runner_config, dict):
        conv_id = task.runner_config.get("antigravity_conversation_id")
    if not conv_id:
        conv_id = assistant_service.get_task_conversation_id(task_id)

    antigravity_cleaned = False
    if conv_id:
        antigravity_cleaned = assistant_service.delete_antigravity_conversation(conv_id)

    # 3. Limpa worktree e branch git associadas
    if project_root and os.path.exists(project_root):
        try:
            git_service.cleanup_task_git(project_root, task_id)
        except Exception:
            pass

    # 4. Remove a tarefa do banco de dados (mensagens apagadas em cascata)
    db.delete(task)
    db.commit()

    # 5. Notifica via WebSocket clientes conectados
    await ws_manager.broadcast_dashboard({
        "type": "TASK_DELETED",
        "task_id": task_id,
        "project_id": project_id
    })
    await ws_manager.broadcast_task(task_id, {
        "type": "TASK_DELETED",
        "task_id": task_id
    })

    return {
        "deleted": True,
        "task_id": task_id,
        "antigravity_cleaned": antigravity_cleaned
    }

