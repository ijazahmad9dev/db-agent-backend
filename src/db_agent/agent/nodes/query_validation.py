from db_agent.agent.state import AgentState
from db_agent.query.validator import validate_query


def query_validation(state: AgentState) -> dict:
    if state.get("error"):
        return {}

    result = validate_query(
        query=state["generated_query"],
        schema=state["schema"],
        allowed_tables=state["allowed_tables"],
        dialect=state.get("dialect", "postgres"),
    )
    if result.is_valid:
        return {"validation_error": None}
    return {"validation_error": result.error}


def route_after_validation(state: AgentState) -> str:
    if state.get("error"):
        return "end"
    if state.get("validation_error"):
        return "retry" if state["retry_count"] < state["max_retries"] else "give_up"
    return "execute"