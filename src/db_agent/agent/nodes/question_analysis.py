from db_agent.agent.state import AgentState


def question_analysis(state: AgentState) -> dict:
    # Stub for now — passes the question through as-is. A natural place to add later:
    # standalone-question rewriting for multi-turn chat, or intent classification
    # (e.g., "this needs no DB access, answer directly"). Not needed for a single-turn agent yet.
    return {"retry_count": 0, "max_retries": state.get("max_retries", 3)}