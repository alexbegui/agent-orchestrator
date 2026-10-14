"""
O mesmo arquivo aparecia DUAS VEZES na aba Artefatos.

Visto numa execução real do agy: um único `walkthrough.md` no disco, duas
entradas na lista, com `name` e `rel_path` idênticos.

A causa é o Windows. `listar` junta duas fontes num `set` de caminhos
relativos:

    _do_git              → ".agent/artefatos/walkthrough.md"   (git usa /)
    _da_pasta_combinada  → ".agent\\artefatos\\walkthrough.md"  (os.path.relpath usa \\)

São a mesma coisa e duas strings diferentes, então o set guarda as duas. Em
Linux nunca aconteceria — por isso nenhum teste pegou, e por isso o defeito
sobreviveu num projeto "fortemente orientado a Windows".

Só duplica quando o arquivo está DENTRO da pasta combinada (`.agent/artefatos`)
E é visto pelo git. O walkthrough.md que o agente passou a escrever cai
exatamente nessa interseção — por isso apareceu agora.
"""
import os
import subprocess
import pytest

from app.services.artifact_service import ArtifactService, ARTIFACT_DIR


def _git(*args, cwd):
    subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True)


@pytest.fixture
def projeto(tmp_path):
    """Projeto git com o worktree da tarefa DENTRO dele, como na vida real."""
    raiz = tmp_path / "projeto"
    raiz.mkdir()
    (raiz / "app.py").write_text("print(1)\n", encoding="utf-8")
    _git("init", cwd=raiz)
    _git("config", "user.email", "t@t", cwd=raiz)
    _git("config", "user.name", "T", cwd=raiz)
    _git("add", "-A", cwd=raiz)
    _git("commit", "-m", "inicial", cwd=raiz)

    worktree = raiz / ".worktrees" / "task-abc"
    _git("worktree", "add", "-b", "task/abc", str(worktree), cwd=raiz)

    # O agente escreve o sumário na pasta combinada — vista pelas DUAS fontes.
    artefatos = worktree / ARTIFACT_DIR
    artefatos.mkdir(parents=True)
    (artefatos / "walkthrough.md").write_text("# O que mudou\nnada\n", encoding="utf-8")

    return {"raiz": str(raiz), "worktree": str(worktree)}


def test_arquivo_na_pasta_combinada_aparece_uma_vez_so(projeto):
    itens = ArtifactService().listar(projeto["worktree"])

    nomes = [i["name"] for i in itens]
    assert nomes.count("walkthrough.md") + nomes.count(
        f"{ARTIFACT_DIR}/walkthrough.md".replace(os.sep, "/")
    ) <= 1, f"o mesmo arquivo apareceu mais de uma vez: {nomes}"


def test_lista_ampla_nao_repete_o_sumario(projeto):
    """
    A prova pelo caminho que o usuário vê: a rota de artefatos chama
    listar_amplo, e é ali que as duas entradas idênticas apareciam.
    """
    itens = ArtifactService().listar_amplo(projeto["worktree"], projeto["raiz"])

    caminhos = [i.get("rel_path") for i in itens]
    repetidos = [c for c in set(caminhos) if c and caminhos.count(c) > 1]
    assert not repetidos, f"caminhos repetidos na lista: {repetidos}"


def test_nomes_sempre_com_barra_normal(projeto):
    """
    Contrabarra no `name` é o sintoma visível da mesma causa: a tela e a
    leitura do arquivo falam com barra, e misturar os dois separadores é o que
    criava a entrada gêmea.
    """
    itens = ArtifactService().listar(projeto["worktree"])

    assert all("\\" not in i["name"] for i in itens), [i["name"] for i in itens]
