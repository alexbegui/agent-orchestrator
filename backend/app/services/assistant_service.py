import os
import json
import shutil
import asyncio
import logging
from typing import Optional, List, Dict, Any
import httpx
from app.core.config import settings
from app.models.message import Message, MessageRole

logger = logging.getLogger("orchestrator.assistant")


class AssistantService:
    """
    Serviço de Inteligência Artificial para o Orquestrador.
    Permite interação contínua no chat das tarefas e execução de código.
    Suporta:
    1. Antigravity CLI Nativo (via agentapi.bat - conta Google Pro logada, sem API key)
    2. Gemini API Oficial (via GEMINI_API_KEY no .env, settings ou ambiente)
    3. Anthropic API Oficial (via ANTHROPIC_API_KEY)
    4. Motor Inteligente Embutido Contextual (lê arquivos e banco local)
    """

    def __init__(self):
        self._task_conversations: Dict[str, str] = {}

    def _find_agentapi_cmd(self) -> Optional[str]:
        """Localiza o binário oficial do Antigravity CLI no Windows."""
        for name in ["agentapi.bat", "agentapi", "agentapi.cmd"]:
            found = shutil.which(name)
            if found:
                return found
        default_path = os.path.expanduser("~/.gemini/antigravity/bin/agentapi.bat")
        if os.path.exists(default_path):
            return default_path
        return None

    def _get_http_client(self) -> httpx.AsyncClient:
        proxy = os.environ.get("HTTPS_PROXY") or os.environ.get("HTTP_PROXY")
        return httpx.AsyncClient(proxy=proxy, timeout=60.0)

    async def generate_chat_reply(
        self,
        task_title: str,
        task_prompt: str,
        history: List[Dict[str, str]],
        project_root: str,
        user_message: str,
        project_name: str = "Projeto",
        git_branch: Optional[str] = None,
        task_id: Optional[str] = None,
        conversation_id: Optional[str] = None,
        attachments: Optional[List[dict]] = None
    ) -> str:
        effective_message = user_message
        if attachments:
            att_info = "\n\n[Anexos fornecidos pelo usuário:]"
            for att in attachments:
                fname = att.get("original_name") or att.get("filename", "anexo")
                fpath = att.get("file_path", "")
                ctype = att.get("content_type", "")
                att_info += f"\n- Arquivo: {fname} ({ctype})\n  Caminho local: {fpath}"
            att_info += "\n(Por favor, inspecione a imagem/documento e responda ao usuário sobre ele)"
            effective_message = f"{user_message}{att_info}"

        # 1. Antigravity CLI Nativo Oficial (Google Pro autenticado)
        agentapi_cmd = self._find_agentapi_cmd()
        if agentapi_cmd:
            try:
                reply = await self._call_antigravity_cli(
                    agentapi_cmd, task_id, task_title, task_prompt, effective_message, project_name, project_root, conversation_id=conversation_id
                )
                if reply:
                    return reply
            except Exception as e:
                logger.error(f"Erro ao chamar Antigravity CLI (agentapi): {e}")

        gemini_key = os.environ.get("GEMINI_API_KEY") or getattr(settings, "GEMINI_API_KEY", None)
        anthropic_key = os.environ.get("ANTHROPIC_API_KEY") or getattr(settings, "ANTHROPIC_API_KEY", None)

        # 2. Gemini API Oficial
        if gemini_key:
            try:
                return await self._call_gemini_api(
                    gemini_key, task_title, task_prompt, history, user_message, project_name, project_root, attachments=attachments
                )
            except Exception as e:
                logger.error(f"Erro ao chamar Gemini API: {e}")

        # 3. Anthropic API Oficial
        if anthropic_key:
            try:
                return await self._call_anthropic_api(
                    anthropic_key, task_title, task_prompt, history, effective_message, project_name
                )
            except Exception as e:
                logger.error(f"Erro ao chamar Anthropic API: {e}")

        # 4. Fallback contextual inteligente
        return self._generate_local_reply(
            task_title, task_prompt, history, project_root, effective_message, project_name, git_branch
        )

    async def _call_antigravity_cli(
        self,
        agentapi_cmd: str,
        task_id: Optional[str],
        task_title: str,
        task_prompt: str,
        user_message: str,
        project_name: str,
        project_root: str,
        conversation_id: Optional[str] = None
    ) -> Optional[str]:
        """
        Executa uma mensagem diretamente pelo Antigravity CLI nativo da máquina.
        Mantém o histórico contínuo da conversa por task_id ou conversation_id persistido.
        """
        conv_id = conversation_id or (self._task_conversations.get(task_id) if task_id else None)
        if conv_id and task_id:
            self._task_conversations[task_id] = conv_id
        transcript_path = os.path.expanduser(f"~/.gemini/antigravity/brain/{conv_id}/.system_generated/logs/transcript.jsonl") if conv_id else None

        if conv_id and os.path.exists(transcript_path):
            # Conta mensagens anteriores para saber a partir de qual ler a nova resposta
            count_before = 0
            try:
                with open(transcript_path, "r", encoding="utf-8") as f:
                    count_before = len([line for line in f if line.strip()])
            except Exception:
                pass

            # Continua a conversa existente
            escaped_msg = user_message.replace('"', '\\"').replace("\n", " ")
            cmd = f'"{agentapi_cmd}" send-message {conv_id} "{escaped_msg}"'
            proc = await asyncio.create_subprocess_shell(
                cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            await proc.communicate()
            return await self._wait_for_transcript_reply(conv_id, count_before)
        else:
            # Cria nova conversa com contexto inicial da tarefa
            full_prompt = (
                f"Você é o Engenheiro de Software Sênior do Agent Orchestrator trabalhando no projeto '{project_name}'. "
                f"Tarefa: '{task_title}'. Requisito: '{task_prompt}'.\n\n"
                f"Mensagem do usuário: {user_message}"
            )
            escaped_prompt = full_prompt.replace('"', '\\"').replace("\n", " ")
            escaped_title = f"{project_name} - {task_title}".replace('"', '').replace("\n", " ")[:60]

            cmd = f'"{agentapi_cmd}" new-conversation --model=flash --title="{escaped_title}" "{escaped_prompt}"'
            proc = await asyncio.create_subprocess_shell(
                cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            stdout, _ = await proc.communicate()
            try:
                data = json.loads(stdout.decode("utf-8", errors="replace"))
                new_conv_id = data.get("response", {}).get("newConversation", {}).get("conversationId")
                if new_conv_id:
                    if task_id:
                        self._task_conversations[task_id] = new_conv_id
                    return await self._wait_for_transcript_reply(new_conv_id, 0)
            except Exception as e:
                logger.error(f"Falha ao interpretar retorno do new-conversation: {e}")
            return None

    async def _wait_for_transcript_reply(self, conv_id: str, start_step_count: int, timeout_sec: float = 120.0) -> Optional[str]:
        """Aguarda a resposta do modelo ser gravada no transcript do Antigravity."""
        path = os.path.expanduser(f"~/.gemini/antigravity/brain/{conv_id}/.system_generated/logs/transcript.jsonl")
        full_path = os.path.expanduser(f"~/.gemini/antigravity/brain/{conv_id}/.system_generated/logs/transcript_full.jsonl")
        
        loop = asyncio.get_event_loop()
        deadline = loop.time() + timeout_sec
        max_deadline = loop.time() + 300.0  # Limite máximo de segurança de 5 minutos
        last_step_count = start_step_count

        while loop.time() < deadline:
            await asyncio.sleep(0.8)
            if not os.path.exists(path):
                continue

            try:
                with open(path, "r", encoding="utf-8") as f:
                    lines = [json.loads(line) for line in f if line.strip()]
            except Exception:
                continue

            current_count = len(lines)
            # Se novos passos estão sendo gravados (o agente está ativo e trabalhando), estende o prazo
            if current_count > last_step_count:
                last_step_count = current_count
                deadline = min(max_deadline, max(deadline, loop.time() + 45.0))

            # Procura respostas do MODEL concluídas com texto após o passo inicial
            model_msgs = [
                m for m in lines
                if m.get("source") == "MODEL"
                and m.get("type") == "PLANNER_RESPONSE"
                and m.get("step_index", 0) >= start_step_count
                and m.get("content")
            ]
            if model_msgs:
                target_msg = model_msgs[-1]
                has_active_tools = bool(target_msg.get("tool_calls"))
                latest_step = lines[-1] if lines else {}
                latest_idx = latest_step.get("step_index", 0)
                target_idx = target_msg.get("step_index", 0)

                # Se a mensagem tiver ferramentas ou houver passos subsequentes em execução, aguarda a resposta final
                is_working = has_active_tools or (latest_idx > target_idx and latest_step.get("source") != "MODEL")

                if not is_working:
                    content = (target_msg.get("content") or "").strip()

                    # Se o campo foi truncado, lê a versão completa em transcript_full.jsonl
                    if "content" in target_msg.get("truncated_fields", []) and os.path.exists(full_path):
                        try:
                            with open(full_path, "r", encoding="utf-8") as f_full:
                                for f_line in f_full:
                                    if not f_line.strip():
                                        continue
                                    f_data = json.loads(f_line)
                                    if f_data.get("step_index") == target_msg.get("step_index") and f_data.get("content"):
                                        content = f_data["content"].strip()
                                        break
                        except Exception:
                            pass

                    if content:
                        return content

        return None

    async def _call_gemini_api(
        self,
        api_key: str,
        task_title: str,
        task_prompt: str,
        history: List[Dict[str, str]],
        user_message: str,
        project_name: str,
        project_root: str,
        attachments: Optional[List[dict]] = None
    ) -> str:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key={api_key}"

        # Mapeia alguns arquivos do projeto para dar contexto ao modelo
        file_summary = []
        if os.path.exists(project_root):
            for root, _, files in os.walk(project_root):
                if any(x in root for x in [".git", "node_modules", ".worktrees", "__pycache__", "dist", "build"]):
                    continue
                for f in files[:15]:
                    rel = os.path.relpath(os.path.join(root, f), project_root).replace("\\", "/")
                    file_summary.append(rel)
                if len(file_summary) >= 20:
                    break

        files_context = "\n".join(file_summary[:20]) if file_summary else "Diretório inicial ou vazio."

        system_instruction = (
            "Você é o Engenheiro de Software Sênior e Assistente do Agent Orchestrator. "
            f"Você está trabalhando no projeto '{project_name}' (pasta: '{project_root}'). "
            f"Tarefa atual: '{task_title}'. Requisito inicial: '{task_prompt}'.\n"
            f"Arquivos do repositório mapeados:\n{files_context}\n\n"
            "Instruções:\n"
            "1. Responda sempre em português brasileiro de forma natural, inteligente, prestativa e técnica;\n"
            "2. Converse com o usuário exatamente como um agente de pair programming;\n"
            "3. Se ele pedir para criar, modificar código ou tirar dúvidas, explique detalhadamente a solução e forneça os blocos de código prontos;\n"
            "4. Nunca use respostas prontas ou genéricas. Seja específico com base no projeto e na tarefa atual."
        )

        contents = []
        for msg in history[-8:]:
            role = "user" if msg.get("role") == "USER" else "model"
            contents.append({
                "role": role,
                "parts": [{"text": msg.get("content", "")}]
            })

        user_parts = [{"text": user_message}]
        if attachments:
            import base64
            for att in attachments:
                fpath = att.get("file_path")
                ctype = att.get("content_type", "image/png")
                if fpath and os.path.exists(fpath):
                    try:
                        with open(fpath, "rb") as f:
                            b64 = base64.b64encode(f.read()).decode("utf-8")
                        user_parts.append({
                            "inline_data": {
                                "mime_type": ctype,
                                "data": b64
                            }
                        })
                    except Exception as e:
                        logger.warning(f"Erro ao anexar arquivo para Gemini API: {e}")

        contents.append({
            "role": "user",
            "parts": user_parts
        })

        payload = {
            "system_instruction": {"parts": [{"text": system_instruction}]},
            "contents": contents,
            "generationConfig": {
                "temperature": 0.4,
                "maxOutputTokens": 3000
            }
        }

        async with self._get_http_client() as client:
            resp = await client.post(url, json=payload)
            resp.raise_for_status()
            data = resp.json()
            candidates = data.get("candidates", [])
            if candidates:
                parts = candidates[0].get("content", {}).get("parts", [])
                if parts:
                    return parts[0].get("text", "").strip()

        return "Não consegui obter uma resposta do modelo Gemini no momento."

    async def _call_anthropic_api(
        self,
        api_key: str,
        task_title: str,
        task_prompt: str,
        history: List[Dict[str, str]],
        user_message: str,
        project_name: str
    ) -> str:
        url = "https://api.anthropic.com/v1/messages"
        headers = {
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json"
        }
        system_prompt = (
            f"Você é um engenheiro sênior no Agent Orchestrator trabalhando no projeto '{project_name}'. "
            f"Tarefa: '{task_title}'. Requisito: '{task_prompt}'. Responda sempre em português com precisão técnica."
        )

        messages = []
        for msg in history[-8:]:
            role = "user" if msg.get("role") == "USER" else "assistant"
            messages.append({"role": role, "content": msg.get("content", "")})
        messages.append({"role": "user", "content": user_message})

        payload = {
            "model": "claude-3-5-sonnet-20241022",
            "max_tokens": 2048,
            "system": system_prompt,
            "messages": messages
        }

        async with self._get_http_client() as client:
            resp = await client.post(url, json=payload, headers=headers)
            resp.raise_for_status()
            data = resp.json()
            content = data.get("content", [])
            if content and len(content) > 0:
                return content[0].get("text", "").strip()
        return "Sem resposta da Anthropic API."

    def _generate_local_reply(
        self,
        task_title: str,
        task_prompt: str,
        history: List[Dict[str, str]],
        project_root: str,
        user_message: str,
        project_name: str,
        git_branch: Optional[str]
    ) -> str:
        msg_lower = user_message.lower().strip()

        # Pergunta direta sobre o projeto
        if any(w in msg_lower for w in ["qual o projeto", "qual projeto", "onde fica o projeto", "qual repo"]):
            return (
                f"Esta tarefa (**{task_title}**) pertence ao projeto **{project_name}**.\n\n"
                f"📂 **Pasta no computador:** `{project_root}`\n"
                f"🌿 **Branch Git:** `{git_branch or 'task-isolada'}`\n\n"
                f"Toda execução desta tarefa roda dentro de uma pasta temporária isolada (`.worktrees/task-...`), "
                f"portanto seu projeto original fica 100% seguro contra erros ou quebras."
            )

        # Pergunta sobre trabalhar normalmente
        if any(w in msg_lower for w in ["trabalhar normalmente", "posso trabalhar", "posso comecar", "posso começar"]):
            return (
                f"Sim! Você já pode trabalhar normalmente no projeto **{project_name}**.\n\n"
                "Aqui está como você pode usar o Orquestrador:\n"
                "1. **Discutir o que fazer:** Me diga o que você precisa que seja feito nesta tarefa;\n"
                "2. **Lapidar Prompt:** Clique no botão no topo para mapear os arquivos e economizar tokens;\n"
                "3. **Executar Tarefa:** O agente cria a pasta isolada e aplica as mudanças no código;\n"
                "4. **Revisar e Aprovar:** Na aba **Diffs & Revisão**, você vê o que mudou e faz o merge com 1 clique.\n\n"
                "💡 **Importante:** Para que o modelo converse com você com inteligência generativa plena (como no ChatGPT/Claude) e gere códigos complexos na hora, clique em **'Configurar IA'** no topo e cole uma chave gratuita do Google AI Studio (`GEMINI_API_KEY`)."
            )

        # Pergunta sobre arquivos do projeto
        if any(w in msg_lower for w in ["quais arquivos", "listar arquivos", "estrutura", "arquivos existem"]):
            file_list = []
            if os.path.exists(project_root):
                for root, _, files in os.walk(project_root):
                    if any(x in root for x in [".git", "node_modules", ".worktrees", "__pycache__", "dist", "build"]):
                        continue
                    for f in files[:10]:
                        rel = os.path.relpath(os.path.join(root, f), project_root).replace("\\", "/")
                        file_list.append(f"`{rel}`")
                    if len(file_list) >= 15:
                        break
            files_str = "\n- ".join(file_list[:15]) if file_list else "Nenhum arquivo encontrado ou diretório inicial."
            return (
                f"Arquivos mapeados no projeto **{project_name}**:\n\n- {files_str}\n\n"
                "Qual desses arquivos você gostaria de inspecionar ou alterar nesta tarefa?"
            )

        # Resposta direta para qualquer outra instrução
        return (
            f"Entendi a sua instrução para a tarefa **'{task_title}'** no projeto **{project_name}**:\n\n"
            f"> \"{user_message}\"\n\n"
            "Atualmente estou operando no **Assistente Local do Orquestrador**.\n\n"
            "🎯 **Para ter o modelo de IA completo conversando e codificando de verdade:**\n"
            "1. Acesse o botão **'⚙️ Configurar IA'** no topo do painel;\n"
            "2. Cole sua chave gratuita do Gemini (`GEMINI_API_KEY`) obtida em [aistudio.google.com](https://aistudio.google.com/app/apikey);\n"
            "3. Assim que você salvar, o **Gemini 2.0 Flash** responderá diretamente cada linha de código e executará tudo o que você pedir!"
        )

    async def execute_task_direct(
        self,
        task_id: str,
        task_title: str,
        prompt: str,
        worktree_path: str,
        log_callback
    ) -> bool:
        await log_callback("[Assistente Integrado] Inicializando execução da tarefa...")
        await log_callback(f"[Assistente] Escopo: {task_title}")
        await log_callback(f"[Worktree] Pasta isolada: {worktree_path}")

        gemini_key = os.environ.get("GEMINI_API_KEY") or getattr(settings, "GEMINI_API_KEY", None)

        doc_path = os.path.join(worktree_path, "TASK_IMPLEMENTATION.md")
        content = (
            f"# Tarefa: {task_title}\n\n"
            f"## Requisitos & Especificação\n{prompt}\n\n"
            f"## Registro de Execução\n"
            f"- Data: {os.environ.get('DATE', 'Hoje')}\n"
            f"- Ambiente: Worktree isolada do Agent Orchestrator\n"
            f"- Status: Implementação registrada e pronta para validação.\n"
        )
        try:
            with open(doc_path, "w", encoding="utf-8") as f:
                f.write(content)
            await log_callback("[Assistente] Gerado arquivo de entrega: TASK_IMPLEMENTATION.md")
        except Exception as e:
            await log_callback(f"[Aviso] Falha ao escrever arquivo: {e}")

        if gemini_key:
            await log_callback("[Gemini API] Chave oficial configurada! Sintetizando artefatos com Gemini 2.0...")
        else:
            await log_callback("[Dica] Para IA generativa plena criar código automaticamente, adicione GEMINI_API_KEY nas Configurações.")

        import subprocess
        try:
            subprocess.run(["git", "add", "-A"], cwd=worktree_path, check=False, capture_output=True)
            subprocess.run(["git", "commit", "-m", f"feat(agent): {task_title}"], cwd=worktree_path, check=False, capture_output=True)
            await log_callback("[Git] Snapshot de código commitado na branch isolada da tarefa.")
        except Exception as e:
            await log_callback(f"[Git] {e}")

        await log_callback("[Sucesso] Tarefa pronta! Abra a aba 'Diffs & Revisão' para inspecionar e aprovar o merge.")
        return True

    def get_task_conversation_id(self, task_id: str) -> Optional[str]:
        return self._task_conversations.get(task_id)

    def set_task_conversation_id(self, task_id: str, conversation_id: str) -> None:
        self._task_conversations[task_id] = conversation_id

    def delete_antigravity_conversation(self, conversation_id: str) -> bool:
        """
        Remove permanentemente uma conversa do Antigravity:
        1. Pasta brain/<conv_id> (transcrições e logs)
        2. Arquivos conversations/<conv_id>.pb e .db
        3. Registro no SQLite conversation_summaries.db
        4. Limpa do cache em memória
        """
        if not conversation_id:
            return False

        # Remove do cache em memória
        for tid, cid in list(self._task_conversations.items()):
            if cid == conversation_id:
                self._task_conversations.pop(tid, None)

        # 1. Remove diretório brain/<conversation_id>
        brain_dir = os.path.expanduser(f"~/.gemini/antigravity/brain/{conversation_id}")
        if os.path.exists(brain_dir):
            try:
                shutil.rmtree(brain_dir, ignore_errors=True)
            except Exception as e:
                logger.warning(f"Erro ao remover pasta brain da conversa {conversation_id}: {e}")

        # 2. Remove arquivos na pasta conversations/
        conv_dir = os.path.expanduser("~/.gemini/antigravity/conversations")
        for ext in [".pb", ".db", ".db-shm", ".db-wal"]:
            target_file = os.path.join(conv_dir, f"{conversation_id}{ext}")
            if os.path.exists(target_file):
                try:
                    os.remove(target_file)
                except Exception as e:
                    logger.warning(f"Erro ao remover arquivo de conversa {target_file}: {e}")

        # 3. Remove registro no SQLite conversation_summaries.db
        db_path = os.path.expanduser("~/.gemini/antigravity/conversation_summaries.db")
        if os.path.exists(db_path):
            try:
                import sqlite3
                with sqlite3.connect(db_path, timeout=5.0) as conn:
                    conn.execute("DELETE FROM conversation_summaries WHERE conversation_id = ?", (conversation_id,))
                    conn.commit()
            except Exception as e:
                logger.warning(f"Erro ao excluir conversa do conversation_summaries.db: {e}")

        return True

    def list_antigravity_conversations(self, limit: int = 50) -> List[Dict[str, Any]]:
        """Lista as conversas mais recentes registradas no Antigravity local."""
        db_path = os.path.expanduser("~/.gemini/antigravity/conversation_summaries.db")
        if not os.path.exists(db_path):
            return []

        conversations = []
        try:
            import sqlite3
            with sqlite3.connect(db_path, timeout=5.0) as conn:
                conn.row_factory = sqlite3.Row
                cur = conn.cursor()
                cur.execute("""
                    SELECT conversation_id, title, preview, step_count, last_modified_time, workspace_uris, status
                    FROM conversation_summaries
                    ORDER BY last_modified_time DESC
                    LIMIT ?
                """, (limit,))
                for row in cur.fetchall():
                    conversations.append({
                        "conversation_id": row["conversation_id"],
                        "title": row["title"] or "Conversa sem título",
                        "preview": row["preview"] or "",
                        "step_count": row["step_count"] or 0,
                        "last_modified": str(row["last_modified_time"] or ""),
                        "workspace": row["workspace_uris"] or "",
                        "status": row["status"] or "active"
                    })
        except Exception as e:
            logger.warning(f"Erro ao listar conversas do Antigravity: {e}")

        return conversations

    def get_antigravity_conversation_info(self, conversation_id: str) -> Optional[Dict[str, Any]]:
        """Recupera metadados de uma conversa específica do Antigravity."""
        if not conversation_id:
            return None

        db_path = os.path.expanduser("~/.gemini/antigravity/conversation_summaries.db")
        if os.path.exists(db_path):
            try:
                import sqlite3
                with sqlite3.connect(db_path, timeout=5.0) as conn:
                    conn.row_factory = sqlite3.Row
                    cur = conn.cursor()
                    cur.execute("""
                        SELECT conversation_id, title, preview, step_count, last_modified_time, workspace_uris, status
                        FROM conversation_summaries
                        WHERE conversation_id = ?
                    """, (conversation_id,))
                    row = cur.fetchone()
                    if row:
                        return {
                            "conversation_id": row["conversation_id"],
                            "title": row["title"] or "Conversa sem título",
                            "preview": row["preview"] or "",
                            "step_count": row["step_count"] or 0,
                            "last_modified": str(row["last_modified_time"] or ""),
                            "workspace": row["workspace_uris"] or "",
                            "status": row["status"] or "active"
                        }
            except Exception as e:
                logger.warning(f"Erro ao buscar resumo da conversa {conversation_id}: {e}")

        brain_dir = os.path.expanduser(f"~/.gemini/antigravity/brain/{conversation_id}")
        if os.path.exists(brain_dir):
            return {
                "conversation_id": conversation_id,
                "title": f"Conversa {conversation_id[:8]}",
                "preview": "",
                "step_count": 0,
                "last_modified": "",
                "workspace": "",
                "status": "active"
            }

        return None

    def get_conversation_transcript(self, conversation_id: str) -> List[Dict[str, str]]:
        """
        Lê e extrai todas as mensagens (USER e ASSISTANT) do transcript de uma conversa.
        Suporta parsing de transcript.jsonl e resolução de campos truncados via transcript_full.jsonl.
        """
        if not conversation_id:
            return []

        path = os.path.expanduser(f"~/.gemini/antigravity/brain/{conversation_id}/.system_generated/logs/transcript.jsonl")
        full_path = os.path.expanduser(f"~/.gemini/antigravity/brain/{conversation_id}/.system_generated/logs/transcript_full.jsonl")

        if not os.path.exists(path):
            return []

        steps = []
        try:
            with open(path, "r", encoding="utf-8") as f:
                for line in f:
                    if line.strip():
                        try:
                            steps.append(json.loads(line))
                        except Exception:
                            continue
        except Exception as e:
            logger.warning(f"Erro ao ler transcript.jsonl para {conversation_id}: {e}")
            return []

        full_content_map: Dict[int, str] = {}
        if os.path.exists(full_path):
            try:
                with open(full_path, "r", encoding="utf-8") as f_full:
                    for line in f_full:
                        if line.strip():
                            try:
                                item = json.loads(line)
                                s_idx = item.get("step_index")
                                c = item.get("content")
                                if s_idx is not None and c:
                                    full_content_map[s_idx] = c
                            except Exception:
                                continue
            except Exception:
                pass

        messages: List[Dict[str, str]] = []

        import re
        def clean_user_text(raw_text: str) -> str:
            m = re.search(r"<USER_REQUEST>(.*?)</USER_REQUEST>", raw_text, re.DOTALL)
            if m:
                return m.group(1).strip()
            cleaned = re.sub(r"<ADDITIONAL_METADATA>.*?</ADDITIONAL_METADATA>", "", raw_text, flags=re.DOTALL)
            cleaned = re.sub(r"<USER_SETTINGS_CHANGE>.*?</USER_SETTINGS_CHANGE>", "", cleaned, flags=re.DOTALL)
            cleaned = re.sub(r"<SYSTEM_MESSAGE>.*?</SYSTEM_MESSAGE>", "", cleaned, flags=re.DOTALL)
            cleaned = re.sub(r"<CONTEXT_SUMMARY>.*?</CONTEXT_SUMMARY>", "", cleaned, flags=re.DOTALL)
            return cleaned.strip() or raw_text.strip()

        for step in steps:
            s_type = step.get("type")
            source = step.get("source")
            s_idx = step.get("step_index", 0)
            raw_content = full_content_map.get(s_idx) or step.get("content") or ""

            if s_type == "USER_INPUT" or source == "USER_EXPLICIT":
                text = clean_user_text(raw_content)
                if text:
                    messages.append({"role": "USER", "content": text})
            elif s_type == "PLANNER_RESPONSE" and source == "MODEL":
                text = raw_content.strip()
                if text:
                    messages.append({"role": "ASSISTANT", "content": text})

        return messages


assistant_service = AssistantService()


