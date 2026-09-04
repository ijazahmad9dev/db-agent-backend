from db_agent.adapters.base import DataSourceAdapter
from db_agent.adapters.postgres_adapter import PostgresAdapter
from db_agent.adapters.mysql_adapter import MySQLAdapter
from db_agent.adapters.csv_adapter import CSVAdapter
from db_agent.adapters.gsheets_adapter import GoogleSheetsAdapter

_ADAPTER_REGISTRY: dict[str, type[DataSourceAdapter]] = {
    "postgres": PostgresAdapter,
    "mysql": MySQLAdapter,
    "csv": CSVAdapter,
    "gsheets": GoogleSheetsAdapter,
}


def get_adapter(source_type: str, config: dict) -> DataSourceAdapter:
    adapter_cls = _ADAPTER_REGISTRY.get(source_type)
    if adapter_cls is None:
        raise ValueError(f"Unsupported source_type: {source_type}")
    return adapter_cls(config)