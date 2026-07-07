"""Assemblage du graphe LangGraph.

Le LLM propose, le code garantit :

    START → extract → curate ⇄ validate → finalize → END
                        ▲          │
                        └─ écarts ─┘   (3 tentatives max)

- extract  : LLM → contraintes structurées (durée, année min, doublons…).
- curate   : agent ReAct avec outils de LECTURE seulement → propose une
             sélection (le graphe historique de ce projet vit ici).
- validate : CODE PUR — relit chaque morceau depuis Spotify et vérifie les
             contraintes (`app/validation.py`). Un LLM peut affirmer
             « environ 1h30 » sans l'avoir calculé ; ce nœud, non.
- finalize : crée la playlist et ajoute EXACTEMENT la sélection validée.
"""

from __future__ import annotations

import json
from datetime import date
from typing import Any, TypedDict

from langchain_core.messages import BaseMessage, HumanMessage
from langchain_core.tools import BaseTool, StructuredTool
from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph
from langgraph.prebuilt import create_react_agent

from app.agent import gather_tools, get_model
from app.config import get_logger
from app.prompts import CURATOR_PROMPT, EXTRACT_CONSTRAINTS_PROMPT, EXTRACT_SELECTION_PROMPT
from app.validation import Constraints, Selection, validate_selection

logger = get_logger(__name__)

MAX_ATTEMPTS = 4
# Outils d'écriture : réservés au nœud `finalize`, jamais donnés au LLM.
WRITE_TOOLS = {"create_playlist", "add_tracks_to_playlist"}


class AgentState(TypedDict, total=False):
    request: str
    constraints: Constraints
    existing: list[dict]        # morceaux déjà présents dans les playlists (uri, name)
    messages: list[BaseMessage]
    selection: Selection
    tracks: list[dict]          # détails réels des morceaux sélectionnés
    violations: list[str]
    attempts: int
    result: dict[str, Any]


def _parse(tool_result: Any) -> Any:
    """Désérialise un résultat d'outil MCP.

    L'adaptateur renvoie du JSON en texte — soit une chaîne, soit une liste de
    blocs `{"type": "text", "text": ...}` (un bloc par élément quand l'outil
    retourne une liste).
    """
    try:
        if isinstance(tool_result, str):
            return json.loads(tool_result)
        if isinstance(tool_result, list):
            texts = [
                b["text"] for b in tool_result if isinstance(b, dict) and b.get("type") == "text"
            ]
            if len(texts) == 1:
                return json.loads(texts[0])
            if texts:
                return [json.loads(t) for t in texts]
    except json.JSONDecodeError as exc:
        # Un outil qui échoue renvoie un message d'erreur en clair, pas du JSON.
        raise RuntimeError(f"Échec d'un outil MCP : {tool_result}") from exc
    return tool_result


async def build_graph() -> CompiledStateGraph:
    """Construit et compile le graphe : extract → curate ⇄ validate → finalize."""
    model = get_model()
    all_tools = await gather_tools()
    tools: dict[str, BaseTool] = {t.name: t for t in all_tools}

    def _make_curator(constraints: Constraints, excluded_uris: set[str]):
        """Curateur dont le `search_tracks` est PRÉ-FILTRÉ en code.

        Le LLM ne voit jamais un morceau exclu ou trop ancien — il ne peut
        donc plus en sélectionner (les opérations d'ensembles sont fiables en
        code, pas dans un modèle).
        """

        async def filtered_search(query: str, limit: int = 10) -> list[dict]:
            results = _parse(
                await tools["search_tracks"].ainvoke({"query": query, "limit": limit})
            )
            return [
                t
                for t in results
                if t["uri"] not in excluded_uris
                and (
                    constraints.min_release_year is None
                    or (t.get("release_date") or "9999")[:4] >= str(constraints.min_release_year)
                )
            ]

        search = StructuredTool.from_function(
            coroutine=filtered_search,
            name="search_tracks",
            description=(
                tools["search_tracks"].description
                + "\nLes résultats sont déjà filtrés (exclusions et année minimale) : "
                "tout titre renvoyé est sélectionnable."
            ),
        )
        read_tools = [
            search if t.name == "search_tracks" else t
            for t in all_tools
            if t.name not in WRITE_TOOLS
        ]
        return create_react_agent(model, read_tools, prompt=CURATOR_PROMPT)

    async def extract(state: AgentState) -> AgentState:
        # La date du jour vient du CODE : un LLM ne sait pas quel jour on est
        # (son « présent » est figé à la fin de son entraînement).
        today = date.today().isoformat()
        constraints = await model.with_structured_output(Constraints).ainvoke(
            [
                HumanMessage(
                    content=f"Date du jour : {today}.\n{EXTRACT_CONSTRAINTS_PROMPT}\n\n"
                    f"Demande : {state['request']}"
                )
            ]
        )
        logger.info("Contraintes extraites : %s", constraints.model_dump(exclude_none=True))
        # Le code fait le déterministe : indices chiffrés + liste d'exclusion,
        # injectés dans la demande (un LLM estime mal « combien de morceaux
        # font 1h30 » et oublie des exclusions).
        hints = [f"Nous sommes le {today}."]
        if constraints.target_duration_min:
            n = round(constraints.target_duration_min / 3)
            hints.append(
                f"Indication : {constraints.target_duration_min:.0f} min ≈ {n} morceaux "
                f"(~3 min chacun). Constitue un vivier d'au moins {n + 10} candidats "
                "(nombreuses recherches), puis additionne les duration_min réels."
            )
        existing: list[dict] = []
        if constraints.avoid_duplicates:
            playlists = _parse(await tools["get_user_playlists"].ainvoke({}))
            for pl in playlists:
                items = _parse(
                    await tools["get_playlist_tracks"].ainvoke({"playlist_id": pl["id"]})
                )
                existing.extend({"uri": t["uri"], "name": t["name"]} for t in items)
            if existing:
                hints.append(
                    "URIs à EXCLURE (déjà dans les playlists existantes) :\n"
                    + "\n".join(f"- {t['name']} — {t['uri']}" for t in existing)
                )
        content = state["request"] + ("\n\n" + "\n\n".join(hints) if hints else "")
        return {
            "constraints": constraints,
            "existing": existing,
            "messages": [HumanMessage(content=content)],
            "attempts": 0,
        }

    async def curate(state: AgentState) -> AgentState:
        curator = _make_curator(
            state["constraints"], {t["uri"] for t in state.get("existing", [])}
        )
        out = await curator.ainvoke(
            {"messages": state["messages"]}, config={"recursion_limit": 120}
        )
        messages = out["messages"]
        selection = await model.with_structured_output(Selection).ainvoke(
            [HumanMessage(content=f"{EXTRACT_SELECTION_PROMPT}\n\n{messages[-1].content}")]
        )
        logger.info("Sélection proposée : %d morceaux", len(selection.uris))
        return {"messages": messages, "selection": selection, "attempts": state["attempts"] + 1}

    async def validate(state: AgentState) -> AgentState:
        # Relit les données RÉELLES de chaque morceau (jamais celles du LLM).
        tracks = [
            _parse(await tools["get_track"].ainvoke({"track_id": uri}))
            for uri in state["selection"].uris
        ]
        existing_uris = {t["uri"] for t in state.get("existing", [])}
        c = state["constraints"]
        violations = validate_selection(tracks, c, existing_uris)
        logger.info(
            "Validation tentative %d : %s",
            state["attempts"],
            violations or "OK",
        )
        if violations:
            # Réparation en code : retire doublons et morceaux trop anciens,
            # puis re-valide. Si le reste tient les contraintes, inutile de
            # renvoyer le LLM en boucle pour une opération déterministe.
            seen: set[str] = set()
            kept = []
            for t in tracks:
                if t["uri"] in seen or t["uri"] in existing_uris:
                    continue
                if c.min_release_year is not None and (
                    not (t.get("release_date") or "")[:4].isdigit()
                    or int(t["release_date"][:4]) < c.min_release_year
                ):
                    continue
                seen.add(t["uri"])
                kept.append(t)
            if kept != tracks and not validate_selection(kept, c, existing_uris):
                logger.info(
                    "Réparation en code : %d morceau(x) retiré(s), sélection conforme",
                    len(tracks) - len(kept),
                )
                return {"tracks": kept, "violations": []}
        return {"tracks": tracks, "violations": violations}

    def route(state: AgentState) -> str:
        if not state["violations"]:
            return "finalize"
        if state["attempts"] >= MAX_ATTEMPTS:
            return "abort"
        return "retry"

    async def retry(state: AgentState) -> AgentState:
        # Feedback chiffré, calculé en code : quoi garder, combien ajouter.
        c = state["constraints"]
        existing_uris = {t["uri"] for t in state.get("existing", [])}
        keep = [
            t
            for t in state["tracks"]
            if t["uri"] not in existing_uris
            and (
                c.min_release_year is None
                or (t.get("release_date") or "9999")[:4] >= str(c.min_release_year)
            )
        ]
        parts = [
            "Ta sélection a été REFUSÉE par la validation :",
            "- " + "\n- ".join(state["violations"]),
        ]
        if keep:
            kept_min = sum(t.get("duration_min") or 0 for t in keep)
            parts.append(
                f"\nCes {len(keep)} morceaux sont CONFORMES, garde-les tels quels "
                f"({kept_min:.0f} min) :\n"
                + "\n".join(f"- {t['name']} — {t['uri']}" for t in keep)
            )
            if c.target_duration_min:
                missing = c.target_duration_min - kept_min
                if missing > 0:
                    parts.append(
                        f"\nIl manque ~{missing:.0f} min ≈ {round(missing / 3)} morceaux "
                        "NOUVEAUX (hors exclusions). Fais autant de recherches que "
                        "nécessaire pour les trouver."
                    )
        parts.append("\nPropose la sélection complète corrigée.")
        # Historique RÉINITIALISÉ : demande initiale + feedback chiffré. La
        # keep-list remplace les transcripts de recherche précédents — moins
        # de tokens par tentative (quota TPM) et un contexte net.
        return {
            "messages": [state["messages"][0], HumanMessage(content="\n".join(parts))]
        }

    async def finalize(state: AgentState) -> AgentState:
        sel = state["selection"]
        name = state["constraints"].playlist_name or sel.playlist_name
        playlist = _parse(
            await tools["create_playlist"].ainvoke(
                {"name": name, "description": sel.description}
            )
        )
        added = _parse(
            await tools["add_tracks_to_playlist"].ainvoke(
                {"playlist_id": playlist["id"], "track_uris": [t["uri"] for t in state["tracks"]]}
            )
        )
        total = sum(t.get("duration_min") or 0 for t in state["tracks"])
        return {
            "result": {
                "name": playlist["name"],
                "url": playlist["url"],
                "n_tracks": added["added"],
                "duration_min": total,
            }
        }

    async def abort(state: AgentState) -> AgentState:
        return {
            "result": {
                "error": (
                    f"Sélection non conforme après {MAX_ATTEMPTS} tentatives — "
                    "playlist NON créée. Écarts restants :\n- "
                    + "\n- ".join(state["violations"])
                )
            }
        }

    graph = StateGraph(AgentState)
    graph.add_node("extract", extract)
    graph.add_node("curate", curate)
    graph.add_node("validate", validate)
    graph.add_node("retry", retry)
    graph.add_node("finalize", finalize)
    graph.add_node("abort", abort)
    graph.add_edge(START, "extract")
    graph.add_edge("extract", "curate")
    graph.add_edge("curate", "validate")
    graph.add_conditional_edges(
        "validate", route, {"finalize": "finalize", "retry": "retry", "abort": "abort"}
    )
    graph.add_edge("retry", "curate")
    graph.add_edge("finalize", END)
    graph.add_edge("abort", END)

    compiled = graph.compile()
    logger.info("Graphe compilé : extract → curate ⇄ validate → finalize (%d outils)", len(all_tools))
    return compiled
