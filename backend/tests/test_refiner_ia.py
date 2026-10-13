"""
O refino passa a ser feito por IA, não por regex.

O serviço antigo devolvia critérios de aceite constantes e escolhia arquivos
casando substring do prompt contra o caminho — dois pedidos sem relação
nenhuma recebiam a mesma lista. Era um portão de aprovação com nada atrás.

Estes testes travam o contrato novo: a spec vem da IA, traz plano de testes,
e quando a IA não responde a tarefa NÃO avança — porque aprovar uma spec
genérica achando que é da IA é pior que não ter spec.

Nenhum teste aqui toca a rede: o motor é injetado.
"""
import json
import pytest

from app.services.refiner_service import (
    PromptRefinerService,
    RefinedSpec,
    RespostaInvalida,
    montar_arvore,
    TETO_ARVORE,
)
from app.services.assistant_service import MotorIndisponivel


def motor_falso(*respostas: str):
    """Devolve as respostas na ordem em que o serviço pedir."""
    fila = list(respostas)

    async def motor(prompt: str, prefixo: str = "") -> str:
        if not fila:
            raise AssertionError("o serviço pediu mais respostas do que o teste preparou")
        return fila.pop(0)

    return motor


ESCOLHA_OK = json.dumps({
    "arquivos": [
        {"caminho": "app/services/frete.py", "motivo": "é onde o cálculo vive"},
        {"caminho": "tests/test_frete.py", "motivo": "o teste do cálculo"},
    ]
})

SPEC_OK = json.dumps({
    "objective": "Expor o cálculo de frete como endpoint POST /frete",
    "steps": [
        "Escrever o teste do endpoint",
        "Criar a rota chamando calcular_frete",
    ],
    "acceptance_criteria": [
        "POST /frete com CEP válido devolve 200 e o valor",
        "CEP inválido devolve 422",
    ],
    "tests": [
        {
            "arquivo": "tests/test_frete.py",
            "nome": "test_frete_de_cep_valido_devolve_valor",
            "prova": "que a rota existe e devolve o valor calculado",
        }
    ],
})


ARVORE = ["app/services/frete.py", "tests/test_frete.py"]


def ler_fixo(caminho: str) -> str:
    return f"# conteúdo de {caminho}\n"


@pytest.mark.asyncio
async def test_a_spec_vem_da_ia_e_nao_do_prompt_cru():
    """O objetivo antigo era `raw_prompt.strip()` — uma cópia, não um refino."""
    refiner = PromptRefinerService(motor=motor_falso(ESCOLHA_OK, SPEC_OK))

    spec = await refiner.refinar(
        "quero calcular frete",
        arvore=["app/services/frete.py", "tests/test_frete.py"],
        ler=ler_fixo,
    )

    assert spec.objective != "quero calcular frete"
    assert "endpoint" in spec.objective
    assert spec.target_files == ["app/services/frete.py", "tests/test_frete.py"]


@pytest.mark.asyncio
async def test_criterios_de_aceite_sao_especificos_da_tarefa():
    """
    Os critérios do serviço antigo eram três constantes, iguais em toda tarefa.
    Um critério que não cita a tarefa não prova nada.
    """
    refiner = PromptRefinerService(motor=motor_falso(ESCOLHA_OK, SPEC_OK))

    spec = await refiner.refinar("quero calcular frete", arvore=ARVORE, ler=ler_fixo)

    assert any("frete" in c.lower() or "cep" in c.lower() for c in spec.acceptance_criteria)
    assert "Cobertura de testes automatizados passando 100%" not in spec.acceptance_criteria


@pytest.mark.asyncio
async def test_spec_traz_plano_de_testes_para_escrever_antes_do_codigo():
    refiner = PromptRefinerService(motor=motor_falso(ESCOLHA_OK, SPEC_OK))

    spec = await refiner.refinar("quero calcular frete", arvore=ARVORE, ler=ler_fixo)

    assert len(spec.tests) == 1
    assert spec.tests[0].arquivo == "tests/test_frete.py"
    assert spec.tests[0].nome.startswith("test_")
    assert spec.tests[0].prova


@pytest.mark.asyncio
async def test_a_ia_diz_por_que_escolheu_cada_arquivo():
    """Sem o motivo, você não tem como discordar da escolha antes de aprovar."""
    refiner = PromptRefinerService(motor=motor_falso(ESCOLHA_OK, SPEC_OK))

    spec = await refiner.refinar("quero calcular frete", arvore=ARVORE, ler=ler_fixo)

    assert spec.motivos["app/services/frete.py"] == "é onde o cálculo vive"


@pytest.mark.asyncio
async def test_resposta_que_nao_e_json_falha_em_vez_de_virar_spec():
    refiner = PromptRefinerService(motor=motor_falso("Claro! Vou te ajudar com isso."))

    with pytest.raises(RespostaInvalida):
        await refiner.refinar("qualquer coisa", arvore=["app/main.py"], ler=ler_fixo)


@pytest.mark.asyncio
async def test_json_sem_os_campos_obrigatorios_falha():
    """Pydantic é o portão: JSON bem formado mas vazio não vira spec."""
    refiner = PromptRefinerService(
        motor=motor_falso(ESCOLHA_OK, json.dumps({"objective": "só isso"}))
    )

    with pytest.raises(RespostaInvalida):
        await refiner.refinar("qualquer coisa", arvore=["app/main.py"], ler=ler_fixo)


@pytest.mark.asyncio
async def test_ia_que_inventa_arquivo_fora_da_arvore_e_recusada():
    """
    O serviço antigo chutava `app/main.py` quando nada casava — um caminho que
    podia não existir. Arquivo que não está na árvore não pode entrar na spec.
    """
    escolha_inventada = json.dumps({
        "arquivos": [{"caminho": "app/nao/existe.py", "motivo": "inventado"}]
    })
    refiner = PromptRefinerService(motor=motor_falso(escolha_inventada))

    with pytest.raises(RespostaInvalida):
        await refiner.refinar("qualquer coisa", arvore=["app/main.py"], ler=ler_fixo)


# --- Árvore enviada à IA -----------------------------------------------------

def test_arvore_pequena_vai_inteira_e_sem_aviso():
    texto, aviso = montar_arvore(["app/main.py", "tests/test_main.py"])

    assert "app/main.py" in texto
    assert aviso is None


def test_arvore_grande_e_truncada_com_aviso_visivel():
    """
    Spec gerada a partir de meia árvore, sem avisar, parece completa e não é.
    "Nunca declare sucesso sem evidência" vale para a spec também.
    """
    muitos = [f"src/modulo_{i:05d}.py" for i in range(20000)]

    texto, aviso = montar_arvore(muitos)

    assert len(texto) <= TETO_ARVORE
    assert aviso is not None
    assert "truncad" in aviso.lower()
    assert "20000" in aviso


def test_arquivos_mexidos_recentemente_sobrevivem_ao_corte():
    """
    Quando não cabe tudo, o que o projeto está mexendo tem mais chance de ser
    o alvo do que o que não muda há anos.
    """
    muitos = [f"src/modulo_{i:05d}.py" for i in range(20000)]
    alvo = "src/modulo_19999.py"  # ficaria de fora num corte pela ordem natural

    texto, _ = montar_arvore(muitos, recentes=[alvo])

    assert alvo in texto


def test_arquivo_que_nao_e_codigo_fica_de_fora():
    texto, _ = montar_arvore(["app/main.py", "logo.png", "yarn.lock", "foto.jpg"])

    assert "app/main.py" in texto
    assert "logo.png" not in texto
    assert "yarn.lock" not in texto


# --- Markdown ----------------------------------------------------------------

def test_markdown_mostra_plano_de_testes_e_motivos():
    spec = RefinedSpec(
        objective="Expor o cálculo de frete",
        target_files=["app/services/frete.py"],
        motivos={"app/services/frete.py": "é onde o cálculo vive"},
        steps=["Escrever o teste"],
        acceptance_criteria=["POST /frete devolve 200"],
        tests=[{"arquivo": "tests/test_frete.py", "nome": "test_frete", "prova": "que a rota existe"}],
    )

    md = PromptRefinerService(motor=motor_falso()).to_markdown(spec)

    assert "## Plano de Testes" in md
    assert "test_frete" in md
    assert "é onde o cálculo vive" in md


def test_markdown_carrega_o_aviso_de_truncamento():
    spec = RefinedSpec(
        objective="x",
        target_files=["a.py"],
        steps=["y"],
        acceptance_criteria=["z"],
        aviso="A árvore foi truncada em 500 de 20000 arquivos.",
    )

    md = PromptRefinerService(motor=motor_falso()).to_markdown(spec)

    assert "truncada" in md


# --- Motor -------------------------------------------------------------------

@pytest.mark.asyncio
async def test_sem_chave_de_api_o_motor_recusa_em_vez_de_inventar(monkeypatch):
    """
    Não existe mais queda para o regex. O motor local do chat também não serve:
    ele não escreve código, e a spec dele seria genérica como a do regex era.
    """
    from app.services.assistant_service import AssistantService

    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)

    with pytest.raises(MotorIndisponivel) as erro:
        await AssistantService().completar_json("qualquer prompt")

    assert "chave" in str(erro.value).lower()
