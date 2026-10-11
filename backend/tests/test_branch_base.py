"""
Nem todo repositório usa `main`.

O projeto real do usuário usa `master`, mas o banco guardava o padrão 'main'
sem nunca conferir. Consequências: a detecção de artefatos commitados falhava
silenciosamente, e o merge tentaria `git checkout main` num repo sem main.
"""
import os
import subprocess
import tempfile
import pytest

from app.services.git_service import GitWorktreeService
from app.services.artifact_service import ArtifactService


def _repo(branch="master"):
    d = tempfile.mkdtemp()
    subprocess.run(["git", "init", "-q", "-b", branch, d], check=True)
    subprocess.run(["git", "config", "user.email", "t@t"], cwd=d, check=True)
    subprocess.run(["git", "config", "user.name", "t"], cwd=d, check=True)
    with open(os.path.join(d, "base.txt"), "w") as f:
        f.write("base\n")
    subprocess.run(["git", "add", "-A"], cwd=d, check=True)
    subprocess.run(["git", "commit", "-q", "-m", "inicial"], cwd=d, check=True)
    return d


def test_descobre_master_como_branch_base():
    assert GitWorktreeService().branch_base(_repo("master")) == "master"


def test_descobre_main_como_branch_base():
    assert GitWorktreeService().branch_base(_repo("main")) == "main"


def test_descobre_nome_incomum():
    assert GitWorktreeService().branch_base(_repo("desenvolvimento")) == "desenvolvimento"


def test_pasta_sem_git_devolve_main_como_chute_seguro():
    with tempfile.TemporaryDirectory() as d:
        assert GitWorktreeService().branch_base(d) == "main"


def test_artefato_commitado_aparece_em_repo_com_master():
    """
    O caso real: `git diff main...HEAD` falhava calado num repo com master,
    e artefatos já commitados pela tarefa ficavam invisíveis.
    """
    repo = _repo("master")
    svc = GitWorktreeService()
    wt = svc.create_worktree(repo, "t1")

    os.makedirs(os.path.join(wt, "docs"), exist_ok=True)
    with open(os.path.join(wt, "docs", "mapa.md"), "w", encoding="utf-8") as f:
        f.write("# Mapa\n")
    subprocess.run(["git", "add", "-A"], cwd=wt, check=True)
    subprocess.run(["git", "commit", "-q", "-m", "mapa"], cwd=wt, check=True)

    nomes = [a["name"] for a in ArtifactService().listar(wt)]
    assert "docs/mapa.md" in nomes


def test_merge_funciona_em_repo_com_master():
    """merge_task fazia `git checkout main` fixo e quebraria aqui."""
    repo = _repo("master")
    svc = GitWorktreeService()
    wt = svc.create_worktree(repo, "t2")

    with open(os.path.join(wt, "novo.txt"), "w") as f:
        f.write("feito\n")

    assert svc.merge_task(repo, "t2", target_branch=svc.branch_base(repo)) is True
    assert os.path.exists(os.path.join(repo, "novo.txt"))
