"""
Sumário de entrega — §8 e §7.2 item 3 da spec de 08/10.

O agente terminava, o card ficava roxo em "Entregou · revisar", e você abria
um diff cru sem nenhuma pista do que procurar. Revisar 500 linhas é caro, e
você faz isso várias vezes por dia com vários agentes.

Quem ESCREVE o sumário é o agente, instruído pelo prompt — não o orquestrador
gerando a partir do diff, que exigiria uma chamada de IA. O orquestrador ACHA
e mostra.

E se o agente não escrever, a tela diz que não escreveu. Inventar um sumário a
partir do diff seria declarar entrega sem evidência de entrega.
"""
import pytest

from app.services.artifact_service import ArtifactService, NOME_WALKTHROUGH


@pytest.fixture
def servico():
    return ArtifactService()


@pytest.fixture
def worktree(tmp_path):
    wt = tmp_path / "worktree"
    (wt / ".agent" / "artefatos").mkdir(parents=True)
    return wt


SUMARIO = """# O que mudou
Troquei o cálculo de frete para usar a tabela nova.

# Como validei
`pytest tests/test_frete.py` — 4 testes, todos verdes.

# O que NÃO fiz
Não mexi no frete internacional; a tabela nova não cobre.
"""


def test_acha_o_sumario_que_o_agente_deixou(servico, worktree):
    (worktree / ".agent" / "artefatos" / NOME_WALKTHROUGH).write_text(SUMARIO, encoding="utf-8")

    achado = servico.achar_walkthrough(str(worktree))

    assert achado is not None
    assert "tabela nova" in achado["conteudo"]


def test_acha_mesmo_se_o_agente_salvou_na_raiz_do_worktree(servico, worktree):
    """
    O agente navega durante o trabalho e nem sempre salva onde mandaram — é o
    mesmo motivo de `listar_amplo` existir. Sumário que existe e não aparece
    é pior que sumário ausente: você conclui que ele não escreveu.
    """
    (worktree / NOME_WALKTHROUGH).write_text(SUMARIO, encoding="utf-8")

    achado = servico.achar_walkthrough(str(worktree))

    assert achado is not None
    assert "tabela nova" in achado["conteudo"]


def test_sem_sumario_devolve_nada_em_vez_de_inventar(servico, worktree):
    """Inventar a partir do diff seria declarar entrega sem evidência."""
    assert servico.achar_walkthrough(str(worktree)) is None


def test_worktree_inexistente_nao_quebra(servico, tmp_path):
    assert servico.achar_walkthrough(str(tmp_path / "nao_existe")) is None


def test_sumario_vazio_conta_como_ausente(servico, worktree):
    """Arquivo criado e deixado em branco não é entrega."""
    (worktree / ".agent" / "artefatos" / NOME_WALKTHROUGH).write_text("   \n", encoding="utf-8")

    assert servico.achar_walkthrough(str(worktree)) is None


def test_sumario_gigante_e_truncado(servico, worktree):
    """Sumário que não cabe na tela deixa de ser sumário."""
    from app.services.artifact_service import MAX_WALKTHROUGH

    (worktree / ".agent" / "artefatos" / NOME_WALKTHROUGH).write_text(
        "linha de sumário\n" * 5000, encoding="utf-8"
    )

    achado = servico.achar_walkthrough(str(worktree))

    assert len(achado["conteudo"]) <= MAX_WALKTHROUGH + 200
    assert achado["truncado"] is True
