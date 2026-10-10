"""
O painel precisa saber na hora, não a cada 20 segundos.

O canal /ws/dashboard existe no backend desde sempre e nunca foi usado: o
frontend fazia polling. Para ele servir, os momentos que mudam o estado de
um card precisam emitir evento — e o mais importante é o chat, porque é
assim que o usuário trabalha.
"""
import pytest
from unittest.mock import patch, AsyncMock
from fastapi.testclient import TestClient

from app.main import app
from app.core.database import SessionLocal
from app.models.project import Project
from app.models.task import Task, TaskStatus
from app.models.message import Message

client = TestClient(app)
PREFIXO = "__pytest_ws__"


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


def _tarefa():
    db = SessionLocal()
    p = Project(name=f"{PREFIXO} Proj", root_path="C:/tmp/ws")
    db.add(p)
    db.commit()
    db.refresh(p)
    t = Task(project_id=p.id, title="T", raw_prompt="faça algo", status=TaskStatus.RUNNING)
    db.add(t)
    db.commit()
    db.refresh(t)
    ids = (p.id, t.id)
    db.close()
    return ids


def _tipos(mock):
    return [c.args[0].get("type") for c in mock.await_args_list if c.args]


def test_inicio_do_chat_avisa_o_painel():
    """Sem isto, o card só vira 'Executando' no próximo ciclo de 20s."""
    _, task_id = _tarefa()

    async def resposta(**kwargs):
        return "ok"

    with patch("app.api.tasks.assistant_service.generate_chat_reply", new=resposta), \
         patch("app.api.tasks.ws_manager.broadcast_dashboard", new=AsyncMock()) as mock:
        client.post(f"/api/tasks/{task_id}/messages", json={"content": "implemente"})

    assert "TASK_BUSY" in _tipos(mock)


def test_fim_do_chat_avisa_o_painel():
    """É o aviso de que a bola voltou para o usuário."""
    _, task_id = _tarefa()

    async def resposta(**kwargs):
        return "ok"

    with patch("app.api.tasks.assistant_service.generate_chat_reply", new=resposta), \
         patch("app.api.tasks.ws_manager.broadcast_dashboard", new=AsyncMock()) as mock:
        client.post(f"/api/tasks/{task_id}/messages", json={"content": "implemente"})

    assert "TASK_UPDATED" in _tipos(mock)


def test_falha_no_chat_tambem_avisa():
    """Senão o card fica 'Executando' até a marca expirar, 15 minutos depois."""
    _, task_id = _tarefa()

    async def explode(**kwargs):
        raise RuntimeError("CLI caiu")

    with patch("app.api.tasks.assistant_service.generate_chat_reply", new=explode), \
         patch("app.api.tasks.ws_manager.broadcast_dashboard", new=AsyncMock()) as mock:
        try:
            client.post(f"/api/tasks/{task_id}/messages", json={"content": "implemente"})
        except Exception:
            pass

    assert "TASK_UPDATED" in _tipos(mock)


def test_evento_carrega_o_id_da_tarefa():
    """O painel precisa saber qual card mudou."""
    _, task_id = _tarefa()

    async def resposta(**kwargs):
        return "ok"

    with patch("app.api.tasks.assistant_service.generate_chat_reply", new=resposta), \
         patch("app.api.tasks.ws_manager.broadcast_dashboard", new=AsyncMock()) as mock:
        client.post(f"/api/tasks/{task_id}/messages", json={"content": "implemente"})

    ids = [c.args[0].get("task_id") for c in mock.await_args_list if c.args]
    assert task_id in ids
