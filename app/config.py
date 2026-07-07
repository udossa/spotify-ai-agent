"""Configuration centralisée + logging structuré.

Toutes les variables sensibles sont chargées depuis `.env` (jamais en dur).

Le `.env` est chargé dans `os.environ` dès l'import de ce module : c'est
indispensable car les SDK (OpenAI, spotipy) lisent leurs clés directement dans
l'environnement, pas via l'objet `Settings` ci-dessous.
"""

from __future__ import annotations

import json
import logging
import sys
from functools import lru_cache
from pathlib import Path

from dotenv import load_dotenv
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

# Racine du projet (dossier contenant ce package `app`).
PROJECT_ROOT = Path(__file__).resolve().parent.parent

load_dotenv(PROJECT_ROOT / ".env")


class Settings(BaseSettings):
    """Paramètres applicatifs, typés et validés (lus depuis l'environnement)."""

    model_config = SettingsConfigDict(extra="ignore")

    # LLM
    llm_model: str = Field(default="openai:gpt-4o-mini", alias="LLM_MODEL")
    embeddings_model: str = Field(default="text-embedding-3-small", alias="EMBEDDINGS_MODEL")

    # Chemins
    data_dir: str = Field(default="data", alias="DATA_DIR")
    vectorstore_dir: str = Field(default="vectorstore", alias="VECTORSTORE_DIR")

    # Logs
    log_level: str = Field(default="INFO", alias="LOG_LEVEL")

    @property
    def data_path(self) -> Path:
        return PROJECT_ROOT / self.data_dir

    @property
    def vectorstore_path(self) -> Path:
        return PROJECT_ROOT / self.vectorstore_dir


@lru_cache
def get_settings() -> Settings:
    """Instance unique et mémoïsée des paramètres."""
    return Settings()


class _JsonFormatter(logging.Formatter):
    """Formatteur JSON minimal : une ligne JSON par log."""

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, object] = {
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        if record.exc_info:
            payload["exc"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=False)


def setup_logging() -> None:
    """Configure un logging JSON sur stderr (idempotent)."""
    root = logging.getLogger()
    if getattr(root, "_spotify_agent_configured", False):
        return
    handler = logging.StreamHandler(sys.stderr)
    handler.setFormatter(_JsonFormatter())
    root.handlers[:] = [handler]
    root.setLevel(get_settings().log_level.upper())
    root._spotify_agent_configured = True  # type: ignore[attr-defined]


def get_logger(name: str) -> logging.Logger:
    setup_logging()
    return logging.getLogger(name)
