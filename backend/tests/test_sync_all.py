import pytest
from unittest.mock import patch
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.database import Base, get_db
from app.main import app
from app.models.task import Task, TaskStatus, RunnerType
from app.models.project import Project


@pytest.fixture
def client(tmp_path):
    db_file = tmp_path / "test_sync_all.db"
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


def test_sync_all_tasks(client, tmp_path):
    # Cria projeto
    proj_dir = tmp_path / "sync-project"
    proj_dir.mkdir()

    p_resp = client.post("/api/projects", json={
        "name": "Sync All Project",
        "root_path": str(proj_dir),
        "default_branch": "main"
    })
    assert p_resp.status_code == 201
    proj_id = p_resp.json()["id"]

    # Cria duas tarefas vinculadas ao Antigravity
    t1_resp = client.post("/api/tasks", json={
        "project_id": proj_id,
        "title": "Tarefa 1",
        "raw_prompt": "Prompt 1",
        "runner_type": "SUBPROCESS_CLI",
        "runner_config": {"antigravity_conversation_id": "conv-1"}
    })
    assert t1_resp.status_code == 201
    t1_id = t1_resp.json()["id"]

    t2_resp = client.post("/api/tasks", json={
        "project_id": proj_id,
        "title": "Tarefa 2",
        "raw_prompt": "Prompt 2",
        "runner_type": "SUBPROCESS_CLI",
        "runner_config": {"antigravity_conversation_id": "conv-2"}
    })
    assert t2_resp.status_code == 201
    t2_id = t2_resp.json()["id"]

    # Cria uma terceira tarefa NÃO vinculada ao Antigravity
    client.post("/api/tasks", json={
        "project_id": proj_id,
        "title": "Tarefa Local Sem AGY",
        "raw_prompt": "Prompt 3",
        "runner_type": "DIRECT_API",
        "runner_config": {}
    })

    # Simula transcripts retornando novas mensagens para conv-1 e conv-2
    def mock_get_transcript(conv_id):
        if conv_id == "conv-1":
            return [
                {"role": "USER", "content": "Pergunta tarefa 1"},
                {"role": "ASSISTANT", "content": "Resposta tarefa 1"}
            ]
        elif conv_id == "conv-2":
            return [
                {"role": "USER", "content": "Pergunta tarefa 2"},
                {"role": "ASSISTANT", "content": "Resposta tarefa 2"},
                {"role": "ASSISTANT", "content": "Segunda resposta tarefa 2"}
            ]
        return []

    with patch("app.api.tasks.assistant_service.get_conversation_transcript", side_effect=mock_get_transcript):
        # Chama POST /api/tasks/sync-all
        sync_resp = client.post(f"/api/tasks/sync-all?project_id={proj_id}")
        assert sync_resp.status_code == 200
        data = sync_resp.json()

        assert data["tasks_checked"] == 2
        assert data["tasks_updated"] == 2
        assert data["total_messages_synced"] == 5

        # Verifica mensagens salvas na tarefa 1
        m1_resp = client.get(f"/api/tasks/{t1_id}/messages")
        assert len(m1_resp.json()) == 2

        # Verifica mensagens salvas na tarefa 2
        m2_resp = client.get(f"/api/tasks/{t2_id}/messages")
        assert len(m2_resp.json()) == 3

        # Segunda chamada imediata: nada novo deve ser sincronizado
        sync_resp2 = client.post(f"/api/tasks/sync-all?project_id={proj_id}")
        assert sync_resp2.status_code == 200
        data2 = sync_resp2.json()
        assert data2["tasks_checked"] == 2
        assert data2["tasks_updated"] == 0
        assert data2["total_messages_synced"] == 0
