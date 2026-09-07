"""
Temp test for the DuckDB-based CSVAdapter (and the shared timeout mechanism).
No server needed — this tests the adapter layer directly.
Run with:  uv run python scripts/test_duckdb_adapters.py
"""
import tempfile
from pathlib import Path

import pandas as pd

from db_agent.adapters.factory import get_adapter


def test_basic_schema_and_sample(tmp_dir: Path):
    print("=== 1. Schema + sample_rows compatibility (unchanged shape from Pandas version) ===")
    orders = pd.DataFrame({"order_id": [1, 2, 3], "customer_id": [1, 2, 1], "total_amount": [100.0, 250.5, 75.0]})
    orders.to_csv(tmp_dir / "orders.csv", index=False)

    adapter = get_adapter("csv", {"files": [{"table_name": "orders", "file_path": str(tmp_dir / "orders.csv")}]})
    assert adapter.test_connection() is True, "test_connection failed on a valid CSV"
    assert adapter.list_tables() == ["orders"]

    schema = adapter.get_schema(["orders"])
    col_names = {c.name for c in schema[0].columns}
    assert col_names == {"order_id", "customer_id", "total_amount"}, f"unexpected columns: {col_names}"
    print(f"OK — schema: {[(c.name, c.data_type) for c in schema[0].columns]}")

    sample = adapter.sample_rows("orders", limit=2)
    assert sample.row_count == 2
    print(f"OK — sample_rows returned {sample.row_count} rows: {sample.rows}")


def test_real_sql_join_across_files(tmp_dir: Path):
    print("\n=== 2. Real SQL JOIN across two CSV files (impossible cleanly with old eval() approach) ===")
    orders = pd.DataFrame({"order_id": [1, 2, 3], "customer_id": [1, 2, 1], "total_amount": [100.0, 250.5, 75.0]})
    customers = pd.DataFrame({"customer_id": [1, 2], "name": ["Alice", "Bob"], "region": ["east", "west"]})
    orders.to_csv(tmp_dir / "orders.csv", index=False)
    customers.to_csv(tmp_dir / "customers.csv", index=False)

    adapter = get_adapter("csv", {
        "files": [
            {"table_name": "orders", "file_path": str(tmp_dir / "orders.csv")},
            {"table_name": "customers", "file_path": str(tmp_dir / "customers.csv")},
        ]
    })

    result = adapter.execute_query(
        '''
        SELECT c.region, SUM(o.total_amount) AS total_revenue
        FROM "orders" o
        JOIN "customers" c ON o.customer_id = c.customer_id
        GROUP BY c.region
        ORDER BY total_revenue DESC
        ''',
        row_limit=100,
        timeout_seconds=10,
    )
    print(f"columns: {result.columns}")
    print(f"rows: {result.rows}")
    assert result.columns == ["region", "total_revenue"]
    by_region = {r["region"]: r["total_revenue"] for r in result.rows}
    assert by_region["east"] == 175.0, f"expected east=175.0, got {by_region}"  # orders 1+3
    assert by_region["west"] == 250.5, f"expected west=250.5, got {by_region}"  # order 2
    print("OK — join + group-by aggregation across two files is numerically correct")


def test_row_limit_truncation(tmp_dir: Path):
    print("\n=== 3. Row-limit truncation behaves correctly ===")
    big = pd.DataFrame({"n": list(range(50))})
    big.to_csv(tmp_dir / "big.csv", index=False)

    adapter = get_adapter("csv", {"files": [{"table_name": "big", "file_path": str(tmp_dir / "big.csv")}]})
    result = adapter.execute_query('SELECT * FROM "big" ORDER BY n', row_limit=10, timeout_seconds=5)

    assert result.row_count == 10, f"expected 10 rows, got {result.row_count}"
    assert result.truncated is True, "expected truncated=True when more rows exist than row_limit"
    print(f"OK — returned {result.row_count} rows, truncated={result.truncated}")

    result_full = adapter.execute_query('SELECT * FROM "big" ORDER BY n', row_limit=100, timeout_seconds=5)
    assert result_full.row_count == 50
    assert result_full.truncated is False
    print(f"OK — with a high enough limit, returned all {result_full.row_count} rows, truncated={result_full.truncated}")


def test_timeout_mechanism(tmp_dir: Path):
    print("\n=== 4. Timeout mechanism (best-effort, per known caveat) ===")
    small = pd.DataFrame({"n": [1, 2, 3]})
    small.to_csv(tmp_dir / "small.csv", index=False)
    adapter = get_adapter("csv", {"files": [{"table_name": "small", "file_path": str(tmp_dir / "small.csv")}]})

    # Pin to a single thread so this is reliably slow regardless of machine core count —
    # DuckDB's default multi-threading made the original cross-join finish before the timeout fired.
    adapter.con.execute("PRAGMA threads=1")
    slow_query = "SELECT COUNT(*) FROM range(2000000000) a, range(20) b"

    try:
        adapter.execute_query(slow_query, row_limit=10, timeout_seconds=1)
        print("FAIL — expected a TimeoutError but query completed instead")
    except TimeoutError as e:
        print(f"OK — timeout correctly raised: {e}")
    except Exception as e:
        print(f"FAIL — expected TimeoutError specifically, got {type(e).__name__}: {e}")

    # confirm the adapter's connection is still usable after an interrupted query
    result = adapter.execute_query('SELECT * FROM "small"', row_limit=10, timeout_seconds=5)
    assert result.row_count == 3
    print(f"OK — connection still usable after timeout/interrupt: {result.row_count} rows")


def main():
    with tempfile.TemporaryDirectory() as tmp:
        tmp_dir = Path(tmp)
        test_basic_schema_and_sample(tmp_dir)
        test_real_sql_join_across_files(tmp_dir)
        test_row_limit_truncation(tmp_dir)
        test_timeout_mechanism(tmp_dir)
    print("\nAll DuckDB adapter checks completed.")


if __name__ == "__main__":
    main()