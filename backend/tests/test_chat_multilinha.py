"""
O chat perdia a pergunta do usuário no Claude Code.

Mesmo defeito do despacho, no outro caminho do código: `claude.cmd` é arquivo
batch, e o cmd.exe corta o argumento na primeira quebra de linha (medido: 90
caracteres em 6 linhas entraram, 1 linha saiu).

DUAS FORMAS, E A PRIMEIRA É PIOR:

1. PRIMEIRA mensagem de qualquer chat. O prompt montado tem `\\n\\n` ANTES de
   "Mensagem do usuário:", então a pergunta era descartada INTEIRA — mesmo
   com uma linha só. O agente recebia só o preâmbulo de papel e respondia
   algo genérico sobre a tarefa. Pior ainda quando a tarefa tem spec
   refinada: `task_prompt` é multilinha e o corte cai no meio do preâmbulo.

2. Mensagens SEGUINTES (--resume). Só corta se a mensagem tiver mais de uma
   linha — colar um erro, escrever em tópicos, apertar Shift+Enter.

É um defeito SILENCIOSO: o agente responde normalmente, coerente com o pedaço
que recebeu. Não há sintoma; o usuário conclui que ele "não entendeu" e
repete a pergunta.

O agy não é afetado: é .exe de verdade e recebe `-p=<prompt>`.
"""
import pytest
from unittest.mock import patch

from app.services.assistant_service import AssistantService


class ProcessoFalso:
    """Captura o que foi mandado pela entrada padrão."""
    returncode = 0

    def __init__(self):
        self.recebido_no_stdin = None

    async def communicate(self, input=None):
        self.recebido_no_stdin = input.decode("utf-8") if input else None
        return b"resposta do agente", b""

    def kill(self):
        pass


@pytest.fixture
def espiao():
    """Devolve (servico, captura) — captura traz o comando e o stdin."""
    servico = AssistantService()
    captura = {}
    proc = ProcessoFalso()

    async def falso_exec(*cmd, **kwargs):
        captura["cmd"] = list(cmd)
        captura["proc"] = proc
        return proc

    servico._espiao_proc = proc
    servico._espiao_captura = captura
    servico._falso_exec = falso_exec
    return servico, captura


async def _conversar(servico, captura, mensagem, sessao=None):
    with patch.object(servico, "_find_claude_cmd", return_value=r"C:\npm\claude.cmd"), \
         patch("asyncio.create_subprocess_exec", new=servico._falso_exec):
        return await servico._call_claude_cli(
            task_id="t1", task_title="Arrumar o frete",
            task_prompt="## Objetivo\nCalcular frete\n\n## Passos\n1. fazer",
            user_message=mensagem,
            project_name="Projeto", project_root=".", session_id=sessao,
        )


MENSAGEM_DE_TRES_LINHAS = (
    "O teste de frete está falhando.\n"
    "O erro é ZeroDivisionError na linha 40.\n"
    "Pode ver?"
)


@pytest.mark.asyncio
async def test_primeira_mensagem_do_chat_chega_ao_agente(espiao):
    """
    A pergunta do usuário era descartada inteira: o `\\n\\n` do preâmbulo
    cortava antes dela.
    """
    servico, captura = espiao

    await _conversar(servico, captura, "por que você fez assim?")

    enviado = captura["proc"].recebido_no_stdin
    assert enviado is not None, "nada foi para a entrada padrão"
    assert "por que você fez assim?" in enviado


@pytest.mark.asyncio
async def test_mensagem_de_varias_linhas_chega_inteira(espiao):
    """Colar um erro é justamente quando mais contexto precisa chegar."""
    servico, captura = espiao

    await _conversar(servico, captura, MENSAGEM_DE_TRES_LINHAS, sessao="sessao-ja-existe")

    enviado = captura["proc"].recebido_no_stdin
    assert "ZeroDivisionError" in enviado
    assert "Pode ver?" in enviado


@pytest.mark.asyncio
async def test_nada_de_texto_longo_sobra_na_linha_de_comando(espiao):
    """
    Não existe escape que resolva: o texto precisa SAIR do argv. Se sobrar
    ali, o cmd.exe corta de novo.
    """
    servico, captura = espiao

    await _conversar(servico, captura, MENSAGEM_DE_TRES_LINHAS, sessao="sessao-ja-existe")

    for arg in captura["cmd"]:
        assert "\n" not in str(arg), f"argumento multilinha sobrou no comando: {arg!r}"
    assert not any("ZeroDivisionError" in str(a) for a in captura["cmd"])


@pytest.mark.asyncio
async def test_as_flags_que_fazem_funcionar_continuam(espiao):
    """Tirar o texto do comando não pode derrubar sessão nem modo de permissão."""
    servico, captura = espiao

    await _conversar(servico, captura, "oi", sessao="sessao-ja-existe")

    cmd = captura["cmd"]
    assert "-p" in cmd
    assert "--permission-mode" in cmd
    assert "--resume" in cmd
    assert "sessao-ja-existe" in cmd


@pytest.mark.asyncio
async def test_primeira_mensagem_ainda_cria_a_sessao(espiao):
    servico, captura = espiao

    await _conversar(servico, captura, "oi")

    assert "--session-id" in captura["cmd"]
    # E o id criado fica guardado para o chat seguinte retomar o MESMO agente.
    assert servico.get_task_conversation_id is not None
    assert servico._claude_sessions.get("t1")


@pytest.mark.asyncio
async def test_o_papel_do_agente_continua_sendo_dito(espiao):
    """O preâmbulo não pode sumir junto — ele só muda de lugar."""
    servico, captura = espiao

    await _conversar(servico, captura, "oi")

    enviado = captura["proc"].recebido_no_stdin
    assert "Engenheiro de Software" in enviado
    assert "Arrumar o frete" in enviado
