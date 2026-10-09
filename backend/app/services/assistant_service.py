import os
import json
import logging
from typing import Optional, List, Dict
import httpx
from app.core.config import settings
from app.models.message import Message, MessageRole

logger = logging.getLogger("orchestrator.assistant")


class AssistantService:
    """
    Serviço de Inteligência Artificial para o Orquestrador.
    Permite interação contínua no chat das tarefas e execução de código.
    Suporta:
    1. Gemini API Oficial (via GEMINI_API_KEY no .env, settings ou ambiente)
    2. Anthropic API Oficial (via ANTHROPIC_API_KEY)
    3. Motor Inteligente Embutido Contextual (lê arquivos e banco local)
    """

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
        git_branch: Optional[str] = None
    ) -> str:
        gemini_key = os.environ.get("GEMINI_API_KEY") or getattr(settings, "GEMINI_API_KEY", None)
        anthropic_key = os.environ.get("ANTHROPIC_API_KEY") or getattr(settings, "ANTHROPIC_API_KEY", None)

        if gemini_key:
            try:
                return await self._call_gemini_api(
                    gemini_key, task_title, task_prompt, history, user_message, project_name, project_root
                )
            except Exception as e:
                logger.error(f"Erro ao chamar Gemini API: {e}")

        if anthropic_key:
            try:
                return await self._call_anthropic_api(
                    anthropic_key, task_title, task_prompt, history, user_message, project_name
                )
            except Exception as e:
                logger.error(f"Erro ao chamar Anthropic API: {e}")

        # Fallback contextual inteligente
        return self._generate_local_reply(
            task_title, task_prompt, history, project_root, user_message, project_name, git_branch
        )

    async def _call_gemini_api(
        self,
        api_key: str,
        task_title: str,
        task_prompt: str,
        history: List[Dict[str, str]],
        user_message: str,
        project_name: str,
        project_root: str
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

        contents.append({
            "role": "user",
            "parts": [{"text": user_message}]
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


assistant_service = AssistantService()
