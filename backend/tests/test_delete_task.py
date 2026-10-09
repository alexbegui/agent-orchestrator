import pytest
from unittest.mock import patch
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.database import Base, get_db
from app.main import app
from app.models.project import Project
from app.models.task import Task, TaskStatus


@pytest.fixture
def client(tmp_path):
    db_file = tmp_path / "test_delete.db"
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


def test_delete_task_success(client, tmp_path):
    # 1. Cria projeto
    proj_dir = tmp_path / "delete-project"
    proj_dir.mkdir()

    resp = client.post("/api/projects", json={
        "name": "Projeto Limpeza",
        "root_path": str(proj_dir),
        "default_branch": "main"
    })
    assert resp.status_code == 201
    proj_id = resp.json()["id"]

    # 2. Cria tarefa com antigravity_conversation_id simulado
    resp = client.post("/api/tasks", json={
        "project_id": proj_id,
        "title": "Tarefa para Excluir",
        "raw_prompt": "Testando exclusão",
        "runner_config": {"antigravity_conversation_id": "test-conv-123"}
    })
    assert resp.status_code == 201
    task_id = resp.json()["id"]

    # 3. Executa DELETE mockando git e antigravity service
    with patch("app.api.tasks.assistant_service.delete_antigravity_conversation", return_value=True) as mock_ag_del, \
         patch("app.api.tasks.git_service.cleanup_task_git") as mock_git_clean:

        del_resp = client.delete(f"/api/tasks/{task_id}")
        assert del_resp.status_code == 200
        del_data = del_resp.json()
        assert del_data["deleted"] is True
        assert del_data["task_id"] == task_id
        assert del_data["antigravity_cleaned"] is True

        mock_ag_del.assert_called_once_with("test-conv-123")
        mock_git_clean.assert_called_once_with(str(proj_dir), task_id)

    # 4. Verifica que a tarefa não existe mais no projeto
    list_resp = client.get(f"/api/tasks/project/{proj_id}")
    assert list_resp.status_code == 200
    assert len(list_resp.json()) == 0


def test_delete_task_not_found(client):
    del_resp = client.delete("/api/tasks/id-inexistente")
    assert del_resp.status_code == 404
