"""
O `agy` é o CLI independente do Antigravity: não exige o IDE aberto nem
token CSRF, diferente do `agentapi`. Deve ser a primeira escolha.

Bug que isto também cobre: na cascata antiga, o os.path.expanduser(...)
no meio de um `or` sempre devolve string — tornando tudo depois dele
inalcançável, inclusive a busca pelo agy.
"""
import os
import pytest
from unittest.mock import patch

from app.services.runner_service import RunnerService
from app.services.assistant_service import AssistantService


def _which_so_agy(nome):
    return "C:/Users/Alex/AppData/Local/agy/bin/agy.exe" if nome in ("agy", "agy.exe") else None


def test_prefere_agy_quando_disponivel():
    runner = RunnerService()
    with patch("shutil.which", side_effect=_which_so_agy):
        cmd = runner.resolve_cli_command("SUBPROCESS_CLI", "faça X", {"cli": "agy"})
    assert "agy.exe" in cmd[0]
    assert "-p" in cmd
    assert "faça X" in cmd


def test_agy_recebe_skip_permissions():
    """Sem isso o agente trava pedindo aprovação que ninguém pode dar."""
    runner = RunnerService()
    with patch("shutil.which", side_effect=_which_so_agy):
        cmd = runner.resolve_cli_command("SUBPROCESS_CLI", "faça X", {"cli": "agy"})
    assert "--dangerously-skip-permissions" in cmd


def test_agy_retoma_conversa_quando_ha_id():
    runner = RunnerService()
    with patch("shutil.which", side_effect=_which_so_agy):
        cmd = runner.resolve_cli_command(
            "SUBPROCESS_CLI", "continue",
            {"cli": "agy", "antigravity_conversation_id": "conv-abc-123"}
        )
    assert "--conversation" in cmd
    assert cmd[cmd.index("--conversation") + 1] == "conv-abc-123"


def test_cai_no_agentapi_apenas_se_nao_houver_agy():
    runner = RunnerService()
    with patch("shutil.which", return_value=None), \
         patch("os.path.exists", side_effect=lambda p: "agentapi" in p):
        cmd = runner.resolve_cli_command("SUBPROCESS_CLI", "faça X", {"cli": "agy"})
    assert "agentapi" in cmd[0]


@pytest.mark.asyncio
async def test_chat_usa_agy_e_retoma_a_conversa():
    """O chat precisa do mesmo caminho: agy primeiro, com continuidade por ID."""
    service = AssistantService()
    capturados = []

    async def fake_exec(*cmd, **kwargs):
        capturados.append(list(cmd))

        class _Proc:
            returncode = 0

            async def communicate(self):
                return (b"resposta do agy", b"")

        return _Proc()

    with patch("asyncio.create_subprocess_exec", new=fake_exec), \
         patch("shutil.which", side_effect=_which_so_agy):
        r1 = await service._call_agy_cli(
            task_id="t1", task_title="T", task_prompt="P",
            user_message="implemente", project_name="Proj",
            project_root="C:/projeto", conversation_id=None,
        )
        await service._call_agy_cli(
            task_id="t1", task_title="T", task_prompt="P",
            user_message="continue", project_name="Proj",
            project_root="C:/projeto", conversation_id="conv-xyz",
        )

    assert r1 == "resposta do agy"
    assert "--dangerously-skip-permissions" in capturados[0]
    assert "--conversation" in capturados[1]
    assert capturados[1][capturados[1].index("--conversation") + 1] == "conv-xyz"


def test_caminho_fixo_inexistente_nao_e_devolvido_cegamente():
    """
    A cascata antiga devolvia o caminho do agentapi existisse ele ou não,
    porque uma string não-vazia é sempre verdadeira num `or`.
    """
    runner = RunnerService()
    with patch("shutil.which", return_value=None), \
         patch("os.path.exists", return_value=False):
        cmd = runner.resolve_cli_command("SUBPROCESS_CLI", "faça X", {"cli": "agy"})
    # Sem nada instalado, sobra o nome nu — e o runner avisa que não achou
    assert cmd[0] in ("agy", "agentapi")
    assert not os.path.isabs(cmd[0])
