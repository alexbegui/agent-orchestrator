"""
O refino passa a usar o CLI da própria tarefa, sem chave de API.

O refino foi implementado chamando a API direta, que exige chave paga por
token. O usuário tem os CLIs logados na assinatura dele e nenhuma chave — o
botão ▶ Lapidar Prompt ficava inutilizável.

A objeção contra o CLI era "ele responde em prosa, não em JSON". Verificado
contra os CLIs reais em 13/10/2026: os DOIS aceitam `--json-schema` e OBRIGAM
a resposta ao esquema, e os dois devolvem o objeto no mesmo campo do envelope:

    agy    -p=<prompt> --json-schema <esq> --output-format json
    claude -p --json-schema <esq> --output-format json   (prompt por stdin)
    → {"...": ..., "structured_output": {<o objeto>}}

Isso é mais forte que o caminho de API como implementado, onde pedimos JSON no
texto e validamos depois.

Quem refina é o motor que VAI EXECUTAR a tarefa: a ordem de serviço sai na
linguagem de quem vai cumpri-la. A API continua disponível para quem tiver
chave e quiser velocidade — o agy levou 38s contra ~4s da API.
"""
import json
import pytest

from app.services.assistant_service import (
    AssistantService,
    MotorIndisponivel,
    montar_comando_json,
    extrair_structured_output,
)

ESQUEMA = {"type": "object", "properties": {"ok": {"type": "boolean"}}, "required": ["ok"]}


# --- Montagem do comando -----------------------------------------------------

def test_agy_recebe_prompt_na_flag_e_o_esquema():
    cmd, entrada = montar_comando_json(
        {"cli": "agy"}, prompt="qual arquivo?", prefixo="contexto", esquema=ESQUEMA,
        caminho_agy=r"C:\agy\agy.exe", caminho_claude=r"C:\npm\claude.cmd")

    assert cmd[0].endswith("agy.exe")
    # O agy toma o argumento seguinte a -p como prompt; a forma correta é -p=<prompt>.
    assert any(a.startswith("-p=") for a in cmd), cmd
    assert "--json-schema" in cmd
    assert "--output-format" in cmd and "json" in cmd
    assert entrada is None  # agy é .exe, o prompt cabe no argv


def test_claude_recebe_o_prompt_pela_entrada_padrao():
    """
    claude.cmd é batch e o cmd.exe corta o argumento na primeira quebra de
    linha. O prompt do refino tem muitas linhas — tem de ir por stdin.
    """
    cmd, entrada = montar_comando_json(
        {"cli": "claude"}, prompt="qual arquivo?", prefixo="linha1\nlinha2", esquema=ESQUEMA,
        caminho_agy=r"C:\agy\agy.exe", caminho_claude=r"C:\npm\claude.cmd")

    assert cmd[0].endswith("claude.cmd")
    assert "--json-schema" in cmd
    assert entrada is not None
    assert "linha1\nlinha2" in entrada
    assert not any("qual arquivo" in a for a in cmd), cmd


def test_o_esquema_vai_como_json_valido():
    cmd, _ = montar_comando_json(
        {"cli": "agy"}, prompt="x", prefixo="", esquema=ESQUEMA,
        caminho_agy=r"C:\agy\agy.exe", caminho_claude=r"C:\npm\claude.cmd")

    bruto = cmd[cmd.index("--json-schema") + 1]
    assert json.loads(bruto) == ESQUEMA


def test_o_esquema_cabe_numa_linha_so():
    """
    O esquema é argumento de linha de comando, e para o claude.cmd uma quebra
    de linha nele cortaria o argumento — o mesmo defeito do prompt.
    """
    cmd, _ = montar_comando_json(
        {"cli": "claude"}, prompt="x", prefixo="", esquema=ESQUEMA,
        caminho_agy=r"C:\agy\agy.exe", caminho_claude=r"C:\npm\claude.cmd")

    assert "\n" not in cmd[cmd.index("--json-schema") + 1]


def test_motor_desconhecido_nao_monta_comando():
    assert montar_comando_json(
        {"cli": "assistant"}, prompt="x", prefixo="", esquema=ESQUEMA,
        caminho_agy=None, caminho_claude=None) == (None, None)


def test_cli_ausente_no_disco_nao_monta_comando():
    """Configurado como agy, mas o agy não está instalado: não inventa caminho."""
    assert montar_comando_json(
        {"cli": "agy"}, prompt="x", prefixo="", esquema=ESQUEMA,
        caminho_agy=None, caminho_claude=r"C:\npm\claude.cmd") == (None, None)


# --- Leitura do envelope -----------------------------------------------------

ENVELOPE_AGY = json.dumps({
    "conversation_id": "abc", "status": "SUCCESS",
    "response": "{\"arquivos\":[]}\n",
    "structured_output": {"arquivos": [{"caminho": "app/frete.py", "motivo": "é aqui"}]},
})

ENVELOPE_CLAUDE = json.dumps({
    "type": "result", "is_error": False, "total_cost_usd": 0.15,
    "result": "{\"arquivos\":[]}",
    "structured_output": {"arquivos": [{"caminho": "app/frete.py", "motivo": "é aqui"}]},
})


@pytest.mark.parametrize("envelope", [ENVELOPE_AGY, ENVELOPE_CLAUDE], ids=["agy", "claude"])
def test_tira_o_objeto_do_envelope_dos_dois_clis(envelope):
    """Os dois CLIs usam o mesmo nome de campo — verificado nos binários reais."""
    saida = extrair_structured_output(envelope)

    assert json.loads(saida)["arquivos"][0]["caminho"] == "app/frete.py"


def test_envelope_sem_structured_output_e_recusado():
    """
    Sem o campo, o CLI não obedeceu ao esquema. Cair para o texto solto seria
    aceitar prosa como spec — o defeito que o regex tinha.
    """
    with pytest.raises(MotorIndisponivel):
        extrair_structured_output(json.dumps({"result": "Claro! Vou te ajudar."}))


def test_saida_que_nao_e_json_e_recusada():
    with pytest.raises(MotorIndisponivel):
        extrair_structured_output("Error: algo deu errado")


def test_saida_vazia_e_recusada():
    with pytest.raises(MotorIndisponivel):
        extrair_structured_output("")


# --- Ordem dos motores -------------------------------------------------------

@pytest.mark.asyncio
async def test_sem_cli_e_sem_chave_recusa_com_motivo_util(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    servico = AssistantService()
    monkeypatch.setattr(servico, "_find_claude_cmd", lambda: None)
    monkeypatch.setattr(servico, "_find_agy_cmd", lambda: None)

    with pytest.raises(MotorIndisponivel) as erro:
        await servico.completar_json("x", runner_config={"cli": "agy"})

    texto = str(erro.value).lower()
    assert "cli" in texto or "chave" in texto


# --- Teto de tempo -----------------------------------------------------------

def test_teto_cobre_o_pior_refino_medido():
    """
    Medido em 13/10/2026 num refino real de ponta a ponta: o agy levou 371s no
    TOTAL, entre as duas chamadas. O teto é POR CHAMADA, e estava em 300s — ou
    seja, uma única chamada mais pesada derrubaria o refino num projeto maior
    que o de teste.

    O teto existe para impedir que um CLI travado prenda a requisição para
    sempre, não para cortar trabalho legítimo. Ele precisa ficar acima do pior
    caso observado com folga, e esta prova trava isso: quem baixar o número
    sem medir de novo quebra aqui.
    """
    from app.services.assistant_service import REFINO_CLI_TIMEOUT

    PIOR_REFINO_MEDIDO = 371.0
    assert REFINO_CLI_TIMEOUT >= PIOR_REFINO_MEDIDO * 1.5


def test_a_mensagem_de_estouro_diz_quanto_esperou():
    """
    "Não respondeu" sozinho manda o usuário adivinhar se foram 5 segundos ou 10
    minutos — e se vale tentar de novo.
    """
    import inspect
    from app.services.assistant_service import AssistantService

    fonte = inspect.getsource(AssistantService._json_por_cli)
    assert "REFINO_CLI_TIMEOUT" in fonte
