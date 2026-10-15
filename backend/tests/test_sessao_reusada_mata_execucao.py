"""
Defeitos vistos em produção, cada um com a mensagem de erro que o CLI gravou
no .run/output.log do usuário.

A) "Error: Session ID <uuid> is already in use." (rc=1, tarefa morta em 0,34s)
   `claude --session-id` CRIA sessão; ele recusa um id que já existe. Como o
   claude_session_id é gravado uma vez e reaproveitado, a primeira execução da
   tarefa funcionava e toda execução seguinte morria no primeiro segundo.
   Retomar exige `--resume`.

B) "Error: -p took "--dangerously-skip-permissions" as its prompt, so the
   intended prompt was left as an argument and ignored." (rc=2)
   O agy lê o argumento seguinte a -p como sendo o prompt. Com a flag logo
   depois de -p, a tarefa real era descartada — o motor agy nunca funcionou.
"""
from unittest.mock import patch
from app.services.runner_service import RunnerService


# ---------------------------------------------------------------- Defeito A

def test_segunda_execucao_retoma_sessao_em_vez_de_recriar():
    """Sessão já criada antes tem de vir com --resume, nunca com --session-id."""
    runner = RunnerService()
    cmd = runner.resolve_cli_command(
        "SUBPROCESS_CLI", "continuar a migração",
        {
            "cli": "claude",
            "claude_session_id": "ab15dfe6-e9d1-4982-830b-da76b196e0fc",
            "claude_session_started": True,
        },
    )

    assert "--session-id" not in cmd, (
        "reusar --session-id faz o claude responder "
        "'Session ID ... is already in use' e a tarefa morre em 0,3s"
    )
    assert "--resume" in cmd
    assert cmd[cmd.index("--resume") + 1] == "ab15dfe6-e9d1-4982-830b-da76b196e0fc"
    # O prompt NÃO vai mais no comando: claude.cmd é batch e o cmd.exe
    # corta na primeira quebra de linha. Ele viaja pela entrada padrão
    # (ver test_prompt_multilinha_para_claude.py).
    assert "continuar a migração" not in cmd


def test_primeira_execucao_ainda_cria_a_sessao():
    """Sem execução anterior não há o que retomar: --session-id continua certo."""
    runner = RunnerService()
    cmd = runner.resolve_cli_command(
        "SUBPROCESS_CLI", "migrar a silver",
        {"cli": "claude", "claude_session_id": "a7f3e1c9-0000-4000-8000-000000000001"},
    )

    assert "--session-id" in cmd
    assert "--resume" not in cmd


# ---------------------------------------------------------------- Defeito B

def test_agy_nao_perde_o_prompt_para_a_flag_de_permissao():
    """O agy toma o argumento seguinte a -p como prompt; a flag não pode estar ali."""
    runner = RunnerService()
    with patch.object(runner, "_agy_padrao", return_value="agy"):
        cmd = runner.resolve_cli_command(
            "SUBPROCESS_CLI", "esta funcionando ?", {"cli": "agy"}
        )

    # Duas formas válidas de entregar o prompt: anexado à flag (-p=<prompt>),
    # que é a que o próprio CLI recomenda, ou como argumento logo depois de -p.
    anexado = [a for a in cmd if a.startswith("-p=")]
    if anexado:
        assert anexado[0] == "-p=esta funcionando ?"
        return

    assert "-p" in cmd, "o comando do agy precisa pedir modo não-interativo"
    seguinte = cmd[cmd.index("-p") + 1]
    assert not seguinte.startswith("-"), (
        f"o agy leria {seguinte!r} como o prompt e ignoraria a tarefa real"
    )
    assert seguinte == "esta funcionando ?"
