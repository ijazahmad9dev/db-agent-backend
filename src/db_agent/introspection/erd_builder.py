from db_agent.adapters.base import TableInfo
from db_agent.semantic.models import SemanticLayer


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
                # A FK column that's also unique/PK on its own table means each parent row
                # maps to at most one child row -> one-to-one. Otherwise it's the standard
                # many-to-one (many rows here can point to the same parent row).
                cardinality = "one-to-one" if c.is_unique else "many-to-one"
                edges.append({
                    "from_table": t.name, "from_column": c.name,
                    "to_table": ref_table, "to_column": ref_col,
                    "cardinality": cardinality, "source": "fk",
                })

    return {"nodes": nodes, "edges": edges}


def merge_semantic_relationships(erd: dict, layer: SemanticLayer | None) -> dict:
    """Adds relationship edges from the semantic layer — the only source of relationships
    for CSV/Sheets connections, which have no real FK constraints to introspect."""
    if layer is None or not layer.relationships:
        return erd

    existing = {(e["from_table"], e["from_column"], e["to_table"], e["to_column"]) for e in erd["edges"]}
    for rel in layer.relationships:
        key = (rel.from_table, rel.from_column, rel.to_table, rel.to_column)
        if key not in existing:
            erd["edges"].append({
                "from_table": rel.from_table, "from_column": rel.from_column,
                "to_table": rel.to_table, "to_column": rel.to_column,
                "cardinality": rel.cardinality, "source": "semantic",
            })
    return erd