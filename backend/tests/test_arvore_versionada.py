"""
A árvore mandada para a IA vem do git, não de os.walk.

Medido neste repositório: o walk antigo (que só pulava .git, node_modules e
.worktrees) devolvia 4.077 arquivos / ~72 mil tokens, dos quais 3.786 eram a
venv do Python. `git ls-files` devolve 99. A lista curada já existe — é o
.gitignore do usuário.
"""
import subprocess
import pytest

from app.services.git_service import GitWorktreeService


def _git(*args, cwd):
    subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True)


@pytest.fixture
def repo(tmp_path):
    raiz = tmp_path / "projeto"
    (raiz / "app").mkdir(parents=True)
    (raiz / "venv" / "lib").mkdir(parents=True)

    (raiz / "app" / "main.py").write_text("print(1)\n", encoding="utf-8")
    (raiz / "venv" / "lib" / "pacote.py").write_text("# dependência\n", encoding="utf-8")
    (raiz / "segredo.env").write_text("CHAVE=1\n", encoding="utf-8")
    (raiz / ".gitignore").write_text("venv/\n*.env\n", encoding="utf-8")

    _git("init", cwd=raiz)
    _git("config", "user.email", "teste@teste", cwd=raiz)
    _git("config", "user.name", "Teste", cwd=raiz)
    _git("add", "-A", cwd=raiz)
    _git("commit", "-m", "inicial", cwd=raiz)
    return raiz


def test_arvore_traz_o_codigo_do_projeto(repo):
    arquivos = GitWorktreeService().listar_versionados(str(repo))

    assert "app/main.py" in arquivos


def test_arvore_nao_traz_a_venv_nem_o_env(repo):
    """O que o .gitignore exclui, a IA não precisa ver — e você não paga por ele."""
    arquivos = GitWorktreeService().listar_versionados(str(repo))

    assert not any("venv" in a for a in arquivos)
    assert not any(a.endswith(".env") for a in arquivos)


def test_pasta_sem_git_devolve_lista_vazia_em_vez_de_quebrar(tmp_path):
    vazia = tmp_path / "sem_git"
    vazia.mkdir()

    assert GitWorktreeService().listar_versionados(str(vazia)) == []


def test_caminhos_usam_barra_normal(repo):
    """O Windows devolveria contrabarra; o prompt e a IA falam com barra."""
    arquivos = GitWorktreeService().listar_versionados(str(repo))

    assert all("\\" not in a for a in arquivos)
