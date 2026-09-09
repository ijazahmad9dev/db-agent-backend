from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from db_agent.db.session import get_db
from db_agent.api.routes.schema import _load_adapter
from db_agent.introspection.erd_builder import build_erd
from db_agent.semantic.loader import load_semantic_layer
from db_agent.introspection.erd_builder import build_erd, merge_semantic_relationships

router = APIRouter(prefix="/connections")


@router.get("/{connection_id}/erd")
def get_erd(connection_id: str, tables: str | None = None, db: Session = Depends(get_db)):
    connection, adapter = _load_adapter(connection_id, db)
    table_names = tables.split(",") if tables else adapter.list_tables()
    erd = build_erd(adapter.get_schema(table_names))

    semantic_layer = load_semantic_layer(connection_id)
    erd = merge_semantic_relationships(erd, semantic_layer)
    return erd