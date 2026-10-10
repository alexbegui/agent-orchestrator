"""
O worktree_path precisa ficar gravado na tarefa.

Sintoma relatado: as pastas .worktrees/task-<id> existem no disco, mas o
banco diz worktree_path=None. Sem esse caminho, a aba Artefatos olha a raiz
do projeto em vez do worktree e não acha nada que o agente produziu.
"""
import pytest
from unittest.mock import patch
from fastapi.testclient import TestClient

from app.main import app
from app.core.database import SessionLocal
from app.models.project import Project
from app.models.task import Task, TaskStatus
from app.models.message import Message

client = TestClient(app)
PREFIXO = "__pytest_wt__"


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


def _tarefa(cli="claude"):
    db = SessionLocal()
    p = Project(name=f"{PREFIXO} Proj", root_path="C:/tmp/wtproj")
    db.add(p)
    db.commit()
    db.refresh(p)
    t = Task(project_id=p.id, title="T", raw_prompt="faça algo",
             status=TaskStatus.SPEC_READY, runner_config={"cli": cli})
    db.add(t)
    db.commit()
    db.refresh(t)
    ids = (p.id, t.id)
    db.close()
    return ids


def _worktree_no_banco(task_id):
    db = SessionLocal()
    t = db.query(Task).filter(Task.id == task_id).first()
    valor = t.worktree_path
    db.close()
    return valor


def test_rodar_grava_o_worktree_path():
    _, task_id = _tarefa()

    with patch("app.api.tasks.BackgroundTasks.add_task"):  # não dispara agente
        resp = client.post(f"/api/tasks/{task_id}/run")

    assert resp.status_code == 200
    assert _worktree_no_banco(task_id), "worktree_path ficou vazio depois de rodar"
    assert task_id in _worktree_no_banco(task_id)


def test_worktree_path_sobrevive_ao_fim_da_execucao():
    """O background grava o status; não pode apagar o caminho no caminho."""
    _, task_id = _tarefa()

    with patch("app.api.tasks.BackgroundTasks.add_task"):
        client.post(f"/api/tasks/{task_id}/run")

    antes = _worktree_no_banco(task_id)

    db = SessionLocal()
    t = db.query(Task).filter(Task.id == task_id).first()
    t.status = TaskStatus.REVIEW_READY
    db.commit()
    db.close()

    assert _worktree_no_banco(task_id) == antes


def test_reencontra_worktree_orfao_no_disco():
    """
    A pasta existe mas o banco não sabe — foi o que aconteceu com as tarefas
    reais do usuário. Como o nome é previsível (task-<id>), dá para religar
    em vez de deixar o trabalho do agente invisível.
    """
    import os, tempfile
    with tempfile.TemporaryDirectory() as raiz:
        db = SessionLocal()
        p = Project(name=f"{PREFIXO} Proj", root_path=raiz)
        db.add(p)
        db.commit()
        db.refresh(p)
        t = Task(project_id=p.id, title="T", raw_prompt="x",
                 status=TaskStatus.RUNNING, worktree_path=None)
        db.add(t)
        db.commit()
        db.refresh(t)
        task_id = t.id
        db.close()

        # A worktree existe no disco, mas a tarefa não a conhece
        os.makedirs(os.path.join(raiz, ".worktrees", f"task-{task_id}"))

        client.post("/api/tasks/refresh-states")

        assert _worktree_no_banco(task_id), "deveria ter religado a worktree órfã"


def test_nao_inventa_worktree_que_nao_existe():
    """Religar só vale quando a pasta está lá de verdade."""
    _, task_id = _tarefa()
    client.post("/api/tasks/refresh-states")
    assert _worktree_no_banco(task_id) is None


def test_assistente_integrado_tambem_grava_o_caminho():
    """Mesmo sem CLI externo, a worktree é criada e precisa ser rastreável."""
    _, task_id = _tarefa(cli="assistant")

    with patch("app.api.tasks.BackgroundTasks.add_task"):
        client.post(f"/api/tasks/{task_id}/run")

    assert _worktree_no_banco(task_id)
