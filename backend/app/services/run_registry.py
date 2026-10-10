import os
import json
import time
import logging
from typing import Optional, List, Dict, Any

logger = logging.getLogger("orchestrator.run")

RUN_DIR = ".run"
RUN_JSON = "run.json"
OUTPUT_LOG = "output.log"


class RunRegistry:
    """
    Vínculo em disco entre o orquestrador e um agente desacoplado.

    O agente não é mais filho do uvicorn — reiniciar o servidor não o mata.
    Em troca, a referência não pode viver em memória: o `run.json` guarda o PID
    e o instante de início, e o `output.log` guarda tudo que o agente escreveu.
    """

    def run_dir(self, worktree_path: str) -> str:
        return os.path.join(worktree_path, RUN_DIR)

    def run_json(self, worktree_path: str) -> str:
        return os.path.join(self.run_dir(worktree_path), RUN_JSON)

    def log_path(self, worktree_path: str) -> str:
        return os.path.join(self.run_dir(worktree_path), OUTPUT_LOG)

    def _ignorar_no_git(self, worktree_path: str) -> None:
        """
        O .run/ vive dentro do worktree, então apareceria no diff que o usuário
        revisa. Um .gitignore local resolve sem tocar no projeto do usuário.
        """
        try:
            caminho = os.path.join(self.run_dir(worktree_path), ".gitignore")
            if not os.path.exists(caminho):
                with open(caminho, "w", encoding="utf-8") as f:
                    f.write("# Metadados de execução do orquestrador\n*\n")
        except OSError as e:
            logger.warning(f"Não foi possível isolar {RUN_DIR} do git: {e}")

    def registrar(
        self, worktree_path: str, task_id: str, pid: int, command: List[str]
    ) -> Dict[str, Any]:
        os.makedirs(self.run_dir(worktree_path), exist_ok=True)
        self._ignorar_no_git(worktree_path)
        dados = {
            "task_id": task_id,
            "pid": pid,
            # Guardado junto do PID porque o Windows reaproveita números:
            # sem o instante de início não dá para saber se o PID ainda é nosso.
            "process_started_at": self._inicio_do_processo(pid),
            "started_at": time.time(),
            "command": command,
            "finished_at": None,
            "returncode": None,
        }
        self._gravar(worktree_path, dados)
        return dados

    def ler(self, worktree_path: str) -> Optional[Dict[str, Any]]:
        caminho = self.run_json(worktree_path)
        if not os.path.exists(caminho):
            return None
        try:
            with open(caminho, "r", encoding="utf-8") as f:
                return json.load(f)
        except (ValueError, OSError) as e:
            logger.warning(f"run.json ilegível em {caminho}: {e}")
            return None

    def concluir(self, worktree_path: str, returncode: Optional[int]) -> None:
        dados = self.ler(worktree_path)
        if not dados:
            return
        dados["finished_at"] = time.time()
        dados["returncode"] = returncode
        self._gravar(worktree_path, dados)

    def esta_vivo(self, worktree_path: str) -> bool:
        """
        Verdadeiro só quando o processo existe E é o mesmo que registramos.
        Confiar apenas no PID mataria um programa alheio se o número tiver
        sido reciclado pelo sistema.
        """
        dados = self.ler(worktree_path)
        if not dados or dados.get("finished_at") is not None:
            return False

        pid = dados.get("pid")
        if not pid:
            return False

        inicio_atual = self._inicio_do_processo(pid)
        if inicio_atual is None:
            return False

        inicio_registrado = dados.get("process_started_at")
        if inicio_registrado is None:
            # Sem referência para comparar, a existência do PID é tudo que temos.
            return True

        # Tolerância de 1s: a leitura do início tem granularidade grosseira.
        return abs(inicio_atual - inicio_registrado) < 1.0

    @staticmethod
    def _inicio_do_processo(pid: int) -> Optional[float]:
        """Instante de criação do processo, ou None se ele não existe."""
        try:
            import psutil  # type: ignore
            return psutil.Process(pid).create_time()
        except ImportError:
            pass
        except Exception:
            return None

        # Sem psutil, no Windows, consulta o próprio sistema.
        if os.name == "nt":
            import subprocess
            try:
                res = subprocess.run(
                    ["wmic", "process", "where", f"ProcessId={pid}", "get", "CreationDate"],
                    capture_output=True, text=True, timeout=10
                )
                linhas = [l.strip() for l in res.stdout.splitlines() if l.strip()]
                if len(linhas) < 2 or not linhas[1][:14].isdigit():
                    return None
                from datetime import datetime
                return datetime.strptime(linhas[1][:14], "%Y%m%d%H%M%S").timestamp()
            except Exception:
                return None

        try:
            os.kill(pid, 0)
            return 0.0
        except OSError:
            return None

    def _gravar(self, worktree_path: str, dados: Dict[str, Any]) -> None:
        os.makedirs(self.run_dir(worktree_path), exist_ok=True)
        with open(self.run_json(worktree_path), "w", encoding="utf-8") as f:
            json.dump(dados, f, indent=2)


run_registry = RunRegistry()
