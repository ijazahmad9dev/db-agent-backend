from db_agent.agent.state import AgentState
from db_agent.semantic.vectorstore import search_relevant_tables


def semantic_layer(state: AgentState) -> dict:
    if state.get("error"):
        return {}

    snippets = search_relevant_tables(
        connection_id=state["connection_id"],
        question=state["question"],
        allowed_tables=state["allowed_tables"],
        top_k=len(state["allowed_tables"]) if len(state["allowed_tables"]) < 8 else 8,
    )
    return {"semantic_snippets": snippets}