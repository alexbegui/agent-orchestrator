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

    def listar_versionados(self, project_path: str) -> list[str]:
        """
        Os arquivos que o git considera do projeto — a árvore que vai para a IA.

        Antes isso era um `os.walk` que só pulava .git, node_modules e
        .worktrees: neste repositório devolvia 4.077 arquivos (~72 mil tokens),
        dos quais 3.786 eram a venv do Python. `git ls-files` devolve 99. A
        lista curada já existe e é o .gitignore do usuário — não há heurística
        a inventar aqui.

        Pasta sem git devolve lista vazia; quem chama decide o que fazer.
        """
        if not project_path or not os.path.isdir(project_path):
            return []
        try:
            res = self._run_git(["ls-files"], cwd=project_path)
        except (subprocess.CalledProcessError, OSError):
            return []
        # O git já devolve com barra normal, mas no Windows um core.quotepath
        # ou um caminho vindo de outra fonte traz contrabarra. Normaliza porque
        # o prompt e a IA falam com barra.
        return [
            linha.strip().replace("\\", "/")
            for linha in res.stdout.splitlines()
            if linha.strip()
        ]

    def arquivos_recentes(self, project_path: str, commits: int = 50) -> list[str]:
        """
        Arquivos tocados nos últimos commits, do mais recente para o mais antigo.

        Serve para o corte da árvore quando ela não cabe: o que o projeto está
        mexendo tem muito mais chance de ser o alvo da tarefa do que o que não
        muda há dois anos.
        """
        if not project_path or not os.path.isdir(project_path):
            return []
        try:
            res = self._run_git(
                ["log", f"-{commits}", "--name-only", "--pretty=format:"],
                cwd=project_path,
            )
        except (subprocess.CalledProcessError, OSError):
            return []

        vistos: list[str] = []
        for linha in res.stdout.splitlines():
            caminho = linha.strip().replace("\\", "/")
            if caminho and caminho not in vistos:
                vistos.append(caminho)
        return vistos

    def branch_base(self, project_path: str) -> str:
        """
        Descobre o ramo principal do repositório em vez de supor "main".

        O projeto real do usuário usa `master`; supor `main` fazia o merge
        tentar um checkout inexistente e a detecção de artefatos commitados
        falhar em silêncio.
        """
        if not project_path or not os.path.isdir(project_path):
            return "main"

        # O que o remoto aponta como padrão é a resposta mais confiável.
        try:
            res = subprocess.run(
                ["git", "symbolic-ref", "--short", "refs/remotes/origin/HEAD"],
                cwd=project_path, capture_output=True, text=True, timeout=10
            )
            if res.returncode == 0 and res.stdout.strip():
                return res.stdout.strip().split("/")[-1]
        except (subprocess.SubprocessError, OSError):
            pass

        # Sem remoto: a primeira dos nomes usuais que existir de verdade.
        for nome in ("main", "master", "trunk", "develop", "desenvolvimento"):
            try:
                res = subprocess.run(
                    ["git", "rev-parse", "--verify", "--quiet", nome],
                    cwd=project_path, capture_output=True, text=True, timeout=10
                )
                if res.returncode == 0:
                    return nome
            except (subprocess.SubprocessError, OSError):
                break

        # Último recurso: o ramo em que o repositório principal está agora.
        try:
            res = subprocess.run(
                ["git", "rev-parse", "--abbrev-ref", "HEAD"],
                cwd=project_path, capture_output=True, text=True, timeout=10
            )
            atual = res.stdout.strip()
            if res.returncode == 0 and atual and not atual.startswith("task/"):
                return atual
        except (subprocess.SubprocessError, OSError):
            pass

        return "main"

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

        os.makedirs(os.path.dirname(worktree_path), exist_ok=True)

        # Worktree válida já existente é REAPROVEITADA.
        #
        # Antes, rodar de novo removia a pasta e recriava a branch com `-B`,
        # destruindo tudo que o agente já tinha feito — arquivos soltos e
        # commits da branch. Era a causa de artefatos "sumirem" entre execuções.
        if self._worktree_valida(worktree_path):
            return worktree_path

        # Pasta órfã ou corrompida: aí sim não há o que preservar.
        if os.path.exists(worktree_path):
            self.remove_worktree(project_path, task_id)

        # `-B` só na criação: reaproveita a branch se ela já existir com trabalho.
        try:
            self._run_git(["worktree", "add", worktree_path, branch], cwd=project_path)
        except subprocess.CalledProcessError:
            # A branch ainda não existe — cria a partir do HEAD atual.
            self._run_git(["worktree", "add", "-b", branch, worktree_path], cwd=project_path)

        return worktree_path

    def _worktree_valida(self, worktree_path: str) -> bool:
        """Pasta existe E o git ainda a reconhece como worktree."""
        if not os.path.isdir(worktree_path):
            return False
        try:
            res = subprocess.run(
                ["git", "rev-parse", "--is-inside-work-tree"],
                cwd=worktree_path, capture_output=True, text=True, timeout=15
            )
            return res.returncode == 0 and res.stdout.strip() == "true"
        except (subprocess.SubprocessError, OSError):
            return False

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

    def change_stats(self, worktree_path: str) -> dict:
        """
        Quanto o agente mexeu: arquivos, linhas somadas e removidas.

        Sai do próprio git — é fato, não interpretação. Conta o que já foi
        commitado na branch da tarefa MAIS o que ainda está solto, porque o
        agente nem sempre commita.
        """
        vazio = {"files": 0, "added": 0, "removed": 0}
        if not worktree_path or not os.path.isdir(worktree_path):
            return vazio

        arquivos, somadas, removidas = set(), 0, 0
        try:
            # Mudanças ainda não commitadas
            res = subprocess.run(
                ["git", "diff", "HEAD", "--numstat"],
                cwd=worktree_path, capture_output=True, text=True,
                encoding="utf-8", errors="replace", timeout=15
            )
            # Arquivos novos não rastreados não aparecem no diff
            novos = subprocess.run(
                ["git", "ls-files", "--others", "--exclude-standard"],
                cwd=worktree_path, capture_output=True, text=True,
                encoding="utf-8", errors="replace", timeout=15
            )
        except (subprocess.SubprocessError, OSError):
            return vazio

        for linha in res.stdout.splitlines():
            partes = linha.split("\t")
            if len(partes) != 3:
                continue
            add, rem, caminho = partes
            arquivos.add(caminho)
            somadas += int(add) if add.isdigit() else 0
            removidas += int(rem) if rem.isdigit() else 0

        for caminho in novos.stdout.splitlines():
            caminho = caminho.strip()
            if not caminho or caminho.startswith(".run/"):
                continue
            arquivos.add(caminho)
            try:
                with open(os.path.join(worktree_path, caminho), "r",
                          encoding="utf-8", errors="replace") as f:
                    somadas += sum(1 for _ in f)
            except OSError:
                pass

        return {"files": len(arquivos), "added": somadas, "removed": removidas}

    def commit_pendente(self, worktree_path: str, mensagem: str) -> bool:
        """
        Commita o que estiver solto no worktree.

        O merge remove a pasta: sem isto, qualquer arquivo não commitado —
        artefato, código — some sem aviso. Antes, só quem abrisse a aba Diffs
        tinha esse commit automático.
        """
        if not worktree_path or not os.path.isdir(worktree_path):
            return False
        try:
            status = subprocess.run(
                ["git", "status", "--porcelain"],
                cwd=worktree_path, capture_output=True, text=True,
                encoding="utf-8", errors="replace", check=True
            )
            if not status.stdout.strip():
                return False
            self._run_git(["add", "-A"], cwd=worktree_path)
            self._run_git(["commit", "-m", mensagem], cwd=worktree_path)
            return True
        except Exception:
            return False

    def merge_task(
        self,
        project_path: str,
        task_id: str,
        target_branch: str = "main"
    ) -> bool:
        branch = f"task/{task_id}"

        # Salva o que ainda não foi commitado ANTES de mergear — logo em
        # seguida a worktree é removida e o que estiver solto se perderia.
        self.commit_pendente(
            self.get_worktree_path(project_path, task_id),
            f"Auto: trabalho pendente da tarefa {task_id[:8]}"
        )

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
