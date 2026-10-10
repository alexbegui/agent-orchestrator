"""
Fechar a tarefa não pode destruir o que ela produziu.

O merge remove o worktree. Se houver trabalho não commitado ali — artefatos,
código —, ele some junto. Antes, só quem abrisse a aba Diffs tinha o
auto-commit; quem aprovasse direto perdia o arquivo sem aviso.
"""
import os
import subprocess
import tempfile
import pytest

from app.services.git_service import GitWorktreeService


def _repo_com_commit_inicial():
    repo = tempfile.mkdtemp()
    subprocess.run(["git", "init", "-q", "-b", "main", repo], check=True)
    subprocess.run(["git", "config", "user.email", "t@t"], cwd=repo, check=True)
    subprocess.run(["git", "config", "user.name", "t"], cwd=repo, check=True)
    with open(os.path.join(repo, "base.txt"), "w") as f:
        f.write("base\n")
    subprocess.run(["git", "add", "-A"], cwd=repo, check=True)
    subprocess.run(["git", "commit", "-q", "-m", "inicial"], cwd=repo, check=True)
    return repo


def test_merge_preserva_artefato_nao_commitado():
    svc = GitWorktreeService()
    repo = _repo_com_commit_inicial()
    wt = svc.create_worktree(repo, "tarefa-1")

    # O agente cria um artefato e NÃO commita
    pasta = os.path.join(wt, ".agent", "artefatos")
    os.makedirs(pasta, exist_ok=True)
    with open(os.path.join(pasta, "mapa.md"), "w", encoding="utf-8") as f:
        f.write("# Mapa mental\n")

    assert svc.merge_task(repo, "tarefa-1", target_branch="main") is True

    # Depois do merge o artefato precisa estar no projeto
    assert os.path.exists(os.path.join(repo, ".agent", "artefatos", "mapa.md"))


def test_merge_preserva_codigo_nao_commitado():
    svc = GitWorktreeService()
    repo = _repo_com_commit_inicial()
    wt = svc.create_worktree(repo, "tarefa-2")

    with open(os.path.join(wt, "novo.py"), "w", encoding="utf-8") as f:
        f.write("print('oi')\n")

    assert svc.merge_task(repo, "tarefa-2", target_branch="main") is True
    assert os.path.exists(os.path.join(repo, "novo.py"))


def test_merge_sem_nada_pendente_continua_funcionando():
    svc = GitWorktreeService()
    repo = _repo_com_commit_inicial()
    wt = svc.create_worktree(repo, "tarefa-3")

    with open(os.path.join(wt, "x.txt"), "w", encoding="utf-8") as f:
        f.write("algo\n")
    subprocess.run(["git", "add", "-A"], cwd=wt, check=True)
    subprocess.run(["git", "commit", "-q", "-m", "feito"], cwd=wt, check=True)

    assert svc.merge_task(repo, "tarefa-3", target_branch="main") is True
    assert os.path.exists(os.path.join(repo, "x.txt"))


def test_metadados_de_execucao_nao_vao_para_o_projeto():
    """O .run/ é controle interno do orquestrador, não trabalho do usuário."""
    svc = GitWorktreeService()
    repo = _repo_com_commit_inicial()
    wt = svc.create_worktree(repo, "tarefa-4")

    run_dir = os.path.join(wt, ".run")
    os.makedirs(run_dir, exist_ok=True)
    with open(os.path.join(run_dir, ".gitignore"), "w") as f:
        f.write("*\n")
    with open(os.path.join(run_dir, "output.log"), "w") as f:
        f.write("log\n")

    svc.merge_task(repo, "tarefa-4", target_branch="main")
    assert not os.path.exists(os.path.join(repo, ".run", "output.log"))
