import os
import shutil
import subprocess
from typing import Optional


class GitWorktreeService:
    """
    Gerencia o ciclo de vida de Git Worktrees e branches para cada tarefa,
    garantindo isolamento total de arquivos físicos durante a execução de agentes.
    """

    def _run_git(self, args: list[str], cwd: str) -> subprocess.CompletedProcess:
        return subprocess.run(
            ["git"] + args,
            cwd=cwd,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=True
        )

    def get_worktree_path(self, project_path: str, task_id: str) -> str:
        return os.path.abspath(os.path.join(project_path, ".worktrees", f"task-{task_id}"))

    def create_worktree(
        self,
        project_path: str,
        task_id: str,
        branch_name: Optional[str] = None
    ) -> str:
        branch = branch_name or f"task/{task_id}"
        worktree_path = self.get_worktree_path(project_path, task_id)
        
        # Cria diretório pai .worktrees se não existir
        os.makedirs(os.path.dirname(worktree_path), exist_ok=True)

        # Se a worktree já existir, remove antes de recriar
        if os.path.exists(worktree_path):
            self.remove_worktree(project_path, task_id)

        # Adiciona a worktree com branch dedicada
        self._run_git(["worktree", "add", "-B", branch, worktree_path], cwd=project_path)
        return worktree_path

    def remove_worktree(self, project_path: str, task_id: str) -> bool:
        worktree_path = self.get_worktree_path(project_path, task_id)
        try:
            # Tenta remoção nativa do git
            self._run_git(["worktree", "remove", "--force", worktree_path], cwd=project_path)
        except Exception:
            pass

        # Fallback para Windows caso diretório permaneça
        if os.path.exists(worktree_path):
            try:
                shutil.rmtree(worktree_path, ignore_errors=True)
            except Exception:
                pass

        # Prune para limpar referências internas do git
        try:
            self._run_git(["worktree", "prune"], cwd=project_path)
        except Exception:
            pass

        return not os.path.exists(worktree_path)

    def get_diff(self, project_path: str, task_id: str, base_branch: str = "main") -> str:
        branch = f"task/{task_id}"
        worktree_path = self.get_worktree_path(project_path, task_id)

        # Se houver alterações não commitadas na worktree, faz auto-snapshot
        if os.path.exists(worktree_path):
            try:
                status_res = subprocess.run(
                    ["git", "status", "--porcelain"],
                    cwd=worktree_path,
                    capture_output=True,
                    text=True,
                    check=True
                )
                if status_res.stdout.strip():
                    self._run_git(["add", "-A"], cwd=worktree_path)
                    self._run_git(["commit", "-m", "Auto: snapshot uncommitted changes"], cwd=worktree_path)
            except Exception:
                pass

        try:
            proc = self._run_git(["diff", f"{base_branch}...{branch}"], cwd=project_path)
            return proc.stdout
        except subprocess.CalledProcessError as e:
            return f"Erro ao obter diff: {e.stderr}"

    def merge_task(
        self,
        project_path: str,
        task_id: str,
        target_branch: str = "main"
    ) -> bool:
        branch = f"task/{task_id}"
        try:
            # Garante que o projeto principal está na branch alvo
            self._run_git(["checkout", target_branch], cwd=project_path)
            # Executa o merge
            self._run_git(["merge", branch, "--no-edit"], cwd=project_path)
            return True
        except subprocess.CalledProcessError:
            # Em caso de conflito, aborta o merge para manter a main limpa
            try:
                self._run_git(["merge", "--abort"], cwd=project_path)
            except Exception:
                pass
            return False

    def cleanup_task_git(self, project_path: str, task_id: str) -> None:
        """
        Descarta a worktree e deleta forçadamente a branch temporária da tarefa,
        deixando o repositório principal limpo.
        """
        # 1. Remove a pasta e desassocia do git worktree
        self.remove_worktree(project_path, task_id)

        # 2. Deleta a branch local dedicada
        branch = f"task/{task_id}"
        try:
            self._run_git(["branch", "-D", branch], cwd=project_path)
        except Exception:
            pass
