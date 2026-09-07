from db_agent.agent.state import AgentState


def query_rewrite(state: AgentState) -> dict:
    # Increments the shared retry counter, then loops back to query_generation,
    # which reads validation_error/execution_error from state to self-correct.
    return {"retry_count": state["retry_count"] + 1}