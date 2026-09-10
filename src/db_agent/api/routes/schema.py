from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from db_agent.db.session import get_db
from db_agent.db.models import Connection, User
from db_agent.adapters.factory import get_adapter
from db_agent.adapters.config_resolver import resolve_adapter_config, GoogleSheetsNotConnectedError
from db_agent.auth.dependencies import get_current_user

router = APIRouter(prefix="/connections")


def _load_adapter(connection_id: str, current_user: User, db: Session):
    connection = (
        db.query(Connection)
        .filter(Connection.id == connection_id, Connection.user_id == current_user.id)
        .first()
    )
    if connection is None:
        raise HTTPException(status_code=404, detail="Connection not found")
    try:
        config = resolve_adapter_config(connection, current_user)
    except GoogleSheetsNotConnectedError as e:
        raise HTTPException(status_code=428, detail=str(e))
    return connection, get_adapter(connection.source_type, config)


@router.get("/{connection_id}/schema")
def get_schema(
    connection_id: str,
    tables: str | None = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _, adapter = _load_adapter(connection_id, current_user, db)
    table_names = tables.split(",") if tables else adapter.list_tables()
    schema = adapter.get_schema(table_names)
    return {
        "tables": [
            {"name": t.name, "columns": [
                {"name": c.name, "data_type": c.data_type, "is_primary_key": c.is_primary_key,
                 "is_foreign_key": c.is_foreign_key, "references": c.references, "nullable": c.nullable}
                for c in t.columns
            ]} for t in schema
        ]
    }