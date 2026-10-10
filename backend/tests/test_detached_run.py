"""
O agente roda desacoplado do servidor: matar o uvicorn não pode matar o agente.
O vínculo passa a ser o run.json em disco (pid + início), não um objeto em memória.
"""
import json
import os
import tempfile
import time
import pytest

from app.services.run_registry import RunRegistry


@pytest.fixture
def pasta():
    with tempfile.TemporaryDirectory() as d:
        yield d


def test_registra_execucao_em_disco(pasta):
    reg = RunRegistry()
    reg.registrar(pasta, task_id="t1", pid=4242, command=["claude", "-p", "x"])

    dados = json.loads(open(reg.run_json(pasta), encoding="utf-8").read())
    assert dados["pid"] == 4242
    assert dados["command"] == ["claude", "-p", "x"]
    assert dados["started_at"]
    assert dados["finished_at"] is None


def test_le_execucao_registrada(pasta):
    reg = RunRegistry()
    reg.registrar(pasta, task_id="t1", pid=4242, command=["claude"])
    lido = reg.ler(pasta)
    assert lido["pid"] == 4242


def test_ler_pasta_sem_execucao_devolve_none(pasta):
    assert RunRegistry().ler(pasta) is None


def test_marca_conclusao_com_codigo_de_saida(pasta):
    reg = RunRegistry()
    reg.registrar(pasta, task_id="t1", pid=4242, command=["claude"])
    reg.concluir(pasta, returncode=0)

    lido = reg.ler(pasta)
    assert lido["returncode"] == 0
    assert lido["finished_at"]


def test_processo_do_proprio_teste_e_reconhecido_como_vivo(pasta):
    """Usa o próprio PID do pytest, que é garantidamente um processo vivo."""
    reg = RunRegistry()
    reg.registrar(pasta, task_id="t1", pid=os.getpid(), command=["x"])
    assert reg.esta_vivo(pasta) is True


def test_pid_reciclado_nao_e_confundido_com_o_agente(pasta):
    """
    O Windows reaproveita PIDs. Só o número não basta: se o horário de início
    do processo não bater com o registrado, não é mais o nosso agente —
    e matá-lo seria matar um programa alheio do usuário.
    """
    reg = RunRegistry()
    reg.registrar(pasta, task_id="t1", pid=os.getpid(), command=["x"])

    dados = reg.ler(pasta)
    dados["process_started_at"] = 1.0  # bem antes do processo real
    with open(reg.run_json(pasta), "w", encoding="utf-8") as f:
        json.dump(dados, f)

    assert reg.esta_vivo(pasta) is False


def test_pid_inexistente_nao_esta_vivo(pasta):
    reg = RunRegistry()
    reg.registrar(pasta, task_id="t1", pid=999999, command=["x"])
    assert reg.esta_vivo(pasta) is False


def test_execucao_ja_concluida_nao_conta_como_viva(pasta):
    reg = RunRegistry()
    reg.registrar(pasta, task_id="t1", pid=os.getpid(), command=["x"])
    reg.concluir(pasta, returncode=0)
    assert reg.esta_vivo(pasta) is False


def test_caminho_do_log_fica_dentro_da_pasta_de_execucao(pasta):
    reg = RunRegistry()
    caminho = reg.log_path(pasta)
    assert caminho.endswith("output.log")
    assert ".run" in caminho
