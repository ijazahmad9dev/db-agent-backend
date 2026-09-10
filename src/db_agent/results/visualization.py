import json

from langchain_ollama import ChatOllama

from db_agent.core.config import get_settings

settings = get_settings()

_ALLOWED_TYPES = {"bar", "line", "pie", "scatter", "area"}

_SUGGESTION_PROMPT = """You are suggesting chart visualizations for a query result.

Question the user asked: {question}
Result columns: {columns}
Sample rows: {sample_rows}

Suggest every chart that would genuinely help visualize this data — not just one.
Skip charts that wouldn't make sense for this data shape (e.g. don't suggest a pie
chart for a single row, don't suggest a chart at all if the data has no meaningful
categorical/numeric structure).

Return ONLY a JSON array, no commentary, no code fences, in this exact shape:
[
  {{"type": "bar", "x": "<column name>", "y": "<column name>", "title": "<short chart title>"}},
  ...
]

Rules:
- "type" must be one of: bar, line, pie, scatter, area
- "x" and "y" must be exact column names from the list above — never invent a column
- For "pie": "x" is the category/label column, "y" is the value column
- Return an empty array [] if nothing here is worth charting
"""


def suggest_visualizations(columns: list[str], rows: list[dict], question: str) -> list[dict]:
    """LLM-first: ask the model to propose every reasonable chart for this result.
    Falls back to a single heuristic-based suggestion if the LLM call fails or
    returns nothing usable — never raises, always returns a (possibly empty) list."""
    try:
        suggestions = _llm_suggest(columns, rows, question)
        if suggestions:
            return suggestions
    except Exception:
        pass

    fallback = _heuristic_visualization(columns, rows)
    return [fallback] if fallback else []


def _llm_suggest(columns: list[str], rows: list[dict], question: str) -> list[dict]:
    if not rows:
        return []

    llm = ChatOllama(base_url=settings.ollama_base_url, model=settings.ollama_model, temperature=0)
    prompt = _SUGGESTION_PROMPT.format(
        question=question, columns=columns, sample_rows=rows[:10]
    )
    raw = llm.invoke(prompt, config={"run_name": "visualization_suggestion", "tags": ["agent-node"]}).content
    parsed = json.loads(_strip_fence(raw))

    if not isinstance(parsed, list):
        return []

    valid_columns = set(columns)
    validated = []
    for item in parsed:
        if not isinstance(item, dict):
            continue
        chart_type = item.get("type")
        x = item.get("x")
        y = item.get("y")
        if chart_type not in _ALLOWED_TYPES:
            continue
        if x not in valid_columns or y not in valid_columns:
            continue  # never trust an LLM-invented column name — same principle as query generation
        validated.append({
            "type": chart_type,
            "x": x,
            "y": y,
            "title": item.get("title") or f"{y} by {x}",
        })
    return validated


def _strip_fence(text: str) -> str:
    text = text.strip()
    if text.startswith("```"):
        lines = text.splitlines()
        lines = lines[1:-1] if lines[-1].strip().startswith("```") else lines[1:]
        text = "\n".join(lines)
    return text


def _heuristic_visualization(columns: list[str], rows: list[dict]) -> dict | None:
    """Original simple heuristic — kept as the fallback path only now."""
    if not rows or len(columns) < 2:
        return None

    numeric_cols = [c for c in columns if isinstance(rows[0].get(c), (int, float))]
    categorical_cols = [c for c in columns if c not in numeric_cols]

    if len(categorical_cols) == 1 and len(numeric_cols) >= 1 and len(rows) <= 50:
        return {"type": "bar", "x": categorical_cols[0], "y": numeric_cols[0], "title": f"{numeric_cols[0]} by {categorical_cols[0]}"}

    date_like_cols = [c for c in columns if "date" in c.lower() or "time" in c.lower() or "_at" in c.lower()]
    if date_like_cols and numeric_cols:
        return {"type": "line", "x": date_like_cols[0], "y": numeric_cols[0], "title": f"{numeric_cols[0]} over {date_like_cols[0]}"}

    return None