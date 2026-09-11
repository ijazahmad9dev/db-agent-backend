from dataclasses import dataclass

from db_agent.adapters.base import TableInfo
from db_agent.security.sql_guard import guard_read_only, extract_referenced_tables, validate_syntax, SQLGuardError


@dataclass
class ValidationResult:
    is_valid: bool
    error: str | None = None


def validate_query(
    query: str,
    schema: list[TableInfo],
    allowed_tables: list[str],
    dialect: str = "postgres",
) -> ValidationResult:
    # 1. Syntax — catches malformed SQL before wasting a guard/execution cycle on
    # something that was never going to run anyway.
    syntax_error = validate_syntax(query, dialect)
    if syntax_error:
        return ValidationResult(is_valid=False, error=syntax_error)

    # 2. Read-only / destructive-operation / injection-shape checks
    try:
        guard_read_only(query, dialect)
    except SQLGuardError as e:
        return ValidationResult(is_valid=False, error=str(e))

    # 3. Table allowlist — the hard security boundary from user table selection
    referenced_tables = extract_referenced_tables(query, dialect)
    allowed_set = set(allowed_tables)
    unauthorized = referenced_tables - allowed_set
    if unauthorized:
        return ValidationResult(
            is_valid=False,
            error=f"Query references unselected/unauthorized tables: {sorted(unauthorized)}. "
                  f"Only these tables are allowed: {sorted(allowed_set)}",
        )

    # 4. Table/column existence against actual introspected schema
    schema_by_table = {t.name: {c.name for c in t.columns} for t in schema}
    unknown_tables = referenced_tables - set(schema_by_table.keys())
    if unknown_tables:
        return ValidationResult(is_valid=False, error=f"Unknown table(s) referenced: {sorted(unknown_tables)}")

    return ValidationResult(is_valid=True)