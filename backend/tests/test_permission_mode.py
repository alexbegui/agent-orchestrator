"""
`claude -p` é não-interativo: sem --permission-mode, tudo que pediria
aprovação é negado automaticamente e o agente trava sem conseguir avisar.
O orquestrador roda em worktree isolado, então o padrão é bypassPermissions.
"""
from app.services.runner_service import RunnerService


def test_claude_recebe_bypass_permissions_por_padrao():
    runner = RunnerService()
    cmd = runner.resolve_cli_command("SUBPROCESS_CLI", "faça X", {"cli": "claude"})
    assert "--permission-mode" in cmd
    assert cmd[cmd.index("--permission-mode") + 1] == "bypassPermissions"


def test_modo_pode_ser_sobrescrito_por_tarefa():
    runner = RunnerService()
    cmd = runner.resolve_cli_command(
        "SUBPROCESS_CLI", "faça X", {"cli": "claude", "permission_mode": "acceptEdits"}
    )
    assert cmd[cmd.index("--permission-mode") + 1] == "acceptEdits"


def test_modo_invalido_cai_no_padrao_em_vez_de_quebrar():
    runner = RunnerService()
    cmd = runner.resolve_cli_command(
        "SUBPROCESS_CLI", "faça X", {"cli": "claude", "permission_mode": "inventado"}
    )
    assert cmd[cmd.index("--permission-mode") + 1] == "bypassPermissions"


def test_permission_mode_convive_com_session_id():
    runner = RunnerService()
    cmd = runner.resolve_cli_command(
        "SUBPROCESS_CLI", "faça X",
        {"cli": "claude", "claude_session_id": "a7f3e1c9-0000-4000-8000-000000000001"}
    )
    assert "--session-id" in cmd
    assert "--permission-mode" in cmd
    # O prompt NÃO vai mais no comando: claude.cmd é batch e o cmd.exe
    # corta na primeira quebra de linha. Ele viaja pela entrada padrão
    # (ver test_prompt_multilinha_para_claude.py).
    assert "faça X" not in cmd


def test_antigravity_nao_recebe_flag_do_claude():
    runner = RunnerService()
    cmd = runner.resolve_cli_command("SUBPROCESS_CLI", "faça X", {"cli": "agy"})
    assert "--permission-mode" not in cmd
