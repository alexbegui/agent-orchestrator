"""
As instruções de COMO trabalhar que vão coladas no prompt do agente.

O prompt dizia onde salvar e o que registrar, e nunca como trabalhar. Sem
regra de comportamento, cada tarefa virava uma loteria de disciplina: um
agente escrevia teste, o seguinte não; um verificava antes de declarar pronto,
o seguinte declarava no escuro.

As regras aqui são as que ESTE repositório aprendeu na pele — estão na seção
"Armadilhas que já custaram caro" do CLAUDE.md, e cada uma custou um bug real.
"""
import os
import logging
from typing import Any, Dict, Optional

logger = logging.getLogger("orchestrator.prompt")

# Teto da memória do projeto alvo. CLAUDE.md de projeto grande chega a dezenas
# de KB; entrar inteiro no prompt de toda tarefa seria a §7.2 ao contrário —
# gastar contexto para economizar contexto.
MAX_MEMORIA = 8000

# Motores que leem o CLAUDE.md sozinhos, a partir do cwd (que é o worktree).
# Injetar para eles é pagar o mesmo token duas vezes.
LEEM_SOZINHOS = ("claude",)


def regras_de_trabalho() -> str:
    """
    Bloco fixo, igual em toda tarefa de todo projeto.

    É estático de propósito: fica no começo do prompt, onde o prompt caching
    casa prefixo. Regra que varia por tarefa quebraria o cache sem avisar.
    """
    return (
        "## Como trabalhar nesta tarefa\n"
        "1. **Teste primeiro.** Escreva o teste antes do código, rode e **veja-o "
        "falhar**, só então implemente. Teste que você nunca viu falhar não "
        "prova que testa a coisa certa.\n"
        "2. **Nunca declare sucesso sem evidência.** Se não deu para verificar, "
        "diga que não deu. Entrega declarada sem entrega manda o usuário caçar "
        "o motivo num diff vazio.\n"
        "3. **Não enfraqueça nem remova teste existente** para fazer o seu passar.\n"
        "4. **Leia os comentários da área antes de mudá-la.** Decisão que parece "
        "estranha costuma ser correção de bug real, e desfazê-la reintroduz o bug.\n"
    )


def le_o_claude_md_sozinho(runner_config: Optional[Dict[str, Any]]) -> bool:
    """O motor desta tarefa já lê o CLAUDE.md do projeto por conta própria?"""
    cli = str((runner_config or {}).get("cli", "")).lower()
    return any(nome in cli for nome in LEEM_SOZINHOS)


def memoria_do_projeto(root_path: str, runner_config: Optional[Dict[str, Any]]) -> str:
    """
    O CLAUDE.md do projeto ALVO, para os motores que não o leem sozinhos.

    O agy e a API direta não têm esse comportamento, então sem isto eles
    trabalham sem saber nada das armadilhas do projeto — e repetem bugs que o
    projeto já documentou.
    """
    if not root_path or le_o_claude_md_sozinho(runner_config):
        return ""

    caminho = os.path.join(root_path, "CLAUDE.md")
    if not os.path.isfile(caminho):
        return ""

    try:
        with open(caminho, "r", encoding="utf-8", errors="replace") as f:
            texto = f.read().strip()
    except OSError as e:
        logger.warning(f"Não foi possível ler o CLAUDE.md de {root_path}: {e}")
        return ""

    if not texto:
        return ""

    if len(texto) > MAX_MEMORIA:
        texto = texto[:MAX_MEMORIA] + "\n…(memória do projeto truncada)"

    return f"## Memória deste projeto (CLAUDE.md)\n{texto}\n"


def instrucao_de_entrega(worktree_path: str) -> str:
    """
    Pede o sumário de entrega ao agente.

    Quem escreve é ele, não o orquestrador: gerar a partir do diff exigiria
    uma chamada de IA, e o diff não sabe o que ele TENTOU e falhou.

    O pedido do "o que NÃO fiz" é a parte que mais importa e a que o agente
    mais omite — sem perguntar, ele escreve só a vitória, e o que ficou de
    fora você só descobre depois de aprovar.
    """
    if not worktree_path:
        return ""
    return (
        "\n## Sumário de entrega (obrigatório ao terminar)\n"
        f"Antes de encerrar, escreva `{worktree_path}/.agent/artefatos/walkthrough.md` "
        "com exatamente três seções curtas:\n"
        "- `# O que mudou` — em 3 linhas, o que o revisor precisa entender antes de "
        "abrir o diff.\n"
        "- `# Como validei` — o comando que você rodou e o resultado real. Se não "
        "rodou nada, escreva que não rodou.\n"
        "- `# O que NÃO fiz` — o que ficou de fora, o que tentou e falhou, e o que "
        "você assumiu sem confirmar.\n"
        "Não escreva o que o diff já conta, arquivo por arquivo.\n"
    )
