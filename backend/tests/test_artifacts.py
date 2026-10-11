"""
Artefatos: o que as tarefas produzem (mockups, specs, análises).

Pertencem à tarefa que os criou E ao projeto, como documentação. Não há
sincronização entre os dois: é o mesmo arquivo, e o merge é a promoção —
quem faz isso é o git, não código nosso.
"""
import os
import tempfile
import pytest

from app.services.artifact_service import ArtifactService, ARTIFACT_DIR


@pytest.fixture
def pasta():
    with tempfile.TemporaryDirectory() as d:
        yield d


def _criar(base, nome, conteudo="x"):
    destino = os.path.join(base, ARTIFACT_DIR)
    os.makedirs(destino, exist_ok=True)
    caminho = os.path.join(destino, nome)
    with open(caminho, "w", encoding="utf-8") as f:
        f.write(conteudo)
    return caminho


def test_lista_artefatos_da_pasta(pasta):
    svc = ArtifactService()
    _criar(pasta, "mockup-kanban.html", "<html></html>")
    _criar(pasta, "spec-migracao.md", "# Spec")

    nomes = [os.path.basename(a["name"]) for a in svc.listar(pasta)]
    assert "mockup-kanban.html" in nomes
    assert "spec-migracao.md" in nomes


def test_pasta_sem_artefatos_devolve_lista_vazia(pasta):
    assert ArtifactService().listar(pasta) == []


def test_classifica_o_tipo_para_a_ui_saber_como_abrir(pasta):
    svc = ArtifactService()
    _criar(pasta, "a.md")
    _criar(pasta, "b.html")
    _criar(pasta, "c.png")

    tipos = {os.path.basename(a["name"]): a["kind"] for a in svc.listar(pasta)}
    assert tipos["a.md"] == "markdown"
    assert tipos["b.html"] == "html"
    assert tipos["c.png"] == "other"


def test_le_o_conteudo_de_um_artefato(pasta):
    svc = ArtifactService()
    _criar(pasta, "spec.md", "# Título\n\ncorpo")
    assert "# Título" in svc.ler(pasta, os.path.join(ARTIFACT_DIR, "spec.md"))


def test_recusa_caminho_que_escapa_da_pasta(pasta):
    """Sem isso, um nome como ../../.env leria qualquer arquivo da máquina."""
    svc = ArtifactService()
    with pytest.raises(ValueError):
        svc.ler(pasta, "../../segredo.txt")
    with pytest.raises(ValueError):
        svc.ler(pasta, "sub/../../fora.md")


def test_artefato_inexistente_devolve_none(pasta):
    assert ArtifactService().ler(pasta, "nao-existe.md") is None


def test_indice_ganha_uma_linha_por_artefato_novo(pasta):
    """No merge, o índice registra o que entrou — sem chamar modelo."""
    svc = ArtifactService()
    _criar(pasta, "analise-etl.md")

    svc.registrar_no_indice(pasta, ["analise-etl.md"], titulo_tarefa="Analisar o ETL")

    indice = open(svc.indice_path(pasta), encoding="utf-8").read()
    assert "analise-etl.md" in indice
    assert "Analisar o ETL" in indice


def test_registrar_duas_vezes_nao_duplica_a_linha(pasta):
    svc = ArtifactService()
    _criar(pasta, "analise-etl.md")

    svc.registrar_no_indice(pasta, ["analise-etl.md"], titulo_tarefa="Analisar o ETL")
    svc.registrar_no_indice(pasta, ["analise-etl.md"], titulo_tarefa="Analisar o ETL")

    indice = open(svc.indice_path(pasta), encoding="utf-8").read()
    assert indice.count("analise-etl.md") == 1


def test_contexto_para_o_agente_e_curto_e_so_o_indice(pasta):
    """
    O agente recebe o índice, nunca os artefatos inteiros — é o que mantém
    o custo fixo e baixo, independente de quantos artefatos existam.
    """
    svc = ArtifactService()
    for i in range(20):
        _criar(pasta, f"doc-{i}.md", "conteúdo enorme " * 500)
    svc.registrar_no_indice(pasta, [f"doc-{i}.md" for i in range(20)], titulo_tarefa="T")

    ctx = svc.contexto_para_prompt(pasta)
    assert "doc-0.md" in ctx
    assert "conteúdo enorme" not in ctx
    assert len(ctx) < 4000


def test_projeto_sem_conhecimento_nao_injeta_nada(pasta):
    assert ArtifactService().contexto_para_prompt(pasta) == ""


