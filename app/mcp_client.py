"""Client MCP : lance le serveur `mcp_spotify_server` en stdio et expose ses
outils comme des outils LangChain.
"""

from __future__ import annotations

import sys

from langchain_core.tools import BaseTool
from langchain_mcp_adapters.client import MultiServerMCPClient

from app.config import PROJECT_ROOT, get_logger

logger = get_logger(__name__)


def _server_config() -> dict:
    # On lance le serveur avec le même interpréteur Python que l'app,
    # en module, depuis la racine du projet.
    return {
        "spotify": {
            "command": sys.executable,
            "args": ["-m", "mcp_spotify_server.server"],
            "transport": "stdio",
            "cwd": str(PROJECT_ROOT),
        }
    }


async def get_spotify_tools() -> list[BaseTool]:
    """Retourne les outils Spotify exposés par le serveur MCP."""
    client = MultiServerMCPClient(_server_config())
    tools = await client.get_tools()
    logger.info("MCP : outils chargés → %s", ", ".join(t.name for t in tools))
    return tools
