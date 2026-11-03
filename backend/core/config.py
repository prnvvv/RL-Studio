"""Core configuration."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any


class Settings:
    def __init__(self) -> None:
        self.project_root = Path(__file__).resolve().parents[2]
        self.app_name = "Self-Healing RL Studio"
        self.debug = os.getenv("DEBUG", "false").lower() == "true"
        self.host = os.getenv("HOST", "0.0.0.0")
        self.port = int(os.getenv("PORT", "8000"))
        self.database_url = os.getenv("DATABASE_URL", f"sqlite:///{self.project_root / 'artifacts.db'}")
        self.meta_ai_api_key = (
            os.getenv("XAI_API_KEY")
            or os.getenv("GROK_API_KEY")
            or os.getenv("META_AI_API_KEY")
            or os.getenv("META_API")
            or os.getenv("MODEL_API_KEY")
        )
        self.meta_ai_base_url = (
            os.getenv("XAI_BASE_URL")
            or os.getenv("GROK_BASE_URL")
            or os.getenv("META_AI_BASE_URL")
            or os.getenv("META_BASE_URL")
        )
        self.meta_ai_model = (
            os.getenv("XAI_MODEL")
            or os.getenv("GROK_MODEL")
            or os.getenv("META_AI_MODEL")
            or os.getenv("META_MODEL")
            or os.getenv("META_DEFAULT_MODEL")
        )
        self.log_level = os.getenv("LOG_LEVEL", "INFO")
        self.cors_origins = os.getenv("CORS_ORIGINS", "*").split(",") if os.getenv("CORS_ORIGINS") else ["*"]

    def model_dump(self) -> dict[str, Any]:
        return {
            "app_name": self.app_name,
            "debug": self.debug,
            "host": self.host,
            "port": self.port,
            "database_url": self.database_url,
            "log_level": self.log_level,
            "meta_ai_configured": bool(self.meta_ai_api_key),
        }


settings = Settings()
