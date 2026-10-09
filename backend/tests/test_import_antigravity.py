import pytest
from unittest.mock import patch
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.database import Base, get_db
from app.main import app
from app.models.task import TaskStatus


@pytest.fixture
def client(tmp_path):
    db_file = tmp_path / "test_import.db"
    engine = create_engine(f"sqlite:///{db_file}", connect_args={"check_same_thread": False})
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    Base.metadata.create_all(bind=engine)

    def override_get_db():
        session = TestingSessionLocal()
        try:
            yield session
        finally:
            session.close()

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


def test_list_antigravity_conversations(client, tmp_path):
    fake_convs = [
        {
            "conversation_id": "conv-111",
            "title": "Primeira Conversa",
            "preview": "Olá agente",
            "step_count": 5,
            "last_modified": "2026-10-09 12:00:00",
            "workspace": "D:/Projetos/Teste",
            "status": "active"
        },
        {
            "conversation_id": "conv-222",
            "title": "Segunda Conversa",
            "preview": "Refatorando código",
            "step_count": 12,
            "last_modified": "2026-10-09 13:00:00",
            "workspace": "D:/Projetos/Teste",
            "status": "active"
        }
    ]

    with patch("app.api.tasks.assistant_service.list_antigravity_conversations", return_value=fake_convs):
        resp = client.get("/api/tasks/antigravity/conversations")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 2
        assert data[0]["conversation_id"] == "conv-111"
        assert data[0]["title"] == "Primeira Conversa"


def test_import_antigravity_conversation_success(client, tmp_path):
    # 1. Cria projeto
    proj_dir = tmp_path / "imported-project"
    proj_dir.mkdir()

    resp = client.post("/api/projects", json={
        "name": "Projeto Import",
        "root_path": str(proj_dir),
        "default_branch": "main"
    })
    assert resp.status_code == 201
    proj_id = resp.json()["id"]

    fake_transcript = [
        {"role": "USER", "content": "Por favor crie a tela de login"},
        {"role": "ASSISTANT", "content": "Com certeza! Vou estruturar o componente."},
        {"role": "USER", "content": "Use Tailwind CSS."},
        {"role": "ASSISTANT", "content": "Perfeito, aplicando Tailwind CSS."}
    ]

    fake_info = {
        "conversation_id": "conv-abc-123",
        "title": "Desenvolvimento Tela de Login",
        "preview": "Por favor crie a tela...",
        "step_count": 4,
        "last_modified": "2026-10-09 13:30:00"
    }

    with patch("app.api.tasks.assistant_service.get_antigravity_conversation_info", return_value=fake_info), \
         patch("app.api.tasks.assistant_service.get_conversation_transcript", return_value=fake_transcript), \
         patch("app.api.tasks.assistant_service.set_task_conversation_id") as mock_set_conv:

        payload = {
            "project_id": proj_id,
            "conversation_id": "conv-abc-123"
        }
        resp = client.post("/api/tasks/import-antigravity", json=payload)
        assert resp.status_code == 201
        data = resp.json()

        assert data["title"] == "Desenvolvimento Tela de Login"
        assert data["status"] == "RUNNING"
        assert data["runner_config"]["antigravity_conversation_id"] == "conv-abc-123"
        task_id = data["id"]

        # Verifica mensagens importadas
        msg_resp = client.get(f"/api/tasks/{task_id}/messages")
        assert msg_resp.status_code == 200
        msgs = msg_resp.json()
        assert len(msgs) == 4
        assert msgs[0]["role"] == "USER"
        assert msgs[0]["content"] == "Por favor crie a tela de login"
        assert msgs[1]["role"] == "ASSISTANT"
        assert msgs[1]["content"] == "Com certeza! Vou estruturar o componente."

        mock_set_conv.assert_called_with(task_id, "conv-abc-123")

    # 4. Testa sincronização com mensagens subsequentes
    updated_transcript = fake_transcript + [
        {"role": "USER", "content": "Adicione validação de e-mail."},
        {"role": "ASSISTANT", "content": "Validação de e-mail adicionada com sucesso!"}
    ]

    with patch("app.api.tasks.assistant_service.get_conversation_transcript", return_value=updated_transcript):
        sync_resp = client.post(f"/api/tasks/{task_id}/sync-antigravity")
        assert sync_resp.status_code == 200
        sync_data = sync_resp.json()
        assert sync_data["synced"] == 2

        # Confirma que o chat da tarefa agora tem 6 mensagens
        msg_resp2 = client.get(f"/api/tasks/{task_id}/messages")
        assert len(msg_resp2.json()) == 6
        assert msg_resp2.json()[-1]["content"] == "Validação de e-mail adicionada com sucesso!"

