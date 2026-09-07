import sqlparse
from sqlparse.sql import Identifier, IdentifierList
from sqlparse.tokens import DML, Keyword

_DESTRUCTIVE_KEYWORDS = {
    "INSERT", "UPDATE", "DELETE", "DROP", "ALTER", "TRUNCATE",
    "CREATE", "GRANT", "REVOKE", "REPLACE", "MERGE", "EXEC", "EXECUTE", "CALL",
}


_JOIN_KEYWORDS = {"FROM", "JOIN", "INNER JOIN", "LEFT JOIN", "RIGHT JOIN", "FULL JOIN", "CROSS JOIN"}


class SQLGuardError(ValueError):
    pass


def guard_read_only(query: str) -> None:
    """Raises SQLGuardError if the query is anything other than a single SELECT statement."""
    statements = sqlparse.parse(query)
    if len(statements) != 1:
        raise SQLGuardError("Only a single SQL statement is allowed per query.")

    stmt = statements[0]
    stmt_type = stmt.get_type()
    if stmt_type != "SELECT":
        raise SQLGuardError(f"Only SELECT statements are allowed — got: {stmt_type}")

    upper_query = query.upper()
    for keyword in _DESTRUCTIVE_KEYWORDS:
        if keyword in upper_query.split():
            raise SQLGuardError(f"Destructive/administrative keyword not allowed: {keyword}")

    if ";" in query.strip().rstrip(";"):
        raise SQLGuardError("Multiple statements (stacked queries via ';') are not allowed.")

    if "--" in query or "/*" in query:
        raise SQLGuardError("SQL comments are not allowed in generated queries.")

def extract_referenced_tables(query: str) -> set[str]:
    """Best-effort extraction of table names referenced in FROM/JOIN clauses, for allowlist checking."""
    parsed = sqlparse.parse(query)[0]
    tables = set()
    expecting_table = False

    for token in parsed.tokens:
        if token.is_whitespace:
            continue
        if expecting_table:
            if isinstance(token, IdentifierList):
                for identifier in token.get_identifiers():
                    tables.add(_base_name(identifier))
            elif isinstance(token, Identifier):
                tables.add(_base_name(token))
            expecting_table = False
            continue
        if token.ttype is Keyword and token.value.upper() in _JOIN_KEYWORDS:
            expecting_table = True

    return tables


def _base_name(identifier: Identifier) -> str:
    name = identifier.get_real_name() or identifier.get_name()
    return name.strip('"').strip("'")