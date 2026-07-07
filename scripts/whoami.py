"""Affiche l'identité du compte Spotify que l'agent utilisera réellement.

Utilise EXACTEMENT le même cache (`.cache`) et le même scope que le serveur MCP,
donc le compte affiché ici est garanti d'être celui avec lequel l'agent agit.
Le but : connaître l'email EXACT à enregistrer dans le dashboard Spotify
(Settings → User Management) pour débloquer la création de playlist (403).

Usage :
    uv run python scripts/whoami.py

Au 1er lancement (ou après `rm -f .cache`), ouvre le navigateur pour le
consentement, puis réutilise le token. L'agent réutilisera ce même `.cache`.
"""

from __future__ import annotations

import os
import sys

import spotipy
from dotenv import load_dotenv
from spotipy.oauth2 import SpotifyOAuth

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
load_dotenv(os.path.join(ROOT, ".env"))

from mcp_spotify_server.server import SCOPE  # noqa: E402  (même scope que l'agent)


def main() -> None:
    missing = [
        v
        for v in ("SPOTIPY_CLIENT_ID", "SPOTIPY_CLIENT_SECRET", "SPOTIPY_REDIRECT_URI")
        if not os.environ.get(v)
    ]
    if missing:
        print("❌ Variables manquantes dans .env :", ", ".join(missing))
        raise SystemExit(1)

    # cache_path=".cache" (défaut spotipy, relatif au cwd) → partagé avec l'agent.
    auth = SpotifyOAuth(
        client_id=os.environ["SPOTIPY_CLIENT_ID"],
        client_secret=os.environ["SPOTIPY_CLIENT_SECRET"],
        redirect_uri=os.environ["SPOTIPY_REDIRECT_URI"],
        scope=SCOPE,
        cache_path=os.path.join(ROOT, ".cache"),
        open_browser=True,
    )
    sp = spotipy.Spotify(auth_manager=auth)
    me = sp.me()

    print("\n===== Compte Spotify utilisé par l'agent =====")
    print("id      :", me.get("id"))
    print("email   :", me.get("email"))
    print("product :", me.get("product"))
    print("pays    :", me.get("country"))
    print("client  :", (os.environ["SPOTIPY_CLIENT_ID"][:6] + "…"))
    print("==============================================")

    # Test d'écriture immédiat, avec le MÊME token que l'agent.
    print("\n→ Test de création de playlist avec ce compte...")
    try:
        pl = sp.user_playlist_create(user=me["id"], name="__diag__", public=False, description="diag")
        print("✅ Création OK :", pl.get("external_urls", {}).get("spotify"))
        sp.current_user_unfollow_playlist(pl["id"])
        print("   (playlist de test supprimée)")
        print("\n🎉 Tout est bon — tu peux lancer :  uv run spotify-agent")
    except spotipy.SpotifyException as e:
        print(f"❌ Création refusée : HTTP {e.http_status}")
        print("\n👉 Enregistre CET email dans le dashboard de l'app 'client' ci-dessus :")
        print("   Settings → User Management → Add user →", me.get("email"))
        print("   Puis relance ce script pour re-tester.")


if __name__ == "__main__":
    main()
