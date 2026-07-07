"""Serveur MCP Spotify (transport stdio).

Expose des outils « bruts » au-dessus de l'API Web Spotify via spotipy.
CONTRAINTE : aucune logique métier ici — seulement des actions Spotify
paramétrables et leurs résultats normalisés. Le raisonnement (sélection,
règles, quantités) appartient à l'agent.

Auth : OAuth Authorization Code (spotipy.SpotifyOAuth). Les identifiants sont
lus depuis l'environnement (SPOTIPY_CLIENT_ID / SECRET / REDIRECT_URI), jamais
en dur. Le token est mis en cache localement (`.cache`).
"""

from __future__ import annotations

import os
from functools import lru_cache
from typing import Any

import spotipy
from dotenv import load_dotenv
from mcp.server.fastmcp import FastMCP
from spotipy.oauth2 import SpotifyOAuth

# Charge le .env de la racine du projet (le cwd est fixé par le client MCP).
load_dotenv()

SCOPE = "playlist-modify-public playlist-modify-private user-read-private user-read-email"

mcp = FastMCP("spotify")


@lru_cache
def _client() -> spotipy.Spotify:
    """Client Spotify authentifié (mémoïsé pour la durée du process)."""
    auth = SpotifyOAuth(
        client_id=os.environ["SPOTIPY_CLIENT_ID"],
        client_secret=os.environ["SPOTIPY_CLIENT_SECRET"],
        redirect_uri=os.environ.get("SPOTIPY_REDIRECT_URI", "http://127.0.0.1:8888/callback"),
        scope=SCOPE,
        open_browser=True,
    )
    return spotipy.Spotify(auth_manager=auth)


def _fmt_track(item: dict[str, Any]) -> dict[str, Any]:
    """Normalise un objet track Spotify en dictionnaire compact."""
    return {
        "id": item.get("id"),
        "uri": item.get("uri"),
        "name": item.get("name"),
        "artists": [a.get("name") for a in item.get("artists", [])],
        "album": item.get("album", {}).get("name"),
        "popularity": item.get("popularity"),
        "url": item.get("external_urls", {}).get("spotify"),
    }


@mcp.tool()
def get_current_user() -> dict[str, Any]:
    """Retourne le profil de l'utilisateur Spotify authentifié (id, nom)."""
    me = _client().me()
    return {"id": me.get("id"), "display_name": me.get("display_name")}


MAX_SEARCH_LIMIT = 10  # Plafond Spotify /search depuis février 2026 (était 50).


@mcp.tool()
def search_tracks(query: str, limit: int = 10) -> list[dict[str, Any]]:
    """Recherche des morceaux sur Spotify.

    query : requête. Filtres valides uniquement : `genre:`, `artist:`, `track:`,
        `album:`, `year:` (ex. 'genre:afrobeat year:2020-2024'). N'utilise PAS de
        filtres inexistants comme `energy:`, `mood:` ou `bpm:` (erreur 400).
    limit : nombre de résultats, entre 1 et 10 (plafond Spotify). Pour couvrir
        plusieurs genres, fais plusieurs recherches plutôt qu'un grand limit.
    """
    limit = max(1, min(limit, MAX_SEARCH_LIMIT))
    res = _client().search(q=query, type="track", limit=limit)
    return [_fmt_track(t) for t in res.get("tracks", {}).get("items", [])]


@mcp.tool()
def get_track(track_id: str) -> dict[str, Any]:
    """Retourne les détails d'un morceau à partir de son id Spotify."""
    return _fmt_track(_client().track(track_id))


@mcp.tool()
def create_playlist(name: str, description: str = "", public: bool = False) -> dict[str, Any]:
    """Crée une playlist vide pour l'utilisateur courant et la retourne (id, uri, url).

    Endpoint `POST /me/playlists` (l'ancien `POST /users/{id}/playlists` a été
    supprimé par Spotify en février 2026).
    """
    client = _client()
    pl = client._post(
        "me/playlists",
        payload={"name": name, "public": public, "description": description},
    )
    return {
        "id": pl.get("id"),
        "uri": pl.get("uri"),
        "name": pl.get("name"),
        "url": pl.get("external_urls", {}).get("spotify"),
    }


@mcp.tool()
def add_tracks_to_playlist(playlist_id: str, track_uris: list[str]) -> dict[str, Any]:
    """Ajoute des morceaux (URIs Spotify) à une playlist. Retourne le nb ajouté.

    Endpoint `POST /playlists/{id}/items` (l'ancien `.../tracks` a été supprimé
    par Spotify en février 2026).
    """
    client = _client()
    added = 0
    # L'API Spotify limite à 100 URIs par appel.
    for i in range(0, len(track_uris), 100):
        batch = track_uris[i : i + 100]
        client._post(f"playlists/{playlist_id}/items", payload={"uris": batch})
        added += len(batch)
    return {"playlist_id": playlist_id, "added": added}


@mcp.tool()
def get_user_playlists(limit: int = 20) -> list[dict[str, Any]]:
    """Liste les playlists de l'utilisateur courant (id, nom, nb de morceaux)."""
    res = _client().current_user_playlists(limit=max(1, min(limit, 50)))
    return [
        {"id": p.get("id"), "name": p.get("name"), "tracks": p.get("tracks", {}).get("total")}
        for p in res.get("items", [])
    ]


if __name__ == "__main__":
    mcp.run()
