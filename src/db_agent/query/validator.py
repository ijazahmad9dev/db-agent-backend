from dataclasses import dataclass

from db_agent.adapters.base import TableInfo
from db_agent.security.sql_guard import guard_read_only, extract_referenced_tables, SQLGuardError


@dataclass
class ValidationResult:
    is_valid: bool
    error: str | None = None


def validate_query(query: str, schema: list[TableInfo], allowed_tables: list[str]) -> ValidationResult:
    # 1. Read-only / destructive-operation / injection-shape checks
    try:
        guard_read_only(query)
    except SQLGuardError as e:
        return ValidationResult(is_valid=False, error=str(e))

    # 2. Table allowlist — the hard security boundary from user table selection
    referenced_tables = extract_referenced_tables(query)
    allowed_set = set(allowed_tables)
    unauthorized = referenced_tables - allowed_set
    if unauthorized:
        return ValidationResult(
            is_valid=False,
            error=f"Query references unselected/unauthorized tables: {sorted(unauthorized)}. "
                  f"Only these tables are allowed: {sorted(allowed_set)}",
        )

    # 3. Table/column existence against actual introspected schema
    schema_by_table = {t.name: {c.name for c in t.columns} for t in schema}
    unknown_tables = referenced_tables - set(schema_by_table.keys())
    if unknown_tables:
        return ValidationResult(is_valid=False, error=f"Unknown table(s) referenced: {sorted(unknown_tables)}")

    return ValidationResult(is_valid=True)