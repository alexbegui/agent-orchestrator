"""
Localização dos CLIs externos num só lugar.

O `agy` era procurado em dois pontos (runner_service e assistant_service) com
cascatas parecidas mas não idênticas, e um terceiro ponto (api/settings) nem
procurava. Resolver num lugar só evita que eles voltem a divergir.
"""
import os
import shutil
from typing import Optional

from app.core.config import settings


def _existente(caminho: Optional[str]) -> Optional[str]:
    """
    Só devolve caminho que existe: uma string não-vazia é sempre verdadeira num
    `or`, o que tornaria o resto da cascata inalcançável e entregaria ao
    subprocess um caminho inválido (WinError 2).
    """
    return caminho if caminho and os.path.exists(caminho) else None


def find_agy() -> Optional[str]:
    """
    Localiza o CLI independente do Antigravity (`agy`), que não exige o IDE
    aberto nem ANTIGRAVITY_LS_ADDRESS/CSRF_TOKEN.

    Ordem: override absoluto em AGY_PATH -> PATH -> local do instalador.
    O fallback pelo local do instalador cobre o caso comum no Windows em que o
    instalador acrescentou %LOCALAPPDATA%\\agy\\bin ao PATH do usuário, mas o
    processo atual herdou um PATH anterior a isso.
    """
    configurado = getattr(settings, "AGY_PATH", None)

    # AGY_PATH tem dois usos: um caminho completo (override) ou só o nome do
    # executável a procurar no PATH. Separar os dois evita tratar o default
    # "agy" como se fosse um arquivo em disco.
    if configurado and os.path.isabs(configurado):
        achado = _existente(configurado)
        if achado:
            return achado
        configurado = None

    nomes = [n for n in [configurado, "agy", "agy.exe"] if n]
    for nome in nomes:
        achado = shutil.which(nome)
        if achado:
            return achado

    local_app_data = os.environ.get("LOCALAPPDATA")
    if local_app_data:
        achado = _existente(os.path.join(local_app_data, "agy", "bin", "agy.exe"))
        if achado:
            return achado

    # Sem LOCALAPPDATA (ou com ele redirecionado), ainda vale tentar o perfil.
    return _existente(os.path.expanduser("~/AppData/Local/agy/bin/agy.exe"))


def find_agentapi() -> Optional[str]:
    """
    Fallback legado: o agentapi embutido no IDE, que só funciona com o
    Antigravity aberto.
    """
    for nome in ["agentapi.bat", "agentapi"]:
        achado = shutil.which(nome)
        if achado:
            return achado
    return _existente(os.path.expanduser("~/.gemini/antigravity/bin/agentapi.bat"))
