"""
Temp integration test for Day 2: connections, schema, ERD, semantic draft, vector retrieval.
Run with the server already up:  uv run uvicorn db_agent.main:app --reload
Then:                            uv run python scripts/test_day2.py
"""
import json
import tempfile
from pathlib import Path

import httpx
import pandas as pd

BASE_URL = "http://localhost:8000/api/v1"

# 12 tables across a few "business domains" — enough to see top-k actually filter something
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
            resp = client.post(
                f"{BASE_URL}/connections/csv",
                data={"name": "day2-test"},
                files=files,
            )
            for _, (_, f, _) in files:
                f.close()
            resp.raise_for_status()
            connection = resp.json()
            connection_id = connection["id"]
            print(f"connection_id = {connection_id}")

            print("\n=== 2. Listing tables ===")
            resp = client.get(f"{BASE_URL}/connections/{connection_id}/tables")
            resp.raise_for_status()
            print(json.dumps(resp.json(), indent=2))

            print("\n=== 3. Schema introspection ===")
            resp = client.get(f"{BASE_URL}/connections/{connection_id}/schema")
            resp.raise_for_status()
            schema = resp.json()
            print(f"{len(schema['tables'])} tables introspected")
            print(json.dumps(schema["tables"][0], indent=2))  # sample one table

            print("\n=== 4. ERD ===")
            resp = client.get(f"{BASE_URL}/connections/{connection_id}/erd")
            resp.raise_for_status()
            erd = resp.json()
            print(f"nodes: {len(erd['nodes'])}, edges: {len(erd['edges'])}")

            print("\n=== 5. Drafting semantic layer (this calls the LLM per table — may take a bit) ===")
            resp = client.post(f"{BASE_URL}/connections/{connection_id}/semantic/draft")
            resp.raise_for_status()
            layer = resp.json()
            for name, table in list(layer["tables"].items())[:3]:
                print(f"- {name} -> {table['business_name']}: {table['description']}")
            print(f"... {len(layer['tables'])} tables drafted total")

            print("\n=== 6. Fetching saved semantic layer ===")
            resp = client.get(f"{BASE_URL}/connections/{connection_id}/semantic")
            resp.raise_for_status()
            print("OK — semantic layer persisted and retrievable")

    # Vector search test — done directly against the module since it's not exposed via API yet
    print("\n=== 7. Vector retrieval test (direct module call) ===")
    from db_agent.semantic.vectorstore import search_relevant_tables

    all_tables = list(TABLES.keys())

    question = "what is the total revenue from customer orders?"
    print(f"\nQuestion: {question!r} | allowed_tables=ALL")
    for r in search_relevant_tables(connection_id, question, allowed_tables=all_tables, top_k=5):
        print(f"  {r['table_name']:20s} score={r['score']:.3f}")

    restricted = ["support_tickets", "employees", "departments"]
    print(f"\nSame question | allowed_tables={restricted} (should ONLY return these, regardless of relevance)")
    for r in search_relevant_tables(connection_id, question, allowed_tables=restricted, top_k=5):
        print(f"  {r['table_name']:20s} score={r['score']:.3f}")

    print("\nDone. Connection left in place for further poking:", connection_id)


if __name__ == "__main__":
    main()