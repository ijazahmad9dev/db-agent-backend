import gspread
import pandas as pd
from google.oauth2.service_account import Credentials

from db_agent.adapters.base import DataSourceAdapter, TableInfo, ColumnInfo, QueryResult

_SCOPES = ["https://www.googleapis.com/auth/spreadsheets.readonly"]


class GoogleSheetsAdapter(DataSourceAdapter):
    source_type = "gsheets"

    def __init__(self, config: dict):
        # config: {"spreadsheet_id": "...", "service_account_json": "...", "selected_sheets": [...]}
        self.config = config
        self._client = None
        self._sheet_frames: dict[str, pd.DataFrame] = {}

    @property
    def client(self):
        if self._client is None:
            creds = Credentials.from_service_account_info(
                self.config["service_account_json"], scopes=_SCOPES
            )
            self._client = gspread.authorize(creds)
        return self._client

    def _load_sheet(self, sheet_name: str) -> pd.DataFrame:
        if sheet_name not in self._sheet_frames:
            spreadsheet = self.client.open_by_key(self.config["spreadsheet_id"])
            worksheet = spreadsheet.worksheet(sheet_name)
            records = worksheet.get_all_records()
            self._sheet_frames[sheet_name] = pd.DataFrame(records)
        return self._sheet_frames[sheet_name]

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
            df = self._load_sheet(name)
            columns = [
                ColumnInfo(name=col, data_type=str(dtype), is_primary_key=False, nullable=True)
                for col, dtype in df.dtypes.items()
            ]
            tables.append(TableInfo(name=name, columns=columns))
        return tables

    def execute_query(self, query: str, row_limit: int, timeout_seconds: int) -> QueryResult:
        # `query` is a pandas expression like the CSV adapter, but must reference which
        # sheet(s) it uses via a "df_<sheet_name>" convention supplied by the generator.
        local_vars = {f"df_{name}": self._load_sheet(name) for name in self.list_tables()}
        local_vars["pd"] = pd
        result_df = eval(query, {"__builtins__": {}}, local_vars)  # noqa: S307 — restricted, validated expr only
        if not isinstance(result_df, pd.DataFrame):
            result_df = pd.DataFrame(result_df)

        truncated = len(result_df) > row_limit
        result_df = result_df.head(row_limit)
        return QueryResult(
            columns=list(result_df.columns),
            rows=result_df.to_dict(orient="records"),
            row_count=len(result_df),
            truncated=truncated,
        )

    def sample_rows(self, table_name: str, limit: int = 5) -> QueryResult:
        df = self._load_sheet(table_name).head(limit)
        return QueryResult(
            columns=list(df.columns),
            rows=df.to_dict(orient="records"),
            row_count=len(df),
            truncated=False,
        )