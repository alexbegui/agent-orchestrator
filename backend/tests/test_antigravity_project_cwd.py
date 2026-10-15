import os
import sqlite3
import pytest
from unittest.mock import patch, AsyncMock, MagicMock
from app.services.assistant_service import AssistantService

@pytest.mark.asyncio
async def test_call_antigravity_cli_passes_project_cwd(tmp_path):
    """Verifica que o agentapi roda no diretório do projeto para não herdar a pasta do orquestrador."""
    service = AssistantService()
    project_dir = str(tmp_path / "MeuProjeto")
    os.makedirs(project_dir, exist_ok=True)

    fake_proc = AsyncMock()
    fake_proc.communicate.return_value = (
        b'{"response": {"newConversation": {"conversationId": "conv-123"}}}',
        b""
    )
    fake_proc.returncode = 0

    with patch("asyncio.create_subprocess_shell", return_value=fake_proc) as mock_sub, \
         patch.object(service, "_wait_for_transcript_reply", return_value="Resposta do agente"), \
         patch.object(service, "ensure_conversation_workspace") as mock_ensure:
        
        reply = await service._call_antigravity_cli(
            agentapi_cmd="agentapi.bat",
            task_id="task-1",
            task_title="Ajuste de Tela",
            task_prompt="Ajustar",
            user_message="Olá",
            project_name="MeuProjeto",
            project_root=project_dir,
            conversation_id=None
        )

        assert mock_sub.called
        # Confirma que cwd foi passado e aponta para project_dir
        kwargs = mock_sub.call_args.kwargs
        assert kwargs.get("cwd") == project_dir
        assert mock_ensure.called
        assert mock_ensure.call_args[0] == ("conv-123", project_dir)

def test_ensure_conversation_workspace_updates_db(tmp_path):
    """Verifica que ensure_conversation_workspace grava workspace_uris e project_id no banco."""
    service = AssistantService()
    fake_db = str(tmp_path / "conversation_summaries.db")
    
    conn = sqlite3.connect(fake_db)
    conn.execute("""
        CREATE TABLE conversation_summaries (
            conversation_id TEXT PRIMARY KEY,
            title TEXT,
            preview TEXT,
            step_count INTEGER,
            last_modified_time TEXT,
            workspace_uris TEXT,
            status TEXT,
            source TEXT,
            project_id TEXT,
            agent_name TEXT,
            parent_conversation_id TEXT,
            nesting_depth INTEGER,
            battle_id TEXT,
            winning_conversation_id TEXT,
            not_fully_idle INTEGER,
            killed INTEGER,
            last_user_input_time TEXT,
            last_user_input_step_index INTEGER,
            app_data_dir TEXT,
            raw_summary BLOB,
            group_id TEXT
        )
    """)
    # Insere conversa prévia do projeto para ter um project_id já existente
    conn.execute("""
        INSERT INTO conversation_summaries (conversation_id, workspace_uris, project_id)
        VALUES ('conv-existing', '["file:///d%3A/Projetos/Patrimonio"]', 'proj-patrimonio-id')
    """)
    # Insere conversa nova sem workspace
    conn.execute("""
        INSERT INTO conversation_summaries (conversation_id, workspace_uris, project_id)
        VALUES ('conv-new', '', 'outside-of-project')
    """)
    conn.commit()
    conn.close()

    with patch("os.path.expanduser", return_value=fake_db):
        service.ensure_conversation_workspace("conv-new", r"D:\Projetos\Patrimonio")

    conn = sqlite3.connect(fake_db)
    row = conn.execute("SELECT workspace_uris, project_id FROM conversation_summaries WHERE conversation_id = 'conv-new'").fetchone()
    conn.close()

    assert row[0] == '["file:///d%3A/Projetos/Patrimonio"]'
    assert row[1] == 'proj-patrimonio-id'
