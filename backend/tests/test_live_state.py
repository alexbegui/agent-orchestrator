"""
O card precisa dizer a verdade sobre o que está acontecendo AGORA.

O status no banco é um registro que pode estar velho; o processo real é o
fato. Tarefa com agente vivo está executando — e, portanto, não espera você.
"""
import os
import tempfile
import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.core.database import SessionLocal
from app.models.project import Project
from app.models.task import Task, TaskStatus
from app.models.message import Message, MessageRole
from app.services.run_registry import run_registry

client = TestClient(app)
PREFIXO = "__pytest_live__"


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


def _tarefa(worktree=None, status=TaskStatus.RUNNING):
    db = SessionLocal()
    p = Project(name=f"{PREFIXO} Proj", root_path="C:/tmp/live")
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


def test_agente_vivo_marca_a_tarefa_como_executando():
    with tempfile.TemporaryDirectory() as wt:
        run_registry.registrar(wt, task_id="x", pid=os.getpid(), command=["x"])
        proj_id, task_id = _tarefa(worktree=wt)

        assert _buscar(proj_id, task_id)["is_alive"] is True


def test_agente_vivo_nao_aparece_como_esperando_voce():
    """O defeito relatado: tarefa rodando ficava presa na fila de triagem."""
    with tempfile.TemporaryDirectory() as wt:
        run_registry.registrar(wt, task_id="x", pid=os.getpid(), command=["x"])
        proj_id, task_id = _tarefa(worktree=wt)
        _msg(task_id, MessageRole.USER)
        _msg(task_id, MessageRole.ASSISTANT)  # agente falou por último

        alvo = _buscar(proj_id, task_id)
        assert alvo["is_alive"] is True
        assert alvo["awaiting_you"] is False


def test_processo_morto_nao_conta_como_executando():
    with tempfile.TemporaryDirectory() as wt:
        run_registry.registrar(wt, task_id="x", pid=999999, command=["x"])
        proj_id, task_id = _tarefa(worktree=wt)

        assert _buscar(proj_id, task_id)["is_alive"] is False


def test_marcada_rodando_mas_sem_processo_e_sinalizada_como_parada():
    """Hoje isso fica invisível: o card diz 'Rodando' para sempre."""
    with tempfile.TemporaryDirectory() as wt:
        run_registry.registrar(wt, task_id="x", pid=999999, command=["x"])
        proj_id, task_id = _tarefa(worktree=wt)

        alvo = _buscar(proj_id, task_id)
        assert alvo["is_alive"] is False
        assert alvo["stalled"] is True


def test_tarefa_concluida_nao_e_considerada_parada():
    with tempfile.TemporaryDirectory() as wt:
        run_registry.registrar(wt, task_id="x", pid=999999, command=["x"])
        proj_id, task_id = _tarefa(worktree=wt, status=TaskStatus.DONE)

        assert _buscar(proj_id, task_id)["stalled"] is False


def test_tarefa_sem_worktree_nao_quebra_a_listagem():
    proj_id, task_id = _tarefa(worktree=None, status=TaskStatus.DRAFT)
    alvo = _buscar(proj_id, task_id)
    assert alvo["is_alive"] is False
    assert alvo["stalled"] is False


def test_expoe_desde_quando_esta_rodando():
    with tempfile.TemporaryDirectory() as wt:
        run_registry.registrar(wt, task_id="x", pid=os.getpid(), command=["x"])
        proj_id, task_id = _tarefa(worktree=wt)

        alvo = _buscar(proj_id, task_id)
        assert alvo["started_at"] is not None
