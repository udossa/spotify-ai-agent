"""Point d'entrée CLI de l'agent.

Usage :
    uv run spotify-agent "Crée une playlist Afrobounce Workout de 20 morceaux..."
    uv run spotify-agent --ingest        # (ré)indexe le RAG puis quitte
"""

from __future__ import annotations

import argparse
import asyncio
import sys

from app.config import get_logger
from app.graph import build_graph
from app.rag import ingest

logger = get_logger(__name__)

DEFAULT_PROMPT = (
    'Crée une playlist "Afrobounce Workout" de 20 morceaux mêlant Afro, Rap '
    "et Electronica avec une énergie élevée."
)


async def run_agent(user_request: str) -> str:
    """Exécute l'agent sur une requête et retourne la réponse finale."""
    graph = await build_graph()
    state = await graph.ainvoke({"request": user_request})
    result = state["result"]
    if "error" in result:
        return f"❌ {result['error']}"
    return (
        f"✅ Playlist « {result['name']} » créée : {result['n_tracks']} titres, "
        f"{result['duration_min']:.0f} min.\n{result['url']}"
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Spotify AI Agent (LangGraph + RAG + MCP)")
    parser.add_argument("request", nargs="?", default=DEFAULT_PROMPT, help="Intention en langage naturel")
    parser.add_argument("--ingest", action="store_true", help="(Ré)indexer le RAG puis quitter")
    parser.add_argument("--reset", action="store_true", help="Vider la collection avant ingestion")
    args = parser.parse_args()

    if args.ingest:
        ingest(reset=args.reset)
        print("✅ RAG indexé.")
        return

    try:
        answer = asyncio.run(run_agent(args.request))
    except Exception:  # noqa: BLE001 — on log proprement puis on sort en erreur
        logger.exception("agent_run_failed")
        print("❌ Échec de l'agent (voir logs).", file=sys.stderr)
        raise SystemExit(1)

    print("\n" + answer)


if __name__ == "__main__":
    main()
