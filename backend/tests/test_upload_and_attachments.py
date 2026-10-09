import pytest
import io
from unittest.mock import patch
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.database import Base, get_db
from app.main import app


@pytest.fixture
def client(tmp_path):
    db_file = tmp_path / "test_attachments.db"
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


def test_upload_attachment_and_send_message(client, tmp_path):
    # 1. Cria projeto e tarefa
    proj_dir = tmp_path / "proj"
    proj_dir.mkdir()
    resp = client.post("/api/projects", json={
        "name": "Projeto Anexos",
        "root_path": str(proj_dir),
        "default_branch": "main"
    })
    proj_id = resp.json()["id"]

    resp = client.post("/api/tasks", json={
        "project_id": proj_id,
        "title": "Tarefa com Anexo",
        "raw_prompt": "Analise esta imagem"
    })
    task_id = resp.json()["id"]

    # 2. Testa upload de arquivo
    file_content = b"fake image bytes png header"
    files = {"file": ("screenshot.png", io.BytesIO(file_content), "image/png")}
    upload_resp = client.post(f"/api/tasks/{task_id}/upload", files=files)
    assert upload_resp.status_code == 200
    upload_data = upload_resp.json()
    assert upload_data["original_name"] == "screenshot.png"
    assert upload_data["content_type"] == "image/png"
    assert upload_data["size"] == len(file_content)
    assert upload_data["file_url"].startswith(f"/api/uploads/tasks/{task_id}/")

    # 3. Envia mensagem com anexo
    with patch("app.api.tasks.assistant_service.generate_chat_reply", return_value="Imagem analisada com sucesso!"):
        msg_payload = {
            "content": "Veja este erro na tela em anexo",
            "attachments": [upload_data]
        }
        msg_resp = client.post(f"/api/tasks/{task_id}/messages", json=msg_payload)
        assert msg_resp.status_code == 201

        # 4. Verifica histórico de mensagens
        get_msgs = client.get(f"/api/tasks/{task_id}/messages")
        assert get_msgs.status_code == 200
        msgs = get_msgs.json()
        assert len(msgs) == 2
        user_msg = msgs[0]
        assert user_msg["role"] == "USER"
        assert len(user_msg["attachments"]) == 1
        assert user_msg["attachments"][0]["original_name"] == "screenshot.png"
