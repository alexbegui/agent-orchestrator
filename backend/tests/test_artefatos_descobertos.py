"""
Artefato é o que a tarefa produziu — não o que está numa pasta combinada.

Exigir `.agent/artefatos/` era uma convenção que o agente não conhece: ele
salvou o mapa mental em `docs/`, que é o lugar natural, e a aba não mostrou
nada. O git já sabe o que a tarefa criou; basta perguntar a ele.
"""
import os
import subprocess
import tempfile
import pytest

from app.services.artifact_service import ArtifactService


def _worktree():
    d = tempfile.mkdtemp()
    subprocess.run(["git", "init", "-q", "-b", "main", d], check=True)
    subprocess.run(["git", "config", "user.email", "t@t"], cwd=d, check=True)
    subprocess.run(["git", "config", "user.name", "t"], cwd=d, check=True)
    with open(os.path.join(d, "base.txt"), "w") as f:
        f.write("base\n")
    subprocess.run(["git", "add", "-A"], cwd=d, check=True)
    subprocess.run(["git", "commit", "-q", "-m", "inicial"], cwd=d, check=True)
    return d


def _escrever(base, caminho_rel, conteudo="conteudo"):
    destino = os.path.join(base, caminho_rel)
    os.makedirs(os.path.dirname(destino), exist_ok=True)
    with open(destino, "w", encoding="utf-8") as f:
        f.write(conteudo)


def test_acha_documento_criado_em_docs():
    """O caso real: o agente salvou em docs/ e a aba não mostrava nada."""
    wt = _worktree()
    _escrever(wt, "docs/databricks-mapa-mental.md", "# Mapa\n\n```mermaid\nmindmap\n```")

    nomes = [a["name"] for a in ArtifactService().listar(wt)]
    assert "docs/databricks-mapa-mental.md" in nomes


def test_continua_achando_a_pasta_combinada():
    wt = _worktree()
    _escrever(wt, ".agent/artefatos/analise.md", "# Análise")

    nomes = [a["name"] for a in ArtifactService().listar(wt)]
    assert ".agent/artefatos/analise.md" in nomes


def test_ignora_codigo_fonte():
    """Artefato é documento. Código é o que o diff mostra."""
    wt = _worktree()
    _escrever(wt, "backend/app/novo.py", "print('oi')")
    _escrever(wt, "src/componente.tsx", "export const X = 1")

    nomes = [a["name"] for a in ArtifactService().listar(wt)]
    assert not any(n.endswith((".py", ".tsx")) for n in nomes)


def test_ignora_arquivos_de_dependencia():
    """
    package-lock.json apareceu como artefato num teste real. Arquivo de
    bloqueio não é documento que alguém vá consultar — é ruído gerado
    por ferramenta, e o diff já mostra que mudou.
    """
    wt = _worktree()
    _escrever(wt, "package-lock.json", "{}")
    _escrever(wt, "frontend/package-lock.json", "{}")
    _escrever(wt, "poetry.lock", "")
    _escrever(wt, "tsconfig.json", "{}")

    nomes = [a["name"] for a in ArtifactService().listar(wt)]
    assert nomes == [], f"nenhum desses é artefato, mas veio: {nomes}"


def test_dados_de_verdade_continuam_aparecendo():
    """Um CSV ou JSON de resultado é artefato legítimo."""
    wt = _worktree()
    _escrever(wt, "docs/resultado-analise.json", '{"total": 42}')
    _escrever(wt, "relatorios/vendas.csv", "mes,valor")

    nomes = [a["name"] for a in ArtifactService().listar(wt)]
    assert "docs/resultado-analise.json" in nomes
    assert "relatorios/vendas.csv" in nomes


def test_ignora_metadados_do_orquestrador():
    wt = _worktree()
    _escrever(wt, ".run/output.log", "log")
    _escrever(wt, ".agent/_proposto.md", "[x] algo")

    nomes = [a["name"] for a in ArtifactService().listar(wt)]
    assert not any(".run" in n or "_proposto" in n for n in nomes)


def _branch_de_tarefa(wt):
    """Reproduz o que o orquestrador faz: a tarefa roda na própria branch."""
    subprocess.run(["git", "checkout", "-q", "-b", "task/abc123"], cwd=wt, check=True)


def test_acha_documento_ja_commitado_na_tarefa():
    """O agente às vezes commita; o artefato não pode sumir por isso."""
    wt = _worktree()
    _branch_de_tarefa(wt)
    _escrever(wt, "docs/analise.md", "# Análise")
    subprocess.run(["git", "add", "-A"], cwd=wt, check=True)
    subprocess.run(["git", "commit", "-q", "-m", "doc"], cwd=wt, check=True)

    nomes = [a["name"] for a in ArtifactService().listar(wt)]
    assert "docs/analise.md" in nomes


def test_nao_lista_documento_que_ja_existia_antes_da_tarefa():
    """README do projeto não é artefato desta tarefa."""
    wt = _worktree()
    _escrever(wt, "README.md", "# Projeto")
    subprocess.run(["git", "add", "-A"], cwd=wt, check=True)
    subprocess.run(["git", "commit", "-q", "-m", "readme"], cwd=wt, check=True)
    _branch_de_tarefa(wt)

    nomes = [a["name"] for a in ArtifactService().listar(wt)]
    assert "README.md" not in nomes


def test_pasta_sem_git_ainda_lista_a_pasta_combinada():
    """Projeto sem git, ou visão do projeto depois do merge."""
    with tempfile.TemporaryDirectory() as d:
        _escrever(d, ".agent/artefatos/x.md", "# X")
        nomes = [a["name"] for a in ArtifactService().listar(d)]
        assert ".agent/artefatos/x.md" in nomes
