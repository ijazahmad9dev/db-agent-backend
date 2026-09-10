import uuid

from qdrant_client.http import models as qmodels

from db_agent.semantic.vectorstore import get_client, get_embeddings
from db_agent.adapters.base import TableInfo

COLLECTION_NAME = "schema_ddl"


def _ensure_collection(client) -> None:
    if client.collection_exists(COLLECTION_NAME):
        return
    dim = len(get_embeddings().embed_query("dimension probe"))
    client.create_collection(
        collection_name=COLLECTION_NAME,
        vectors_config=qmodels.VectorParams(size=dim, distance=qmodels.Distance.COSINE),
    )


def _point_id(connection_id: str, table_name: str) -> str:
    return str(uuid.uuid5(uuid.NAMESPACE_DNS, f"ddl:{connection_id}:{table_name}"))


def _table_to_ddl_text(table: TableInfo) -> str:
    lines = [f"TABLE {table.name} ("]
    for c in table.columns:
        parts = [c.name, c.data_type]
        if c.is_primary_key:
            parts.append("PRIMARY KEY")
        if c.is_foreign_key and c.references:
            parts.append(f"REFERENCES {c.references}")
        lines.append("  " + " ".join(parts))
    lines.append(")")
    return "\n".join(lines)


def _fk_targets(table: TableInfo) -> list[str]:
    return sorted({c.references.split(".")[0] for c in table.columns if c.is_foreign_key and c.references})


def index_ddl(connection_id: str, tables: list[TableInfo]) -> None:
    client = get_client()
    _ensure_collection(client)
    embeddings = get_embeddings()

    client.delete(
        collection_name=COLLECTION_NAME,
        points_selector=qmodels.FilterSelector(
            filter=qmodels.Filter(
                must=[qmodels.FieldCondition(key="connection_id", match=qmodels.MatchValue(value=connection_id))]
            )
        ),
    )
    if not tables:
        return

    texts = [_table_to_ddl_text(t) for t in tables]
    vectors = embeddings.embed_documents(texts)

    points = [
        qmodels.PointStruct(
            id=_point_id(connection_id, t.name),
            vector=vector,
            payload={
                "connection_id": connection_id,
                "table_name": t.name,
                "ddl_text": text,
                "fk_targets": _fk_targets(t),  # used for join-aware expansion below
            },
        )
        for t, text, vector in zip(tables, texts, vectors)
    ]
    client.upsert(collection_name=COLLECTION_NAME, points=points)


def search_relevant_schema(
    connection_id: str,
    question: str,
    allowed_tables: list[str],
    top_k: int = 8,
    expand_joins: bool = True,
) -> list[dict]:
    """
    Vector search scoped to allowed_tables, THEN expanded to include any table that's
    FK-related to a retrieved table (still restricted to allowed_tables). This exists
    specifically to avoid the failure mode where a join needs two tables but only one
    scores high enough to make top-k on its own.
    """
    if not allowed_tables:
        return []

    client = get_client()
    _ensure_collection(client)
    query_vector = get_embeddings().embed_query(question)

    response = client.query_points(
        collection_name=COLLECTION_NAME,
        query=query_vector,
        query_filter=qmodels.Filter(
            must=[
                qmodels.FieldCondition(key="connection_id", match=qmodels.MatchValue(value=connection_id)),
                qmodels.FieldCondition(key="table_name", match=qmodels.MatchAny(any=allowed_tables)),
            ]
        ),
        limit=min(top_k, len(allowed_tables)),
    )
    results = {p.payload["table_name"]: {"table_name": p.payload["table_name"], "ddl_text": p.payload["ddl_text"], "score": p.score} for p in response.points}

    if expand_joins:
        allowed_set = set(allowed_tables)
        related_needed = set()
        for r in list(results.values()):
            fk_targets = next((p.payload.get("fk_targets", []) for p in response.points if p.payload["table_name"] == r["table_name"]), [])
            related_needed.update(t for t in fk_targets if t in allowed_set and t not in results)

        if related_needed:
            expanded = client.scroll(
                collection_name=COLLECTION_NAME,
                scroll_filter=qmodels.Filter(
                    must=[
                        qmodels.FieldCondition(key="connection_id", match=qmodels.MatchValue(value=connection_id)),
                        qmodels.FieldCondition(key="table_name", match=qmodels.MatchAny(any=list(related_needed))),
                    ]
                ),
                limit=len(related_needed),
            )[0]
            for point in expanded:
                results[point.payload["table_name"]] = {
                    "table_name": point.payload["table_name"],
                    "ddl_text": point.payload["ddl_text"],
                    "score": None,  # added via join expansion, not ranked by relevance
                }

    return list(results.values())

def delete_connection_ddl(connection_id: str) -> None:
    client = get_client()
    _ensure_collection(client)
    client.delete(
        collection_name=COLLECTION_NAME,
        points_selector=qmodels.FilterSelector(
            filter=qmodels.Filter(must=[qmodels.FieldCondition(key="connection_id", match=qmodels.MatchValue(value=connection_id))])
        ),
    )