from langchain_ollama import ChatOllama

from db_agent.core.config import get_settings
from db_agent.agent.state import AgentState

settings = get_settings()

_RELEVANCE_PROMPT = """You are checking whether a question can be answered using ONLY the data described below.
Do not assume any other tables or data exist beyond what's listed here — if the question needs something
not described here, it CANNOT be answered, even if it sounds like a reasonable business question.

Available tables (business context):
{semantic_context}

Available tables (schema):
{schema_context}

Question: {question}

Respond with EXACTLY one line, no other text:
ANSWERABLE: yes
or
ANSWERABLE: no | <one short sentence explaining what's missing>
"""


def relevance_check(state: AgentState) -> dict:
    if state.get("error"):
        return {}

    semantic_context = "\n\n".join(s["text"] for s in state.get("semantic_snippets", [])) or "(none)"
    schema_context = "\n\n".join(s["ddl_text"] for s in state.get("schema_snippets", [])) or "(none)"

    llm = ChatOllama(base_url=settings.ollama_base_url, model=settings.ollama_model, temperature=0)
    prompt = _RELEVANCE_PROMPT.format(
        semantic_context=semantic_context, schema_context=schema_context, question=state["question"]
    )
    raw = llm.invoke(prompt, config={"run_name": "relevance_check", "tags": ["agent-node"]}).content.strip()

    if raw.lower().startswith("answerable: no"):
        reason = raw.split("|", 1)[1].strip() if "|" in raw else "the selected tables don't contain relevant data."
        return {
            "error": (
                f"I can't answer this using the currently selected tables "
                f"({', '.join(state['allowed_tables'])}). {reason}"
            )
        }
    return {}


def route_after_relevance(state: AgentState) -> str:
    return "unanswerable" if state.get("error") else "generate"