"""
O Claude Code recebia só a PRIMEIRA LINHA do prompt.

Visto numa execução real: o agente respondeu *"A mensagem chegou só com o
título 'Como trabalhar nesta tarefa' e sem o conteúdo, então não sei qual é a
tarefa"*, terminou com rc=0 e zero arquivos alterados — e o card mostrou
"Entregou".

A causa é o Windows. `claude.cmd` é um arquivo batch, e o cmd.exe **corta o
argumento na primeira quebra de linha**. Medido com um .cmd espião: 90
caracteres e 6 linhas entraram, uma linha saiu.

Por que só apareceu agora: antes o prompt começava pelo pedido do usuário, que
costuma ter uma linha só — a tarefa chegava e as instruções do fim (onde
salvar, registro de conhecimento) se perdiam caladas. Quando as regras de
trabalho passaram a vir primeiro, o que sobrou foi o título delas e a TAREFA
se perdeu. O defeito é antigo; a mudança só trocou o que era descartado.

O conserto é mandar o prompt pela ENTRADA PADRÃO, que não passa pelo
interpretador de linha de comando. Verificado contra o CLI real: `claude -p`
sem prompt posicional lê stdin e responde ao texto inteiro.

O agy NÃO tem esse problema: é um .exe de verdade, e recebe o prompt na forma
`-p=<prompt>` que o próprio CLI indica.
"""
import os
import subprocess
import sys

import pytest

from app.services.runner_service import RunnerService


@pytest.fixture
def runner():
    return RunnerService()


PROMPT = "## Como trabalhar\n1. Teste primeiro.\n\n---\n\nAdicione dividir(a, b)."


# --- O comando montado -------------------------------------------------------

def test_prompt_do_claude_nao_vai_na_linha_de_comando(runner, monkeypatch):
    """
    Argumento multilinha para um .cmd chega cortado. O prompt tem de sair da
    linha de comando inteiro, não ser escapado — não há escape que resolva.
    """
    monkeypatch.setattr(runner, "_claude_padrao", lambda: r"C:\npm\claude.cmd")

    cmd = runner.resolve_cli_command("SUBPROCESS_CLI", PROMPT, {"cli": "claude"})

    assert PROMPT not in cmd
    assert not any("Adicione dividir" in str(a) for a in cmd), cmd


def test_claude_continua_em_modo_nao_interativo(runner, monkeypatch):
    """Tirar o prompt não pode derrubar as flags que o fazem funcionar."""
    monkeypatch.setattr(runner, "_claude_padrao", lambda: r"C:\npm\claude.cmd")

    cmd = runner.resolve_cli_command("SUBPROCESS_CLI", PROMPT, {"cli": "claude"})

    assert "-p" in cmd
    assert "--permission-mode" in cmd


def test_runner_avisa_que_o_claude_quer_o_prompt_por_stdin(runner):
    assert runner.prompt_por_stdin({"cli": "claude"}) is True
    assert runner.prompt_por_stdin({"cli": "agy"}) is False


def test_agy_continua_recebendo_o_prompt_no_comando(runner, monkeypatch):
    """
    O agy é .exe, não passa pelo cmd.exe, e já funciona. Mexer nele seria
    desfazer uma correção que custou caro (`-p=<prompt>`).
    """
    monkeypatch.setattr(runner, "_agy_padrao", lambda: r"C:\agy\agy.exe")

    cmd = runner.resolve_cli_command("SUBPROCESS_CLI", PROMPT, {"cli": "agy"})

    assert any(a.startswith("-p=") and "Adicione dividir" in a for a in cmd), cmd


# --- O envoltório entrega o prompt -------------------------------------------

def test_envoltorio_entrega_o_prompt_inteiro_pela_entrada_padrao(tmp_path):
    """
    A prova de ponta a ponta sem gastar cota: o envoltório roda um programa que
    lê stdin e grava o que recebeu. Tem de chegar o texto COMPLETO, com as
    quebras de linha.
    """
    arquivo_prompt = tmp_path / "prompt.txt"
    arquivo_prompt.write_text(PROMPT, encoding="utf-8")
    recebido = tmp_path / "recebido.txt"
    run_json = tmp_path / "run.json"
    run_json.write_text("{}", encoding="utf-8")

    leitor = (
        "import sys,io;"
        "d=io.TextIOWrapper(sys.stdin.buffer,encoding='utf-8').read();"
        f"open(r'{recebido}','w',encoding='utf-8').write(d)"
    )

    rc = subprocess.run(
        [sys.executable, "-m", "app.services.run_wrapper",
         str(run_json), "--stdin", str(arquivo_prompt), "--",
         sys.executable, "-c", leitor],
        cwd=os.path.join(os.path.dirname(__file__), ".."),
        capture_output=True, text=True, timeout=60,
    ).returncode

    assert rc == 0
    assert recebido.read_text(encoding="utf-8") == PROMPT


def test_envoltorio_sem_stdin_continua_funcionando(tmp_path):
    """O agy não usa stdin — o envoltório não pode exigir o parâmetro."""
    run_json = tmp_path / "run.json"
    run_json.write_text("{}", encoding="utf-8")

    r = subprocess.run(
        [sys.executable, "-m", "app.services.run_wrapper",
         str(run_json), "--", sys.executable, "-c", "print('ok')"],
        cwd=os.path.join(os.path.dirname(__file__), ".."),
        capture_output=True, text=True, timeout=60,
    )

    assert r.returncode == 0
