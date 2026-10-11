"""
Rodar de novo não pode apagar o que o agente já fez.

`create_worktree` removia a pasta e recriava a branch com `-B`. Resultado:
cada ▶ Rodar numa tarefa que já rodou destruía tudo — arquivos soltos e
commits da branch. Era a causa de "o artefato sumiu" relatado pelo usuário.
"""
import os
import subprocess
import tempfile
import pytest

from app.services.git_service import GitWorktreeService


def _repo():
    d = tempfile.mkdtemp()
    subprocess.run(["git", "init", "-q", "-b", "main", d], check=True)
    subprocess.run(["git", "config", "user.email", "t@t"], cwd=d, check=True)
    subprocess.run(["git", "config", "user.name", "t"], cwd=d, check=True)
    with open(os.path.join(d, "base.txt"), "w") as f:
        f.write("base\n")
    subprocess.run(["git", "add", "-A"], cwd=d, check=True)
    subprocess.run(["git", "commit", "-q", "-m", "inicial"], cwd=d, check=True)
    return d


def test_rodar_de_novo_preserva_arquivo_nao_commitado():
    """O caso que o usuário viveu: o mapa mental sumiu ao rodar de novo."""
    svc = GitWorktreeService()
    repo = _repo()

    wt = svc.create_worktree(repo, "t1")
    os.makedirs(os.path.join(wt, "docs"), exist_ok=True)
    with open(os.path.join(wt, "docs", "mapa.md"), "w", encoding="utf-8") as f:
        f.write("# Mapa mental\n")

    wt2 = svc.create_worktree(repo, "t1")  # ▶ Rodar de novo

    assert os.path.exists(os.path.join(wt2, "docs", "mapa.md")), \
        "o arquivo do agente foi destruído ao rodar de novo"


def test_rodar_de_novo_preserva_commit_da_tarefa():
    svc = GitWorktreeService()
    repo = _repo()

    wt = svc.create_worktree(repo, "t2")
    with open(os.path.join(wt, "feito.txt"), "w") as f:
        f.write("trabalho\n")
    subprocess.run(["git", "add", "-A"], cwd=wt, check=True)
    subprocess.run(["git", "commit", "-q", "-m", "progresso"], cwd=wt, check=True)

    svc.create_worktree(repo, "t2")

    log = subprocess.run(
        ["git", "log", "--oneline"], cwd=wt,
        capture_output=True, text=True, check=True
    )
    assert "progresso" in log.stdout, "o commit da tarefa foi perdido"


def test_primeira_vez_cria_normalmente():
    svc = GitWorktreeService()
    repo = _repo()
    wt = svc.create_worktree(repo, "t3")

    assert os.path.isdir(wt)
    branch = subprocess.run(
        ["git", "rev-parse", "--abbrev-ref", "HEAD"], cwd=wt,
        capture_output=True, text=True, check=True
    )
    assert branch.stdout.strip() == "task/t3"


def test_pasta_quebrada_e_recriada():
    """Se a worktree ficou corrompida, recriar é o certo — não há o que perder."""
    svc = GitWorktreeService()
    repo = _repo()
    wt = svc.create_worktree(repo, "t4")

    # Simula pasta órfã, sem vínculo com o git
    import shutil
    shutil.rmtree(os.path.join(wt, ".git"), ignore_errors=True)
    if os.path.isfile(os.path.join(wt, ".git")):
        os.remove(os.path.join(wt, ".git"))

    wt2 = svc.create_worktree(repo, "t4")
    assert os.path.isdir(wt2)
