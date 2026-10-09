import os
import sys
import shutil
import asyncio
import subprocess
from typing import AsyncGenerator, Optional, Union


class RunnerService:
    """
    Executa comandos e CLIs locais de agentes (Claude Code, Antigravity/Gemini)
    com streaming de saída assíncrono e encerramento de processos sem órfãos no Windows.
    """

    def __init__(self):
        self.active_processes: dict[str, asyncio.subprocess.Process] = {}
        self.last_returncodes: dict[str, int] = {}
        self.stopped_tasks: set[str] = set()

    def resolve_cli_command(self, runner_type: str, prompt: str, config: Optional[dict] = None) -> list[str]:
        cfg = config or {}
        cli_choice = (cfg.get("cli") or cfg.get("cli_cmd") or runner_type or "").lower()

        if "claude" in cli_choice:
            cmd = shutil.which("claude.cmd") or shutil.which("claude") or "claude"
            return [cmd, "-p", prompt]
        elif "agy" in cli_choice or "gemini" in cli_choice:
            cmd = shutil.which("agy.exe") or shutil.which("agy") or "agy"
            return [cmd, prompt]
        elif cfg.get("cli_cmd"):
            return [cfg["cli_cmd"], prompt]
        else:
            # Fallback caso não seja claude nem agy
            return ["cmd", "/c", prompt]

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
