import pytest
from unittest.mock import patch, AsyncMock

from app.services.assistant_service import AssistantService


@pytest.mark.asyncio
async def test_cli_preference_claude_usa_claude_cli():
    """Quando a tarefa foi criada com o CLI 'claude', o chat deve falar com o claude,
    mesmo que o Antigravity esteja instalado nesta maquina."""
    service = AssistantService()

    with patch.object(service, "_find_agentapi_cmd", return_value="C:/fake/agentapi.bat"), \
         patch.object(service, "_call_claude_cli", new=AsyncMock(return_value="resposta do claude")) as mock_claude, \
         patch.object(service, "_call_antigravity_cli", new=AsyncMock(return_value="resposta do antigravity")) as mock_agy:

        reply = await service.generate_chat_reply(
            task_title="Tarefa",
            task_prompt="Requisito",
            history=[],
            project_root="C:/projeto",
            user_message="ola",
            task_id="task-1",
            cli_preference="claude",
        )

    assert reply == "resposta do claude"
    mock_claude.assert_awaited_once()
    mock_agy.assert_not_awaited()


@pytest.mark.asyncio
async def test_cli_preference_agy_usa_antigravity():
    service = AssistantService()

    with patch.object(service, "_find_agentapi_cmd", return_value="C:/fake/agentapi.bat"), \
         patch.object(service, "_call_claude_cli", new=AsyncMock(return_value="resposta do claude")) as mock_claude, \
         patch.object(service, "_call_antigravity_cli", new=AsyncMock(return_value="resposta do antigravity")) as mock_agy:

        reply = await service.generate_chat_reply(
            task_title="Tarefa",
            task_prompt="Requisito",
            history=[],
            project_root="C:/projeto",
            user_message="ola",
            task_id="task-1",
            cli_preference="agy",
        )

    assert reply == "resposta do antigravity"
    mock_agy.assert_awaited_once()
    mock_claude.assert_not_awaited()


@pytest.mark.asyncio
async def test_sem_preferencia_mantem_comportamento_atual():
    """Tarefas antigas nao tem 'cli' no runner_config: devem seguir a cascata de hoje,
    que tenta o Antigravity primeiro."""
    service = AssistantService()

    with patch.object(service, "_find_agentapi_cmd", return_value="C:/fake/agentapi.bat"), \
         patch.object(service, "_call_claude_cli", new=AsyncMock(return_value="resposta do claude")) as mock_claude, \
         patch.object(service, "_call_antigravity_cli", new=AsyncMock(return_value="resposta do antigravity")) as mock_agy:

        reply = await service.generate_chat_reply(
            task_title="Tarefa",
            task_prompt="Requisito",
            history=[],
            project_root="C:/projeto",
            user_message="ola",
            task_id="task-1",
        )

    assert reply == "resposta do antigravity"
    mock_claude.assert_not_awaited()


@pytest.mark.asyncio
async def test_falha_do_cli_escolhido_cai_na_cascata():
    """Se o CLI escolhido quebrar, o chat nao pode morrer: cai no motor local."""
    service = AssistantService()

    with patch.object(service, "_find_agentapi_cmd", return_value=None), \
         patch.object(service, "_call_claude_cli", new=AsyncMock(side_effect=OSError("claude sumiu"))), \
         patch.dict("os.environ", {}, clear=True):

        reply = await service.generate_chat_reply(
            task_title="Tarefa",
            task_prompt="Requisito",
            history=[],
            project_root="C:/projeto",
            user_message="ola",
            task_id="task-1",
            cli_preference="claude",
        )

    assert isinstance(reply, str) and reply.strip()


@pytest.mark.asyncio
async def test_claude_cli_reaproveita_session_id_da_tarefa():
    """A primeira mensagem cria um session id; a segunda retoma o mesmo."""
    service = AssistantService()
    captured = []

    async def fake_exec(*cmd, **kwargs):
        captured.append(list(cmd))

        class _Proc:
            returncode = 0

            async def communicate(self, input=None):
                return (b"resposta", b"")

        return _Proc()

    with patch("asyncio.create_subprocess_exec", new=fake_exec), \
         patch("shutil.which", return_value="C:/fake/claude.cmd"):

        await service._call_claude_cli(
            task_id="task-1", task_title="T", task_prompt="P",
            user_message="primeira", project_name="Proj", project_root="C:/projeto",
        )
        await service._call_claude_cli(
            task_id="task-1", task_title="T", task_prompt="P",
            user_message="segunda", project_name="Proj", project_root="C:/projeto",
        )

    assert "--session-id" in captured[0]
    session_id = captured[0][captured[0].index("--session-id") + 1]
    assert "--resume" in captured[1]
    assert captured[1][captured[1].index("--resume") + 1] == session_id


@pytest.mark.asyncio
async def test_chat_tambem_passa_permission_mode():
    """
    O chat monta o próprio comando. Sem --permission-mode ele é não-interativo
    e nega tudo — o agente trava ao tentar escrever arquivo ou rodar docker,
    mesmo com a execução (▶ Rodar) já corrigida.
    """
    service = AssistantService()
    captured = []

    async def fake_exec(*cmd, **kwargs):
        captured.append(list(cmd))

        class _Proc:
            returncode = 0

            async def communicate(self, input=None):
                return (b"resposta", b"")

        return _Proc()

    with patch("asyncio.create_subprocess_exec", new=fake_exec), \
         patch("shutil.which", return_value="C:/fake/claude.cmd"):

        await service._call_claude_cli(
            task_id="task-perm", task_title="T", task_prompt="P",
            user_message="implemente", project_name="Proj", project_root="C:/projeto",
        )
        await service._call_claude_cli(
            task_id="task-perm", task_title="T", task_prompt="P",
            user_message="continue", project_name="Proj", project_root="C:/projeto",
        )

    # Vale tanto na criação da sessão quanto na retomada
    for cmd in captured:
        assert "--permission-mode" in cmd
        assert cmd[cmd.index("--permission-mode") + 1] == "bypassPermissions"
