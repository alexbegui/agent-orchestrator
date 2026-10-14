"""
O agente que EXECUTA a tarefa e o agente com quem o usuário CONVERSA
depois precisam ser o mesmo. Isso exige que a sessão criada na execução
seja gravada e reaproveitada pelo chat.
"""
import json
import pytest

from app.services.runner_service import RunnerService


def test_claude_recebe_session_id_quando_fornecido():
    runner = RunnerService()
    cmd = runner.resolve_cli_command(
        "SUBPROCESS_CLI", "migrar a silver",
        {"cli": "claude", "claude_session_id": "a7f3e1c9-0000-4000-8000-000000000001"}
    )
    assert "--session-id" in cmd
    assert cmd[cmd.index("--session-id") + 1] == "a7f3e1c9-0000-4000-8000-000000000001"
    # O prompt NÃO vai mais no comando: claude.cmd é batch e o cmd.exe
    # corta na primeira quebra de linha. Ele viaja pela entrada padrão
    # (ver test_prompt_multilinha_para_claude.py).
    assert "migrar a silver" not in cmd


def test_claude_sem_session_id_continua_funcionando():
    """Tarefas antigas, sem id gravado, não podem quebrar."""
    runner = RunnerService()
    cmd = runner.resolve_cli_command("SUBPROCESS_CLI", "migrar a silver", {"cli": "claude"})
    assert "--session-id" not in cmd
    # O prompt NÃO vai mais no comando: claude.cmd é batch e o cmd.exe
    # corta na primeira quebra de linha. Ele viaja pela entrada padrão
    # (ver test_prompt_multilinha_para_claude.py).
    assert "migrar a silver" not in cmd


def test_antigravity_conversation_id_e_extraido_da_saida():
    """O agentapi devolve o conversationId em JSON. Hoje ele é jogado fora."""
    runner = RunnerService()
    saida = json.dumps({
        "response": {"newConversation": {"conversationId": "conv-abc-123"}}
    })
    assert runner.extract_conversation_id(saida) == "conv-abc-123"


def test_extract_conversation_id_ignora_saida_que_nao_e_json():
    runner = RunnerService()
    assert runner.extract_conversation_id("iniciando agente...\n") is None


def test_extract_conversation_id_acha_json_no_meio_de_outras_linhas():
    """Na prática o CLI imprime ruído antes do JSON."""
    runner = RunnerService()
    saida = (
        "warning: telemetry enabled\n"
        '{"response": {"newConversation": {"conversationId": "conv-xyz-789"}}}\n'
        "done\n"
    )
    assert runner.extract_conversation_id(saida) == "conv-xyz-789"
