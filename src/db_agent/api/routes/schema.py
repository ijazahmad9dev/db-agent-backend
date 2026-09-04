from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from db_agent.db.session import get_db
from db_agent.db.models import Connection
from db_agent.security.credentials import decrypt_config
from db_agent.adapters.factory import get_adapter

router = APIRouter(prefix="/connections")


def _load_adapter(connection_id: str, db: Session):
    connection = db.get(Connection, connection_id)
    if connection is None:
        raise HTTPException(status_code=404, detail="Connection not found")
    return connection, get_adapter(connection.source_type, decrypt_config(connection.encrypted_config))


@router.get("/{connection_id}/schema")
def get_schema(connection_id: str, tables: str | None = None, db: Session = Depends(get_db)):
    _, adapter = _load_adapter(connection_id, db)
    table_names = tables.split(",") if tables else adapter.list_tables()
    schema = adapter.get_schema(table_names)
    return {
        "tables": [
            {
                "name": t.name,
                "columns": [
                    {"name": c.name, "data_type": c.data_type, "is_primary_key": c.is_primary_key,
                     "is_foreign_key": c.is_foreign_key, "references": c.references, "nullable": c.nullable}
                    for c in t.columns
                ],
            }
            for t in schema
        ]
    }