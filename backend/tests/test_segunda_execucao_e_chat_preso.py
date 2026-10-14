"""
Segunda metade do defeito A, e o defeito C.

A) resolve_cli_command já sabe retomar com --resume, mas só se alguém marcar
   que a sessão existe. Sem a marca, todo ▶ Rodar seguinte ao primeiro volta a
   mandar --session-id e morre com "Session ID ... is already in use".

C) O chat marcava a tarefa como ocupada e chamava o CLI com
   `await proc.communicate()` SEM timeout. CLI que não retorna deixava a marca
   presa pelos 15 minutos do CHAT_BUSY_TIMEOUT, e nesse intervalo a entrada do
   usuário ficava bloqueada ("fica só processando").
"""
import asyncio
import pytest
from unittest.mock import patch
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.database import Base, get_db
from app.main import app
from app.services.assistant_service import assistant_service

SESSAO = "ab15dfe6-0000-4000-8000-00000000cafe"


@pytest.fixture
def client(tmp_path):
    db_file = tmp_path / "test_segunda_exec.db"
    engine = create_engine(f"sqlite:///{db_file}", connect_args={"check_same_thread": False})
    Session = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    Base.metadata.create_all(bind=engine)

    def override_get_db():
        session = Session()
        try:
            yield session
        finally:
            session.close()

    app.dependency_overrides[get_db] = override_get_db
    assistant_service._claude_sessions.clear()
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()
    assistant_service._claude_sessions.clear()


def _tarefa(client, tmp_path, nome="projeto-exec"):
    proj_dir = tmp_path / nome
    proj_dir.mkdir(exist_ok=True)
    r = client.post("/api/projects", json={
        "name": nome, "root_path": str(proj_dir), "default_branch": "main"
    })
    proj_id = r.json()["id"]
    r = client.post("/api/tasks", json={
        "project_id": proj_id,
        "title": "Migrar a silver",
        "raw_prompt": "migre a camada silver",
        "runner_config": {"cli": "claude", "claude_session_id": SESSAO},
    })
    return r.json()["id"]


# ---------------------------------------------------------------- Defeito A

def test_execucao_marca_que_a_sessao_ja_existe(client, tmp_path):
    """Sem a marca, o ▶ Rodar seguinte recria a sessão e a tarefa morre em 0,3s."""
    task_id = _tarefa(client, tmp_path)

    r = client.post(f"/api/tasks/{task_id}/run")
    assert r.status_code == 200, r.text

    cfg = r.json()["runner_config"]
    assert cfg.get("claude_session_started") is True, (
        "a execução não registrou que a sessão passou a existir; "
        "a próxima mandaria --session-id de novo e o claude recusaria"
    )


# ---------------------------------------------------------------- Defeito C

def test_chat_nao_fica_preso_quando_o_cli_nao_responde(client, tmp_path):
    """CLI mudo não pode bloquear a entrada do usuário por 15 minutos."""
    task_id = _tarefa(client, tmp_path, nome="projeto-chat-preso")

    async def cli_que_nunca_responde(*cmd, **kwargs):
        class _Proc:
            returncode = None
            pid = 4242

            async def communicate(self):
                await asyncio.sleep(3600)  # nunca volta

            def kill(self):
                self.returncode = -9

        return _Proc()

    with patch("asyncio.create_subprocess_exec", new=cli_que_nunca_responde), \
         patch("shutil.which", return_value="C:/fake/claude.cmd"), \
         patch("app.services.assistant_service.CHAT_CLI_TIMEOUT", 0.3):
        r = client.post(f"/api/tasks/{task_id}/messages", json={
            "content": "oi", "auto_run": False
        })

    assert r.status_code == 201, r.text

    # A marca de ocupado tem de ter saído: é ela que bloqueia a entrada e faz
    # o card dizer "Executando" com ninguém trabalhando.
    tarefa = next(t for t in client.get("/api/tasks/all").json() if t["id"] == task_id)

    assert "chat_busy_since" not in (tarefa["runner_config"] or {}), (
        "a tarefa ficou marcada como ocupada; a entrada seguiria bloqueada"
    )
    assert tarefa["is_alive"] is False
    assert tarefa["card_state"] != "EXECUTANDO"
