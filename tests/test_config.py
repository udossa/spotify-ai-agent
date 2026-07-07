"""Tests de configuration — vérifie les valeurs par défaut et les chemins."""

from app.config import Settings


def test_defaults(monkeypatch) -> None:
    # Isole des variables d'environnement locales pour tester les défauts.
    for var in ("LLM_MODEL", "EMBEDDINGS_MODEL", "DATA_DIR", "VECTORSTORE_DIR", "LOG_LEVEL"):
        monkeypatch.delenv(var, raising=False)
    settings = Settings()
    assert settings.llm_model == "openai:gpt-4o-mini"
    assert settings.embeddings_model == "text-embedding-3-small"
    assert settings.data_path.name == "data"
    assert settings.vectorstore_path.name == "vectorstore"
