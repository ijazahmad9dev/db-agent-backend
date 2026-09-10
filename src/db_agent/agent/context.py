from db_agent.db.session import SessionLocal
from db_agent.db.models import Connection, TableSelection
from db_agent.adapters.factory import get_adapter
from db_agent.adapters.config_resolver import resolve_adapter_config, GoogleSheetsNotConnectedError


class ConnectionContextError(Exception):
    """Raised when the agent can't establish adapter access for a connection — the caller
    (schema_retrieval node) turns this into a clean agent-level error, not a crash."""


def load_connection_context(connection_id: str):
    with SessionLocal() as db:
        connection = db.get(Connection, connection_id)
        if connection is None:
            raise ConnectionContextError(f"Connection not found: {connection_id}")

        owner = connection.owner  # SQLAlchemy relationship — loads the User row
        try:
            config = resolve_adapter_config(connection, owner)
        except GoogleSheetsNotConnectedError as e:
            raise ConnectionContextError(str(e))

        selected = db.query(TableSelection).filter(
            TableSelection.connection_id == connection_id, TableSelection.is_selected == True  # noqa: E712
        ).all()
        allowed_tables = [s.table_name for s in selected]
        top_k = connection.semantic_top_k

        adapter = get_adapter(connection.source_type, config)
        return adapter, allowed_tables, top_k, connection.source_type