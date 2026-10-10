"""
O "Assistente Integrado" não implementa código.

Ele escrevia um TASK_IMPLEMENTATION.md em toda tarefa contendo apenas o
prompt do usuário de volta e a string literal "Hoje" como data — e commitava.
Era o padrão "um .md por tarefa" que entulha o repositório sem informar nada.

Removido o arquivo, sobra uma função que commita o vazio e declara sucesso.
Declarar entrega sem ter entregue é pior que não entregar: o usuário vai
revisar um diff vazio sem entender por quê.
"""
import os
import tempfile
import pytest

from app.services.assistant_service import AssistantService


@pytest.fixture
def worktree():
    with tempfile.TemporaryDirectory() as d:
        yield d


async def _executar(worktree):
    logs = []

    async def log(msg):
        logs.append(msg)

    ok = await AssistantService().execute_task_direct(
        task_id="t1", task_title="Trocar o banco",
        prompt="migrar para postgres", worktree_path=worktree, log_callback=log,
    )
    return ok, logs


@pytest.mark.asyncio
async def test_nao_escreve_mais_o_arquivo_inutil(worktree):
    await _executar(worktree)
    assert not os.path.exists(os.path.join(worktree, "TASK_IMPLEMENTATION.md"))


@pytest.mark.asyncio
async def test_nao_declara_sucesso_sem_ter_implementado(worktree):
    ok, _ = await _executar(worktree)
    assert ok is False


@pytest.mark.asyncio
async def test_explica_ao_usuario_o_que_aconteceu_e_o_que_fazer(worktree):
    """Falhar em silêncio mandaria o usuário caçar o motivo no diff vazio."""
    _, logs = await _executar(worktree)
    texto = " ".join(logs).lower()

    assert "não implementa" in texto or "nao implementa" in texto
    assert "claude" in texto and "agy" in texto


@pytest.mark.asyncio
async def test_nao_commita_nada_no_worktree(worktree):
    """Commit vazio com mensagem de feature polui o histórico do projeto."""
    _, logs = await _executar(worktree)
    assert not any("commit" in l.lower() for l in logs)
