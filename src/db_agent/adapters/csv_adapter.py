import duckdb

from db_agent.adapters.base import DataSourceAdapter, TableInfo, ColumnInfo, QueryResult
from db_agent.adapters.duckdb_utils import run_with_timeout
import logging

logger = logging.getLogger(__name__)

class CSVAdapter(DataSourceAdapter):
    source_type = "csv"

    def __init__(self, config: dict):
        # config: {"files": [{"table_name": "orders", "file_path": "..."}, ...]}
        self.config = config
        self._con: duckdb.DuckDBPyConnection | None = None

    @property
    def con(self) -> duckdb.DuckDBPyConnection:
        if self._con is None:
            self._con = duckdb.connect(":memory:")
            for entry in self.config["files"]:
                escaped_path = entry["file_path"].replace("'", "''")
                self._con.execute(
                    f'CREATE VIEW "{entry["table_name"]}" AS SELECT * FROM read_csv_auto(\'{escaped_path}\')'
                )
        return self._con

    def test_connection(self) -> bool:
        try:
            for name in self.list_tables():
                self.con.execute(f'SELECT * FROM "{name}" LIMIT 1')
            return True
        except Exception:
            logger.exception("CSV connection test failed")  # now prints the real traceback to the backend terminal
            return False

    def list_tables(self) -> list[str]:
        return [f["table_name"] for f in self.config["files"]]

    def get_schema(self, table_names: list[str]) -> list[TableInfo]:
        tables = []
        for name in table_names:
            rows = self.con.execute(f'DESCRIBE "{name}"').fetchall()
            columns = [ColumnInfo(name=r[0], data_type=r[1], nullable=True) for r in rows]
            tables.append(TableInfo(name=name, columns=columns))
        return tables

    def execute_query(self, query: str, row_limit: int, timeout_seconds: int) -> QueryResult:
        # `query` is now real SQL, referencing table names directly (e.g. "orders", "customers") —
        # same generator/validator path as Postgres/MySQL applies here now.
        result = run_with_timeout(self.con, query, timeout_seconds)
        columns = [d[0] for d in result.description]
        rows_raw = result.fetchmany(row_limit + 1)
        truncated = len(rows_raw) > row_limit
        rows = [dict(zip(columns, row)) for row in rows_raw[:row_limit]]
        return QueryResult(columns=columns, rows=rows, row_count=len(rows), truncated=truncated)

    def sample_rows(self, table_name: str, limit: int = 5) -> QueryResult:
        return self.execute_query(f'SELECT * FROM "{table_name}" LIMIT {limit}', row_limit=limit, timeout_seconds=10)