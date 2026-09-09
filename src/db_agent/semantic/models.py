from pydantic import BaseModel


class ColumnSemantic(BaseModel):
    original_name: str
    business_name: str
    description: str = ""


class RelationshipSemantic(BaseModel):
    from_table: str
    from_column: str
    to_table: str
    to_column: str
    cardinality: str = "many-to-one"  # "one-to-one" | "many-to-one" | "many-to-many"
    description: str = ""

class TableSemantic(BaseModel):
    original_name: str
    business_name: str
    description: str = ""
    columns: dict[str, ColumnSemantic]  # keyed by original column name
    business_rules: list[str] = []


class SemanticLayer(BaseModel):
    connection_id: str
    tables: dict[str, TableSemantic]  # keyed by original table name
    relationships: list[RelationshipSemantic] = []