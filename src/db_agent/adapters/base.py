from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any


@dataclass
class ColumnInfo:
    name: str
    data_type: str
    is_primary_key: bool = False
    is_foreign_key: bool = False
    references: str | None = None
    nullable: bool = True
    is_unique: bool = False   # new — determines FK cardinality (1:1 vs many-to-one)


@dataclass
class TableInfo:
    name: str
    columns: list[ColumnInfo] = field(default_factory=list)


@dataclass
class QueryResult:
    columns: list[str]
    rows: list[dict[str, Any]]
    row_count: int
    truncated: bool = False


class DataSourceAdapter(ABC):
    """Common interface every data source (SQL DB, CSV, Google Sheets, ...) must implement."""

    source_type: str

    @abstractmethod
    def test_connection(self) -> bool:
        """Return True if the connection/config is valid and reachable."""

    @abstractmethod
    def list_tables(self) -> list[str]:
        """List available tables/sheets."""

    @abstractmethod
    def get_schema(self, table_names: list[str]) -> list[TableInfo]:
        """Introspect schema (columns, types, PK/FK) for the given tables."""

    @abstractmethod
    def execute_query(self, query: str, row_limit: int, timeout_seconds: int) -> QueryResult:
        """Execute a validated, read-only query and return structured results."""

    @abstractmethod
    def sample_rows(self, table_name: str, limit: int = 5) -> QueryResult:
        """Return a small sample of rows — used for schema/semantic-layer context."""