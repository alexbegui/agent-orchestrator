"""
Os cinco estados explícitos do card.

"Esperando você" escondia duas coisas de custo muito diferente:
responder uma pergunta leva segundos; revisar um diff leva minutos.
Separar deixa o usuário escolher pelo tempo que tem.
"""
import os
import tempfile
import subprocess
import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.core.database import SessionLocal
from app.models.project import Project
from app.models.task import Task, TaskStatus
from app.models.message import Message, MessageRole
from app.services.run_registry import run_registry

client = TestClient(app)
PREFIXO = "__pytest_cards__"


@pytest.fixture(autouse=True)
def limpar():
    def _purgar():
        db = SessionLocal()
        for p in db.query(Project).filter(Project.name.like(f"{PREFIXO}%")).all():
            for t in db.query(Task).filter(Task.project_id == p.id).all():
                db.query(Message).filter(Message.task_id == t.id).delete()
                db.delete(t)
            db.delete(p)
        db.commit()
        db.close()
    _purgar()
    yield
    _purgar()


def _tarefa(status=TaskStatus.RUNNING, worktree=None, root="C:/tmp/cards"):
    db = SessionLocal()
    p = Project(name=f"{PREFIXO} Proj", root_path=root)
    db.add(p)
    db.commit()
    db.refresh(p)
    t = Task(project_id=p.id, title="T", raw_prompt="faça algo",
             status=status, worktree_path=worktree)
    db.add(t)
    db.commit()
    db.refresh(t)
    ids = (p.id, t.id)
    db.close()
    return ids


def _msg(task_id, role):
    db = SessionLocal()
    db.add(Message(task_id=task_id, role=role, content="m"))
    db.commit()
    db.close()


def _buscar(proj_id, task_id):
    tasks = client.get(f"/api/tasks/project/{proj_id}").json()
    return next(t for t in tasks if t["id"] == task_id)


# ---------- o estado único e explícito ----------

def test_agente_vivo_tem_estado_executando():
    with tempfile.TemporaryDirectory() as wt:
        run_registry.registrar(wt, task_id="x", pid=os.getpid(), command=["x"])
        proj_id, task_id = _tarefa(worktree=wt)
        assert _buscar(proj_id, task_id)["card_state"] == "EXECUTANDO"


def test_agente_respondeu_no_chat_tem_estado_te_perguntou():
    proj_id, task_id = _tarefa(status=TaskStatus.RUNNING)
    _msg(task_id, MessageRole.USER)
    _msg(task_id, MessageRole.ASSISTANT)
    assert _buscar(proj_id, task_id)["card_state"] == "TE_PERGUNTOU"


def test_diff_pronto_tem_estado_entregou():
    """Revisar diff é esforço diferente de responder pergunta."""
    proj_id, task_id = _tarefa(status=TaskStatus.REVIEW_READY)
    assert _buscar(proj_id, task_id)["card_state"] == "ENTREGOU"


def test_processo_sumiu_tem_estado_parou():
    with tempfile.TemporaryDirectory() as wt:
        run_registry.registrar(wt, task_id="x", pid=999999, command=["x"])
        proj_id, task_id = _tarefa(worktree=wt)
        assert _buscar(proj_id, task_id)["card_state"] == "PAROU"


def test_mergeada_tem_estado_concluido():
    proj_id, task_id = _tarefa(status=TaskStatus.DONE)
    assert _buscar(proj_id, task_id)["card_state"] == "CONCLUIDO"


def test_rascunho_tem_estado_na_fila():
    proj_id, task_id = _tarefa(status=TaskStatus.DRAFT)
    assert _buscar(proj_id, task_id)["card_state"] == "NA_FILA"


def test_executando_tem_precedencia_sobre_a_conversa():
    """Agente trabalhando não é 'te perguntou', mesmo com fala dele por último."""
    with tempfile.TemporaryDirectory() as wt:
        run_registry.registrar(wt, task_id="x", pid=os.getpid(), command=["x"])
        proj_id, task_id = _tarefa(worktree=wt)
        _msg(task_id, MessageRole.ASSISTANT)
        assert _buscar(proj_id, task_id)["card_state"] == "EXECUTANDO"


# ---------- quanto mexeu ----------

def test_conta_arquivos_e_linhas_do_worktree():
    with tempfile.TemporaryDirectory() as repo:
        subprocess.run(["git", "init", "-q", repo], check=True)
        subprocess.run(["git", "config", "user.email", "t@t"], cwd=repo, check=True)
        subprocess.run(["git", "config", "user.name", "t"], cwd=repo, check=True)
        open(os.path.join(repo, "a.txt"), "w").write("linha1\n")
        subprocess.run(["git", "add", "-A"], cwd=repo, check=True)
        subprocess.run(["git", "commit", "-q", "-m", "base"], cwd=repo, check=True)

        # Mudança não commitada do "agente"
        open(os.path.join(repo, "a.txt"), "w").write("linha1\nlinha2\nlinha3\n")
        open(os.path.join(repo, "b.txt"), "w").write("novo\n")

        proj_id, task_id = _tarefa(status=TaskStatus.REVIEW_READY, worktree=repo, root=repo)
        alvo = _buscar(proj_id, task_id)

        assert alvo["changed_files"] >= 2
        assert alvo["lines_added"] >= 3


def test_sem_worktree_nao_quebra_a_contagem():
    proj_id, task_id = _tarefa(status=TaskStatus.DRAFT)
    alvo = _buscar(proj_id, task_id)
    assert alvo["changed_files"] == 0
    assert alvo["lines_added"] == 0


# ---------- o botão Verificar agora ----------

def test_verificar_agora_devolve_o_estado_de_todas_as_tarefas():
    proj_id, task_id = _tarefa(status=TaskStatus.REVIEW_READY)
    resp = client.post("/api/tasks/refresh-states")
    assert resp.status_code == 200
    body = resp.json()
    assert "checked" in body
    assert any(t["id"] == task_id for t in body["tasks"])


def test_verificar_agora_corrige_tarefa_que_morreu_sem_avisar():
    """O botão existe justamente para quando a detecção automática falhar."""
    with tempfile.TemporaryDirectory() as wt:
        run_registry.registrar(wt, task_id="x", pid=999999, command=["x"])
        run_registry.concluir(wt, returncode=1)
        proj_id, task_id = _tarefa(worktree=wt, status=TaskStatus.RUNNING)

        client.post("/api/tasks/refresh-states")

        db = SessionLocal()
        t = db.query(Task).filter(Task.id == task_id).first()
        estado = t.status
        db.close()
        assert estado == TaskStatus.FAILED
