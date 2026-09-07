"""
Temp integration test for Day 3: query generator, validator, sql_guard, executor,
result processor, visualization inference — and a manual generate/validate/retry
chain previewing what Day 4's LangGraph loop will automate.

No API server needed — tests the query pipeline modules directly against a
DuckDB-backed CSV adapter.

Run with:  uv run python scripts/test_day3.py
(Ollama must be running locally with OLLAMA_MODEL pulled for steps 5-6)
"""
import tempfile
from pathlib import Path

import pandas as pd

from db_agent.adapters.factory import get_adapter
from db_agent.security.sql_guard import guard_read_only, extract_referenced_tables, SQLGuardError
from db_agent.query.validator import validate_query
from db_agent.query.executor import execute_query
from db_agent.results.processor import process_result
from db_agent.results.visualization import infer_visualization
from db_agent.query.generator import generate_query

MAX_RETRIES = 3


def make_test_adapter(tmp_dir: Path):
    orders = pd.DataFrame({
        "order_id": [1, 2, 3, 4],
        "customer_id": [1, 2, 1, 2],
        "total_amount": [100.0, 250.5, 75.0, 60.0],
    })
    customers = pd.DataFrame({
        "customer_id": [1, 2],
        "name": ["Alice", "Bob"],
        "region": ["east", "west"],
    })
    orders.to_csv(tmp_dir / "orders.csv", index=False)
    customers.to_csv(tmp_dir / "customers.csv", index=False)

    return get_adapter("csv", {
        "files": [
            {"table_name": "orders", "file_path": str(tmp_dir / "orders.csv")},
            {"table_name": "customers", "file_path": str(tmp_dir / "customers.csv")},
        ]
    })


def test_sql_guard():
    print("=== 1. sql_guard: destructive/unsafe query rejection ===")
    bad_queries = {
        "DELETE FROM orders": "destructive DELETE",
        "DROP TABLE orders": "destructive DROP",
        "SELECT * FROM orders; DROP TABLE orders": "stacked statements",
        "SELECT * FROM orders -- comment": "SQL comment",
        "UPDATE orders SET total_amount = 0": "destructive UPDATE",
    }
    for query, label in bad_queries.items():
        try:
            guard_read_only(query)
            print(f"FAIL — expected rejection for {label}: {query!r}")
        except SQLGuardError as e:
            print(f"OK — blocked ({label}): {e}")

    good_query = "SELECT region, SUM(total_amount) FROM orders o JOIN customers c ON o.customer_id = c.customer_id GROUP BY region"
    try:
        guard_read_only(good_query)
        print(f"OK — valid SELECT passed guard")
    except SQLGuardError as e:
        print(f"FAIL — valid SELECT was incorrectly rejected: {e}")


def test_extract_referenced_tables():
    print("\n=== 2. extract_referenced_tables ===")
    query = 'SELECT o.order_id, c.name FROM "orders" o JOIN "customers" c ON o.customer_id = c.customer_id'
    tables = extract_referenced_tables(query)
    print(f"Extracted: {tables}")
    assert tables == {"orders", "customers"}, f"expected {{'orders', 'customers'}}, got {tables}"
    print("OK — correctly extracted both joined tables")


def test_validator(adapter):
    print("\n=== 3. validate_query: allowlist + schema checks ===")
    schema = adapter.get_schema(["orders", "customers"])

    # valid: within allowed tables, tables exist
    result = validate_query(
        'SELECT region, SUM(total_amount) FROM orders o JOIN customers c ON o.customer_id = c.customer_id GROUP BY region',
        schema=schema,
        allowed_tables=["orders", "customers"],
    )
    print(f"Valid query -> is_valid={result.is_valid}, error={result.error}")
    assert result.is_valid is True

    # invalid: references a table outside the allowlist (security boundary)
    result = validate_query(
        "SELECT * FROM orders",
        schema=schema,
        allowed_tables=["customers"],  # orders deliberately NOT allowed
    )
    print(f"Unauthorized-table query -> is_valid={result.is_valid}, error={result.error}")
    assert result.is_valid is False and "unauthorized" in result.error.lower()
    print("OK — allowlist violation correctly rejected")

    # invalid: destructive
    result = validate_query("DELETE FROM orders", schema=schema, allowed_tables=["orders"])
    assert result.is_valid is False
    print(f"OK — destructive query rejected at validator level too: {result.error}")


def test_executor_and_processing(adapter):
    print("\n=== 4. executor + result processor + visualization ===")
    query = 'SELECT c.region, SUM(o.total_amount) AS total_revenue FROM "orders" o JOIN "customers" c ON o.customer_id = c.customer_id GROUP BY c.region ORDER BY total_revenue DESC'

    outcome = execute_query(adapter, query, row_limit=100, timeout_seconds=10)
    assert outcome.success, f"expected success, got error: {outcome.error}"
    print(f"OK — execution succeeded: {outcome.result.rows}")

    processed = process_result(outcome.result)
    assert processed["columns"] == ["region", "total_revenue"]
    print(f"OK — processed result: {processed}")

    viz = infer_visualization(processed["columns"], processed["rows"])
    print(f"Inferred visualization: {viz}")
    assert viz is not None and viz["type"] == "bar"
    print("OK — bar chart correctly inferred for categorical+numeric result")

    # executor failure path — invalid SQL should come back as a structured failure, not raise
    bad_outcome = execute_query(adapter, "SELECT nonexistent_column FROM orders", row_limit=10, timeout_seconds=10)
    assert bad_outcome.success is False
    print(f"OK — executor returned structured failure for bad SQL: {bad_outcome.error}")


def test_generate_validate_retry_chain(adapter):
    print("\n=== 5. End-to-end: LLM generate -> validate -> execute, with manual bounded retry ===")
    schema = adapter.get_schema(["orders", "customers"])
    allowed_tables = ["orders", "customers"]
    question = "What is the total revenue per customer region?"

    previous_error = None
    for attempt in range(1, MAX_RETRIES + 1):
        print(f"\n--- Attempt {attempt} ---")
        query = generate_query(
            question=question,
            dialect="duckdb",
            schema=schema,
            semantic_snippets=[{"text": "orders.total_amount is the business metric 'Revenue'. customers.region is the customer's geographic region."}],
            previous_error=previous_error,
        )
        print(f"Generated SQL: {query}")

        validation = validate_query(query, schema=schema, allowed_tables=allowed_tables)
        if not validation.is_valid:
            print(f"Validation failed: {validation.error}")
            previous_error = validation.error
            continue

        outcome = execute_query(adapter, query, row_limit=100, timeout_seconds=10)
        if not outcome.success:
            print(f"Execution failed: {outcome.error}")
            previous_error = outcome.error
            continue

        processed = process_result(outcome.result)
        print(f"SUCCESS on attempt {attempt}: {processed}")
        return

    print(f"FAIL — exhausted {MAX_RETRIES} attempts without a valid, executable query")


def test_generator_respects_allowlist_in_practice(adapter):
    print("\n=== 6. Sanity check: does the LLM stay within a restricted table set when only given that schema? ===")
    schema = adapter.get_schema(["customers"])  # only expose customers — orders not in schema_context at all
    query = generate_query(
        question="What is the total revenue per region?",  # a question orders data would answer, but orders isn't available
        dialect="duckdb",
        schema=schema,
        semantic_snippets=[],
    )
    print(f"Generated SQL with only 'customers' in context: {query}")
    tables = extract_referenced_tables(query)
    print(f"Referenced tables: {tables}")
    if tables - {"customers"}:
        print(f"NOTE — model referenced a table outside what it was given ({tables - {'customers'}}). "
              f"This is exactly why the validator's allowlist check (not just prompt scoping) is the real security boundary.")
    else:
        print("OK — model stayed within the schema it was given (as expected, but validator enforces this regardless)")


def main():
    with tempfile.TemporaryDirectory() as tmp:
        tmp_dir = Path(tmp)
        adapter = make_test_adapter(tmp_dir)

        test_sql_guard()
        test_extract_referenced_tables()
        test_validator(adapter)
        test_executor_and_processing(adapter)
        test_generate_validate_retry_chain(adapter)
        test_generator_respects_allowlist_in_practice(adapter)

    print("\nAll Day 3 checks completed.")


if __name__ == "__main__":
    main()