from pydantic import BaseModel


class ColumnSemantic(BaseModel):
    original_name: str
    business_name: str
    description: str = ""


class RelationshipKey(BaseModel):
    """Identifies a relationship (FK-derived or semantic) without cardinality/description —
    used to mark a relationship as removed without needing to restate its other fields."""
    from_table: str
    from_column: str
    to_table: str
    to_column: str


class RelationshipSemantic(BaseModel):
    from_table: str
    from_column: str
    to_table: str
    to_column: str
    cardinality: str = "many-to-one"  # "one-to-one" | "many-to-one" | "many-to-many"
    description: str = ""
    # Participation/optionality per side, for full crow's-foot (Information
    # Engineering) notation — a circle means "may be zero", its absence means
    # "must be at least one". For FK-derived edges these are derived automatically
    # (see erd_builder.build_erd); for manually added/edited relationships they
    # default to the more conservative "optional" assumption and are editable.
    from_optional: bool = True
    to_optional: bool = True


class TableSemantic(BaseModel):
    original_name: str
    business_name: str
    description: str = ""
    columns: dict[str, ColumnSemantic]  # keyed by original column name
    business_rules: list[str] = []


class SemanticLayer(BaseModel):
    connection_id: str
    tables: dict[str, TableSemantic]
    relationships: list[RelationshipSemantic] = []
    # Suppresses a relationship (typically FK-derived) from the ERD and from what the
    # agent treats as a valid join. The real constraint, if any, is left untouched in
    # the actual database. Postgres/MySQL only, enforced in api/routes/semantic.py.
    removed_relationships: list[RelationshipKey] = []


class RelationshipsUpdate(BaseModel):
    """Request body for PUT /connections/{id}/semantic/relationships."""
    relationships: list[RelationshipSemantic] = []
    removed_relationships: list[RelationshipKey] = []