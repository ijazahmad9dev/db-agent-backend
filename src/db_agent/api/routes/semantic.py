from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from db_agent.db.session import get_db
from db_agent.db.models import User
from db_agent.api.routes.schema import _load_adapter
from db_agent.semantic.models import SemanticLayer, RelationshipsUpdate
from db_agent.semantic.drafter import draft_table_semantic
from db_agent.semantic.loader import save_semantic_layer, load_semantic_layer
from db_agent.semantic.vectorstore import index_semantic_layer
from db_agent.auth.dependencies import get_current_user

router = APIRouter(prefix="/connections")

# Manual relationship editing only makes sense for connection types with real,
# introspected FK constraints — CSV/Sheets relationships are already fully
# user-controlled via the drafted semantic layer's `relationships` list, so this
# separate CRUD surface is scoped to Postgres/MySQL only, per product decision.
_RELATIONSHIP_EDITABLE_SOURCE_TYPES = {"postgres", "mysql"}


@router.post("/{connection_id}/semantic/draft")
def draft_semantic_layer(
    connection_id: str,
    tables: str | None = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _, adapter = _load_adapter(connection_id, current_user, db)
    table_names = tables.split(",") if tables else adapter.list_tables()
    schema = adapter.get_schema(table_names)

    table_semantics = {t.name: draft_table_semantic(adapter, t) for t in schema}
    layer = SemanticLayer(connection_id=connection_id, tables=table_semantics)

    save_semantic_layer(layer)
    index_semantic_layer(connection_id, layer)
    return layer.model_dump()


@router.get("/{connection_id}/semantic")
def get_semantic_layer(
    connection_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _load_adapter(connection_id, current_user, db)  # ownership check, discard the adapter
    layer = load_semantic_layer(connection_id)
    if layer is None:
        raise HTTPException(status_code=404, detail="No semantic layer drafted yet for this connection")
    return layer.model_dump()


@router.put("/{connection_id}/semantic")
def update_semantic_layer(
    connection_id: str,
    layer: SemanticLayer,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _load_adapter(connection_id, current_user, db)
    if layer.connection_id != connection_id:
        raise HTTPException(status_code=400, detail="connection_id mismatch")

    # Relationship changes (add/edit/delete) must go through PUT /semantic/relationships,
    # which enforces the Postgres/MySQL-only restriction in one place. This endpoint is
    # for table/column business metadata only — whatever the client sends for
    # relationships/removed_relationships here is discarded and the existing stored
    # values are kept, so this can't be used as a bypass of that restriction.
    existing = load_semantic_layer(connection_id)
    layer.relationships = existing.relationships if existing else []
    layer.removed_relationships = existing.removed_relationships if existing else []

    save_semantic_layer(layer)
    index_semantic_layer(connection_id, layer)
    return layer.model_dump()


@router.put("/{connection_id}/semantic/relationships")
def update_relationships(
    connection_id: str,
    payload: RelationshipsUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    connection, _ = _load_adapter(connection_id, current_user, db)
    if connection.source_type not in _RELATIONSHIP_EDITABLE_SOURCE_TYPES:
        raise HTTPException(
            status_code=400,
            detail=(
                f"Manual relationship editing is only available for Postgres/MySQL connections "
                f"(this connection is '{connection.source_type}')."
            ),
        )

    layer = load_semantic_layer(connection_id)
    if layer is None:
        raise HTTPException(status_code=404, detail="No semantic layer found for this connection.")

    layer.relationships = payload.relationships
    layer.removed_relationships = payload.removed_relationships
    save_semantic_layer(layer)
    index_semantic_layer(connection_id, layer)
    return layer.model_dump()


@router.patch("/{connection_id}/semantic-config")
def update_semantic_config(
    connection_id: str,
    top_k: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    connection, _ = _load_adapter(connection_id, current_user, db)
    connection.semantic_top_k = top_k
    db.commit()
    return {"connection_id": connection_id, "semantic_top_k": top_k}