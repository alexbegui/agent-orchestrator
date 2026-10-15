import os
import sys
import json
import time
import shutil
import logging
import subprocess
from typing import Optional, Dict, Any, List

logger = logging.getLogger("orchestrator.project_service")

SERVICE_DIR = ".run"
SERVICE_JSON = "project_service.json"
SERVICE_LOG = "project_service.log"


class ProjectServiceRunner:
    """
    Gerenciador de ciclo de vida do serviço do projeto do usuário.

    Permite rodar, parar e reiniciar comandos locais (ex: dotnet run, npm run dev,
    docker compose up) de forma desacoplada do servidor FastAPI, com log em disco
    e encerramento limpo da árvore de processos no Windows.
    """

    def service_dir(self, root_path: str) -> str:
        return os.path.join(root_path, SERVICE_DIR)

    def service_json_path(self, root_path: str) -> str:
        return os.path.join(self.service_dir(root_path), SERVICE_JSON)

    def log_path(self, root_path: str) -> str:
        return os.path.join(self.service_dir(root_path), SERVICE_LOG)

    def _ignorar_no_git(self, root_path: str) -> None:
        try:
            caminho = os.path.join(self.service_dir(root_path), ".gitignore")
            if not os.path.exists(caminho):
                os.makedirs(self.service_dir(root_path), exist_ok=True)
                with open(caminho, "w", encoding="utf-8") as f:
                    f.write("# Metadados de servico do orquestrador\n*\n")
        except OSError as e:
            logger.warning(f"Não foi possível isolar {SERVICE_DIR} do git: {e}")

    def infer_default_command(self, root_path: str) -> str:
        """Inferência inteligente do comando padrão com base nos arquivos do projeto."""
        if not root_path or not os.path.isdir(root_path):
            return "npm run dev"

        # 1. .NET / C#
        for f in os.listdir(root_path):
            if f.endswith(".sln") or f.endswith(".csproj"):
                return "dotnet run"

        # 2. Node / Web
        pkg = os.path.join(root_path, "package.json")
        if os.path.exists(pkg):
            try:
                with open(pkg, "r", encoding="utf-8") as pf:
                    data = json.load(pf)
                    scripts = data.get("scripts", {})
                    if "dev" in scripts:
                        return "npm run dev"
                    if "start" in scripts:
                        return "npm start"
            except Exception:
                pass
            return "npm run dev"

        # 3. Docker Compose
        if any(os.path.exists(os.path.join(root_path, f)) for f in ["docker-compose.yml", "docker-compose.yaml", "compose.yaml", "compose.yml"]):
            return "docker compose up"

        # 4. Python
        if os.path.exists(os.path.join(root_path, "requirements.txt")) or os.path.exists(os.path.join(root_path, "pyproject.toml")):
            if os.path.exists(os.path.join(root_path, "main.py")):
                return "py main.py"
            if os.path.exists(os.path.join(root_path, "app", "main.py")):
                return "uvicorn app.main:app --reload"

        return "npm run dev"

    def read_metadata(self, root_path: str) -> Optional[Dict[str, Any]]:
        caminho = self.service_json_path(root_path)
        if not os.path.isfile(caminho):
            return None
        try:
            with open(caminho, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            logger.warning(f"Erro ao ler {caminho}: {e}")
            return None

    def is_alive(self, root_path: str) -> bool:
        dados = self.read_metadata(root_path)
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
            return True

        return abs(inicio_atual - inicio_registrado) < 1.0

    @staticmethod
    def _inicio_do_processo(pid: int) -> Optional[float]:
        try:
            import psutil
            return psutil.Process(pid).create_time()
        except Exception:
            pass

        if os.name == "nt":
            try:
                res = subprocess.run(
                    ["wmic", "process", "where", f"ProcessId={pid}", "get", "CreationDate"],
                    capture_output=True, text=True, timeout=5
                )
                linhas = [l.strip() for l in res.stdout.splitlines() if l.strip()]
                if len(linhas) >= 2 and linhas[1][:14].isdigit():
                    from datetime import datetime
                    return datetime.strptime(linhas[1][:14], "%Y%m%d%H%M%S").timestamp()
            except Exception:
                pass

        try:
            os.kill(pid, 0)
            return 0.0
        except OSError:
            return None

    def get_logs(self, root_path: str, max_lines: int = 150) -> str:
        """Lê as últimas linhas do arquivo de log do serviço."""
        log_f = self.log_path(root_path)
        if not os.path.isfile(log_f):
            return "Nenhum log gerado ainda."
        try:
            with open(log_f, "r", encoding="utf-8", errors="replace") as f:
                lines = f.readlines()
                return "".join(lines[-max_lines:])
        except Exception as e:
            return f"Erro ao ler logs: {e}"

    def detect_access_urls(self, root_path: str) -> List[str]:
        """
        Detecta URLs de acesso analisando o log recente e as portas abertas do processo.
        Ex: http://localhost:3000, http://127.0.0.1:5173, http://localhost:8000
        """
        urls = set()

        # 1. Analisa as últimas 60 linhas do log à procura de padrões de URL
        log_f = self.log_path(root_path)
        if os.path.isfile(log_f):
            try:
                import re
                url_pattern = re.compile(r"https?://(?:localhost|127\.0\.0\.1|0\.0\.0\.0|\[::1\]):[0-9]{2,5}(?:/[a-zA-Z0-9_\-\./]*)?")
                with open(log_f, "r", encoding="utf-8", errors="replace") as f:
                    for line in f.readlines()[-60:]:
                        for match in url_pattern.findall(line):
                            # Normaliza 0.0.0.0 para localhost para o usuário poder clicar
                            normalized = match.replace("0.0.0.0", "localhost").replace("[::1]", "localhost").rstrip("/>")
                            urls.add(normalized)
            except Exception:
                pass

        # 2. Se não encontrou no log ou para complementar, inspeciona conexões abertas no PID
        dados = self.read_metadata(root_path) or {}
        pid = dados.get("pid")
        if pid and self.is_alive(root_path):
            try:
                import psutil
                if psutil.pid_exists(pid):
                    p = psutil.Process(pid)
                    procs = [p] + p.children(recursive=True)
                    for pr in procs:
                        try:
                            for conn in pr.net_connections(kind="inet"):
                                if conn.status == psutil.CONN_LISTEN and conn.laddr:
                                    port = conn.laddr.port
                                    if port not in [8000]: # não confundir com o próprio orquestrador se for diferente
                                        urls.add(f"http://localhost:{port}")
                        except Exception:
                            pass
            except Exception:
                pass

        # Ordena dando preferência a portas web conhecidas (3000, 5173, 8080, 5000, etc.)
        return sorted(list(urls))

    def get_status(self, root_path: str) -> Dict[str, Any]:
        alive = self.is_alive(root_path)
        dados = self.read_metadata(root_path) or {}
        urls = self.detect_access_urls(root_path) if alive else []
        return {
            "is_running": alive,
            "pid": dados.get("pid") if alive else None,
            "command": dados.get("command"),
            "started_at": dados.get("started_at") if alive else None,
            "uptime_seconds": int(time.time() - dados["started_at"]) if alive and dados.get("started_at") else None,
            "access_urls": urls
        }

    def stop_service(self, root_path: str) -> bool:
        dados = self.read_metadata(root_path)
        if not dados:
            return False

        pid = dados.get("pid")
        if not pid:
            return False

        parou = False
        try:
            import psutil
            if psutil.pid_exists(pid):
                pai = psutil.Process(pid)
                for filho in pai.children(recursive=True):
                    try:
                        filho.kill()
                    except Exception:
                        pass
                pai.kill()
                pai.wait(timeout=5)
                parou = True
        except Exception as e:
            logger.warning(f"psutil falhou ao matar PID {pid}: {e}")

        if not parou and os.name == "nt":
            try:
                res = subprocess.run(
                    ["taskkill", "/PID", str(pid), "/T", "/F"],
                    capture_output=True, timeout=10
                )
                parou = (res.returncode == 0)
            except Exception as e:
                logger.error(f"taskkill falhou para PID {pid}: {e}")

        # Grava conclusão no json
        dados["finished_at"] = time.time()
        try:
            with open(self.service_json_path(root_path), "w", encoding="utf-8") as f:
                json.dump(dados, f, indent=2)
        except Exception:
            pass

        return True

    def start_service(self, project_id: str, root_path: str, command_str: str) -> Dict[str, Any]:
        if not root_path or not os.path.isdir(root_path):
            raise FileNotFoundError(f"Pasta do projeto não encontrada: {root_path}")

        # Se já estiver rodando, encerra antes de subir
        if self.is_alive(root_path):
            self.stop_service(root_path)
            time.sleep(1.0)

        self._ignorar_no_git(root_path)
        log_file_path = self.log_path(root_path)
        log_file = open(log_file_path, "a", encoding="utf-8", buffering=1)
        log_file.write(f"\n--- Início de serviço: {command_str} ({time.strftime('%Y-%m-%d %H:%M:%S')}) ---\n")

        kwargs = {}
        if os.name == "nt":
            kwargs["creationflags"] = (
                subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP
            )
            # No Windows, usamos o shell cmd /c para resolver scripts .cmd ou caminhos complexos
            cmd_args = ["cmd.exe", "/c", command_str]
        else:
            kwargs["start_new_session"] = True
            cmd_args = ["sh", "-c", command_str]

        proc = subprocess.Popen(
            cmd_args,
            cwd=root_path,
            stdout=log_file,
            stderr=subprocess.STDOUT,
            stdin=subprocess.DEVNULL,
            **kwargs
        )

        try:
            log_file.close()
        except Exception:
            pass

        dados = {
            "project_id": project_id,
            "pid": proc.pid,
            "command": command_str,
            "process_started_at": self._inicio_do_processo(proc.pid),
            "started_at": time.time(),
            "finished_at": None,
        }

        with open(self.service_json_path(root_path), "w", encoding="utf-8") as f:
            json.dump(dados, f, indent=2)

        return {
            "is_running": True,
            "pid": proc.pid,
            "command": command_str,
            "started_at": dados["started_at"]
        }

    def restart_service(self, project_id: str, root_path: str, command_str: str) -> Dict[str, Any]:
        """Para o serviço atual (se estiver vivo) e sobe novamente."""
        if self.is_alive(root_path):
            self.stop_service(root_path)
            time.sleep(1.2)
        return self.start_service(project_id, root_path, command_str)


project_service_runner = ProjectServiceRunner()
