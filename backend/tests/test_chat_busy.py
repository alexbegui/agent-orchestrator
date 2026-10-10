"""
Trabalho feito PELO CHAT também precisa aparecer no card.

O usuário abre uma tarefa, pede algo no chat, sai para outra tarefa — e
precisa saber pelo painel se aquela está executando, terminou ou parou,
sem reabrir. Antes, só o ▶ Rodar produzia sinal.
"""
import time
import pytest
from unittest.mock import patch
from fastapi.testclient import TestClient

from app.main import app
from app.core.database import SessionLocal
from app.models.project import Project
from app.models.task import Task, TaskStatus
from app.models.message import Message, MessageRole

client = TestClient(app)
PREFIXO = "__pytest_busy__"


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


def _tarefa(runner_config=None):
    db = SessionLocal()
    p = Project(name=f"{PREFIXO} Proj", root_path="C:/tmp/busy")
    db.add(p)
    db.commit()
    db.refresh(p)
    t = Task(project_id=p.id, title="T", raw_prompt="faça algo",
             status=TaskStatus.RUNNING, runner_config=runner_config or {})
    db.add(t)
    db.commit()
    db.refresh(t)
    ids = (p.id, t.id)
    db.close()
    return ids


def _buscar(proj_id, task_id):
    tasks = client.get(f"/api/tasks/project/{proj_id}").json()
    return next(t for t in tasks if t["id"] == task_id)


def test_chat_em_andamento_marca_a_tarefa_como_executando():
    proj_id, task_id = _tarefa({"chat_busy_since": time.time()})
    alvo = _buscar(proj_id, task_id)
    assert alvo["is_alive"] is True
    assert alvo["awaiting_you"] is False


def test_marca_antiga_expira_para_nao_travar_o_card_para_sempre():
    """Se o servidor morrer no meio da conversa, a marca fica presa no banco."""
    proj_id, task_id = _tarefa({"chat_busy_since": time.time() - 3600})
    alvo = _buscar(proj_id, task_id)
    assert alvo["is_alive"] is False
    assert alvo["stalled"] is True


def test_enviar_mensagem_marca_e_desmarca_a_tarefa():
    proj_id, task_id = _tarefa()
    vistos = []

    async def fake_reply(**kwargs):
        # Durante a chamada, a tarefa precisa estar marcada como ocupada.
        db = SessionLocal()
        t = db.query(Task).filter(Task.id == task_id).first()
        vistos.append(t.runner_config.get("chat_busy_since"))
        db.close()
        return "resposta"

    with patch("app.api.tasks.assistant_service.generate_chat_reply", new=fake_reply):
        resp = client.post(f"/api/tasks/{task_id}/messages", json={"content": "implemente"})

    assert resp.status_code == 201
    assert vistos and vistos[0] is not None, "deveria estar marcada durante a conversa"

    db = SessionLocal()
    t = db.query(Task).filter(Task.id == task_id).first()
    assert t.runner_config.get("chat_busy_since") is None, "deveria desmarcar ao terminar"
    db.close()


def test_falha_no_chat_tambem_desmarca():
    """Sem isso, um erro deixaria o card dizendo 'executando' para sempre."""
    proj_id, task_id = _tarefa()

    async def fake_reply(**kwargs):
        raise RuntimeError("CLI explodiu")

    with patch("app.api.tasks.assistant_service.generate_chat_reply", new=fake_reply):
        try:
            client.post(f"/api/tasks/{task_id}/messages", json={"content": "implemente"})
        except Exception:
            pass

    db = SessionLocal()
    t = db.query(Task).filter(Task.id == task_id).first()
    assert t.runner_config.get("chat_busy_since") is None
    db.close()
