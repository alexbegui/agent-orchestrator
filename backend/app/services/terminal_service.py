import os
import shutil
import logging
import subprocess
from typing import List

logger = logging.getLogger("orchestrator.terminal")


class TerminalService:
    """
    Abre um terminal nativo numa pasta do disco.

    O navegador não consegue fazer isso — mas o backend roda na máquina do
    usuário, então é ele quem dispara. Só faz sentido porque o orquestrador é
    local-first e o uvicorn escuta apenas em 127.0.0.1.
    """

    def build_command(self, path: str) -> List[str]:
        """Monta o comando conforme o terminal disponível, do melhor para o mais básico."""
        wt = shutil.which("wt")
        if wt:
            # Windows Terminal: abre em aba nova, respeitando o perfil padrão
            return [wt, "-d", path]

        pwsh = shutil.which("pwsh")
        if pwsh:
            return [pwsh, "-NoExit", "-WorkingDirectory", path]

        powershell = shutil.which("powershell")
        if powershell:
            return [powershell, "-NoExit", "-Command", f"Set-Location -LiteralPath '{path}'"]

        cmd = shutil.which("cmd")
        if cmd:
            return [cmd, "/K", f'cd /d "{path}"']

        raise RuntimeError(
            "Nenhum terminal encontrado (wt, pwsh, powershell ou cmd). "
            "Instale o Windows Terminal ou verifique o PATH."
        )

    def open_at(self, path: str) -> str:
        """Abre o terminal e devolve o caminho usado. Não espera o terminal fechar."""
        if not path or not os.path.isdir(path):
            raise FileNotFoundError(f"Pasta não encontrada no disco: {path or '(vazio)'}")

        command = self.build_command(path)
        subprocess.Popen(command, cwd=path, shell=False)
        logger.info(f"Terminal aberto em {path}")
        return path


terminal_service = TerminalService()
