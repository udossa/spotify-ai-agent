"""Fabrique du modèle LLM et agrégation des outils (RAG + MCP Spotify)."""

from __future__ import annotations

from langchain.chat_models import init_chat_model
from langchain_core.language_models import BaseChatModel
from langchain_core.tools import BaseTool

from app.config import get_logger, get_settings
from app.mcp_client import get_spotify_tools
from app.rag import get_retriever_tool

logger = get_logger(__name__)


def get_model() -> BaseChatModel:
    """Instancie le LLM à partir de `LLM_MODEL` (ex: 'openai:gpt-4o-mini')."""
    settings = get_settings()
    # max_retries élevé : encaisse les 429 (quota tokens/min) avec backoff.
    model = init_chat_model(settings.llm_model, temperature=0.4, max_retries=8)
    logger.info("LLM initialisé : %s", settings.llm_model)
    return model


async def gather_tools() -> list[BaseTool]:
    """Réunit l'outil RAG et les outils MCP Spotify."""
    tools: list[BaseTool] = [get_retriever_tool()]
    tools.extend(await get_spotify_tools())
    return tools
