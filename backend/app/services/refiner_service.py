import json
import re
from typing import Callable, Optional, Awaitable

from pydantic import BaseModel, Field, ValidationError

# Teto do texto da árvore de arquivos que vai no prompt. ~20 mil caracteres são
# ~5 mil tokens: cabe com folga nos projetos reais do usuário (o maior tem 305
# arquivos versionados, ~9,6 mil caracteres) e ainda assim impede que um
# monorepo transforme um refino numa conta de dezenas de milhares de tokens.
TETO_ARVORE = 20000

# Extensões que não ajudam a IA a escolher onde mexer e só ocupam a árvore.
EXTENSOES_IGNORADAS = {
    ".png", ".jpg", ".jpeg", ".gif", ".ico", ".svg", ".webp", ".bmp",
    ".pdf", ".zip", ".gz", ".tar", ".7z", ".exe", ".dll", ".so", ".dylib",
    ".woff", ".woff2", ".ttf", ".eot", ".mp4", ".mp3", ".wav",
    ".lock", ".map", ".min.js", ".min.css", ".pyc",
}

ARQUIVOS_IGNORADOS = {
    "package-lock.json", "yarn.lock", "pnpm-lock.yaml", "poetry.lock",
    "Cargo.lock", "composer.lock",
}

# Quanto de cada arquivo escolhido vai no prompt da segunda chamada. Arquivo
# gigante inteiro estoura o custo sem melhorar a spec.
TETO_POR_ARQUIVO = 12000


class RespostaInvalida(Exception):
    """
    A IA respondeu, mas o que veio não é uma spec utilizável.

    Prosa em vez de JSON, campos faltando, ou arquivo que não existe na
    árvore. Sempre erro, nunca conserto por heurística: o valor da spec é
    você poder confiar que ela diz o que a IA realmente entendeu.
    """


class PlanoDeTeste(BaseModel):
    arquivo: str = Field(description="Arquivo de teste a criar ou editar")
    nome: str = Field(description="Nome da função de teste")
    prova: str = Field(description="O que esse teste prova")


class RefinedSpec(BaseModel):
    objective: str = Field(description="Objetivo principal da tarefa")
    target_files: list[str] = Field(default_factory=list, description="Arquivos afetados")
    motivos: dict[str, str] = Field(default_factory=dict, description="Por que cada arquivo foi escolhido")
    steps: list[str] = Field(default_factory=list, description="Passos atômicos de execução")
    acceptance_criteria: list[str] = Field(default_factory=list, description="Critérios de aceite")
    tests: list[PlanoDeTeste] = Field(default_factory=list, description="Testes a escrever ANTES do código")
    aviso: Optional[str] = Field(default=None, description="Ressalva sobre como a spec foi gerada")


def montar_arvore(
    arquivos: list[str],
    recentes: Optional[list[str]] = None,
    teto: int = TETO_ARVORE,
) -> tuple[str, Optional[str]]:
    """
    Monta o texto da árvore que vai no prompt, e o aviso quando ela não coube.

    Três etapas, nesta ordem (a segunda só acontece se a primeira não bastar):
    1. tira o que não é código — imagem, lockfile, binário;
    2. põe na frente o que o git mostra como mexido recentemente, porque numa
       árvore que não cabe o arquivo tocado esta semana é muito mais provável
       de ser o alvo que um que não muda há anos;
    3. corta no teto E DIZ QUE CORTOU.

    O aviso é a parte que importa: uma spec gerada a partir de meia árvore,
    sem avisar, parece completa e não é — o usuário aprovaria sem saber.
    """
    uteis = [a for a in arquivos if _vale_mandar(a)]
    total = len(arquivos)

    if recentes:
        ordem = {c: i for i, c in enumerate(recentes)}
        uteis.sort(key=lambda a: ordem.get(a, len(ordem)))

    incluidos: list[str] = []
    tamanho = 0
    for caminho in uteis:
        custo = len(caminho) + 1
        if tamanho + custo > teto:
            break
        incluidos.append(caminho)
        tamanho += custo

    texto = "\n".join(incluidos)
    if len(incluidos) < len(uteis):
        aviso = (
            f"A árvore foi truncada em {len(incluidos)} de {total} arquivos — "
            "os caminhos considerados podem estar incompletos. Se o alvo da "
            "tarefa não aparece nos arquivos abaixo, refaça apontando a pasta."
        )
        return texto, aviso
    return texto, None


def _vale_mandar(caminho: str) -> bool:
    nome = caminho.rsplit("/", 1)[-1]
    if nome in ARQUIVOS_IGNORADOS:
        return False
    minusculo = caminho.lower()
    return not any(minusculo.endswith(ext) for ext in EXTENSOES_IGNORADAS)


def _extrair_json(bruto: str) -> dict:
    """
    Tira o JSON da resposta, tolerando cerca de código — e só isso.

    Modelo às vezes embrulha em ```json apesar da instrução. O que NÃO se faz
    aqui é tentar adivinhar um objeto a partir de prosa: se não há JSON, a
    resposta não serve e vira RespostaInvalida.
    """
    texto = bruto.strip()
    cerca = re.match(r"^```(?:json)?\s*(.*?)\s*```$", texto, re.DOTALL)
    if cerca:
        texto = cerca.group(1).strip()
    try:
        dados = json.loads(texto)
    except (json.JSONDecodeError, ValueError):
        raise RespostaInvalida(
            f"A IA não devolveu JSON. Começo da resposta: {bruto[:200]!r}"
        )
    if not isinstance(dados, dict):
        raise RespostaInvalida("A IA devolveu JSON que não é um objeto.")
    return dados


class PromptRefinerService:
    """
    Converte uma ideia crua numa spec técnica — com IA, em duas chamadas.

    Por que duas e não uma: para escrever critérios de aceite específicos, a IA
    precisa ter LIDO o código envolvido. Numa chamada só, ela receberia apenas
    caminhos e escreveria critérios por adivinhação — que é o defeito do regex
    anterior com outra roupa. Então: primeiro escolhe os arquivos vendo a
    árvore (barato), depois especifica vendo o conteúdo deles (caro, mas só
    dos 2 a 5 que importam).
    """

    def __init__(self, motor: Optional[Callable[[str], Awaitable[str]]] = None):
        # Motor injetável: os testes passam um falso e nenhum deles toca a rede.
        self._motor = motor

    async def _perguntar(self, prompt: str, prefixo: str = "") -> str:
        """
        `prefixo` é a parte do prompt que NÃO muda entre tarefas do mesmo
        projeto, e vai marcada para prompt caching. Ver
        `assistant_service.montar_blocos_cacheaveis`.
        """
        if self._motor is not None:
            return await self._motor(prompt, prefixo)
        # Import tardio: assistant_service é pesado e só é necessário em
        # produção — os testes injetam o motor e nunca chegam aqui.
        from app.services.assistant_service import assistant_service
        return await assistant_service.completar_json(prompt, prefixo=prefixo)

    async def refinar(
        self,
        raw_prompt: str,
        arvore: list[str],
        ler: Callable[[str], str],
        recentes: Optional[list[str]] = None,
        conhecimento: str = "",
    ) -> RefinedSpec:
        texto_arvore, aviso = montar_arvore(arvore, recentes=recentes)
        permitidos = set(arvore)

        escolhas = await self._escolher_arquivos(raw_prompt, texto_arvore, conhecimento, permitidos)
        conteudos = self._ler_escolhidos(escolhas, ler)
        spec = await self._especificar(raw_prompt, escolhas, conteudos, conhecimento)

        spec.target_files = [e["caminho"] for e in escolhas]
        spec.motivos = {e["caminho"]: e["motivo"] for e in escolhas}
        spec.aviso = aviso
        return spec

    async def _escolher_arquivos(
        self, raw_prompt: str, texto_arvore: str, conhecimento: str, permitidos: set
    ) -> list[dict]:
        # A ORDEM AQUI É O QUE FAZ O CACHE FUNCIONAR. Instruções, conhecimento
        # e árvore são idênticos para toda tarefa deste projeto, então vão
        # primeiro, num bloco marcado. O pedido do usuário muda a cada tarefa e
        # vem depois. Inverter não dá erro: só faz o cache nunca acertar.
        prefixo = f"""Você é o engenheiro de especificação de um orquestrador de agentes.

Sua tarefa: dado o pedido de um usuário, escolher de 2 a 5 arquivos do projeto
que a tarefa provavelmente precisa tocar ou ler.

Regras:
- Use SOMENTE caminhos que aparecem na lista abaixo, copiados exatamente.
- Para cada arquivo, diga em uma frase curta por que ele foi escolhido.
- Se a tarefa pede um arquivo novo, escolha o arquivo existente mais próximo
  (o vizinho onde ele vai nascer), e diga isso no motivo.

Responda em JSON:
{{"arquivos": [{{"caminho": "...", "motivo": "..."}}]}}

{conhecimento}

## Arquivos do projeto
{texto_arvore}"""

        pedido = f"""## Pedido do usuário
{raw_prompt}"""

        dados = _extrair_json(await self._perguntar(pedido, prefixo))
        escolhas = dados.get("arquivos") or []
        if not isinstance(escolhas, list) or not escolhas:
            raise RespostaInvalida("A IA não escolheu nenhum arquivo.")

        limpas = []
        for item in escolhas:
            if not isinstance(item, dict) or not item.get("caminho"):
                raise RespostaInvalida(f"Escolha de arquivo malformada: {item!r}")
            caminho = str(item["caminho"]).replace("\\", "/").strip()
            # O serviço antigo chutava "app/main.py" quando nada casava — um
            # caminho que podia nem existir. Arquivo fora da árvore é alucinação
            # e invalida a spec inteira, porque o agente receberia uma ordem
            # para mexer em algo inexistente.
            if caminho not in permitidos:
                raise RespostaInvalida(
                    f"A IA escolheu '{caminho}', que não existe na árvore do projeto."
                )
            limpas.append({"caminho": caminho, "motivo": str(item.get("motivo", "")).strip()})
        return limpas

    def _ler_escolhidos(self, escolhas: list[dict], ler: Callable[[str], str]) -> dict[str, str]:
        conteudos = {}
        for escolha in escolhas:
            caminho = escolha["caminho"]
            try:
                texto = ler(caminho) or ""
            except OSError:
                # Arquivo listado pelo git mas ilegível agora (removido, lock do
                # Windows). Não derruba o refino: a IA especifica com o resto.
                texto = "(não foi possível ler este arquivo)"
            if len(texto) > TETO_POR_ARQUIVO:
                texto = texto[:TETO_POR_ARQUIVO] + "\n…(arquivo truncado)"
            conteudos[caminho] = texto
        return conteudos

    async def _especificar(
        self, raw_prompt: str, escolhas: list[dict], conteudos: dict[str, str], conhecimento: str
    ) -> RefinedSpec:
        blocos = "\n\n".join(
            f"### {caminho}\n```\n{texto}\n```" for caminho, texto in conteudos.items()
        )
        prompt = f"""Você é o engenheiro de especificação de um orquestrador de agentes.
Escreva a especificação técnica que será entregue a um agente de IA para
implementar o pedido abaixo. Quem vai ler isto não conhece o projeto.

Regras:
- Escreva em português.
- O objetivo deve ser uma frase técnica SUA, não uma cópia do pedido.
- Os critérios de aceite precisam ser verificáveis e citar o comportamento
  concreto desta tarefa. Critério genérico ("testes passando", "sem erro de
  lint") não serve e será rejeitado.
- O trabalho é feito com TDD: liste os testes a escrever ANTES do código,
  cada um com o arquivo, o nome da função e o que ele prova.

{conhecimento}

## Pedido do usuário
{raw_prompt}

## Conteúdo dos arquivos escolhidos
{blocos}

Responda em JSON:
{{"objective": "...",
  "steps": ["..."],
  "acceptance_criteria": ["..."],
  "tests": [{{"arquivo": "...", "nome": "test_...", "prova": "..."}}]}}"""

        dados = _extrair_json(await self._perguntar(prompt))
        try:
            # Pydantic é o portão: JSON bem formado mas sem os campos não vira
            # spec. Sem isso, uma resposta vazia viraria uma spec vazia de
            # aparência normal — o defeito que estamos consertando.
            return RefinedSpec(**dados)
        except ValidationError as e:
            raise RespostaInvalida(f"A spec devolvida está incompleta: {e}")

    def to_markdown(self, spec: RefinedSpec) -> str:
        if spec.target_files:
            linhas = []
            for f in spec.target_files:
                motivo = spec.motivos.get(f)
                linhas.append(f"- `{f}` — {motivo}" if motivo else f"- `{f}`")
            files_str = "\n".join(linhas)
        else:
            files_str = "- A definir"

        steps_str = "\n".join([f"{i+1}. {s}" for i, s in enumerate(spec.steps)]) if spec.steps else "1. Implementar funcionalidade"
        criteria_str = "\n".join([f"- [ ] {c}" for c in spec.acceptance_criteria]) if spec.acceptance_criteria else "- [ ] Testes passando"

        md = f"""## Objetivo
{spec.objective}

## Arquivos Alvo
{files_str}

## Passos de Execução
{steps_str}

## Critérios de Aceite
{criteria_str}
"""

        if spec.tests:
            testes_str = "\n".join(
                f"- `{t.arquivo}` → **{t.nome}** — prova {t.prova}" for t in spec.tests
            )
            md += f"""
## Plano de Testes (escrever ANTES do código)
{testes_str}
"""

        if spec.aviso:
            md += f"""
> ⚠️ {spec.aviso}
"""

        return md
