"""
Testes de continuidade de conversa e geração de IDs para o motor Antigravity (agy).
Garante que uma sessão de execução agy seja reaproveitada pelo chat e chamadas subsequentes,
da mesma forma que é feito para o Claude.
"""
import uuid
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.database import Base, get_db
from app.main import app
from app.models.project import Project
from app.models.task import Task, TaskStatus, RunnerType
from app.services.runner_service import RunnerService


def test_agy_resolve_cli_inclui_conversation_id():
    runner = RunnerService()
    conv_id = str(uuid.uuid4())
    cmd = runner.resolve_cli_command(
        runner_type="SUBPROCESS_CLI",
        prompt="minha tarefa",
        config={"cli": "agy", "antigravity_conversation_id": conv_id}
    )
    assert "--conversation" in cmd
    idx = cmd.index("--conversation")
    assert cmd[idx + 1] == conv_id


def test_run_task_pre_gera_antigravity_conversation_id(tmp_path):
    """
    Ao rodar uma tarefa com CLI agy, o orchestrator deve pré-gerar o antigravity_conversation_id
    no runner_config antes de despachar, para permitir continuidade imediata no chat.
    """
    db_file = tmp_path / "test_ag_continuity.db"
    engine = create_engine(f"sqlite:///{db_file}", connect_args={"check_same_thread": False})
    TestingSession = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    Base.metadata.create_all(bind=engine)

    def override_db():
        s = TestingSession()
        try:
            yield s
        finally:
            s.close()

    app.dependency_overrides[get_db] = override_db
    try:
        with TestClient(app) as client:
            proj_dir = tmp_path / "p1"
            proj_dir.mkdir()
            p_resp = client.post("/api/projects", json={
                "name": "P1", "root_path": str(proj_dir), "default_branch": "main"
            })
            proj_id = p_resp.json()["id"]

            t_resp = client.post("/api/tasks", json={
                "project_id": proj_id,
                "title": "Tarefa Antigravity",
                "raw_prompt": "Fazer algo",
                "runner_type": "SUBPROCESS_CLI",
                "runner_config": {"cli": "agy"}
            })
            task_id = t_resp.json()["id"]

            # Roda a tarefa com background mockado
            with TestClient(app) as cl:
                r_resp = cl.post(f"/api/tasks/{task_id}/run")
                assert r_resp.status_code == 200
                data = r_resp.json()
                cfg = data.get("runner_config") or {}
                assert "antigravity_conversation_id" in cfg
                assert cfg["antigravity_conversation_id"] is not None
                assert len(cfg["antigravity_conversation_id"]) == 36  # UUID válido
    finally:
        app.dependency_overrides.clear()
