"""
Artefatos precisam ser consultáveis SEM sair do painel.

Dois problemas que isto resolve:
1. o navegador bloqueia `file://` vindo de uma página http — por isso
   o usuário tinha que abrir a pasta na mão;
2. "texto", "mockup" e "mapa mental" são coisas diferentes e precisam
   aparecer separadas para ele achar o que procura.
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
    with open(os.path.join(destino, nome), "w", encoding="utf-8") as f:
        f.write(conteudo)


def test_separa_documento_de_mockup_e_imagem(pasta):
    svc = ArtifactService()
    _criar(pasta, "analise.md", "# Análise\n\ntexto comum")
    _criar(pasta, "mockup-tela.html", "<html><body>oi</body></html>")
    _criar(pasta, "foto.png")

    cats = {a["name"]: a["category"] for a in svc.listar(pasta)}
    assert cats["analise.md"] == "documento"
    assert cats["mockup-tela.html"] == "mockup"
    assert cats["foto.png"] == "imagem"


def test_markdown_com_mermaid_e_classificado_como_diagrama(pasta):
    """Mapa mental não é 'mais um texto' — precisa aparecer separado."""
    svc = ArtifactService()
    _criar(pasta, "mapa-databricks.md", "# Mapa\n\n```mermaid\nmindmap\n  root((Databricks))\n```")

    cats = {a["name"]: a["category"] for a in svc.listar(pasta)}
    assert cats["mapa-databricks.md"] == "diagrama"


def test_mmd_solto_e_reconhecido_como_mermaid(pasta):
    """
    Um .mmd é mermaid puro, sem markdown ao redor. Precisa de um tipo próprio
    para a UI saber que dá para desenhar — senão aparece listado sem preview.
    """
    svc = ArtifactService()
    _criar(pasta, "mapa-databricks.mmd", "mindmap\n  root((Databricks))")

    item = next(a for a in svc.listar(pasta) if a["name"] == "mapa-databricks.mmd")
    assert item["kind"] == "mermaid"
    assert item["category"] == "diagrama"


def test_mmd_tem_content_type_de_texto(pasta):
    """Sem isso o navegador baixaria o arquivo em vez de exibir."""
    assert ArtifactService().content_type("x.mmd").startswith("text/plain")


def test_svg_tambem_e_diagrama(pasta):
    svc = ArtifactService()
    _criar(pasta, "fluxo.svg", "<svg></svg>")
    cats = {a["name"]: a["category"] for a in svc.listar(pasta)}
    assert cats["fluxo.svg"] == "diagrama"


def test_dados_tem_categoria_propria(pasta):
    svc = ArtifactService()
    _criar(pasta, "resultado.json", "{}")
    _criar(pasta, "tabela.csv", "a,b")
    cats = {a["name"]: a["category"] for a in svc.listar(pasta)}
    assert cats["resultado.json"] == "dados"
    assert cats["tabela.csv"] == "dados"


def test_informa_o_tipo_de_conteudo_para_servir_no_navegador(pasta):
    """Sem content-type certo, o HTML baixa em vez de abrir."""
    svc = ArtifactService()
    assert svc.content_type("x.html") == "text/html; charset=utf-8"
    assert svc.content_type("x.md") == "text/markdown; charset=utf-8"
    assert svc.content_type("x.svg") == "image/svg+xml"
    assert svc.content_type("x.png") == "image/png"
    assert svc.content_type("x.desconhecido") == "application/octet-stream"


def test_le_bytes_para_servir_imagem(pasta):
    svc = ArtifactService()
    destino = os.path.join(pasta, ARTIFACT_DIR)
    os.makedirs(destino, exist_ok=True)
    with open(os.path.join(destino, "a.png"), "wb") as f:
        f.write(b"\x89PNG\r\n")

    assert svc.ler_bytes(pasta, "a.png") == b"\x89PNG\r\n"


def test_ler_bytes_tambem_recusa_caminho_que_escapa(pasta):
    with pytest.raises(ValueError):
        ArtifactService().ler_bytes(pasta, "../../segredo.bin")


def test_primeira_linha_util_vira_resumo_do_documento(pasta):
    """Para o usuário reconhecer o artefato sem abrir."""
    svc = ArtifactService()
    _criar(pasta, "analise.md", "# Análise do ETL\n\nO ETL quebrava porque...")

    item = next(a for a in svc.listar(pasta) if a["name"] == "analise.md")
    assert "Análise do ETL" in item["preview"]
