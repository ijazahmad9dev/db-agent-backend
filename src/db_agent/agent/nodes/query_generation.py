from db_agent.agent.state import AgentState
from db_agent.query.generator import generate_query


def query_generation(state: AgentState) -> dict:
    if state.get("error"):
        return {}

    question = state.get("normalized_question") or state["question"]
    previous_error = state.get("validation_error") or state.get("execution_error") or state.get("verification_error")

    query = generate_query(
        question=question,
        dialect=state["dialect"],
        schema=state["schema"],
        semantic_snippets=state.get("semantic_snippets", []),
        previous_error=previous_error,
    )
    return {
        "generated_query": query,
        "validation_error": None,
        "execution_error": None,
        "verification_error": None,
    }