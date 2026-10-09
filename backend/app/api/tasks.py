import os
import asyncio
from fastapi import APIRouter, Depends, HTTPException, status, BackgroundTasks
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

    model_config = ConfigDict(from_attributes=True)


class MessageResponse(BaseModel):
    id: str
    task_id: str
    role: str
    content: str

    model_config = ConfigDict(from_attributes=True)


@router.get("/project/{project_id}", response_model=List[TaskResponse])
def list_tasks_by_project(project_id: str, db: Session = Depends(get_db)):
    return db.query(Task).filter(Task.project_id == project_id).all()


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
            async for line in runner_service.execute_command(task_id, command, cwd=worktree_path):
                await ws_manager.broadcast_task(task_id, {
                    "type": "LOG",
                    "content": line.rstrip()
                })

            if runner_service.was_stopped(task_id):
                return

            rc = runner_service.get_last_returncode(task_id)
            final_status = TaskStatus.REVIEW_READY if rc == 0 else TaskStatus.FAILED

        db = db_session_factory()
        t = db.query(Task).filter(Task.id == task_id).first()
        if t:
            t.status = final_status
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
    is_assistant = (
        task.runner_type == RunnerType.DIRECT_API
        or (task.runner_config and task.runner_config.get("cli") in ["assistant", "integrated"])
    )

    cmd = []
    if not is_assistant:
        cmd = runner_service.resolve_cli_command(task.runner_type.value, prompt, task.runner_config)

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

    stopped = runner_service.stop_task(task_id)
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

    merged = git_service.merge_task(task.project.root_path, task.id, target_branch=task.project.default_branch)
    if not merged:
        raise HTTPException(status_code=409, detail="Conflito de merge detectado")

    git_service.remove_worktree(task.project.root_path, task.id)
    task.status = TaskStatus.DONE
    db.commit()
    return {"merged": True, "status": "DONE"}


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
        content=data.content
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
            "created_at": user_msg.created_at.isoformat()
        }
    })

    # Gera resposta do Assistente
    reply_text = await assistant_service.generate_chat_reply(
        task_title=task.title,
        task_prompt=task.raw_prompt,
        history=history,
        project_root=task.project.root_path,
        user_message=data.content
    )

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

