from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import Optional


class Settings(BaseSettings):
    PROJECT_NAME: str = "Agent Orchestrator"
    DATABASE_URL: str = "sqlite:///./orchestrator.db"
    CLAUDE_PATH: Optional[str] = "claude"
    AGY_PATH: Optional[str] = "agy"
    MAX_CONCURRENT_TASKS: int = 4

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


settings = Settings()
