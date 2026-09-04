import pandas as pd

from db_agent.adapters.base import DataSourceAdapter, TableInfo, ColumnInfo, QueryResult


class CSVAdapter(DataSourceAdapter):
    source_type = "csv"

    def __init__(self, config: dict):
        # config: {"files": [{"table_name": "orders", "file_path": "storage/uploads/<conn_id>/orders.csv"}, ...]}
        self.config = config
        self._frames: dict[str, pd.DataFrame] = {}

    def _load(self, table_name: str) -> pd.DataFrame:
        if table_name not in self._frames:
            entry = next((f for f in self.config["files"] if f["table_name"] == table_name), None)
            if entry is None:
                raise ValueError(f"Unknown CSV table: {table_name}")
            self._frames[table_name] = pd.read_csv(entry["file_path"])
        return self._frames[table_name]

    def test_connection(self) -> bool:
        try:
            for entry in self.config["files"]:
                pd.read_csv(entry["file_path"], nrows=1)
            return True
        except Exception:
            return False

    def list_tables(self) -> list[str]:
        return [f["table_name"] for f in self.config["files"]]

    def get_schema(self, table_names: list[str]) -> list[TableInfo]:
        tables = []
        for name in table_names:
            df = self._load(name)
            columns = [
                ColumnInfo(name=col, data_type=str(dtype), is_primary_key=False, nullable=True)
                for col, dtype in df.dtypes.items()
            ]
            tables.append(TableInfo(name=name, columns=columns))
        return tables

    def execute_query(self, query: str, row_limit: int, timeout_seconds: int) -> QueryResult:
        # Convention matches GoogleSheetsAdapter: reference each table as df_<table_name>
        # e.g. "df_orders.merge(df_customers, on='customer_id')"
        local_vars = {f"df_{name}": self._load(name) for name in self.list_tables()}
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
        df = self._load(table_name).head(limit)
        return QueryResult(
            columns=list(df.columns),
            rows=df.to_dict(orient="records"),
            row_count=len(df),
            truncated=False,
        )