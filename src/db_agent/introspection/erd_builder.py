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
                cardinality = "one-to-one" if c.is_unique else "many-to-one"
                edges.append({
                    "from_table": t.name, "from_column": c.name,
                    "to_table": ref_table, "to_column": ref_col,
                    "cardinality": cardinality, "source": "fk",
                    # Participation derived from real schema facts:
                    # - to_optional: if the FK column (c) is nullable, a row on the
                    #   "from" side can exist without a matching "to" row -> the "one"
                    #   side is optional (zero-or-one) rather than mandatory.
                    # - from_optional: whether every "to" row has at least one "from"
                    #   row can't be determined from a single column's nullability
                    #   (it's a data fact, not a schema constraint) — defaults to the
                    #   conventional "zero or many" assumption, editable via the
                    #   relationship editor if a stricter business rule is known.
                    "to_optional": bool(c.nullable),
                    "from_optional": True,
                })

    return {"nodes": nodes, "edges": edges}


def _key(e: dict) -> tuple:
    return (e["from_table"], e["from_column"], e["to_table"], e["to_column"])


def merge_semantic_relationships(erd: dict, layer: SemanticLayer | None) -> dict:
    """Applies the semantic layer's relationship overrides on top of the raw (FK-derived)
    edges:
      - removed_relationships suppresses a relationship (usually FK-derived) from the view
        entirely — the real DB constraint, if any, is never touched.
      - relationships with a key matching an existing edge REPLACE it (this is how "editing"
        an FK-derived relationship's cardinality/optionality works, without any DDL against
        the real DB).
      - relationships with a new key are pure additions (the only source of relationships
        for CSV/Sheets, which have no real FK constraints to introspect).
    """
    if layer is None:
        return erd

    removed_keys = {(r.from_table, r.from_column, r.to_table, r.to_column) for r in layer.removed_relationships}
    erd["edges"] = [e for e in erd["edges"] if _key(e) not in removed_keys]

    if not layer.relationships:
        return erd

    by_key = {_key(e): i for i, e in enumerate(erd["edges"])}
    for rel in layer.relationships:
        key = (rel.from_table, rel.from_column, rel.to_table, rel.to_column)
        edge = {
            "from_table": rel.from_table, "from_column": rel.from_column,
            "to_table": rel.to_table, "to_column": rel.to_column,
            "cardinality": rel.cardinality, "source": "semantic",
            "from_optional": rel.from_optional, "to_optional": rel.to_optional,
        }
        if key in by_key:
            erd["edges"][by_key[key]] = edge
        else:
            erd["edges"].append(edge)
            by_key[key] = len(erd["edges"]) - 1

    return erd