import duckdb
import gspread
import pandas as pd
from google.oauth2.service_account import Credentials

from db_agent.adapters.base import DataSourceAdapter, TableInfo, ColumnInfo, QueryResult
from db_agent.adapters.duckdb_utils import run_with_timeout

_SCOPES = ["https://www.googleapis.com/auth/spreadsheets.readonly"]


class GoogleSheetsAdapter(DataSourceAdapter):
    source_type = "gsheets"

    def __init__(self, config: dict):
        self.config = config
        self._client = None
        self._con: duckdb.DuckDBPyConnection | None = None

    @property
    def client(self):
        if self._client is None:
            creds = Credentials.from_service_account_info(self.config["service_account_json"], scopes=_SCOPES)
            self._client = gspread.authorize(creds)
        return self._client

    @property
    def con(self) -> duckdb.DuckDBPyConnection:
        if self._con is None:
            self._con = duckdb.connect(":memory:")
            spreadsheet = self.client.open_by_key(self.config["spreadsheet_id"])
            for name in self.list_tables():
                df = pd.DataFrame(spreadsheet.worksheet(name).get_all_records())
                self._con.register(name, df)  # DuckDB can query a registered DataFrame directly, no CSV round-trip
        return self._con

    def test_connection(self) -> bool:
        try:
            self.client.open_by_key(self.config["spreadsheet_id"])
            return True
        except Exception:
            return False

    def list_tables(self) -> list[str]:
        spreadsheet = self.client.open_by_key(self.config["spreadsheet_id"])
        all_sheets = [ws.title for ws in spreadsheet.worksheets()]
        selected = self.config.get("selected_sheets")
        return [s for s in all_sheets if s in selected] if selected else all_sheets

    def get_schema(self, table_names: list[str]) -> list[TableInfo]:
        tables = []
        for name in table_names:
            rows = self.con.execute(f'DESCRIBE "{name}"').fetchall()
            columns = [ColumnInfo(name=r[0], data_type=r[1], nullable=True) for r in rows]
            tables.append(TableInfo(name=name, columns=columns))
        return tables

    def execute_query(self, query: str, row_limit: int, timeout_seconds: int) -> QueryResult:
        result = run_with_timeout(self.con, query, timeout_seconds)
        columns = [d[0] for d in result.description]
        rows_raw = result.fetchmany(row_limit + 1)
        truncated = len(rows_raw) > row_limit
        rows = [dict(zip(columns, row)) for row in rows_raw[:row_limit]]
        return QueryResult(columns=columns, rows=rows, row_count=len(rows), truncated=truncated)

    def sample_rows(self, table_name: str, limit: int = 5) -> QueryResult:
        return self.execute_query(f'SELECT * FROM "{table_name}" LIMIT {limit}', row_limit=limit, timeout_seconds=10)