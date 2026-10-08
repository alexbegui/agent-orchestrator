import os
import sys
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

    def resolve_cli_command(self, runner_type: str, prompt: str, config: Optional[dict] = None) -> list[str]:
        cfg = config or {}
        custom_cmd = cfg.get("cli_cmd")

        if custom_cmd:
            return [custom_cmd, prompt]

        runner_lower = runner_type.lower()
        if "claude" in runner_lower:
            # Claude Code CLI usa -p para prompts diretos
            return ["claude", "-p", prompt]
        elif "agy" in runner_lower or "gemini" in runner_lower:
            # Antigravity CLI
            return ["agy", prompt]
        else:
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

        if isinstance(command, list):
            proc = await asyncio.create_subprocess_exec(
                *command,
                cwd=cwd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.STDOUT,
                env=env
            )
        else:
            proc = await asyncio.create_subprocess_shell(
                command,
                cwd=cwd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.STDOUT,
                env=env
            )

        self.active_processes[task_id] = proc

        try:
            while True:
                line_bytes = await proc.stdout.readline()
                if not line_bytes:
                    break
                line = line_bytes.decode("utf-8", errors="replace")
                yield line
            await proc.wait()
        except asyncio.CancelledError:
            self.stop_task(task_id)
            raise
        finally:
            self.active_processes.pop(task_id, None)

    def stop_task(self, task_id: str) -> bool:
        proc = self.active_processes.get(task_id)
        if not proc:
            return False

        try:
            if sys.platform == "win32":
                # Encerra toda a árvore de processos no Windows
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
