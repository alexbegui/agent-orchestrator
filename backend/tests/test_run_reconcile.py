"""
Acompanhar o log em arquivo (substituto do pipe) e reconciliar ao subir:
o servidor reinicia e precisa descobrir o que realmente aconteceu com cada
tarefa que ele achava estar rodando.
"""
import os
import sys
import tempfile
import pytest

from app.services.runner_service import RunnerService
from app.services.run_registry import run_registry


@pytest.fixture
def worktree():
    with tempfile.TemporaryDirectory() as d:
        yield d


@pytest.mark.asyncio
async def test_acompanha_o_log_ate_o_agente_terminar(worktree):
    runner = RunnerService()
    cmd = [sys.executable, "-c", "print('alfa'); print('beta')"]
    runner.launch_detached("t1", cmd, cwd=worktree)

    linhas = []
    async for linha in runner.follow_log("t1", worktree, poll=0.05, timeout=30):
        linhas.append(linha.rstrip())

    assert "alfa" in linhas
    assert "beta" in linhas


@pytest.mark.asyncio
async def test_acompanhar_log_registra_o_codigo_de_saida(worktree):
    runner = RunnerService()
    runner.launch_detached("t2", [sys.executable, "-c", "raise SystemExit(3)"], cwd=worktree)

    async for _ in runner.follow_log("t2", worktree, poll=0.05, timeout=30):
        pass

    assert runner.get_last_returncode("t2") == 3
    assert run_registry.ler(worktree)["returncode"] == 3


def test_reconciliar_marca_concluida_quando_saiu_com_zero(worktree):
    runner = RunnerService()
    run_registry.registrar(worktree, task_id="t3", pid=999999, command=["x"])
    run_registry.concluir(worktree, returncode=0)

    assert runner.reconcile(worktree) == "REVIEW_READY"


def test_reconciliar_marca_falha_quando_saiu_com_erro(worktree):
    runner = RunnerService()
    run_registry.registrar(worktree, task_id="t4", pid=999999, command=["x"])
    run_registry.concluir(worktree, returncode=1)

    assert runner.reconcile(worktree) == "FAILED"


def test_reconciliar_mantem_rodando_quando_o_agente_esta_vivo(worktree):
    runner = RunnerService()
    run_registry.registrar(worktree, task_id="t5", pid=os.getpid(), command=["x"])

    assert runner.reconcile(worktree) == "RUNNING"


def test_reconciliar_marca_falha_quando_o_processo_sumiu_sem_rastro(worktree):
    """Registrado como rodando, mas o processo não existe e nada foi concluído."""
    runner = RunnerService()
    run_registry.registrar(worktree, task_id="t6", pid=999999, command=["x"])

    assert runner.reconcile(worktree) == "FAILED"


def test_reconciliar_sem_registro_nenhum_devolve_none(worktree):
    assert RunnerService().reconcile(worktree) is None
