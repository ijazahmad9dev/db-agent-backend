import re

import duckdb
import gspread
import httpx
import pandas as pd
from google.oauth2.credentials import Credentials as OAuthCredentials
from google.oauth2.service_account import Credentials as ServiceAccountCredentials

from db_agent.adapters.base import DataSourceAdapter, TableInfo, ColumnInfo, QueryResult
from db_agent.adapters.duckdb_utils import run_with_timeout

_SCOPES = ["https://www.googleapis.com/auth/spreadsheets.readonly"]


def extract_spreadsheet_id(url_or_id: str) -> str:
    """Accepts either a raw spreadsheet ID or a full Google Sheets URL and returns the ID."""
    match = re.search(r"/spreadsheets/d/([a-zA-Z0-9_-]+)", url_or_id)
    if match:
        return match.group(1)
    return url_or_id.strip()  # assume it's already a bare ID

def _normalize_sheet_rows(header: list[str], rows: list[list[str]]) -> tuple[list[str], list[list[str]]]:
    """Google Sheets API rows are ragged (trailing empty cells omitted per-row,
    independently). Extend the header with placeholder names for any columns beyond
    what the header row declared, and pad every row to that full width — so no data
    is ever silently dropped or misaligned, regardless of which row is "widest"."""
    max_cols = max([len(header)] + [len(r) for r in rows]) if rows else len(header)

    full_header = list(header)
    for i in range(len(full_header), max_cols):
        full_header.append(f"column_{i + 1}")  # unnamed trailing columns get a generic label

    normalized_rows = [row + [""] * (max_cols - len(row)) for row in rows]
    return full_header, normalized_rows

class GoogleSheetsAdapter(DataSourceAdapter):
    source_type = "gsheets"

    def __init__(self, config: dict):
        # config shapes:
        #   public mode: {"spreadsheet_id": "...", "auth_mode": "public", "api_key": "...", "selected_sheets": [...]}
        #   oauth mode:  {"spreadsheet_id": "...", "auth_mode": "oauth", "refresh_token": "...",
        #                 "client_id": "...", "client_secret": "...", "selected_sheets": [...]}
        #   service_account mode (existing, unchanged): {"spreadsheet_id": "...", "service_account_json": {...}, "selected_sheets": [...]}
        self.config = config
        self.spreadsheet_id = extract_spreadsheet_id(config["spreadsheet_id"])
        self.auth_mode = config.get("auth_mode", "service_account")
        self._client = None
        self._con: duckdb.DuckDBPyConnection | None = None

    @property
    def client(self):
        if self._client is None:
            if self.auth_mode == "service_account":
                creds = ServiceAccountCredentials.from_service_account_info(
                    self.config["service_account_json"], scopes=_SCOPES
                )
                self._client = gspread.authorize(creds)
            elif self.auth_mode == "oauth":
                creds = OAuthCredentials(
                    token=None,
                    refresh_token=self.config["refresh_token"],
                    client_id=self.config["client_id"],
                    client_secret=self.config["client_secret"],
                    token_uri="https://oauth2.googleapis.com/token",
                    scopes=_SCOPES,
                )
                self._client = gspread.authorize(creds)
            # "public" mode never builds a gspread client — see _list_tables_public / _load_sheet_public below
        return self._client

    def _list_tables_public(self) -> list[str]:
        resp = httpx.get(
            f"https://sheets.googleapis.com/v4/spreadsheets/{self.spreadsheet_id}",
            params={"key": self.config["api_key"], "fields": "sheets.properties.title"},
        )
        resp.raise_for_status()
        all_sheets = [s["properties"]["title"] for s in resp.json().get("sheets", [])]
        selected = self.config.get("selected_sheets")
        return [s for s in all_sheets if s in selected] if selected else all_sheets

    def _load_sheet_public(self, sheet_name: str) -> pd.DataFrame:
        resp = httpx.get(
            f"https://sheets.googleapis.com/v4/spreadsheets/{self.spreadsheet_id}/values/{sheet_name}",
            params={"key": self.config["api_key"]},
        )
        resp.raise_for_status()
        values = resp.json().get("values", [])
        if not values:
            return pd.DataFrame()
        header, *rows = values
        full_header, normalized_rows = _normalize_sheet_rows(header, rows)
        return pd.DataFrame(normalized_rows, columns=full_header)

    @property
    def con(self) -> duckdb.DuckDBPyConnection:
        if self._con is None:
            self._con = duckdb.connect(":memory:")
            for name in self.list_tables():
                df = self._load_sheet_public(name) if self.auth_mode == "public" else self._load_sheet_authed(name)
                self._con.register(name, df)
        return self._con

    def _load_sheet_authed(self, sheet_name: str) -> pd.DataFrame:
        spreadsheet = self.client.open_by_key(self.spreadsheet_id)
        worksheet = spreadsheet.worksheet(sheet_name)
        values = worksheet.get_all_values()  # raw, ragged rows — NOT get_all_records(), which silently truncates
        if not values:
            return pd.DataFrame()
        header, *rows = values
        full_header, normalized_rows = _normalize_sheet_rows(header, rows)
        return pd.DataFrame(normalized_rows, columns=full_header)

    def test_connection(self) -> bool:
        try:
            self.list_tables()
            return True
        except Exception:
            return False

    def list_tables(self) -> list[str]:
        if self.auth_mode == "public":
            return self._list_tables_public()
        spreadsheet = self.client.open_by_key(self.spreadsheet_id)
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