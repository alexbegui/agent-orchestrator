"""
Prompt caching no refino — §7.2 item 1 da spec de 08/10.

O caching é um casamento de PREFIXO: qualquer byte diferente no começo invalida
tudo depois dele. Então a economia não vem de "ligar o cache", vem de arrumar a
ordem do prompt: o que não muda entre refinos do mesmo projeto (instruções,
índice de conhecimento, árvore de arquivos) vem primeiro e leva a marca; o
pedido do usuário, que muda a cada tarefa, vem depois.

Pôr o pedido antes da árvore — que era a ordem anterior — faz o cache nunca
acertar, sem erro nenhum: só `cache_read_input_tokens: 0` para sempre.
"""
import pytest

from app.services.assistant_service import (
    montar_blocos_cacheaveis,
    MIN_CHARS_PARA_CACHE,
)
from app.services.refiner_service import PromptRefinerService


PREFIXO_GRANDE = "instruções estáveis\n" + "\n".join(f"src/arquivo_{i}.py" for i in range(400))


def test_o_que_nao_muda_vem_primeiro_e_leva_a_marca():
    blocos = montar_blocos_cacheaveis(PREFIXO_GRANDE, "quero calcular frete")

    assert blocos[0]["text"] == PREFIXO_GRANDE
    assert blocos[0]["cache_control"] == {"type": "ephemeral"}


def test_o_pedido_do_usuario_fica_fora_do_trecho_cacheado():
    """Se o pedido entrasse no bloco marcado, cada tarefa nova invalidaria o cache."""
    blocos = montar_blocos_cacheaveis(PREFIXO_GRANDE, "quero calcular frete")

    assert blocos[-1]["text"] == "quero calcular frete"
    assert "cache_control" not in blocos[-1]


def test_prefixo_curto_demais_nao_recebe_marca():
    """
    Abaixo do mínimo do modelo (512 tokens no Opus 5.5) a marca não cacheia nada
    e não dá erro — fica `cache_creation_input_tokens: 0` em silêncio. Preferimos
    não marcar a fingir que marcamos.
    """
    blocos = montar_blocos_cacheaveis("oi", "quero calcular frete")

    assert all("cache_control" not in b for b in blocos)


def test_sem_prefixo_manda_so_o_pedido():
    blocos = montar_blocos_cacheaveis("", "quero calcular frete")

    assert len(blocos) == 1
    assert blocos[0]["text"] == "quero calcular frete"


def test_limiar_de_marcacao_cobre_o_minimo_do_modelo():
    """~4 caracteres por token; 512 tokens ≈ 2048 caracteres."""
    assert MIN_CHARS_PARA_CACHE >= 2048


# --- O refino monta o prompt na ordem certa ---------------------------------

@pytest.mark.asyncio
async def test_arvore_e_conhecimento_vao_no_prefixo_estavel():
    """
    São iguais para toda tarefa do mesmo projeto — é exatamente o que repete
    entre refinos e, portanto, o que vale cachear.
    """
    capturado = {}

    async def motor(prompt: str, prefixo: str = "") -> str:
        capturado["prefixo"] = prefixo
        capturado["pedido"] = prompt
        return '{"arquivos": [{"caminho": "app/frete.py", "motivo": "x"}]}'

    refiner = PromptRefinerService(motor=motor)
    await refiner._escolher_arquivos(
        "quero calcular frete",
        texto_arvore="app/frete.py\napp/main.py",
        conhecimento="## Conhecimento acumulado\nO projeto usa master.",
        permitidos={"app/frete.py", "app/main.py"},
    )

    assert "app/frete.py" in capturado["prefixo"]
    assert "master" in capturado["prefixo"]
    assert "quero calcular frete" not in capturado["prefixo"]
    assert "quero calcular frete" in capturado["pedido"]
