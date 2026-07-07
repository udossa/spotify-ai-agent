"""Tests unitaires du serveur MCP — sans appel réseau ni auth Spotify."""

from mcp_spotify_server.server import MAX_SEARCH_LIMIT, SCOPE, _fmt_track


def test_fmt_track_extracts_expected_fields() -> None:
    raw = {
        "id": "abc123",
        "uri": "spotify:track:abc123",
        "name": "Last Last",
        "artists": [{"name": "Burna Boy"}],
        "album": {"name": "Love, Damini", "release_date": "2022-07-08"},
        "duration_ms": 172800,
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
        "release_date": "2022-07-08",
        "duration_min": 2.9,
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


def test_scope_includes_write_and_read_permissions() -> None:
    # Écriture : création de playlist. Lecture : déduplication inter-playlists.
    for scope in ("playlist-modify-public", "playlist-modify-private", "playlist-read-private"):
        assert scope in SCOPE
