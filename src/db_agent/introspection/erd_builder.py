from db_agent.adapters.base import TableInfo


def build_erd(tables: list[TableInfo]) -> dict:
    nodes = [
        {
            "id": t.name,
            "name": t.name,
            "columns": [
                {"name": c.name, "data_type": c.data_type, "is_primary_key": c.is_primary_key, "is_foreign_key": c.is_foreign_key}
                for c in t.columns
            ],
        }
        for t in tables
    ]
    edges = []
    for t in tables:
        for c in t.columns:
            if c.is_foreign_key and c.references:
                ref_table, ref_col = c.references.split(".", 1)
                edges.append({"from_table": t.name, "from_column": c.name, "to_table": ref_table, "to_column": ref_col})
    return {"nodes": nodes, "edges": edges}