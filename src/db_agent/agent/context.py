from db_agent.db.session import SessionLocal
from db_agent.db.models import Connection, TableSelection
from db_agent.security.credentials import decrypt_config
from db_agent.adapters.factory import get_adapter


def load_connection_context(connection_id: str):
    with SessionLocal() as db:
        connection = db.get(Connection, connection_id)
        if connection is None:
            raise ValueError(f"Connection not found: {connection_id}")
        selected = db.query(TableSelection).filter(
            TableSelection.connection_id == connection_id, TableSelection.is_selected == True  # noqa: E712
        ).all()
        allowed_tables = [s.table_name for s in selected]
        top_k = connection.semantic_top_k

        config = decrypt_config(connection.encrypted_config)
        adapter = get_adapter(connection.source_type, config)
        return adapter, allowed_tables, top_k, connection.source_type