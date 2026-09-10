from sqlalchemy import create_engine, inspect, text
from sqlalchemy.engine import Engine

from db_agent.adapters.base import DataSourceAdapter, TableInfo, ColumnInfo, QueryResult


class MySQLAdapter(DataSourceAdapter):
    source_type = "mysql"

    def __init__(self, config: dict):
        self.config = config
        self._engine: Engine | None = None

    @property
    def engine(self) -> Engine:
        if self._engine is None:
            url = (
                f"mysql+pymysql://{self.config['user']}:{self.config['password']}"
                f"@{self.config['host']}:{self.config['port']}/{self.config['database']}"
            )
            self._engine = create_engine(url, pool_pre_ping=True)
        return self._engine

    def test_connection(self) -> bool:
        try:
            with self.engine.connect() as conn:
                conn.execute(text("SELECT 1"))
            return True
        except Exception:
            return False

    def list_tables(self) -> list[str]:
        return inspect(self.engine).get_table_names()

    def get_schema(self, table_names: list[str]) -> list[TableInfo]:
        inspector = inspect(self.engine)
        tables = []
        for name in table_names:
            pk_cols = set(inspector.get_pk_constraint(name).get("constrained_columns", []))
            unique_cols = set()
            for uc in inspector.get_unique_constraints(name):
                if len(uc["column_names"]) == 1:
                    unique_cols.add(uc["column_names"][0])

            fk_map = {}
            for fk in inspector.get_foreign_keys(name):
                for local_col, remote_col in zip(fk["constrained_columns"], fk["referred_columns"]):
                    fk_map[local_col] = f"{fk['referred_table']}.{remote_col}"

            columns = [
                ColumnInfo(
                    name=col["name"],
                    data_type=str(col["type"]),
                    is_primary_key=col["name"] in pk_cols,
                    is_foreign_key=col["name"] in fk_map,
                    references=fk_map.get(col["name"]),
                    nullable=col.get("nullable", True),
                    is_unique=col["name"] in unique_cols or col["name"] in pk_cols,
                )
                for col in inspector.get_columns(name)
            ]
            tables.append(TableInfo(name=name, columns=columns))
        return tables

    def execute_query(self, query: str, row_limit: int, timeout_seconds: int) -> QueryResult:
        with self.engine.connect() as conn:
            # MySQL syntax — NOT Postgres's "SET statement_timeout". MAX_EXECUTION_TIME
            # is milliseconds and, per MySQL docs, only enforced on SELECT statements —
            # acceptable here since sql_guard already restricts generated queries to SELECT.
            conn.execute(text(f"SET SESSION MAX_EXECUTION_TIME={timeout_seconds * 1000}"))
            result = conn.execute(text(query))
            columns = list(result.keys())
            rows = []
            for i, row in enumerate(result):
                if i >= row_limit:
                    return QueryResult(columns=columns, rows=rows, row_count=len(rows), truncated=True)
                rows.append(dict(zip(columns, row)))
            return QueryResult(columns=columns, rows=rows, row_count=len(rows), truncated=False)

    def sample_rows(self, table_name: str, limit: int = 5) -> QueryResult:
        return self.execute_query(f"SELECT * FROM {table_name} LIMIT {limit}", row_limit=limit, timeout_seconds=10)