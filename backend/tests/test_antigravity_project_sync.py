import os
import sqlite3
import pytest
from unittest.mock import patch
from fastapi.testclient import TestClient
from app.main import app
from app.core.database import Base, get_db
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from app.services.assistant_service import AssistantService

def test_discover_antigravity_projects(tmp_path):
    service = AssistantService()
    fake_db = str(tmp_path / "conversation_summaries.db")
    conn = sqlite3.connect(fake_db)
    conn.execute("""
        CREATE TABLE conversation_summaries (
            conversation_id TEXT PRIMARY KEY,
            workspace_uris TEXT,
            project_id TEXT,
            title TEXT
        )
    """)
    conn.execute("""
        INSERT INTO conversation_summaries (conversation_id, workspace_uris, project_id, title)
        VALUES ('c1', '["file:///d%3A/Projetos/SIGMA"]', 'proj-sigma-id', 'Tarefa Sigma'),
               ('c2', '["file:///d%3A/Git-PMFI/Censo"]', 'proj-censo-id', 'Tarefa Censo')
    """)
    conn.commit()
    conn.close()

    with patch("os.path.expanduser", side_effect=lambda p: fake_db if "conversation_summaries.db" in p else "/nonexistent"):
        projects = service.discover_antigravity_projects()

    paths = [p["root_path"].lower() for p in projects]
    assert any("sigma" in p for p in paths)
    assert any("censo" in p for p in paths)


def test_api_discover_and_import_antigravity_projects(tmp_path):
    test_db_file = str(tmp_path / "test.db")
    engine = create_engine(f"sqlite:///{test_db_file}")
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    Base.metadata.create_all(bind=engine)

    def override_get_db():
        db = TestingSessionLocal()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    client = TestClient(app)

    fake_discovered = [
        {"name": "SIGMA", "root_path": str(tmp_path / "SIGMA"), "antigravity_project_id": "pid-1", "uri": "file:///fake/sigma"},
        {"name": "Censo", "root_path": str(tmp_path / "Censo"), "antigravity_project_id": "pid-2", "uri": "file:///fake/censo"},
    ]

    with patch("app.api.projects.assistant_service.discover_antigravity_projects", return_value=fake_discovered):
        res = client.get("/api/projects/antigravity/discover")
        assert res.status_code == 200
        data = res.json()
        assert len(data) == 2
        assert data[0]["name"] == "SIGMA"
        assert data[0]["already_imported"] is False

        # Agora importa os projetos descobertos
        payload = {
            "projects": [
                {"name": "SIGMA", "root_path": str(tmp_path / "SIGMA"), "default_branch": "main"},
                {"name": "Censo", "root_path": str(tmp_path / "Censo"), "default_branch": "main"}
            ]
        }
        res_import = client.post("/api/projects/antigravity/import", json=payload)
        assert res_import.status_code == 200
        imported = res_import.json()
        assert len(imported) == 2
        assert imported[0]["name"] == "SIGMA"
        assert imported[1]["name"] == "Censo"

        # Chamando discover novamente, devem vir marcados como already_imported = True
        res2 = client.get("/api/projects/antigravity/discover")
        data2 = res2.json()
        assert all(item["already_imported"] is True for item in data2)

    app.dependency_overrides.clear()
