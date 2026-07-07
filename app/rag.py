"""RAG : ingestion des documents `data/*.md` dans ChromaDB + outil de retrieval.

Aucune logique métier Spotify ici : uniquement la connaissance (préférences,
règles, genres, artistes) et sa récupération.
"""

from __future__ import annotations

from langchain_chroma import Chroma
from langchain_core.documents import Document
from langchain_core.tools import Tool
from langchain_openai import OpenAIEmbeddings
from langchain_text_splitters import MarkdownTextSplitter

from app.config import get_logger, get_settings

logger = get_logger(__name__)

COLLECTION_NAME = "music_knowledge"


def _embeddings() -> OpenAIEmbeddings:
    settings = get_settings()
    return OpenAIEmbeddings(model=settings.embeddings_model)


def _load_documents() -> list[Document]:
    """Charge et découpe tous les `.md` du dossier `data/`."""
    settings = get_settings()
    splitter = MarkdownTextSplitter(chunk_size=1000, chunk_overlap=150)
    docs: list[Document] = []
    for md_file in sorted(settings.data_path.glob("*.md")):
        text = md_file.read_text(encoding="utf-8")
        for chunk in splitter.split_text(text):
            docs.append(Document(page_content=chunk, metadata={"source": md_file.name}))
    logger.info("RAG : %d chunks chargés depuis data/", len(docs))
    return docs


def ingest(reset: bool = False) -> Chroma:
    """(Ré)indexe les documents du RAG dans ChromaDB (persistant)."""
    settings = get_settings()
    store = Chroma(
        collection_name=COLLECTION_NAME,
        embedding_function=_embeddings(),
        persist_directory=str(settings.vectorstore_path),
    )
    if reset:
        store.reset_collection()
    docs = _load_documents()
    if docs:
        store.add_documents(docs)
    logger.info("RAG : index persisté dans %s", settings.vectorstore_path)
    return store


def get_vectorstore() -> Chroma:
    settings = get_settings()
    return Chroma(
        collection_name=COLLECTION_NAME,
        embedding_function=_embeddings(),
        persist_directory=str(settings.vectorstore_path),
    )


def get_retriever_tool() -> Tool:
    """Outil LangChain de recherche dans la base de connaissance musicale."""
    retriever = get_vectorstore().as_retriever(search_kwargs={"k": 4})

    def _search(query: str) -> str:
        docs = retriever.invoke(query)
        if not docs:
            return "Aucune connaissance pertinente trouvée."
        return "\n\n---\n\n".join(
            f"[{d.metadata.get('source', '?')}]\n{d.page_content}" for d in docs
        )

    return Tool(
        name="search_music_knowledge",
        description=(
            "Recherche dans la base de connaissance musicale de l'utilisateur : "
            "préférences (music_profile), règles de playlist (playlist_rules), "
            "artistes favoris (artists) et genres (genres). "
            "À appeler en premier pour cadrer la création d'une playlist."
        ),
        func=_search,
    )
