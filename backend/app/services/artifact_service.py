import os
import logging
from typing import List, Dict, Any, Optional

logger = logging.getLogger("orchestrator.artifacts")

# Pasta separada da documentação que o usuário escreve à mão — fica claro
# o que foi produzido em tarefa, e o agente não polui os docs do projeto.
ARTIFACT_DIR = os.path.join(".agent", "artefatos")
INDEX_FILE = os.path.join(".agent", "CONHECIMENTO.md")

SECAO_ARTEFATOS = "## Artefatos deste projeto"
SECAO_CONHECIMENTO = "## O que já aprendemos"

# Rascunho onde o agente propõe linhas. Não é o índice: o agente nunca
# escreve nele direto — dois agentes paralelos dariam conflito de merge.
PROPOSTAS_FILE = os.path.join(".agent", "_proposto.md")

# Teto baixo de propósito: com muito espaço o agente registra trivialidades
# e o sinal se perde no ruído.
MAX_PROPOSTAS = 3

KINDS = {
    ".md": "markdown", ".markdown": "markdown",
    ".html": "html", ".htm": "html",
}

# Categoria é o que o usuário vê agrupado na aba. "Mapa mental" não é
# "mais um texto" — precisa aparecer separado para ser encontrável.
CATEGORIAS_POR_EXT = {
    ".md": "documento", ".markdown": "documento", ".txt": "documento",
    ".html": "mockup", ".htm": "mockup",
    ".svg": "diagrama", ".mmd": "diagrama", ".drawio": "diagrama",
    ".png": "imagem", ".jpg": "imagem", ".jpeg": "imagem",
    ".gif": "imagem", ".webp": "imagem",
    ".json": "dados", ".csv": "dados", ".tsv": "dados", ".yaml": "dados", ".yml": "dados",
}

CONTENT_TYPES = {
    ".html": "text/html; charset=utf-8", ".htm": "text/html; charset=utf-8",
    ".md": "text/markdown; charset=utf-8", ".markdown": "text/markdown; charset=utf-8",
    ".txt": "text/plain; charset=utf-8",
    ".svg": "image/svg+xml",
    ".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
    ".gif": "image/gif", ".webp": "image/webp",
    ".json": "application/json; charset=utf-8",
    ".csv": "text/csv; charset=utf-8",
}

# Um .md pode ser texto comum OU um mapa mental/diagrama. Decide pelo conteúdo.
MARCAS_DE_DIAGRAMA = ("```mermaid", "~~~mermaid", "```mindmap")

# Teto do que vai no prompt. Se o índice passar disso, é sinal de poda —
# não de aumentar o limite.
MAX_CONTEXTO = 4000


class ArtifactService:
    """
    Artefatos pertencem à tarefa que os criou E ao projeto.

    Não há sincronização entre os dois: é o mesmo arquivo em disco. Enquanto
    a tarefa está aberta ele vive no worktree; depois do merge, no projeto.
    A promoção é o próprio merge — quem faz é o git, não código nosso.
    """

    def dir(self, base: str) -> str:
        return os.path.join(base, ARTIFACT_DIR)

    def indice_path(self, base: str) -> str:
        return os.path.join(base, INDEX_FILE)

    def listar(self, base: str) -> List[Dict[str, Any]]:
        pasta = self.dir(base)
        if not base or not os.path.isdir(pasta):
            return []

        itens = []
        for nome in sorted(os.listdir(pasta)):
            caminho = os.path.join(pasta, nome)
            if not os.path.isfile(caminho):
                continue
            ext = os.path.splitext(nome)[1].lower()
            try:
                st = os.stat(caminho)
            except OSError:
                continue
            categoria, preview = self._classificar(caminho, ext)
            itens.append({
                "name": nome,
                "kind": KINDS.get(ext, "other"),
                "category": categoria,
                "preview": preview,
                "size": st.st_size,
                "modified_at": st.st_mtime,
                "path": caminho,
            })
        return itens

    def _classificar(self, caminho: str, ext: str) -> tuple:
        """
        Devolve (categoria, resumo). Para texto, espia o começo do arquivo:
        é o que distingue um mapa mental de uma análise, e dá ao usuário uma
        pista do conteúdo sem precisar abrir.
        """
        categoria = CATEGORIAS_POR_EXT.get(ext, "outro")
        preview = ""

        if categoria not in ("documento", "dados"):
            return categoria, preview

        try:
            with open(caminho, "r", encoding="utf-8", errors="replace") as f:
                inicio = f.read(2000)
        except OSError:
            return categoria, preview

        if categoria == "documento" and any(m in inicio for m in MARCAS_DE_DIAGRAMA):
            categoria = "diagrama"

        for linha in inicio.splitlines():
            limpa = linha.strip().lstrip("#").strip()
            if limpa and not limpa.startswith("```"):
                preview = limpa[:120]
                break

        return categoria, preview

    def content_type(self, nome: str) -> str:
        """Sem o tipo certo, o navegador baixa o arquivo em vez de exibir."""
        ext = os.path.splitext(nome)[1].lower()
        return CONTENT_TYPES.get(ext, "application/octet-stream")

    def ler_bytes(self, base: str, nome: str) -> Optional[bytes]:
        """Para servir imagens e HTML direto no navegador."""
        alvo = self._resolver(base, nome)
        if not os.path.isfile(alvo):
            return None
        try:
            with open(alvo, "rb") as f:
                return f.read()
        except OSError as e:
            logger.warning(f"Falha lendo artefato {alvo}: {e}")
            return None

    def _resolver(self, base: str, nome: str) -> str:
        """
        Impede que um nome como `../../.env` leia qualquer arquivo da máquina.
        O caminho resolvido precisa continuar dentro da pasta de artefatos.
        """
        pasta = os.path.abspath(self.dir(base))
        alvo = os.path.abspath(os.path.join(pasta, nome))
        if os.path.commonpath([pasta, alvo]) != pasta:
            raise ValueError(f"Caminho fora da pasta de artefatos: {nome}")
        return alvo

    def ler(self, base: str, nome: str) -> Optional[str]:
        alvo = self._resolver(base, nome)
        if not os.path.isfile(alvo):
            return None
        try:
            with open(alvo, "r", encoding="utf-8", errors="replace") as f:
                return f.read()
        except OSError as e:
            logger.warning(f"Falha lendo artefato {alvo}: {e}")
            return None

    def registrar_no_indice(
        self, base: str, nomes: List[str], titulo_tarefa: str
    ) -> None:
        """
        Acrescenta uma linha por artefato novo ao índice do projeto.

        Usa o título da tarefa como descrição — sem chamar modelo, custo zero.
        Não duplica: se o artefato já está listado, ignora.
        """
        if not nomes:
            return

        caminho = self.indice_path(base)
        os.makedirs(os.path.dirname(caminho), exist_ok=True)

        texto = ""
        if os.path.exists(caminho):
            try:
                with open(caminho, "r", encoding="utf-8") as f:
                    texto = f.read()
            except OSError:
                texto = ""

        novos = [n for n in nomes if f"`{n}`" not in texto]
        if not novos:
            return

        if SECAO_ARTEFATOS not in texto:
            if texto and not texto.endswith("\n"):
                texto += "\n"
            texto += f"\n{SECAO_ARTEFATOS}\n"

        linhas = "".join(f"- `{n}` — {titulo_tarefa}\n" for n in novos)

        # Insere logo abaixo do cabeçalho da seção, não no fim do arquivo
        partes = texto.split(SECAO_ARTEFATOS, 1)
        resto = partes[1].lstrip("\n")
        texto = f"{partes[0]}{SECAO_ARTEFATOS}\n{linhas}{resto}"

        try:
            with open(caminho, "w", encoding="utf-8") as f:
                f.write(texto)
        except OSError as e:
            logger.warning(f"Falha escrevendo o índice {caminho}: {e}")

    # ---------- linhas de conhecimento ----------

    def propostas_path(self, base: str) -> str:
        return os.path.join(base, PROPOSTAS_FILE)

    def ler_propostas(self, base: str) -> List[str]:
        """Linhas que o agente propôs durante a tarefa. Vazio é o normal."""
        caminho = self.propostas_path(base)
        if not base or not os.path.exists(caminho):
            return []
        try:
            with open(caminho, "r", encoding="utf-8", errors="replace") as f:
                bruto = f.read()
        except OSError:
            return []

        linhas = []
        for linha in bruto.splitlines():
            limpa = linha.strip().lstrip("-").strip()
            if not limpa or limpa.startswith("#"):
                continue
            linhas.append(limpa)
            if len(linhas) >= MAX_PROPOSTAS:
                break
        return linhas

    def limpar_propostas(self, base: str) -> None:
        caminho = self.propostas_path(base)
        try:
            if os.path.exists(caminho):
                os.remove(caminho)
        except OSError as e:
            logger.warning(f"Falha ao remover {caminho}: {e}")

    def registrar_conhecimento(self, base: str, linhas: List[str]) -> None:
        """
        Grava as linhas aprovadas pelo usuário no índice do projeto.

        Quem escreve é o backend, no repo principal — nunca o agente na sua
        worktree, senão dois agentes paralelos gerariam conflito de merge.
        """
        self._acrescentar_na_secao(
            base, SECAO_CONHECIMENTO,
            [f"- {l}\n" for l in linhas],
            chave=lambda l: l,
        )

    def _acrescentar_na_secao(self, base, secao, linhas_formatadas, chave):
        caminho = self.indice_path(base)
        os.makedirs(os.path.dirname(caminho), exist_ok=True)

        texto = ""
        if os.path.exists(caminho):
            try:
                with open(caminho, "r", encoding="utf-8") as f:
                    texto = f.read()
            except OSError:
                texto = ""

        novas = [l for l in linhas_formatadas if l.strip("- \n") not in texto]
        if not novas:
            return

        if secao not in texto:
            if texto and not texto.endswith("\n"):
                texto += "\n"
            texto += f"\n{secao}\n"

        partes = texto.split(secao, 1)
        resto = partes[1].lstrip("\n")
        texto = f"{partes[0]}{secao}\n{''.join(novas)}{resto}"

        try:
            with open(caminho, "w", encoding="utf-8") as f:
                f.write(texto)
        except OSError as e:
            logger.warning(f"Falha escrevendo o índice {caminho}: {e}")

    def instrucao_de_conhecimento(self) -> str:
        """
        Vai colada no prompt do agente. Curta e com o padrão explícito em
        "não escreva nada" — sem isso ele registra em toda tarefa e o índice
        vira ruído, que é exatamente o que sufoca o usuário.
        """
        return (
            "## Registro de conhecimento (opcional)\n"
            "Se — e somente se — você descobrir algo NÃO ÓBVIO sobre este projeto "
            "que um agente futuro erraria por não saber, escreva até 3 linhas em "
            f"`{PROPOSTAS_FILE}`, no formato `[tags] afirmação`.\n"
            "Não registre o que o diff já conta (arquivos alterados, o que foi feito). "
            "Registre o porquê, o que você tentou e falhou, e armadilhas.\n"
            "**Na maioria das tarefas, não escreva nada.**\n"
        )

    def contexto_para_prompt(self, base: str) -> str:
        """
        O que vai colado no prompt do agente: APENAS o índice.

        Os artefatos em si nunca entram — o agente vê que existem e abre só
        se a tarefa pedir. É isso que mantém o custo fixo e baixo.
        """
        caminho = self.indice_path(base)
        if not base or not os.path.exists(caminho):
            return ""
        try:
            with open(caminho, "r", encoding="utf-8", errors="replace") as f:
                texto = f.read().strip()
        except OSError:
            return ""

        if not texto:
            return ""

        if len(texto) > MAX_CONTEXTO:
            texto = texto[:MAX_CONTEXTO] + "\n…(índice truncado — considere podar)"

        return (
            "## Conhecimento acumulado deste projeto\n"
            f"{texto}\n\n"
            f"Os arquivos citados estão em `{ARTIFACT_DIR}`. "
            "Abra apenas os que forem relevantes para esta tarefa.\n"
        )


artifact_service = ArtifactService()
