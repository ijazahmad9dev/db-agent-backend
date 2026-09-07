from db_agent.agent.state import AgentState
from db_agent.agent.context import load_connection_context
from db_agent.query.executor import execute_query
from db_agent.query.validator import validate_query
from db_agent.core.config import get_settings
from db_agent.results.processor import process_result

settings = get_settings()


def query_execution(state: AgentState) -> dict:
    if state.get("error"):
        return {}

    adapter, _, _, _ = load_connection_context(state["connection_id"])
    outcome = execute_query(
        adapter,
        state["generated_query"],
        row_limit=settings.query_row_limit,
        timeout_seconds=settings.query_timeout_seconds,
    )

    if outcome.success:
        return {"result": process_result(outcome.result), "execution_error": None}
    return {"execution_error": outcome.error}


def route_after_execution(state: AgentState) -> str:
    if state.get("error"):
        return "end"
    if state.get("execution_error"):
        return "retry" if state["retry_count"] < state["max_retries"] else "give_up"
    return "analyze"