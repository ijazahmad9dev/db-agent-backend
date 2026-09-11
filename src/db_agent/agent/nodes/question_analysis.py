from db_agent.agent.state import AgentState


def question_analysis(state: AgentState) -> dict:
    # With checkpointed state now persisting across invocations on the same
    # thread_id (one thread per connection), every field here MUST be explicitly
    # reset at the start of each new question — otherwise a previous question's
    # error, retry count, or generated query could silently leak into this one.
    return {
        "retry_count": 0,
        "max_retries": state.get("max_retries", 3),
        "validation_error": None,
        "execution_error": None,
        "error": None,
        "generated_query": None,
        "result": None,
        "answer": None,
        "visualizations": [],
    }