"""Tests du nœud de validation — la logique de garantie, en code pur."""

from app.validation import Constraints, validate_selection


def _track(uri: str, minutes: float, date: str = "2025-06-01", name: str | None = None) -> dict:
    return {"uri": uri, "name": name or uri, "duration_min": minutes, "release_date": date}


def test_selection_conforme() -> None:
    c = Constraints(target_duration_min=90, min_release_year=2025, avoid_duplicates=True)
    tracks = [_track(f"spotify:track:{i}", 3.0) for i in range(30)]  # 90 min
    assert validate_selection(tracks, c, existing_uris=set()) == []


def test_duree_hors_tolerance() -> None:
    c = Constraints(target_duration_min=90)
    tracks = [_track(f"spotify:track:{i}", 3.0) for i in range(10)]  # 30 min
    violations = validate_selection(tracks, c, set())
    assert len(violations) == 1
    assert "30 min" in violations[0] and "Ajoute" in violations[0]


def test_duree_dans_la_tolerance_de_10_pourcent() -> None:
    c = Constraints(target_duration_min=90)
    tracks = [_track(f"spotify:track:{i}", 3.0) for i in range(28)]  # 84 min ≥ 81
    assert validate_selection(tracks, c, set()) == []


def test_annee_minimale() -> None:
    c = Constraints(min_release_year=2025)
    tracks = [_track("spotify:track:a", 3.0, "2023-07-28", name="FE!N")]
    violations = validate_selection(tracks, c, set())
    assert len(violations) == 1
    assert "FE!N" in violations[0] and "2025" in violations[0]


def test_doublons_avec_playlists_existantes() -> None:
    c = Constraints(avoid_duplicates=True)
    tracks = [_track("spotify:track:a", 3.0, name="Kanan"), _track("spotify:track:b", 3.0)]
    violations = validate_selection(tracks, c, existing_uris={"spotify:track:a"})
    assert len(violations) == 1
    assert "Kanan" in violations[0]


def test_doublons_internes() -> None:
    c = Constraints()
    tracks = [_track("spotify:track:a", 3.0), _track("spotify:track:a", 3.0)]
    violations = validate_selection(tracks, c, set())
    assert any("internes" in v for v in violations)


def test_nombre_de_morceaux() -> None:
    c = Constraints(track_count=15)
    tracks = [_track(f"spotify:track:{i}", 3.0) for i in range(12)]
    violations = validate_selection(tracks, c, set())
    assert any("12" in v and "15" in v for v in violations)


def test_sans_contrainte_tout_passe() -> None:
    tracks = [_track("spotify:track:a", 3.0, "1999-01-01")]
    assert validate_selection(tracks, Constraints(), set()) == []
