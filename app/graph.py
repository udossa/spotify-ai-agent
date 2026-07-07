"""Assemblage du graphe LangGraph.

Le graphe suit le schéma du brief :

    START → Agent → Décision ├── RAG
                             ├── Spotify MCP
                             └── Réponse finale → END

Implémenté avec `create_react_agent` : le nœud `agent` décide, à chaque tour,
d'appeler un outil (RAG ou MCP) ou de produire la réponse finale.
"""

from __future__ import annotations

from langgraph.graph.state import CompiledStateGraph
from langgraph.prebuilt import create_react_agent

from app.agent import gather_tools, get_model
from app.config import get_logger
from app.prompts import SYSTEM_PROMPT

logger = get_logger(__name__)


async def build_graph() -> CompiledStateGraph:
    """Construit et compile le graphe de l'agent (modèle + outils RAG/MCP)."""
    model = get_model()
    tools = await gather_tools()
    graph = create_react_agent(model, tools, prompt=SYSTEM_PROMPT)
    logger.info("Graphe compilé avec %d outils", len(tools))
    return graph
