from db_agent.agent.state import AgentState
from db_agent.agent.context import load_connection_context
from db_agent.introspection.ddl_vectorstore import search_relevant_schema


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
    retrieved_table_names = [s["table_name"] for s in schema_snippets]
    schema = adapter.get_schema(retrieved_table_names) if retrieved_table_names else []

    return {
        "allowed_tables": allowed_tables,
        "dialect": dialect,
        "schema_snippets": schema_snippets,
        "schema": schema,
    }