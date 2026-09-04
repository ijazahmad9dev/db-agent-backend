import uuid

from qdrant_client import QdrantClient
from qdrant_client.http import models as qmodels
from langchain_ollama import OllamaEmbeddings

from db_agent.core.config import get_settings
from db_agent.semantic.models import SemanticLayer, TableSemantic

settings = get_settings()
COLLECTION_NAME = "semantic_tables"

_client: QdrantClient | None = None
_embeddings: OllamaEmbeddings | None = None


def get_embeddings() -> OllamaEmbeddings:
    global _embeddings
    if _embeddings is None:
        _embeddings = OllamaEmbeddings(base_url=settings.ollama_base_url, model=settings.embedding_model)
    return _embeddings


def get_client() -> QdrantClient:
    global _client
    if _client is None:
        _client = QdrantClient(url=settings.qdrant_url)
        _ensure_collection(_client)
    return _client


def _ensure_collection(client: QdrantClient) -> None:
    if client.collection_exists(COLLECTION_NAME):
        return
    dim = len(get_embeddings().embed_query("dimension probe"))  # avoids hardcoding a guessed dim
    client.create_collection(
        collection_name=COLLECTION_NAME,
        vectors_config=qmodels.VectorParams(size=dim, distance=qmodels.Distance.COSINE),
    )


def _point_id(connection_id: str, table_name: str) -> str:
    return str(uuid.uuid5(uuid.NAMESPACE_DNS, f"{connection_id}:{table_name}"))


def _table_to_text(table: TableSemantic) -> str:
    col_lines = "\n".join(
        f"- {c.business_name} ({c.original_name}): {c.description}" for c in table.columns.values()
    )
    return f"Table: {table.business_name} ({table.original_name})\nDescription: {table.description}\nColumns:\n{col_lines}"


def index_semantic_layer(connection_id: str, layer: SemanticLayer) -> None:
    client = get_client()
    embeddings = get_embeddings()

    # clear any prior chunks for this connection before re-indexing (schema/semantic layer may have changed)
    client.delete(
        collection_name=COLLECTION_NAME,
        points_selector=qmodels.FilterSelector(
            filter=qmodels.Filter(
                must=[qmodels.FieldCondition(key="connection_id", match=qmodels.MatchValue(value=connection_id))]
            )
        ),
    )

    tables = list(layer.tables.values())
    if not tables:
        return

    texts = [_table_to_text(t) for t in tables]
    vectors = embeddings.embed_documents(texts)

    points = [
        qmodels.PointStruct(
            id=_point_id(connection_id, t.original_name),
            vector=vector,
            payload={"connection_id": connection_id, "table_name": t.original_name, "text": text},
        )
        for t, text, vector in zip(tables, texts, vectors)
    ]
    client.upsert(collection_name=COLLECTION_NAME, points=points)


def search_relevant_tables(
    connection_id: str,
    question: str,
    allowed_tables: list[str],
    top_k: int = 8,
) -> list[dict]:
    """Semantic search hard-scoped to this connection AND the user's selected-table allowlist."""
    if not allowed_tables:
        return []

    client = get_client()
    query_vector = get_embeddings().embed_query(question)

    results = client.search(
        collection_name=COLLECTION_NAME,
        query_vector=query_vector,
        query_filter=qmodels.Filter(
            must=[
                qmodels.FieldCondition(key="connection_id", match=qmodels.MatchValue(value=connection_id)),
                qmodels.FieldCondition(key="table_name", match=qmodels.MatchAny(any=allowed_tables)),
            ]
        ),
        limit=min(top_k, len(allowed_tables)),
    )
    return [{"table_name": r.payload["table_name"], "text": r.payload["text"], "score": r.score} for r in results]