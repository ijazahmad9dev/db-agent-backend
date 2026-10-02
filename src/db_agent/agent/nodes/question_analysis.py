from langchain_ollama import ChatOllama
from db_agent.core.llm import get_chat_llm
from db_agent.core.config import get_settings
from db_agent.agent.state import AgentState

settings = get_settings()

_ANALYSIS_PROMPT = """You are analyzing a business question before it gets turned into SQL against a database.

Question: {question}

Think through:
1. INTENT — what kind of question is this (e.g. a single aggregate metric, a ranked/top-N list, a
   trend over time, a comparison between groups, a lookup of specific records)? If it isn't a data
   question at all (small talk, a request unrelated to data, a request to write code/poems/etc.),
   say so.
2. ASSUMPTIONS — is anything ambiguous that needs a reasonable default to proceed? (e.g. "top"
   without a stated metric, "recent"/"last month" without an exact range, a term that could map to
   more than one column or table). For each one, state the single most reasonable assumption you'd
   make — do NOT ask the user unless literally no reasonable assumption exists.
3. CLARIFY — only say yes if the question is NOT a data question at all, or is so vague that no
   reasonable assumption could produce a meaningful query (e.g. "show me stuff", "how are we
   doing"). Prefer making a reasonable assumption over asking for clarification.

Respond with EXACTLY this format, no other text, no markdown:
INTENT: <one short phrase>
ASSUMPTIONS: <comma-separated short assumptions you made, or "none">
CLARIFY: yes | no
CLARIFY_QUESTION: <if CLARIFY is yes, one short question to ask the user back; otherwise "n/a">
NORMALIZED: <the question, rewritten to be fully explicit and incorporate your assumptions — this is what will actually be used to write SQL. If CLARIFY is yes, just repeat the original question here.>
"""


def question_analysis(state: AgentState) -> dict:
    # With checkpointed state now persisting across invocations on the same
    # thread_id (one thread per session), every field here MUST be explicitly
    # reset at the start of each new question — otherwise a previous question's
    # error, retry count, or generated query could silently leak into this one.
    reset = {
        "retry_count": 0,
        "max_retries": state.get("max_retries", 3),
        "validation_error": None,
        "execution_error": None,
        "verification_error": None,
        "error": None,
        "generated_query": None,
        "result": None,
        "answer": None,
        "visualizations": [],
        "needs_clarification": False,
    }

    reset.update(_analyze(state["question"]))
    return reset


def _analyze(question: str) -> dict:
    """LLM-based intent/ambiguity analysis. Never raises — any parsing failure
    falls back to treating the question at face value so a single bad LLM
    response can't block the whole pipeline."""
    try:
        llm = get_chat_llm()
        raw = llm.invoke(
            _ANALYSIS_PROMPT.format(question=question),
            config={"run_name": "question_analysis", "tags": ["agent-node"]},
        ).content
        parsed = _parse(raw, question)
        if parsed is not None:
            return parsed
    except Exception:
        pass

    return {
        "normalized_question": question,
        "question_assumptions": [],
        "needs_clarification": False,
    }


def _parse(raw: str, original_question: str) -> dict | None:
    lines = [line.strip() for line in raw.strip().splitlines() if line.strip()]
    fields: dict[str, str] = {}
    for line in lines:
        if ":" not in line:
            continue
        key, _, value = line.partition(":")
        fields[key.strip().upper()] = value.strip()

    if "CLARIFY" not in fields or "NORMALIZED" not in fields:
        return None  # malformed response — fall back to face-value handling

    clarify = fields["CLARIFY"].lower().startswith("y")
    assumptions_raw = fields.get("ASSUMPTIONS", "none")
    assumptions = (
        [] if assumptions_raw.lower() == "none" else [a.strip() for a in assumptions_raw.split(",") if a.strip()]
    )

    result: dict = {
        "question_assumptions": assumptions,
        "needs_clarification": clarify,
        "normalized_question": fields["NORMALIZED"] or original_question,
    }
    if clarify:
        clarify_question = fields.get("CLARIFY_QUESTION", "").strip()
        result["error"] = (
            clarify_question
            if clarify_question and clarify_question.lower() != "n/a"
            else "Could you clarify what you're asking for? I wasn't able to tell what data question this maps to."
        )
    return result


def route_after_question_analysis(state: AgentState) -> str:
    return "clarify" if state.get("needs_clarification") else "proceed"