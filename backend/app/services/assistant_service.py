import os
import json
import uuid
import shutil
import asyncio
import logging
from typing import Optional, List, Dict, Any
import httpx
from app.core.config import settings
from app.core.cli_paths import find_agy
from app.models.message import Message, MessageRole

logger = logging.getLogger("orchestrator.assistant")

# Teto para uma resposta do CLI no chat. Sem ele, `communicate()` esperava para
# sempre: um CLI que não retorna deixava a marca `chat_busy_since` presa, e o
# usuário ficava até 15 minutos (CHAT_BUSY_TIMEOUT) sem conseguir perguntar
# nada — o sintoma "fica só processando". Estourado o teto, o processo é morto
# e a cascata tenta o próximo motor, em vez de o chat emudecer.
CHAT_CLI_TIMEOUT = 600.0

# Refino é uma chamada curta que precisa voltar JSON. Não é conversa: se não
# respondeu em 2 minutos, respondeu errado.
REFINO_TIMEOUT = 120.0


# Abaixo do mínimo do modelo a marca de cache não cacheia nada e NÃO dá erro —
# fica `cache_creation_input_tokens: 0` em silêncio. No Opus 5.5 o mínimo é 512
# tokens; a ~4 caracteres por token, 2048 caracteres. Marcamos com folga para
# não gastar escrita de cache (1,25x) num prefixo que nunca vai ser lido.
MIN_CHARS_PARA_CACHE = 2400


def montar_blocos_cacheaveis(prefixo: str, pedido: str) -> List[Dict[str, Any]]:
    """
    Separa o prompt em "o que não muda" e "o que muda", nessa ordem.

    Caching é casamento de PREFIXO: um byte diferente no começo invalida tudo
    depois. Então a economia não vem de ligar uma opção, vem da ordem — o que
    repete entre refinos do mesmo projeto (instruções, conhecimento, árvore de
    arquivos) vem primeiro e leva a marca; o pedido do usuário, que muda a cada
    tarefa, vem depois e fica de fora.

    A ordem inversa não dá erro nenhum: só nunca acerta o cache.
    """
    if not prefixo:
        return [{"type": "text", "text": pedido}]

    bloco = {"type": "text", "text": prefixo}
    if len(prefixo) >= MIN_CHARS_PARA_CACHE:
        bloco["cache_control"] = {"type": "ephemeral"}
    return [bloco, {"type": "text", "text": pedido}]


class MotorIndisponivel(Exception):
    """
    Nenhum motor de IA real respondeu.

    Existe para que a falha seja alta e visível. A versão antiga do refino era
    regex e nunca falhava — sempre saía uma spec, de aparência igual à de uma
    spec de verdade. Aprovar aquilo achando que veio da IA é pior que ficar
    sem spec, então aqui a ausência de motor é erro, nunca um fallback.
    """


async def _comunicar_com_teto(proc, rotulo: str):
    """
    Espera a saída do processo, mas desiste no teto e mata a árvore.

    Devolve (stdout, stderr) ou None quando estourou — quem chama trata o None
    como "este motor não respondeu" e cai para o próximo.
    """
    try:
        return await asyncio.wait_for(proc.communicate(), timeout=CHAT_CLI_TIMEOUT)
    except asyncio.TimeoutError:
        logger.error(
            f"{rotulo} não respondeu em {CHAT_CLI_TIMEOUT}s; encerrando o processo"
        )
        try:
            proc.kill()
        except Exception:
            pass
        return None


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
        self._claude_sessions: Dict[str, str] = {}

    def _find_claude_cmd(self) -> Optional[str]:
        """Localiza o binário do Claude Code CLI no Windows."""
        for name in ["claude.cmd", "claude", "claude.exe"]:
            found = shutil.which(name)
            if found:
                return found
        return None

    def _find_agy_cmd(self) -> Optional[str]:
        """
        Localiza o CLI independente do Antigravity. Diferente do agentapi, ele
        não exige o IDE aberto nem ANTIGRAVITY_LS_ADDRESS/CSRF_TOKEN.
        Resolução completa (PATH + local do instalador) em app.core.cli_paths.
        """
        return find_agy()

    async def _call_agy_cli(
        self,
        task_id: Optional[str],
        task_title: str,
        task_prompt: str,
        user_message: str,
        project_name: str,
        project_root: str,
        conversation_id: Optional[str] = None,
        worktree_path: Optional[str] = None
    ) -> Optional[str]:
        """Conversa pelo agy, retomando a conversa por ID quando já existe."""
        agy_cmd = self._find_agy_cmd()
        if not agy_cmd:
            return None

        cwd = worktree_path if (worktree_path and os.path.isdir(worktree_path)) else project_root
        conv_id = conversation_id or (self._task_conversations.get(task_id) if task_id else None)

        # O agy lê o argumento seguinte a -p como o prompt; com a flag ali, ele
        # respondia à flag e descartava a pergunta. O prompt vai anexado.
        if conv_id:
            cmd = [agy_cmd, f"-p={user_message}", "--dangerously-skip-permissions",
                   "--conversation", conv_id]
        else:
            abertura = (
                f"Você é o Engenheiro de Software Sênior do Agent Orchestrator "
                f"trabalhando no projeto '{project_name}'. "
                f"Tarefa: '{task_title}'. Requisito: '{task_prompt}'.\n\n"
                f"Mensagem do usuário: {user_message}"
            )
            cmd = [agy_cmd, f"-p={abertura}", "--dangerously-skip-permissions"]

        proc = await asyncio.create_subprocess_exec(
            *cmd, cwd=cwd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        resultado = await _comunicar_com_teto(proc, "agy")
        if resultado is None:
            return None
        stdout, stderr = resultado

        if proc.returncode != 0:
            logger.error(
                f"agy retornou {proc.returncode}: "
                f"{stderr.decode('utf-8', errors='replace')[:500]}"
            )
            return None

        return stdout.decode("utf-8", errors="replace").strip() or None

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

    async def completar_json(self, prompt: str, prefixo: str = "", max_tokens: int = 4000) -> str:
        """
        Uma chamada curta de API direta que devolve texto (esperado: JSON).

        Usa API direta — não os CLIs — de propósito: o refino precisa de
        resposta estruturada em segundos, e CLI responde em prosa e demora.
        Anthropic primeiro, Gemini como segunda opção.

        `prefixo` é a parte estável do prompt (instruções, conhecimento do
        projeto, árvore de arquivos) e vai antes, marcada para cache; `prompt`
        é a parte que muda a cada tarefa. Ver `montar_blocos_cacheaveis`.

        NÃO cai para o motor local embutido: ele não lê o projeto nem escreve
        código, e a spec que ele produziria seria genérica — exatamente o
        defeito do regex que este caminho veio substituir. Sem motor real,
        levanta MotorIndisponivel e a tarefa não avança.
        """
        anthropic_key = os.environ.get("ANTHROPIC_API_KEY") or getattr(settings, "ANTHROPIC_API_KEY", None)
        gemini_key = os.environ.get("GEMINI_API_KEY") or getattr(settings, "GEMINI_API_KEY", None)

        if not anthropic_key and not gemini_key:
            raise MotorIndisponivel(
                "Nenhuma chave de API configurada. Informe ANTHROPIC_API_KEY ou "
                "GEMINI_API_KEY em Ajustes para lapidar o prompt."
            )

        falhas: List[str] = []

        if anthropic_key:
            try:
                return await self._json_anthropic(anthropic_key, prompt, prefixo, max_tokens)
            except Exception as e:
                logger.error(f"Refino via Anthropic falhou: {e}")
                falhas.append(f"Anthropic: {self._motivo(e)}")

        if gemini_key:
            try:
                # O Gemini não tem equivalente a cache_control explícito; o
                # prefixo entra como texto normal, na mesma ordem.
                return await self._json_gemini(gemini_key, f"{prefixo}\n\n{prompt}".strip(), max_tokens)
            except Exception as e:
                logger.error(f"Refino via Gemini falhou: {e}")
                falhas.append(f"Gemini: {self._motivo(e)}")

        raise MotorIndisponivel("Nenhum motor respondeu — " + "; ".join(falhas))

    @staticmethod
    def _motivo(e: Exception) -> str:
        """
        O motivo que chega na tela. Precisa carregar o status HTTP: "401" diz
        ao usuário que a chave está errada; "falhou" o manda adivinhar.
        """
        resp = getattr(e, "response", None)
        if resp is not None and getattr(resp, "status_code", None):
            return f"HTTP {resp.status_code} — {str(e)[:200]}"
        return str(e)[:200] or e.__class__.__name__

    async def _json_anthropic(
        self, api_key: str, prompt: str, prefixo: str, max_tokens: int
    ) -> str:
        payload = {
            "model": "claude-opus-5-5",
            "max_tokens": max_tokens,
            "system": (
                "Você responde EXCLUSIVAMENTE com um objeto JSON válido, sem "
                "cercas de código e sem texto antes ou depois."
            ),
            "messages": [
                {"role": "user", "content": montar_blocos_cacheaveis(prefixo, prompt)}
            ],
        }
        async with httpx.AsyncClient(
            proxy=os.environ.get("HTTPS_PROXY") or os.environ.get("HTTP_PROXY"),
            timeout=REFINO_TIMEOUT,
        ) as client:
            resp = await client.post(
                "https://api.anthropic.com/v1/messages",
                json=payload,
                headers={
                    "x-api-key": api_key,
                    "anthropic-version": "2023-06-01",
                    "content-type": "application/json",
                },
            )
            resp.raise_for_status()
            data = resp.json()

        # Cache que não acerta falha em SILÊNCIO — não há erro, só
        # `cache_read_input_tokens: 0` para sempre. Sem registrar isso, não há
        # como distinguir "está economizando" de "a ordem do prompt quebrou o
        # prefixo". Este log é a única evidência de que o caching funciona.
        uso = data.get("usage", {})
        logger.info(
            "Refino via Anthropic — tokens: %s novos, %s escritos no cache, %s lidos do cache",
            uso.get("input_tokens", "?"),
            uso.get("cache_creation_input_tokens", "?"),
            uso.get("cache_read_input_tokens", "?"),
        )

        # A resposta pode trazer blocos de raciocínio antes do texto; só o
        # bloco de texto interessa.
        for bloco in data.get("content", []):
            if bloco.get("type") == "text" and bloco.get("text", "").strip():
                return bloco["text"].strip()
        raise MotorIndisponivel("A Anthropic respondeu sem conteúdo de texto.")

    async def _json_gemini(self, api_key: str, prompt: str, max_tokens: int) -> str:
        url = (
            "https://generativelanguage.googleapis.com/v1beta/models/"
            f"gemini-2.0-flash:generateContent?key={api_key}"
        )
        payload = {
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {
                "maxOutputTokens": max_tokens,
                # Pedir JSON ao modelo em vez de torcer para ele obedecer o texto.
                "responseMimeType": "application/json",
            },
        }
        async with httpx.AsyncClient(
            proxy=os.environ.get("HTTPS_PROXY") or os.environ.get("HTTP_PROXY"),
            timeout=REFINO_TIMEOUT,
        ) as client:
            resp = await client.post(url, json=payload)
            resp.raise_for_status()
            data = resp.json()

        for cand in data.get("candidates", []):
            for parte in cand.get("content", {}).get("parts", []):
                if parte.get("text", "").strip():
                    return parte["text"].strip()
        raise MotorIndisponivel("O Gemini respondeu sem conteúdo de texto.")

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
        attachments: Optional[List[dict]] = None,
        cli_preference: Optional[str] = None,
        worktree_path: Optional[str] = None
    ) -> str:
        # O agente navega durante o trabalho (entra na pasta do docker, por
        # exemplo) e passa a salvar lá. Lembrar a cada mensagem é barato.
        if worktree_path:
            from app.services.artifact_service import artifact_service
            user_message = f"{user_message}\n{artifact_service.instrucao_de_local(worktree_path)}"

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

        # 0. CLI escolhido na criação da tarefa tem prioridade sobre a cascata.
        #    Se ele falhar, seguimos para a cascata abaixo em vez de deixar o chat mudo.
        choice = (cli_preference or "").lower()
        if any(k in choice for k in ("agy", "antigravity", "gemini")):
            try:
                reply = await self._call_agy_cli(
                    task_id=task_id, task_title=task_title, task_prompt=task_prompt,
                    user_message=effective_message, project_name=project_name,
                    project_root=project_root, conversation_id=conversation_id,
                    worktree_path=worktree_path
                )
                if reply:
                    return reply
            except Exception as e:
                logger.error(f"Erro ao chamar o agy (escolha da tarefa): {e}")

        if "claude" in choice:
            try:
                reply = await self._call_claude_cli(
                    task_id=task_id, task_title=task_title, task_prompt=task_prompt,
                    user_message=effective_message, project_name=project_name,
                    project_root=project_root, worktree_path=worktree_path
                )
                if reply:
                    return reply
            except Exception as e:
                logger.error(f"Erro ao chamar Claude CLI: {e}")

        # 1. agy — CLI independente do Antigravity (não precisa do IDE aberto)
        try:
            reply = await self._call_agy_cli(
                task_id=task_id, task_title=task_title, task_prompt=task_prompt,
                user_message=effective_message, project_name=project_name,
                project_root=project_root, conversation_id=conversation_id,
                worktree_path=worktree_path
            )
            if reply:
                return reply
        except Exception as e:
            logger.error(f"Erro ao chamar o agy: {e}")

        # 2. agentapi — legado, só funciona com o IDE Antigravity aberto
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

    async def _call_claude_cli(
        self,
        task_id: Optional[str],
        task_title: str,
        task_prompt: str,
        user_message: str,
        project_name: str,
        project_root: str,
        session_id: Optional[str] = None,
        worktree_path: Optional[str] = None
    ) -> Optional[str]:
        """
        Conversa pelo Claude Code CLI local, mantendo a continuidade por sessão.
        A primeira mensagem cria a sessão com um UUID nosso (--session-id);
        as seguintes retomam a mesma sessão (--resume), sem reenviar o histórico.

        Trabalha no worktree da tarefa quando ele existe: o agente pode escrever
        arquivos, e tudo precisa virar diff a ser aprovado — não alteração direta
        no projeto real. Sem worktree (tarefa não executada), cai no projeto.
        """
        claude_cmd = self._find_claude_cmd()
        if not claude_cmd:
            return None

        cwd = worktree_path if (worktree_path and os.path.isdir(worktree_path)) else project_root

        known = session_id or (self._claude_sessions.get(task_id) if task_id else None)

        # O chat também é não-interativo: sem o modo explícito, qualquer pedido
        # de permissão é negado e o agente trava ao escrever arquivo ou rodar
        # comandos — mesmo com a execução (▶ Rodar) já configurada.
        modo = getattr(settings, "CLAUDE_PERMISSION_MODE", None) or "bypassPermissions"
        base = [claude_cmd, "-p", "--permission-mode", modo]

        if known:
            cmd = base + ["--resume", known, user_message]
        else:
            new_session = str(uuid.uuid4())
            prompt = (
                f"Você é o Engenheiro de Software Sênior do Agent Orchestrator "
                f"trabalhando no projeto '{project_name}'. "
                f"Tarefa: '{task_title}'. Requisito: '{task_prompt}'.\n\n"
                f"Mensagem do usuário: {user_message}"
            )
            cmd = base + ["--session-id", new_session, prompt]
            known = new_session

        proc = await asyncio.create_subprocess_exec(
            *cmd,
            cwd=cwd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        resultado = await _comunicar_com_teto(proc, "Claude CLI")
        if resultado is None:
            return None
        stdout, stderr = resultado

        if proc.returncode != 0:
            logger.error(
                f"Claude CLI retornou {proc.returncode}: "
                f"{stderr.decode('utf-8', errors='replace')[:500]}"
            )
            return None

        if task_id:
            self._claude_sessions[task_id] = known

        return stdout.decode("utf-8", errors="replace").strip() or None

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
        """
        O Assistente Integrado NÃO implementa código.

        Antes, esta função escrevia um TASK_IMPLEMENTATION.md com o prompt do
        usuário de volta, commitava, e declarava "[Sucesso] Tarefa pronta!" —
        sem ter feito nada. O usuário abria o diff e encontrava só esse arquivo.

        Agora ela diz a verdade. Declarar entrega sem entregar é pior do que
        não entregar: manda o usuário caçar o motivo num diff vazio.
        """
        await log_callback(f"[Assistente Integrado] Tarefa: {task_title}")
        await log_callback(f"[Worktree] Pasta isolada criada em: {worktree_path}")
        await log_callback("")
        await log_callback(
            "[Atenção] O Assistente Integrado não implementa código — ele só "
            "conversa. Nenhum arquivo foi criado ou alterado."
        )
        await log_callback("")
        await log_callback("Para o agente escrever código de verdade nesta tarefa:")
        await log_callback(
            "  1. Crie a tarefa escolhendo 'Claude Code CLI' ou 'Antigravity CLI (agy)'"
        )
        await log_callback(
            "  2. Ou converse na aba Chat — lá o agente trabalha no worktree isolado"
        )

        return False

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


