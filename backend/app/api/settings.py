import os
from fastapi import APIRouter
from pydantic import BaseModel
from typing import Optional
from app.core.config import settings

router = APIRouter(prefix="/api/settings", tags=["settings"])


class SettingsStatus(BaseModel):
    has_gemini_key: bool
    has_anthropic_key: bool
    gemini_key_preview: Optional[str] = None
    anthropic_key_preview: Optional[str] = None


class SettingsUpdate(BaseModel):
    gemini_api_key: Optional[str] = None
    anthropic_api_key: Optional[str] = None


@router.get("", response_model=SettingsStatus)
def get_settings():
    gemini_key = os.environ.get("GEMINI_API_KEY") or getattr(settings, "GEMINI_API_KEY", None)
    anthropic_key = os.environ.get("ANTHROPIC_API_KEY") or getattr(settings, "ANTHROPIC_API_KEY", None)

    g_preview = f"{gemini_key[:6]}...{gemini_key[-4:]}" if gemini_key and len(gemini_key) > 10 else None
    a_preview = f"{anthropic_key[:6]}...{anthropic_key[-4:]}" if anthropic_key and len(anthropic_key) > 10 else None

    return SettingsStatus(
        has_gemini_key=bool(gemini_key),
        has_anthropic_key=bool(anthropic_key),
        gemini_key_preview=g_preview,
        anthropic_key_preview=a_preview
    )


@router.post("", response_model=SettingsStatus)
def update_settings(data: SettingsUpdate):
    env_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..", ".env"))

    # Lê variáveis existentes do .env se existir
    lines = []
    if os.path.exists(env_path):
        with open(env_path, "r", encoding="utf-8") as f:
            lines = f.readlines()

    env_dict = {}
    for line in lines:
        line_clean = line.strip()
        if line_clean and not line_clean.startswith("#") and "=" in line_clean:
            k, v = line_clean.split("=", 1)
            env_dict[k.strip()] = v.strip()

    if data.gemini_api_key is not None:
        key_val = data.gemini_api_key.strip()
        if key_val:
            env_dict["GEMINI_API_KEY"] = key_val
            os.environ["GEMINI_API_KEY"] = key_val
        elif "GEMINI_API_KEY" in env_dict:
            del env_dict["GEMINI_API_KEY"]
            os.environ.pop("GEMINI_API_KEY", None)

    if data.anthropic_api_key is not None:
        key_val = data.anthropic_api_key.strip()
        if key_val:
            env_dict["ANTHROPIC_API_KEY"] = key_val
            os.environ["ANTHROPIC_API_KEY"] = key_val
        elif "ANTHROPIC_API_KEY" in env_dict:
            del env_dict["ANTHROPIC_API_KEY"]
            os.environ.pop("ANTHROPIC_API_KEY", None)

    # Regrava .env
    with open(env_path, "w", encoding="utf-8") as f:
        for k, v in env_dict.items():
            f.write(f"{k}={v}\n")

    return get_settings()
