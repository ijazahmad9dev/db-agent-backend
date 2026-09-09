"""
Temp integration test for Day 4: full LangGraph agent, end-to-end, via the actual /chat API.

Requires ALL of these running:
  - uv run uvicorn db_agent.main:app --reload   (from backend/)
  - docker compose up -d qdrant                  (from backend/)
  - ollama serve  (and OLLAMA_MODEL pulled, e.g.:  ollama pull llama3.1)

Run with:  uv run python scripts/test_day4.py
"""
import json
import tempfile
import time
from pathlib import Path

import httpx
import pandas as pd

BASE_URL = "http://localhost:8000/api/v1"

TABLES = {
    "orders": pd.DataFrame({
        "order_id": [1, 2, 3, 4],
        "customer_id": [1, 2, 1, 2],
        "total_amount": [100.0, 250.5, 75.0, 60.0],
    }),
    "customers": pd.DataFrame({
        "customer_id": [1, 2],
        "name": ["Alice", "Bob"],
        "region": ["east", "west"],
    }),
    "order_items": pd.DataFrame({
        "order_id": [1, 2, 3, 4],
        "product_name": ["Widget", "Gadget", "Widget", "Gizmo"],
        "qty": [3, 1, 2, 5],
    }),
    "payments": pd.DataFrame({
        "payment_id": [1, 2, 3, 4],
        "order_id": [1, 2, 3, 4],
        "amount": [100.0, 250.5, 75.0, 60.0],
        "method": ["card", "cash", "card", "card"],
    }),
    # deliberately NOT selected — used to prove the agent won't reach outside its selection
    "employees": pd.DataFrame({
        "employee_id": [1, 2],
        "name": ["Sam", "Jo"],
        "department": ["sales", "support"],
    }),
}

SELECTED_TABLES = ["orders", "customers", "order_items", "payments"]


def check_prereqs(client: httpx.Client):
    print("=== 0. Checking prerequisites ===")
    resp = client.get(f"{BASE_URL}/health")
    resp.raise_for_status()
    print("OK — API server is up")

    try:
        ollama_resp = httpx.get("https://subscriptions-persons-emission-thus.trycloudflare.com/api/tags", timeout=5)
        ollama_resp.raise_for_status()
        print("OK — Ollama is reachable")
    except Exception as e:
        print(f"FAIL — Ollama not reachable: {e}")
        print("Start it with: ollama serve")
        raise SystemExit(1)


def setup_connection(client: httpx.Client, tmp_dir: Path) -> str:
    print("\n=== 1. Setting up test connection ===")
    for name, df in TABLES.items():
        df.to_csv(tmp_dir / f"{name}.csv", index=False)

    files = [("files", (f"{name}.csv", open(tmp_dir / f"{name}.csv", "rb"), "text/csv")) for name in TABLES]
    resp = client.post(f"{BASE_URL}/connections/csv", data={"name": "day4-test"}, files=files)
    for _, (_, f, _) in files:
        f.close()
    resp.raise_for_status()
    connection_id = resp.json()["id"]
    print(f"connection_id = {connection_id}")

    print(f"\n=== 2. Selecting tables (should auto-index DDL): {SELECTED_TABLES} ===")
    resp = client.post(f"{BASE_URL}/connections/{connection_id}/tables/select", json={"table_names": SELECTED_TABLES})
    resp.raise_for_status()
    print(f"Selected: {resp.json()['table_names']}")

    print("\n=== 3. Drafting semantic layer for the selection ===")
    resp = client.post(f"{BASE_URL}/connections/{connection_id}/semantic/draft")
    resp.raise_for_status()
    drafted = sorted(resp.json()["tables"].keys())
    assert drafted == sorted(SELECTED_TABLES), f"expected semantic draft to match selection, got {drafted}"
    print(f"OK — semantic layer drafted for: {drafted}")

    return connection_id


def ask(client: httpx.Client, connection_id: str, question: str) -> dict:
    print(f"\nQuestion: {question!r}")
    start = time.time()
    resp = client.post(f"{BASE_URL}/chat", json={"connection_id": connection_id, "question": question}, timeout=180)
    elapsed = time.time() - start
    resp.raise_for_status()
    data = resp.json()
    print(f"({elapsed:.1f}s)")
    print(json.dumps(data, indent=2))
    return data


def test_answerable_question(client: httpx.Client, connection_id: str):
    print("\n=== 4. A question answerable from selected tables ===")
    data = ask(client, connection_id, "What is the total revenue by customer region?")

    assert data["error"] is None, f"expected no error, got: {data['error']}"
    assert data["query"], "expected a generated SQL query in the response"
    assert data["rows"] is not None and len(data["rows"]) > 0, "expected non-empty result rows"
    assert data["answer"], "expected a natural-language answer"
    print("OK — got a grounded answer with query + rows + natural-language summary")

    if data["visualization"]:
        print(f"OK — visualization suggested: {data['visualization']}")
    else:
        print("(no visualization suggested — acceptable, heuristic is conservative)")


def test_unselected_table_question(client: httpx.Client, connection_id: str):
    print("\n=== 5. A question that needs data OUTSIDE the selection (employees table not selected) ===")
    data = ask(client, connection_id, "Which employees work in the support department?")

    if data["query"]:
        assert "employees" not in data["query"].lower(), (
            f"SECURITY FAIL — generated query referenced the unselected 'employees' table: {data['query']}"
        )

    # After the relevance-check fix, this must be an explicit error, not a fabricated empty-result answer.
    assert data["error"] is not None, (
        f"EXPECTED an explicit 'can't answer' error, but got a fabricated answer instead: {data['answer']!r}"
    )
    assert data["query"] is None or "where false" not in data["query"].lower(), (
        "Agent appears to have dodged the question with an always-false query instead of admitting it can't answer."
    )
    print(f"OK — agent correctly refused with an explicit explanation: {data['error']}")


def test_response_contract(data: dict):
    print("\n=== 6. Response contract shape check ===")
    required_keys = {"answer", "query", "columns", "rows", "metadata", "visualization", "error"}
    missing = required_keys - set(data.keys())
    assert not missing, f"Response missing required keys: {missing}"
    print(f"OK — response contains all required keys: {sorted(required_keys)}")


def main():
    with httpx.Client(timeout=30) as client:
        check_prereqs(client)

        with tempfile.TemporaryDirectory() as tmp:
            tmp_dir = Path(tmp)
            connection_id = setup_connection(client, tmp_dir)

        with httpx.Client(timeout=180) as long_client:
            test_answerable_question(long_client, connection_id)
            test_unselected_table_question(long_client, connection_id)
            sample = ask(long_client, connection_id, "How many orders were placed?")
            test_response_contract(sample)

    print("\nAll Day 4 checks completed.")


if __name__ == "__main__":
    main()