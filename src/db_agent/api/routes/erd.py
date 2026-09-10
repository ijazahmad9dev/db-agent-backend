from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from db_agent.db.session import get_db
from db_agent.db.models import TableSelection, User
from db_agent.api.routes.schema import _load_adapter
from db_agent.introspection.erd_builder import build_erd, merge_semantic_relationships
from db_agent.semantic.loader import load_semantic_layer
from db_agent.auth.dependencies import get_current_user

router = APIRouter(prefix="/connections")


@router.get("/{connection_id}/erd")
def get_erd(
    connection_id: str,
    tables: str | None = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _, adapter = _load_adapter(connection_id, current_user, db)

    if tables:
        table_names = tables.split(",")
    else:
        selected = db.query(TableSelection).filter(
            TableSelection.connection_id == connection_id, TableSelection.is_selected == True  # noqa: E712
        ).all()
        table_names = [s.table_name for s in selected]

    if not table_names:
        return {"nodes": [], "edges": []}

    erd = build_erd(adapter.get_schema(table_names))
    semantic_layer = load_semantic_layer(connection_id)
    erd = merge_semantic_relationships(erd, semantic_layer)
    return erd