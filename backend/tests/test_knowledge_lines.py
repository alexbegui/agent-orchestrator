"""
Linhas de conhecimento: o que o diff NÃO conta.

"Arquivos alterados" é git log. Conhecimento é o porquê, o que foi tentado
e falhou, qual armadilha espera o próximo. O agente propõe; o usuário aprova.
O padrão é não registrar nada.
"""
import os
import tempfile
import pytest

from app.services.artifact_service import (
    ArtifactService, ARTIFACT_DIR, PROPOSTAS_FILE, SECAO_CONHECIMENTO
)


@pytest.fixture
def pasta():
    with tempfile.TemporaryDirectory() as d:
        yield d


def _propor(base, texto):
    destino = os.path.join(base, ".agent")
    os.makedirs(destino, exist_ok=True)
    with open(os.path.join(destino, os.path.basename(PROPOSTAS_FILE)), "w", encoding="utf-8") as f:
        f.write(texto)


def test_sem_proposta_devolve_lista_vazia(pasta):
    assert ArtifactService().ler_propostas(pasta) == []


def test_le_as_linhas_propostas_pelo_agente(pasta):
    svc = ArtifactService()
    _propor(pasta, "[db] WAL ligado, backup exige .backup\n[auth] refresh precisa rotacionar\n")

    linhas = svc.ler_propostas(pasta)
    assert len(linhas) == 2
    assert "WAL ligado" in linhas[0]


def test_ignora_linhas_vazias_e_comentarios(pasta):
    svc = ArtifactService()
    _propor(pasta, "# instruções do agente\n\n[db] algo útil\n\n")
    assert svc.ler_propostas(pasta) == ["[db] algo útil"]


def test_limita_a_tres_linhas_por_tarefa(pasta):
    """Teto baixo de propósito: o sinal se dilui se o agente puder escrever muito."""
    svc = ArtifactService()
    _propor(pasta, "\n".join(f"[t] linha {i}" for i in range(10)))
    assert len(svc.ler_propostas(pasta)) == 3


def test_aprovar_registra_no_indice_do_projeto(pasta):
    svc = ArtifactService()
    svc.registrar_conhecimento(pasta, ["[db] WAL ligado, backup exige .backup"])

    indice = open(svc.indice_path(pasta), encoding="utf-8").read()
    assert SECAO_CONHECIMENTO in indice
    assert "WAL ligado" in indice


def test_aprovar_duas_vezes_nao_duplica(pasta):
    svc = ArtifactService()
    svc.registrar_conhecimento(pasta, ["[db] WAL ligado"])
    svc.registrar_conhecimento(pasta, ["[db] WAL ligado"])

    indice = open(svc.indice_path(pasta), encoding="utf-8").read()
    assert indice.count("WAL ligado") == 1


def test_conhecimento_e_artefatos_convivem_no_mesmo_indice(pasta):
    svc = ArtifactService()
    svc.registrar_conhecimento(pasta, ["[db] WAL ligado"])
    svc.registrar_no_indice(pasta, ["analise.md"], titulo_tarefa="Analisar")

    indice = open(svc.indice_path(pasta), encoding="utf-8").read()
    assert "WAL ligado" in indice
    assert "analise.md" in indice


def test_descartar_apaga_o_arquivo_de_propostas(pasta):
    svc = ArtifactService()
    _propor(pasta, "[x] algo")
    svc.limpar_propostas(pasta)
    assert svc.ler_propostas(pasta) == []


def test_instrucao_para_o_agente_deixa_claro_que_o_padrao_e_nada():
    """Sem isso o agente registra em toda tarefa e o índice vira ruído."""
    texto = ArtifactService().instrucao_de_conhecimento()
    assert PROPOSTAS_FILE.replace("\\", "/") in texto.replace("\\", "/")
    assert "não escreva nada" in texto.lower()
    assert len(texto) < 700  # cabe no prompt sem pesar
