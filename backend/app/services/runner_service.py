import os
import sys
import json
import shutil
import asyncio
import subprocess
import logging
from typing import AsyncGenerator, Optional, Union

from app.core.config import settings
from app.core.cli_paths import find_agy, find_agentapi
from app.services.run_registry import run_registry

logger = logging.getLogger("orchestrator.runner")


class RunnerService:
    """
    Executa comandos e CLIs locais de agentes (Claude Code, Antigravity/Gemini)
    com streaming de saída assíncrono e encerramento de processos sem órfãos no Windows.
    """

    # Modos aceitos pelo `claude --permission-mode`
    PERMISSION_MODES = {
        "acceptEdits", "auto", "bypassPermissions", "manual", "dontAsk", "plan"
    }

    def __init__(self):
        self.active_processes: dict[str, asyncio.subprocess.Process] = {}
        self.last_returncodes: dict[str, int] = {}
        self.stopped_tasks: set[str] = set()

    @staticmethod
    def _backend_dir() -> str:
        """Raiz do pacote `app`, para o envoltório conseguir se importar."""
        return os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))

    @staticmethod
    def _agy_padrao() -> Optional[str]:
        """Resolução completa do agy — ver app.core.cli_paths.find_agy."""
        return find_agy()

    @staticmethod
    def _agentapi_padrao() -> Optional[str]:
        return find_agentapi()

    def resolve_cli_command(self, runner_type: str, prompt: str, config: Optional[dict] = None) -> list[str]:
        cfg = config or {}
        cli_choice = (cfg.get("cli") or cfg.get("cli_cmd") or runner_type or "").lower()

        if "claude" in cli_choice:
            cmd = shutil.which("claude.cmd") or shutil.which("claude") or "claude"
            args = [cmd, "-p"]

            # `claude -p` é não-interativo: sem um modo explícito, tudo que
            # pediria aprovação é negado e o agente trava sem poder avisar.
            modo = cfg.get("permission_mode") or settings.CLAUDE_PERMISSION_MODE
            if modo not in self.PERMISSION_MODES:
                modo = "bypassPermissions"
            args += ["--permission-mode", modo]

            # A sessão nomeada permite que o chat retome, depois, o MESMO agente
            # que executou a tarefa — em vez de falar com um que nunca a viu.
            session_id = cfg.get("claude_session_id")
            if session_id:
                args += ["--session-id", session_id]

            args.append(prompt)
            return args
        elif any(k in cli_choice for k in ["agy", "gemini", "antigravity", "agentapi"]):
            # O `agy` é o CLI independente: não exige o IDE aberto nem token CSRF.
            agy = self._agy_padrao()
            if agy:
                args = [agy, "-p", "--dangerously-skip-permissions"]
                conv_id = cfg.get("antigravity_conversation_id")
                if conv_id:
                    args += ["--conversation", conv_id]
                if cfg.get("model"):
                    args += ["--model", cfg["model"]]
                args.append(prompt)
                return args

            # Fallback legado: o agentapi embutido no IDE, que só funciona com
            # o Antigravity aberto e com ANTIGRAVITY_LS_ADDRESS/CSRF_TOKEN no ambiente.
            agentapi = self._agentapi_padrao()
            if agentapi:
                return [agentapi, "new-conversation", "--model=flash", prompt]

            # Nada instalado: devolve o nome nu para o execute_command avisar direito.
            return ["agy", "-p", prompt]
        elif cfg.get("cli_cmd"):
            return [cfg["cli_cmd"], prompt]
        else:
            # Fallback caso não seja claude nem agy
            return ["cmd", "/c", prompt]

    def extract_conversation_id(self, output: str) -> Optional[str]:
        """
        Recupera o conversationId que o agentapi devolve ao criar uma conversa.
        Sem isso, a conversa da execução se perde e o chat fala com outro agente.
        O CLI costuma imprimir ruído antes do JSON, então varremos linha a linha.
        """
        for line in output.splitlines():
            line = line.strip()
            if not line.startswith("{"):
                continue
            try:
                data = json.loads(line)
            except ValueError:
                continue
            conv_id = (
                data.get("response", {})
                .get("newConversation", {})
                .get("conversationId")
            )
            if conv_id:
                return conv_id
        return None

    def launch_detached(self, task_id: str, command: list[str], cwd: str) -> Optional[int]:
        """
        Dispara o agente DESACOPLADO do servidor: ele sobrevive a reinícios do
        uvicorn e só termina sozinho ou quando o usuário mandar parar.

        Como não há mais pipe, a saída vai para .run/output.log e o vínculo
        passa a ser o run.json em disco (ver RunRegistry).
        """
        env = os.environ.copy()
        env["PYTHONIOENCODING"] = "utf-8"
        env["PYTHONUNBUFFERED"] = "1"
        self.stopped_tasks.discard(task_id)

        os.makedirs(run_registry.run_dir(cwd), exist_ok=True)
        log_file = open(run_registry.log_path(cwd), "w", encoding="utf-8", buffering=1)

        kwargs = {}
        if os.name == "nt":
            # Sem o novo grupo, um Ctrl+C no servidor derrubaria o agente junto.
            kwargs["creationflags"] = (
                subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP
            )
        else:
            kwargs["start_new_session"] = True

        # O agente roda sob um envoltório: como processo desacoplado não é nosso
        # filho, só ele mesmo pode registrar com que código terminou.
        envoltorio = [
            sys.executable, "-m", "app.services.run_wrapper",
            run_registry.run_json(cwd), "--", *command
        ]
        env["PYTHONPATH"] = os.pathsep.join(
            filter(None, [self._backend_dir(), env.get("PYTHONPATH", "")])
        )

        try:
            proc = subprocess.Popen(
                envoltorio,
                cwd=cwd,
                stdout=log_file,
                stderr=subprocess.STDOUT,
                stdin=subprocess.DEVNULL,
                env=env,
                **kwargs
            )
        except (FileNotFoundError, OSError) as e:
            log_file.write(f"[Erro no Runner] Falha ao iniciar '{command[0]}': {e}\n")
            log_file.close()
            self.last_returncodes[task_id] = 127
            return None
        finally:
            # O processo herdou o descritor; o servidor não precisa mais dele.
            try:
                log_file.close()
            except Exception:
                pass

        run_registry.registrar(cwd, task_id=task_id, pid=proc.pid, command=command)
        return proc.pid

    def stop_detached(self, cwd: str) -> bool:
        """
        Encerra o agente pela árvore de processos. Matar só o pai deixaria os
        filhos que o claude/agy criam rodando como órfãos.
        """
        if not run_registry.esta_vivo(cwd):
            return False

        dados = run_registry.ler(cwd) or {}
        pid = dados.get("pid")
        if not pid:
            return False

        try:
            import psutil
            pai = psutil.Process(pid)
            for filho in pai.children(recursive=True):
                try:
                    filho.kill()
                except psutil.Error:
                    pass
            pai.kill()
            pai.wait(timeout=10)
        except Exception as e:
            logger.warning(f"psutil não encerrou o PID {pid} ({e}); tentando taskkill")
            if os.name == "nt":
                subprocess.run(
                    ["taskkill", "/PID", str(pid), "/T", "/F"],
                    capture_output=True, timeout=30
                )
            else:
                try:
                    os.kill(pid, 9)
                except OSError:
                    return False

        run_registry.concluir(cwd, returncode=None)
        return True

    async def follow_log(
        self, task_id: str, cwd: str, poll: float = 0.3, timeout: float = 0.0
    ) -> AsyncGenerator[str, None]:
        """
        Acompanha o output.log do agente, no lugar do antigo pipe.

        Lê do início, então reabrir uma tarefa mostra todo o histórico — algo
        que o pipe não permitia. Termina quando o agente morre e não há mais
        nada novo para ler.
        """
        caminho = run_registry.log_path(cwd)
        inicio = asyncio.get_event_loop().time()
        posicao = 0
        vivo_antes = True

        while True:
            if os.path.exists(caminho):
                try:
                    with open(caminho, "r", encoding="utf-8", errors="replace") as f:
                        f.seek(posicao)
                        for linha in f:
                            yield linha
                        posicao = f.tell()
                except OSError as e:
                    logger.warning(f"Falha lendo {caminho}: {e}")

            if self.was_stopped(task_id):
                break

            vivo_agora = run_registry.esta_vivo(cwd)
            # Só encerra uma volta DEPOIS de morrer, para drenar o que ficou
            # escrito entre a última leitura e o fim do processo.
            if not vivo_agora and not vivo_antes:
                break
            vivo_antes = vivo_agora

            if timeout and (asyncio.get_event_loop().time() - inicio) > timeout:
                logger.warning(f"follow_log de {task_id} excedeu {timeout}s")
                break

            await asyncio.sleep(poll)

        rc = self._codigo_de_saida(cwd)
        if rc is not None:
            self.last_returncodes[task_id] = rc

    def _codigo_de_saida(self, cwd: str) -> Optional[int]:
        """
        Lê o código que o envoltório gravou ao terminar.

        Se não houver código e o processo não estiver vivo, ele morreu sem se
        despedir — matado, derrubado ou travado. Marcamos como falha (-1) em
        vez de inventar sucesso: dizer que deu certo sem saber é pior que
        admitir que não sabemos.
        """
        dados = run_registry.ler(cwd)
        if not dados:
            return None
        if dados.get("returncode") is not None:
            return dados["returncode"]

        if run_registry.esta_vivo(cwd):
            return None

        run_registry.concluir(cwd, returncode=-1)
        return -1

    def reconcile(self, cwd: str) -> Optional[str]:
        """
        Ao subir, descobre o que aconteceu com uma tarefa que ficou como RUNNING.
        Devolve o status que ela deveria ter, ou None se nunca houve execução.
        """
        dados = run_registry.ler(cwd)
        if not dados:
            return None

        if run_registry.esta_vivo(cwd):
            return "RUNNING"

        rc = dados.get("returncode")
        if rc is None:
            # Registrado como rodando, mas o processo não existe e nada marcou
            # a conclusão: morreu sem se despedir.
            run_registry.concluir(cwd, returncode=-1)
            return "FAILED"

        return "REVIEW_READY" if rc == 0 else "FAILED"

    async def execute_command(
        self,
        task_id: str,
        command: Union[list[str], str],
        cwd: str
    ) -> AsyncGenerator[str, None]:
        env = os.environ.copy()
        env["PYTHONIOENCODING"] = "utf-8"
        env["PYTHONUNBUFFERED"] = "1"
        self.stopped_tasks.discard(task_id)

        # Verifica se o binário existe antes de disparar no Windows
        if isinstance(command, list) and len(command) > 0:
            exe = command[0]
            if not shutil.which(exe) and not os.path.exists(exe):
                yield f"[Erro no Runner] O executável '{exe}' não foi encontrado no PATH do Windows.\n"
                yield "[Diagnóstico] Os CLIs externos (claude ou agy) precisam estar instalados globalmente.\n"
                yield "[Alternativa] Você pode utilizar a API Direta configurando GEMINI_API_KEY no arquivo .env!\n"
                self.last_returncodes[task_id] = 127
                return

        if isinstance(command, list):
            try:
                proc = await asyncio.create_subprocess_exec(
                    *command,
                    cwd=cwd,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.STDOUT,
                    env=env
                )
            except FileNotFoundError:
                yield f"[Erro no Runner] O executável '{command[0]}' não foi encontrado no sistema.\n"
                self.last_returncodes[task_id] = 127
                return
        else:
            try:
                proc = await asyncio.create_subprocess_shell(
                    command,
                    cwd=cwd,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.STDOUT,
                    env=env
                )
            except FileNotFoundError:
                yield f"[Erro no Runner] Falha ao invocar shell para o comando.\n"
                self.last_returncodes[task_id] = 127
                return


        self.active_processes[task_id] = proc

        try:
            while True:
                line_bytes = await proc.stdout.readline()
                if not line_bytes:
                    break
                line = line_bytes.decode("utf-8", errors="replace")
                yield line
            await proc.wait()
            self.last_returncodes[task_id] = proc.returncode
        except asyncio.CancelledError:
            self.stop_task(task_id)
            raise
        finally:
            self.active_processes.pop(task_id, None)

    def stop_task(self, task_id: str) -> bool:
        self.stopped_tasks.add(task_id)
        proc = self.active_processes.get(task_id)
        if not proc:
            return False

        try:
            if sys.platform == "win32":
                subprocess.run(
                    ["taskkill", "/F", "/T", "/PID", str(proc.pid)],
                    capture_output=True,
                    check=False
                )
            else:
                proc.kill()
        except Exception:
            pass

        self.active_processes.pop(task_id, None)
        return True

    def was_stopped(self, task_id: str) -> bool:
        return task_id in self.stopped_tasks

    def get_last_returncode(self, task_id: str) -> Optional[int]:
        return self.last_returncodes.get(task_id)
