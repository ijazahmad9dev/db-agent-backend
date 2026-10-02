from langchain_ollama import ChatOllama
from db_agent.core.llm import get_chat_llm
from db_agent.core.config import get_settings
from db_agent.agent.state import AgentState

settings = get_settings()

_VERIFICATION_PROMPT = """You are checking whether a SQL query and its result actually answer a business
question — this is a correctness check, separate from whether the query ran without errors.

Question: {question}

SQL query that was run:
{query}

Result columns: {columns}
Result rows (sample): {rows}

Does this query's result genuinely answer the question — right aggregation, right filters, right
grouping, right columns? Minor formatting differences don't matter; what matters is whether the
NUMBERS/ROWS actually answer what was asked. If you are unsure, prefer "yes" over "no" — only say
"no" when there's a clear, specific mismatch (e.g. it counted rows instead of summing a column, it
filtered the wrong date range, it grouped by the wrong dimension, it's missing an obvious join).

Respond with EXACTLY one line, no other text:
VERIFIED: yes
or
VERIFIED: no | <one short sentence on what's wrong, specific enough to fix the query>
"""


def answer_verification(state: AgentState) -> dict:
    if state.get("error"):
        return {}

    result = state.get("result")
    if not result:
        return {}

    question = state.get("normalized_question") or state["question"]
    try:
        llm = get_chat_llm()
        prompt = _VERIFICATION_PROMPT.format(
            question=question,
            query=state["generated_query"],
            columns=result["columns"],
            rows=result["rows"][:10],
        )
        raw = llm.invoke(prompt, config={"run_name": "answer_verification", "tags": ["agent-node"]}).content.strip()
    except Exception:
        # Verification is a quality check, not a hard gate — if the LLM call itself
        # fails, don't block the user from getting an answer.
        return {"verification_error": None}

    if raw.lower().startswith("verified: no"):
        reason = raw.split("|", 1)[1].strip() if "|" in raw else "the query doesn't appear to match what was asked."
        return {"verification_error": reason}

    return {"verification_error": None}


def route_after_verification(state: AgentState) -> str:
    if state.get("error"):
        return "end"
    if state.get("verification_error") and state["retry_count"] < state["max_retries"]:
        return "retry"
    return "proceed"