"""
Importar várias conversas do Antigravity de uma vez.
Regras: pula as já importadas, e uma falha não derruba o lote.
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

PREFIXO = "__pytest_bulk__"


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


def _projeto():
    db = SessionLocal()
    p = Project(name=f"{PREFIXO} Proj", root_path="C:/tmp/bulk")
    db.add(p)
    db.commit()
    db.refresh(p)
    pid = p.id
    db.close()
    return pid


CONVERSAS = [
    {"conversation_id": "conv-1", "title": "Primeira", "preview": "p1"},
    {"conversation_id": "conv-2", "title": "Segunda", "preview": "p2"},
    {"conversation_id": "conv-3", "title": "Terceira", "preview": "p3"},
]

TRANSCRIPT = [
    {"role": "USER", "content": "faça X"},
    {"role": "ASSISTANT", "content": "feito"},
]


def test_importa_todas_as_pendentes_quando_nao_especifica_quais():
    pid = _projeto()
    with patch("app.api.tasks.assistant_service.list_antigravity_conversations", return_value=CONVERSAS), \
         patch("app.api.tasks.assistant_service.get_antigravity_conversation_info", return_value={"title": "T"}), \
         patch("app.api.tasks.assistant_service.get_conversation_transcript", return_value=TRANSCRIPT):
        resp = client.post("/api/tasks/import-antigravity-bulk", json={"project_id": pid})

    assert resp.status_code == 200
    body = resp.json()
    assert body["imported"] == 3
    assert body["skipped"] == 0
    assert body["failed"] == []

    db = SessionLocal()
    criadas = db.query(Task).filter(Task.project_id == pid).all()
    assert len(criadas) == 3
    assert all(t.status == TaskStatus.RUNNING for t in criadas)
    db.close()


def test_pula_as_ja_importadas_em_vez_de_duplicar():
    pid = _projeto()
    db = SessionLocal()
    db.add(Task(project_id=pid, title="ja existe", raw_prompt="x",
                status=TaskStatus.RUNNING,
                runner_config={"antigravity_conversation_id": "conv-2"}))
    db.commit()
    db.close()

    with patch("app.api.tasks.assistant_service.list_antigravity_conversations", return_value=CONVERSAS), \
         patch("app.api.tasks.assistant_service.get_antigravity_conversation_info", return_value={"title": "T"}), \
         patch("app.api.tasks.assistant_service.get_conversation_transcript", return_value=TRANSCRIPT):
        resp = client.post("/api/tasks/import-antigravity-bulk", json={"project_id": pid})

    body = resp.json()
    assert body["imported"] == 2
    assert body["skipped"] == 1


def test_importa_apenas_as_selecionadas():
    pid = _projeto()
    with patch("app.api.tasks.assistant_service.list_antigravity_conversations", return_value=CONVERSAS), \
         patch("app.api.tasks.assistant_service.get_antigravity_conversation_info", return_value={"title": "T"}), \
         patch("app.api.tasks.assistant_service.get_conversation_transcript", return_value=TRANSCRIPT):
        resp = client.post("/api/tasks/import-antigravity-bulk",
                           json={"project_id": pid, "conversation_ids": ["conv-1", "conv-3"]})

    assert resp.json()["imported"] == 2
    db = SessionLocal()
    ids = {t.runner_config.get("antigravity_conversation_id")
           for t in db.query(Task).filter(Task.project_id == pid).all()}
    db.close()
    assert ids == {"conv-1", "conv-3"}


def test_uma_conversa_quebrada_nao_derruba_o_lote():
    pid = _projeto()

    def transcript_com_defeito(conv_id):
        if conv_id == "conv-2":
            raise ValueError("transcript corrompido")
        return TRANSCRIPT

    with patch("app.api.tasks.assistant_service.list_antigravity_conversations", return_value=CONVERSAS), \
         patch("app.api.tasks.assistant_service.get_antigravity_conversation_info", return_value={"title": "T"}), \
         patch("app.api.tasks.assistant_service.get_conversation_transcript", side_effect=transcript_com_defeito):
        resp = client.post("/api/tasks/import-antigravity-bulk", json={"project_id": pid})

    body = resp.json()
    assert body["imported"] == 2
    assert len(body["failed"]) == 1
    assert body["failed"][0]["conversation_id"] == "conv-2"


def test_projeto_inexistente_devolve_404():
    resp = client.post("/api/tasks/import-antigravity-bulk", json={"project_id": "nao-existe"})
    assert resp.status_code == 404
