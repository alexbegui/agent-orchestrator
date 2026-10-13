"""
O agente navega: pedem para rodar o docker, ele vai para a pasta do compose
e passa a salvar lá. Foi o que aconteceu — o mapa mental existia, mas em
`.worktrees/ledger-postgres-docker/docs/`, não no worktree da tarefa.

Duas respostas: instruir onde salvar, e procurar amplo quando ele não obedecer.
"""
import os
import subprocess
import tempfile
import pytest

from app.services.artifact_service import ArtifactService


def _projeto():
    d = tempfile.mkdtemp()
    subprocess.run(["git", "init", "-q", "-b", "master", d], check=True)
    subprocess.run(["git", "config", "user.email", "t@t"], cwd=d, check=True)
    subprocess.run(["git", "config", "user.name", "t"], cwd=d, check=True)
    with open(os.path.join(d, "base.txt"), "w") as f:
        f.write("base\n")
    subprocess.run(["git", "add", "-A"], cwd=d, check=True)
    subprocess.run(["git", "commit", "-q", "-m", "inicial"], cwd=d, check=True)
    return d


def _escrever(base, rel, conteudo="# Doc"):
    destino = os.path.join(base, rel)
    os.makedirs(os.path.dirname(destino), exist_ok=True)
    with open(destino, "w", encoding="utf-8") as f:
        f.write(conteudo)


# ---------- B: instruir o agente ----------

def test_instrucao_diz_a_pasta_de_trabalho():
    texto = ArtifactService().instrucao_de_local("C:/proj/.worktrees/task-abc")
    assert "C:/proj/.worktrees/task-abc" in texto.replace("\\", "/")


def test_instrucao_e_curta_para_nao_pesar_no_prompt():
    texto = ArtifactService().instrucao_de_local("C:/proj/.worktrees/task-abc")
    assert len(texto) < 400


def test_sem_pasta_nao_instrui_nada():
    assert ArtifactService().instrucao_de_local(None) == ""


# ---------- A: procurar amplo ----------

def test_acha_documento_salvo_em_outra_worktree_do_projeto():
    """O caso real: o mapa foi parar na worktree de outro trabalho."""
    proj = _projeto()
    outra = os.path.join(proj, ".worktrees", "ledger-postgres-docker")
    _escrever(outra, "docs/databricks-mapa-mental.md", "# Mapa\n\n```mermaid\nmindmap\n```")

    wt_tarefa = os.path.join(proj, ".worktrees", "task-abc")
    os.makedirs(wt_tarefa, exist_ok=True)

    itens = ArtifactService().listar_amplo(wt_tarefa, proj)
    nomes = [a["name"] for a in itens]
    assert any("databricks-mapa-mental.md" in n for n in nomes)


def test_indica_que_o_artefato_veio_de_fora_da_tarefa():
    """Sem isso o usuário não saberia que o agente salvou no lugar errado."""
    proj = _projeto()
    outra = os.path.join(proj, ".worktrees", "outro-trabalho")
    _escrever(outra, "docs/mapa.md")

    wt_tarefa = os.path.join(proj, ".worktrees", "task-abc")
    os.makedirs(wt_tarefa, exist_ok=True)

    item = next(a for a in ArtifactService().listar_amplo(wt_tarefa, proj)
                if "mapa.md" in a["name"])
    assert item["outside_task"] is True


def test_artefato_da_propria_tarefa_nao_e_marcado_como_de_fora():
    proj = _projeto()
    wt_tarefa = os.path.join(proj, ".worktrees", "task-abc")
    _escrever(wt_tarefa, "docs/meu.md")

    item = next(a for a in ArtifactService().listar_amplo(wt_tarefa, proj)
                if "meu.md" in a["name"])
    assert item["outside_task"] is False


def test_nao_duplica_quando_o_arquivo_esta_nos_dois_lugares():
    proj = _projeto()
    wt_tarefa = os.path.join(proj, ".worktrees", "task-abc")
    _escrever(wt_tarefa, "docs/mapa.md")

    nomes = [a["name"] for a in ArtifactService().listar_amplo(wt_tarefa, proj)]
    assert len(nomes) == len(set(nomes))


def test_ignora_worktrees_de_outras_tarefas_do_orquestrador():
    """
    Worktree de OUTRA tarefa é trabalho de outra tarefa — mostrar seria
    exatamente a mistura que o usuário não quer.
    """
    proj = _projeto()
    outra_tarefa = os.path.join(proj, ".worktrees", "task-zzz999")
    _escrever(outra_tarefa, "docs/da-outra.md")

    wt_tarefa = os.path.join(proj, ".worktrees", "task-abc")
    os.makedirs(wt_tarefa, exist_ok=True)

    nomes = [a["name"] for a in ArtifactService().listar_amplo(wt_tarefa, proj)]
    assert not any("da-outra.md" in n for n in nomes)
