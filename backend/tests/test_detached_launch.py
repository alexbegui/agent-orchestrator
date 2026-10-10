"""
Lançamento desacoplado e parada por árvore de processos.
Estes testes rodam processos de verdade (python curto), porque o
desacoplamento não se verifica com mock.
"""
import os
import sys
import tempfile
import time
import pytest

from app.services.runner_service import RunnerService
from app.services.run_registry import run_registry


@pytest.fixture
def worktree():
    with tempfile.TemporaryDirectory() as d:
        yield d


def test_lanca_desacoplado_e_registra_pid(worktree):
    runner = RunnerService()
    cmd = [sys.executable, "-c", "import time; print('ola'); time.sleep(30)"]

    pid = runner.launch_detached("t1", cmd, cwd=worktree)

    assert pid and pid > 0
    dados = run_registry.ler(worktree)
    assert dados["pid"] == pid
    assert dados["command"] == cmd

    runner.stop_detached(worktree)


def test_saida_do_agente_vai_para_o_arquivo_de_log(worktree):
    runner = RunnerService()
    cmd = [sys.executable, "-c", "print('linha um'); print('linha dois')"]

    runner.launch_detached("t2", cmd, cwd=worktree)

    log = run_registry.log_path(worktree)
    for _ in range(50):
        if os.path.exists(log) and "linha dois" in open(log, encoding="utf-8").read():
            break
        time.sleep(0.1)

    conteudo = open(log, encoding="utf-8").read()
    assert "linha um" in conteudo
    assert "linha dois" in conteudo


def test_parar_encerra_o_processo(worktree):
    runner = RunnerService()
    cmd = [sys.executable, "-c", "import time; time.sleep(60)"]

    runner.launch_detached("t3", cmd, cwd=worktree)
    assert run_registry.esta_vivo(worktree) is True

    assert runner.stop_detached(worktree) is True

    for _ in range(50):
        if not run_registry.esta_vivo(worktree):
            break
        time.sleep(0.1)
    assert run_registry.esta_vivo(worktree) is False


def test_parar_tarefa_que_nao_esta_rodando_nao_quebra(worktree):
    runner = RunnerService()
    assert runner.stop_detached(worktree) is False


def test_agente_sobrevive_a_perda_da_referencia(worktree):
    """
    O ponto central: o orquestrador esquece o processo (como num reinício)
    e o agente continua vivo, reencontrável pelo run.json.
    """
    runner = RunnerService()
    cmd = [sys.executable, "-c", "import time; time.sleep(30)"]
    runner.launch_detached("t4", cmd, cwd=worktree)

    # Simula o reinício: um RunnerService novo, sem nada em memória.
    outro_runner = RunnerService()
    assert outro_runner.active_processes == {}
    assert run_registry.esta_vivo(worktree) is True

    assert outro_runner.stop_detached(worktree) is True
