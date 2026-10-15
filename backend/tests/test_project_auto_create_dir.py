import os
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.database import Base, get_db
from app.main import app

@pytest.fixture
def client(tmp_path):
    db_file = tmp_path / "test_project_create.db"
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


def test_create_project_auto_creates_missing_directory(client, tmp_path):
    """Quando o usuário cadastra um projeto com pasta inexistente, ela deve ser criada automaticamente."""
    non_existent_dir = tmp_path / "SubPasta" / "NovoProjeto"
    assert not non_existent_dir.exists()

    resp = client.post("/api/projects", json={
        "name": "Novo Projeto Criado",
        "root_path": str(non_existent_dir),
        "default_branch": "main"
    })

    assert resp.status_code == 201
    data = resp.json()
    assert data["name"] == "Novo Projeto Criado"
    assert os.path.isdir(data["root_path"])
    assert non_existent_dir.exists()
