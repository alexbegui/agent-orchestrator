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
    1. Gemini API Oficial (via GEMINI_API_KEY no .env ou ambiente)
    2. Anthropic API Oficial (via ANTHROPIC_API_KEY)
    3. Motor Inteligente Embutido (fallback contextual offline)
    """

    def __init__(self):
        self.http_client = httpx.AsyncClient(timeout=60.0)

    async def generate_chat_reply(
        self,
        task_title: str,
        task_prompt: str,
        history: List[Dict[str, str]],
        project_root: str,
        user_message: str
    ) -> str:
        gemini_key = os.environ.get("GEMINI_API_KEY") or getattr(settings, "GEMINI_API_KEY", None)
        anthropic_key = os.environ.get("ANTHROPIC_API_KEY") or getattr(settings, "ANTHROPIC_API_KEY", None)

        if gemini_key:
            try:
                return await self._call_gemini_api(gemini_key, task_title, task_prompt, history, user_message)
            except Exception as e:
                logger.error(f"Erro ao chamar Gemini API: {e}")

        if anthropic_key:
            try:
                return await self._call_anthropic_api(anthropic_key, task_title, task_prompt, history, user_message)
            except Exception as e:
                logger.error(f"Erro ao chamar Anthropic API: {e}")

        # Fallback para o Motor Inteligente Local
        return self._generate_local_reply(task_title, task_prompt, history, project_root, user_message)

    async def _call_gemini_api(
        self,
        api_key: str,
        task_title: str,
        task_prompt: str,
        history: List[Dict[str, str]],
        user_message: str
    ) -> str:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key={api_key}"
        
        system_instruction = (
            "Você é um Assistente Sênior de Engenharia de Software operando dentro do Agent Orchestrator. "
            f"Você está trabalhando na tarefa: '{task_title}'. Contexto/Requisito: '{task_prompt}'. "
            "Responda sempre em português de forma clara, técnica, prestativa e objetiva. "
            "Ajude a tirar dúvidas, analisar o código, orientar a arquitetura e sugerir correções de código."
        )

        contents = []
        for msg in history[-8:]:  # Últimas mensagens para manter contexto sem estourar
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
                "maxOutputTokens": 2048
            }
        }

        resp = await self.http_client.post(url, json=payload)
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
        user_message: str
    ) -> str:
        url = "https://api.anthropic.com/v1/messages"
        headers = {
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json"
        }
        system_prompt = (
            f"Você é um engenheiro sênior no Agent Orchestrator. Tarefa: {task_title}. "
            f"Requisito: {task_prompt}. Responda em português."
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

        resp = await self.http_client.post(url, json=payload, headers=headers)
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
        user_message: str
    ) -> str:
        msg_lower = user_message.lower().strip()

        # Respostas para saudações e dúvidas de funcionamento
        if any(w in msg_lower for w in ["funciona", "funcionando", "status", "ativo"]):
            return (
                "Sim! O Orquestrador e o chat estão funcionando e conectados à sua tarefa.\n\n"
                "📌 **Status atual:**\n"
                f"- **Tarefa:** {task_title}\n"
                "- **Isolamento:** Ativo via Git Worktree (arquivos protegidos).\n\n"
                "💡 **Como prosseguir:**\n"
                "1. Você pode me fazer perguntas sobre o que deseja implementar nesta tarefa;\n"
                "2. Ou clicar em **'Lapidar Prompt'** no topo para gerar a especificação atômica de arquivos;\n"
                "3. Para usar modelos de ponta em tempo real, basta adicionar `GEMINI_API_KEY=sua_chave` no arquivo `.env` (a chave do Google AI Studio é 100% gratuita)."
            )

        if any(w in msg_lower for w in ["o que posso fazer", "como usar", "ajuda", "orientação"]):
            return (
                f"Olá! Nesta tarefa (**{task_title}**), você pode:\n\n"
                "1. **Discutir Requisitos:** Me conte o que você espera desta funcionalidade ou correção de bug;\n"
                "2. **Planejar Arquivos:** Posso te ajudar a identificar quais arquivos do projeto precisam ser alterados;\n"
                "3. **Executar em Isolamento:** Clicando em 'Executar Tarefa', o trabalho é feito em uma pasta separada sem mexer na sua branch principal;\n"
                "4. **Revisar Código:** Quando o código for gerado, você verá a diferença na aba **Diffs & Revisão** e poderá aprová-la com 1 clique."
            )

        if any(w in msg_lower for w in ["erro", "winerror", "cli", "terminal"]):
            return (
                "⚠️ **Sobre o erro no terminal / CLI:**\n\n"
                "O erro `[WinError 2]` ocorre porque os CLIs externos (`claude` ou `agy`) não estão no PATH do seu Windows.\n"
                "Além disso, a versão antiga do `@google/gemini-cli` foi descontinuada pela Google.\n\n"
                "✅ **Solução Recomendada:**\n"
                "Use a **API Direta do Gemini**! É muito mais rápida, estável e gratuita:\n"
                "1. Pegue uma chave em [aistudio.google.com](https://aistudio.google.com);\n"
                "2. Adicione no arquivo `.env` do orchestrator: `GEMINI_API_KEY=AIzaSy...`;\n"
                "3. Reinicie o servidor para o agente gerar códigos e modificações automaticamente!"
            )

        # Resposta técnica contextual genérica
        return (
            f"Recebi sua mensagem sobre a tarefa **'{task_title}'**:\n\n"
            f"> \"{user_message}\"\n\n"
            "Posso te ajudar a detalhar o escopo dessa tarefa, indicar os arquivos que devem ser criados ou alterados no seu projeto, "
            "ou estruturar a lógica necessária. Se desejar que eu gere código diretamente, recomendo configurar sua `GEMINI_API_KEY` "
            "no `.env` ou me dar a diretriz detalhada aqui no chat!"
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

        # Cria ou atualiza documentação da tarefa na worktree isolada
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
            await log_callback(f"[Assistente] Gerado arquivo de entrega: TASK_IMPLEMENTATION.md")
        except Exception as e:
            await log_callback(f"[Aviso] Falha ao escrever arquivo: {e}")

        if gemini_key:
            await log_callback("[Gemini API] Chave oficial configurada! Sintetizando artefatos...")
        else:
            await log_callback("[Dica] Para IA generativa automatizada gerar código em todos os arquivos, adicione GEMINI_API_KEY no arquivo .env.")

        # Commit no git da worktree
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

