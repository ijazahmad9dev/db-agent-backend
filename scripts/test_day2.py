"""
Temp integration test for Day 2: connections, schema, ERD, table selection,
semantic draft (scoped to selection), and vector retrieval.
Run with the server + Qdrant already up:
    docker compose up -d qdrant   (from backend/)
    uv run uvicorn db_agent.main:app --reload
Then:
    uv run python scripts/test_day2.py
"""
import json
import tempfile
from pathlib import Path

import httpx
import pandas as pd

BASE_URL = "http://localhost:8000/api/v1"

# 12 tables across a few "business domains" — enough to see selection + top-k both do something
TABLES = {
    "orders": pd.DataFrame({"order_id": [1, 2], "customer_id": [1, 2], "total_amount": [100.0, 250.5]}),
    "customers": pd.DataFrame({"customer_id": [1, 2], "name": ["Alice", "Bob"], "region": ["east", "west"]}),
    "products": pd.DataFrame({"product_id": [1, 2], "name": ["Widget", "Gadget"], "price": [9.99, 19.99]}),
    "order_items": pd.DataFrame({"order_id": [1, 2], "product_id": [1, 2], "qty": [3, 1]}),
    "payments": pd.DataFrame({"payment_id": [1, 2], "order_id": [1, 2], "amount": [100.0, 250.5], "method": ["card", "cash"]}),
    "invoices": pd.DataFrame({"invoice_id": [1, 2], "order_id": [1, 2], "issued_at": ["2026-01-01", "2026-01-02"]}),
    "employees": pd.DataFrame({"employee_id": [1, 2], "name": ["Sam", "Jo"], "department": ["sales", "support"]}),
    "departments": pd.DataFrame({"department_id": [1, 2], "name": ["Sales", "Support"]}),
    "support_tickets": pd.DataFrame({"ticket_id": [1, 2], "customer_id": [1, 2], "status": ["open", "closed"]}),
    "warehouses": pd.DataFrame({"warehouse_id": [1, 2], "location": ["NY", "CA"]}),
    "shipments": pd.DataFrame({"shipment_id": [1, 2], "order_id": [1, 2], "warehouse_id": [1, 2]}),
    "suppliers": pd.DataFrame({"supplier_id": [1, 2], "name": ["Acme Co", "Widget Inc"]}),
}

# What the "user" selects for the agent to use — deliberately a subset, not all 12
SELECTED_TABLES = ["orders", "customers", "order_items", "payments"]


def make_csvs(tmp_dir: Path) -> list[Path]:
    paths = []
    for table_name, df in TABLES.items():
        path = tmp_dir / f"{table_name}.csv"
        df.to_csv(path, index=False)
        paths.append(path)
    return paths


def main():
    with tempfile.TemporaryDirectory() as tmp:
        tmp_dir = Path(tmp)
        csv_paths = make_csvs(tmp_dir)

        with httpx.Client(timeout=120) as client:
            print("=== 1. Uploading CSV connection with 12 tables ===")
            files = [("files", (p.name, open(p, "rb"), "text/csv")) for p in csv_paths]
            resp = client.post(f"{BASE_URL}/connections/csv", data={"name": "day2-test"}, files=files)
            for _, (_, f, _) in files:
                f.close()
            resp.raise_for_status()
            connection = resp.json()
            connection_id = connection["id"]
            print(f"connection_id = {connection_id}")

            print("\n=== 2. Listing all available tables ===")
            resp = client.get(f"{BASE_URL}/connections/{connection_id}/tables")
            resp.raise_for_status()
            print(json.dumps(resp.json(), indent=2))

            print("\n=== 3. Schema introspection ===")
            resp = client.get(f"{BASE_URL}/connections/{connection_id}/schema")
            resp.raise_for_status()
            schema = resp.json()
            print(f"{len(schema['tables'])} tables introspected")

            print("\n=== 4. ERD ===")
            resp = client.get(f"{BASE_URL}/connections/{connection_id}/erd")
            resp.raise_for_status()
            erd = resp.json()
            print(f"nodes: {len(erd['nodes'])}, edges: {len(erd['edges'])}")

            print(f"\n=== 5. Selecting a subset of tables: {SELECTED_TABLES} ===")
            resp = client.post(
                f"{BASE_URL}/connections/{connection_id}/tables/select",
                json={"table_names": SELECTED_TABLES},
            )
            resp.raise_for_status()
            print(json.dumps(resp.json(), indent=2))

            print("\n=== 5b. Confirming selection persisted ===")
            resp = client.get(f"{BASE_URL}/connections/{connection_id}/tables/selected")
            resp.raise_for_status()
            persisted = resp.json()["table_names"]
            assert sorted(persisted) == sorted(SELECTED_TABLES), (
                f"Selection mismatch! expected {SELECTED_TABLES}, got {persisted}"
            )
            print(f"OK — selected tables persisted correctly: {persisted}")

            print("\n=== 6. Drafting semantic layer (no ?tables= override — should use the selection above) ===")
            resp = client.post(f"{BASE_URL}/connections/{connection_id}/semantic/draft")
            resp.raise_for_status()
            layer = resp.json()
            drafted_tables = sorted(layer["tables"].keys())
            print(f"Drafted tables: {drafted_tables}")
            assert drafted_tables == sorted(SELECTED_TABLES), (
                f"Draft scope mismatch! expected only {SELECTED_TABLES}, got {drafted_tables} "
                f"— semantic draft is NOT respecting table selection."
            )
            print(f"OK — semantic layer drafted ONLY the {len(drafted_tables)} selected tables, not all 12")
            for name, table in layer["tables"].items():
                print(f"  - {name} -> {table['business_name']}: {table['description']}")

            print("\n=== 7. Fetching saved semantic layer ===")
            resp = client.get(f"{BASE_URL}/connections/{connection_id}/semantic")
            resp.raise_for_status()
            print("OK — semantic layer persisted and retrievable")

    print("\n=== 8. Vector retrieval test (direct module call) ===")
    from db_agent.semantic.vectorstore import search_relevant_tables

    question = "what is the total revenue from customer orders?"
    print(f"\nQuestion: {question!r} | allowed_tables=SELECTED ({SELECTED_TABLES})")
    for r in search_relevant_tables(connection_id, question, allowed_tables=SELECTED_TABLES, top_k=5):
        print(f"  {r['table_name']:20s} score={r['score']:.3f}")

    print("\n=== 9. Security check: retrieval MUST NOT return tables outside allowed_tables ===")
    print("(even though relevant unselected tables — 'invoices', 'shipments' — exist and were never indexed anyway,")
    print(" since draft only indexed the selection. This also proves unselected tables are absent from the index.)")
    results = search_relevant_tables(connection_id, question, allowed_tables=SELECTED_TABLES + ["invoices", "shipments"], top_k=10)
    returned_tables = {r["table_name"] for r in results}
    leaked = returned_tables - set(SELECTED_TABLES)
    if leaked:
        print(f"FAIL — unselected tables leaked into results: {leaked}")
    else:
        print(f"OK — only selected tables returned, even though 'invoices'/'shipments' were allowed in the filter: {returned_tables}")

    print("\nDone. Connection left in place for further poking:", connection_id)


if __name__ == "__main__":
    main()