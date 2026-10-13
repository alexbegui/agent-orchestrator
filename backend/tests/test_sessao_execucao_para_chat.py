"""
A sessão criada pela EXECUÇÃO precisa chegar ao CHAT.

O teste que já existia (test_chat_cli_routing) cobre chat -> chat: duas
mensagens seguidas no mesmo processo, ligadas pelo dicionário em memória
`_claude_sessions`. A ponte que ninguém exercitava é outra:

    run_task grava runner_config["claude_session_id"]
      -> send_task_message restaura em _claude_sessions[task.id]
        -> _call_claude_cli monta --resume <id>

Essa ponte é o que faz "por que você fez assim?" chegar ao agente que de fato
fez, e não a um que nunca viu a tarefa. Ela é também o que sobrevive a um
reinício do servidor, já que o dicionário em memória se perde e só o
runner_config persiste.
"""
import pytest
from unittest.mock import patch
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.database import Base, get_db
from app.main import app
from app.services.assistant_service import assistant_service

SESSAO_DA_EXECUCAO = "a7f3e1c9-0000-4000-8000-00000000beef"


@pytest.fixture
def client(tmp_path):
    db_file = tmp_path / "test_sessao_ponte.db"
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
    # O singleton guarda sessões entre testes; sem limpar, o estado de um
    # teste anterior mascararia justamente o que este quer provar.
    assistant_service._claude_sessions.clear()
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()
    assistant_service._claude_sessions.clear()


def _tarefa_ja_executada(client, tmp_path):
    """Tarefa como run_task a deixa: com a sessão do Claude gravada."""
    proj_dir = tmp_path / "projeto-sessao"
    proj_dir.mkdir(exist_ok=True)

    r = client.post("/api/projects", json={
        "name": "Projeto Sessão", "root_path": str(proj_dir), "default_branch": "main"
    })
    assert r.status_code == 201
    proj_id = r.json()["id"]

    r = client.post("/api/tasks", json={
        "project_id": proj_id,
        "title": "Migrar a silver",
        "raw_prompt": "migre a camada silver",
        "runner_config": {"cli": "claude", "claude_session_id": SESSAO_DA_EXECUCAO},
    })
    assert r.status_code == 201
    return r.json()["id"]


def test_chat_retoma_a_sessao_criada_pela_execucao(client, tmp_path):
    """Sem isso, 'por que você fez assim?' vai para um agente que nunca viu a tarefa."""
    task_id = _tarefa_ja_executada(client, tmp_path)
    capturado = []

    async def fake_exec(*cmd, **kwargs):
        capturado.append(list(cmd))

        class _Proc:
            returncode = 0

            async def communicate(self):
                return (b"porque a silver precisa de deduplicacao", b"")

        return _Proc()

    with patch("asyncio.create_subprocess_exec", new=fake_exec), \
         patch("shutil.which", return_value="C:/fake/claude.cmd"):
        r = client.post(f"/api/tasks/{task_id}/messages", json={
            "content": "por que você fez assim?", "auto_run": False
        })

    assert r.status_code == 201, r.text
    assert capturado, "o Claude CLI nem chegou a ser chamado"

    cmd = capturado[0]
    assert "--resume" in cmd, (
        f"o chat criou uma sessão nova em vez de retomar a da execução: {cmd}"
    )
    assert cmd[cmd.index("--resume") + 1] == SESSAO_DA_EXECUCAO, (
        "retomou uma sessão, mas não a que a execução criou"
    )


def test_ponte_funciona_com_o_dicionario_vazio(client, tmp_path):
    """
    O caso do reinício do servidor: `_claude_sessions` nasce vazio e só o
    runner_config sobreviveu. Se a ponte dependesse da memória, aqui quebraria.
    """
    task_id = _tarefa_ja_executada(client, tmp_path)
    assistant_service._claude_sessions.clear()
    capturado = []

    async def fake_exec(*cmd, **kwargs):
        capturado.append(list(cmd))

        class _Proc:
            returncode = 0

            async def communicate(self):
                return (b"ok", b"")

        return _Proc()

    with patch("asyncio.create_subprocess_exec", new=fake_exec), \
         patch("shutil.which", return_value="C:/fake/claude.cmd"):
        r = client.post(f"/api/tasks/{task_id}/messages", json={
            "content": "continue de onde parou", "auto_run": False
        })

    assert r.status_code == 201, r.text
    cmd = capturado[0]
    assert cmd[cmd.index("--resume") + 1] == SESSAO_DA_EXECUCAO
