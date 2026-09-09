from db_agent.agent.state import AgentState
from db_agent.agent.context import load_connection_context
from db_agent.introspection.ddl_vectorstore import search_relevant_schema
from db_agent.semantic.vectorstore import search_relevant_tables


def schema_retrieval(state: AgentState) -> dict:
    adapter, allowed_tables, top_k, dialect = load_connection_context(state["connection_id"])

    if not allowed_tables:
        return {
            "error": "No tables have been selected for this connection. Select tables before asking questions.",
            "allowed_tables": [],
            "dialect": dialect,
        }

    schema_snippets = search_relevant_schema(
        connection_id=state["connection_id"],
        question=state["question"],
        allowed_tables=allowed_tables,
        top_k=top_k,
    )
    semantic_snippets = search_relevant_tables(
        connection_id=state["connection_id"],
        question=state["question"],
        allowed_tables=allowed_tables,
        top_k=min(top_k, len(allowed_tables)),
    )

    # Union: a table surfaced by EITHER retrieval gets its real schema loaded — closes the
    # gap where semantic search finds a relevant table but DDL search misses it (or vice versa),
    # which previously left the generator with business context for a table it had no columns for.
    ddl_tables = {s["table_name"] for s in schema_snippets}
    semantic_tables = {s["table_name"] for s in semantic_snippets}
    union_tables = sorted(ddl_tables | semantic_tables)

    # Fallback: if both retrievals come back empty (e.g. semantic layer not drafted yet,
    # or a genuinely poor embedding match), fall back to the full selection rather than
    # silently handing the generator zero schema and forcing an incorrect "can't answer."
    if not union_tables:
        union_tables = allowed_tables

    schema = adapter.get_schema(union_tables)

    return {
        "allowed_tables": allowed_tables,
        "dialect": dialect,
        "schema_snippets": schema_snippets,
        "semantic_snippets": semantic_snippets,
        "schema": schema,
    }