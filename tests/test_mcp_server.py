"""Tests unitaires du serveur MCP — sans appel réseau ni auth Spotify."""

from mcp_spotify_server.server import MAX_SEARCH_LIMIT, SCOPE, _fmt_track


def test_fmt_track_extracts_expected_fields() -> None:
    raw = {
        "id": "abc123",
        "uri": "spotify:track:abc123",
        "name": "Last Last",
        "artists": [{"name": "Burna Boy"}],
        "album": {"name": "Love, Damini"},
        "popularity": 80,
        "external_urls": {"spotify": "https://open.spotify.com/track/abc123"},
    }
    out = _fmt_track(raw)
    assert out == {
        "id": "abc123",
        "uri": "spotify:track:abc123",
        "name": "Last Last",
        "artists": ["Burna Boy"],
        "album": "Love, Damini",
        "popularity": 80,
        "url": "https://open.spotify.com/track/abc123",
    }


def test_fmt_track_handles_missing_fields() -> None:
    out = _fmt_track({})
    assert out["id"] is None
    assert out["artists"] == []
    assert out["album"] is None


def test_search_limit_matches_feb_2026_api_cap() -> None:
    # Depuis février 2026, /search plafonne à 10 (au-delà : 400 Invalid limit).
    assert MAX_SEARCH_LIMIT == 10


def test_scope_includes_write_and_identity() -> None:
    # Sans les scopes d'écriture, la création de playlist échoue en 403.
    for scope in ("playlist-modify-public", "playlist-modify-private", "user-read-email"):
        assert scope in SCOPE
