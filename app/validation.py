"""Contraintes structurées + validation EN CODE de la sélection de l'agent.

C'est le garde-fou du graphe : le LLM propose, ce module vérifie. Les données
vérifiées (durées, dates) sont re-lues depuis Spotify, jamais reprises de la
sortie du LLM — un modèle peut affirmer « environ 1h30 » sans l'avoir calculé.
"""

from __future__ import annotations

from pydantic import BaseModel, Field

# Tolérance sur la durée cible : ±10 %.
DURATION_TOLERANCE = 0.10


class Constraints(BaseModel):
    """Contraintes objectives extraites de la demande utilisateur."""

    playlist_name: str | None = Field(
        default=None, description="Nom exact demandé pour la playlist, s'il est précisé."
    )
    track_count: int | None = Field(
        default=None, description="Nombre de morceaux demandé, s'il est précisé."
    )
    target_duration_min: float | None = Field(
        default=None, description="Durée totale demandée en minutes (ex. « 1h30 » → 90)."
    )
    min_release_year: int | None = Field(
        default=None, description="Année de sortie minimale exigée (ex. « depuis 2025 » → 2025)."
    )
    avoid_duplicates: bool = Field(
        default=False,
        description="True si l'utilisateur exige d'éviter les morceaux déjà présents dans ses playlists.",
    )
    other_criteria: str = Field(
        default="",
        description="Critères subjectifs restants (genres, répartition, mood…), en une phrase.",
    )


class Selection(BaseModel):
    """Sélection finale proposée par l'agent curateur."""

    playlist_name: str = Field(description="Nom de la playlist.")
    description: str = Field(description="Description courte (1 phrase).")
    uris: list[str] = Field(description="URIs Spotify des morceaux retenus, dans l'ordre.")


def validate_selection(
    tracks: list[dict],
    constraints: Constraints,
    existing_uris: set[str],
) -> list[str]:
    """Vérifie la sélection contre les contraintes. Retourne la liste des écarts.

    tracks : détails RÉELS des morceaux (relus via l'API), avec au moins
        `uri`, `name`, `duration_min`, `release_date`.
    existing_uris : URIs déjà présents dans les playlists de l'utilisateur.
    """
    violations: list[str] = []

    uris = [t["uri"] for t in tracks]
    if len(set(uris)) != len(uris):
        violations.append("La sélection contient des doublons internes.")

    if constraints.track_count is not None and len(tracks) != constraints.track_count:
        violations.append(
            f"{len(tracks)} morceaux au lieu des {constraints.track_count} demandés."
        )

    if constraints.target_duration_min is not None:
        total = sum(t.get("duration_min") or 0 for t in tracks)
        target = constraints.target_duration_min
        tolerance = target * DURATION_TOLERANCE
        if abs(total - target) > tolerance:
            violations.append(
                f"Durée totale {total:.0f} min, hors cible {target:.0f} min "
                f"(±{tolerance:.0f}). "
                + ("Ajoute des morceaux." if total < target else "Retire des morceaux.")
            )

    if constraints.min_release_year is not None:
        too_old = [
            f"« {t['name']} » ({t.get('release_date', '?')})"
            for t in tracks
            if not (t.get("release_date") or "0000")[:4].isdigit()
            or int((t.get("release_date") or "0000")[:4]) < constraints.min_release_year
        ]
        if too_old:
            violations.append(
                f"Morceaux antérieurs à {constraints.min_release_year} : {', '.join(too_old)}."
            )

    if constraints.avoid_duplicates:
        dups = [t["name"] for t in tracks if t["uri"] in existing_uris]
        if dups:
            violations.append(
                "Déjà présents dans les playlists existantes : " + ", ".join(dups) + "."
            )

    return violations
