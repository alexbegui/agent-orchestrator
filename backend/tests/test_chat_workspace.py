"""
O agente do chat agora pode escrever arquivos (bypassPermissions).
Por isso ele precisa trabalhar no worktree isolado da tarefa — não na
pasta real do projeto — para que tudo vire diff a ser aprovado.
"""
import os
import tempfile
import pytest
from unittest.mock import patch

from app.services.assistant_service import AssistantService


def _fake_exec_capturando(capturados):
    async def fake_exec(*cmd, **kwargs):
        capturados.append({"cmd": list(cmd), "cwd": kwargs.get("cwd")})

        class _Proc:
            returncode = 0

            async def communicate(self):
                return (b"ok", b"")

        return _Proc()
    return fake_exec


@pytest.mark.asyncio
async def test_chat_roda_no_worktree_quando_existe():
    service = AssistantService()
    capturados = []

    with tempfile.TemporaryDirectory() as projeto:
        worktree = os.path.join(projeto, ".worktrees", "task-1")
        os.makedirs(worktree)

        with patch("asyncio.create_subprocess_exec", new=_fake_exec_capturando(capturados)), \
             patch("shutil.which", return_value="C:/fake/claude.cmd"):
            await service._call_claude_cli(
                task_id="task-1", task_title="T", task_prompt="P",
                user_message="implemente", project_name="Proj",
                project_root=projeto, worktree_path=worktree,
            )

        assert capturados[0]["cwd"] == worktree


@pytest.mark.asyncio
async def test_chat_cai_no_projeto_quando_nao_ha_worktree():
    """Tarefa ainda não executada não tem worktree — conversar sobre o projeto é válido."""
    service = AssistantService()
    capturados = []

    with tempfile.TemporaryDirectory() as projeto:
        with patch("asyncio.create_subprocess_exec", new=_fake_exec_capturando(capturados)), \
             patch("shutil.which", return_value="C:/fake/claude.cmd"):
            await service._call_claude_cli(
                task_id="task-2", task_title="T", task_prompt="P",
                user_message="o que você acha?", project_name="Proj",
                project_root=projeto, worktree_path=None,
            )

        assert capturados[0]["cwd"] == projeto


@pytest.mark.asyncio
async def test_worktree_apagado_nao_quebra_a_conversa():
    """Se a worktree foi removida (merge ou limpeza), não dá para usar como cwd."""
    service = AssistantService()
    capturados = []

    with tempfile.TemporaryDirectory() as projeto:
        with patch("asyncio.create_subprocess_exec", new=_fake_exec_capturando(capturados)), \
             patch("shutil.which", return_value="C:/fake/claude.cmd"):
            await service._call_claude_cli(
                task_id="task-3", task_title="T", task_prompt="P",
                user_message="e agora?", project_name="Proj",
                project_root=projeto,
                worktree_path=os.path.join(projeto, ".worktrees", "ja-removida"),
            )

        assert capturados[0]["cwd"] == projeto
