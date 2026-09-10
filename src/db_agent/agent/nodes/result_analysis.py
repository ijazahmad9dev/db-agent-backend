from langchain_ollama import ChatOllama

from db_agent.core.config import get_settings
from db_agent.agent.state import AgentState
from db_agent.results.visualization import suggest_visualizations

settings = get_settings()

_ANALYSIS_PROMPT = """Question: {question}
Query result columns: {columns}
Query result rows (sample): {rows}

Write a brief, natural-language answer to the question based on this data. Be direct and factual —
state the actual numbers/values from the result. Do not mention SQL or databases. 2-3 sentences max.
"""


def result_analysis(state: AgentState) -> dict:
    if state.get("error"):
        return {}

    result = state["result"]
    llm = ChatOllama(base_url=settings.ollama_base_url, model=settings.ollama_model)
    prompt = _ANALYSIS_PROMPT.format(
        question=state["question"], columns=result["columns"], rows=result["rows"][:20]
    )
    answer = llm.invoke(prompt, config={"run_name": "result_analysis", "tags": ["agent-node"]}).content.strip()

    visualizations = suggest_visualizations(result["columns"], result["rows"], state["question"])
    return {"answer": answer, "visualizations": visualizations}