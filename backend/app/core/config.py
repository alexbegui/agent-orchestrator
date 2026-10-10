from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import Optional


class Settings(BaseSettings):
    PROJECT_NAME: str = "Agent Orchestrator"
    DATABASE_URL: str = "sqlite:///./orchestrator.db"
    CLAUDE_PATH: Optional[str] = "claude"
    AGY_PATH: Optional[str] = "agy"
    MAX_CONCURRENT_TASKS: int = 4

    # O agente roda sem terminal interativo, em worktree isolado, e você revisa
    # o diff antes do merge. Sem autonomia ele trava na primeira permissão.
    # ATENÇÃO: o worktree isola arquivos entre tarefas, não é sandbox de
    # segurança — neste modo o agente executa qualquer comando na máquina.
    # Baixe para "acceptEdits" se quiser um padrão mais conservador.
    CLAUDE_PERMISSION_MODE: str = "bypassPermissions"

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


settings = Settings()
