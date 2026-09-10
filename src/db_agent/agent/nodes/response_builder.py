from db_agent.agent.state import AgentState


def response_builder(state: AgentState) -> dict:
    if state.get("error"):
        return {
            "answer": None, "generated_query": None, "result": None,
            "visualizations": [], "error": state["error"],
        }

    if state.get("validation_error") or state.get("execution_error"):
        final_error = state.get("execution_error") or state.get("validation_error")
        return {
            "answer": (
                f"I couldn't answer this using the selected tables ({', '.join(state['allowed_tables'])}). "
                f"The question may need data outside what's currently selected, or the query couldn't be resolved."
            ),
            "generated_query": state.get("generated_query"),
            "result": None,
            "visualizations": [],
            "error": final_error,
        }

    return {
        "answer": state.get("answer"),
        "generated_query": state.get("generated_query"),
        "result": state.get("result"),
        "visualizations": state.get("visualizations", []),
        "error": None,
    }