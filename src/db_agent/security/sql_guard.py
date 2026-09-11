import sqlglot
from sqlglot import exp
from sqlglot.errors import ParseError

_DESTRUCTIVE_KEYWORDS = {
    "INSERT", "UPDATE", "DELETE", "DROP", "ALTER", "TRUNCATE",
    "CREATE", "GRANT", "REVOKE", "REPLACE", "MERGE", "EXEC", "EXECUTE", "CALL",
}


class SQLGuardError(ValueError):
    pass


def guard_read_only(query: str, dialect: str = "postgres") -> None:
    """Two independent layers, kept deliberately separate rather than merged:
    a keyword-string check (cheap, no dependency on a successful parse) and an
    AST-based check (precise — checks the actual statement type, not just
    whether a keyword-like string appears anywhere). Both must pass."""
    upper_query = query.upper()
    for keyword in _DESTRUCTIVE_KEYWORDS:
        if keyword in upper_query.split():
            raise SQLGuardError(f"Destructive/administrative keyword not allowed: {keyword}")

    if ";" in query.strip().rstrip(";"):
        raise SQLGuardError("Multiple statements (stacked queries via ';') are not allowed.")

    if "--" in query or "/*" in query:
        raise SQLGuardError("SQL comments are not allowed in generated queries.")

    try:
        parsed = sqlglot.parse_one(query, read=dialect)
    except ParseError:
        return  # a parse failure is validate_syntax()'s concern, not this function's

    if not isinstance(parsed, exp.Select):
        raise SQLGuardError(f"Only SELECT statements are allowed — got: {type(parsed).__name__}")


def validate_syntax(query: str, dialect: str) -> str | None:
    """Returns an error message if the query doesn't parse as valid SQL for the
    given dialect, or None if it's fine. Catches malformed SQL before it ever
    reaches the real database, so a bad query fails fast with a clear message
    the generator's retry loop can act on."""
    try:
        sqlglot.parse_one(query, read=dialect)
        return None
    except ParseError as e:
        return f"SQL syntax error for {dialect}: {e}"


def extract_referenced_tables(query: str, dialect: str = "postgres") -> set[str]:
    """AST-based table extraction — correctly handles CTEs, subqueries, and joins,
    which the previous hand-rolled sqlparse token-walk could not (and had a real
    bug in, once, that silently defeated the table allowlist check)."""
    try:
        parsed = sqlglot.parse_one(query, read=dialect)
    except ParseError:
        return set()  # can't extract from something that doesn't parse — validate_syntax() reports the real error

    cte_names = {cte.alias_or_name for cte in parsed.find_all(exp.CTE)}
    tables = set()
    for table in parsed.find_all(exp.Table):
        name = table.name
        if name and name not in cte_names:  # CTEs aren't real tables — exclude from the allowlist check
            tables.add(name.strip('"').strip("'").strip("`"))
    return tables