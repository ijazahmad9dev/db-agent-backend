import json

from langchain_ollama import ChatOllama

from db_agent.core.config import get_settings

settings = get_settings()

_CHART_TYPES = {"bar", "line", "pie", "scatter", "area"}
_ALLOWED_TYPES = _CHART_TYPES | {"kpi"}

_SUGGESTION_PROMPT = """You are suggesting how to visualize a query result for a business dashboard.

Question the user asked: {question}
Result columns: {columns}
Sample rows: {sample_rows}

Suggest every visualization that would genuinely help — not just one.

IMPORTANT — single-value results:
If the result is a single row containing one or more standalone numeric metrics (a total, an
average, a count, a percentage, or any other single figure you'd put on a dashboard tile),
suggest a "kpi" visualization for EACH such metric instead of a bar/pie/line/scatter/area chart.
Do NOT suggest a chart just to plot one row or one category — "kpi" is what that's for.

Skip visualizations that wouldn't make sense for this data shape (e.g. don't suggest a chart at
all if the data has no meaningful categorical/numeric structure).

Return ONLY a JSON array, no commentary, no code fences, in this exact shape:
[
  {{"type": "bar", "x": "<column name>", "y": "<column name>", "title": "<short chart title>"}},
  {{"type": "kpi", "value": "<column name holding the number>", "label": "<short metric label>", "title": "<short title>"}},
  ...
]

Rules:
- "type" must be one of: bar, line, pie, scatter, area, kpi
- For chart types (bar, line, pie, scatter, area): "x" and "y" must be exact column names from the list above — never invent a column
- For "pie": "x" is the category/label column, "y" is the value column
- For "kpi": "value" must be an exact column name from the list above holding the number; "label" is a short human-readable name for the metric (e.g. "Average Order Value"), not necessarily the raw column name
- Return an empty array [] if nothing here is worth visualizing
"""


def suggest_visualizations(columns: list[str], rows: list[dict], question: str) -> list[dict]:
    """LLM-first: ask the model to propose every reasonable visualization (charts and/or KPI
    tiles) for this result. Falls back to a heuristic if the LLM call fails or returns nothing
    usable — never raises, always returns a (possibly empty) list."""
    try:
        suggestions = _llm_suggest(columns, rows, question)
        if suggestions:
            return suggestions
    except Exception:
        pass

    return _heuristic_visualizations(columns, rows)


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
        vtype = item.get("type")
        if vtype not in _ALLOWED_TYPES:
            continue

        if vtype == "kpi":
            value_col = item.get("value")
            if value_col not in valid_columns:
                continue  # never trust an LLM-invented column name
            label = item.get("label") or value_col.replace("_", " ").title()
            validated.append({
                "type": "kpi",
                "value": value_col,
                "label": label,
                "title": item.get("title") or label,
            })
            continue

        x = item.get("x")
        y = item.get("y")
        if x not in valid_columns or y not in valid_columns:
            continue  # never trust an LLM-invented column name — same principle as query generation
        validated.append({
            "type": vtype,
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


def _is_numeric(value) -> bool:
    # bool is technically an int subclass in Python — exclude it so True/False
    # columns never get treated as a chartable/KPI numeric value.
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _heuristic_visualizations(columns: list[str], rows: list[dict]) -> list[dict]:
    """Fallback path only (used when the LLM call fails or returns nothing usable).
    A single-row result is a dashboard-tile situation, not a chart — so it now
    produces one KPI tile per numeric column instead of the old 1-bar bar chart."""
    if not rows:
        return []

    numeric_cols = [c for c in columns if _is_numeric(rows[0].get(c))]

    if len(rows) == 1:
        return [
            {
                "type": "kpi",
                "value": col,
                "label": col.replace("_", " ").title(),
                "title": col.replace("_", " ").title(),
            }
            for col in numeric_cols
        ]

    if len(columns) < 2:
        return []

    categorical_cols = [c for c in columns if c not in numeric_cols]

    if len(categorical_cols) == 1 and len(numeric_cols) >= 1 and len(rows) <= 50:
        return [{
            "type": "bar", "x": categorical_cols[0], "y": numeric_cols[0],
            "title": f"{numeric_cols[0]} by {categorical_cols[0]}",
        }]

    date_like_cols = [c for c in columns if "date" in c.lower() or "time" in c.lower() or "_at" in c.lower()]
    if date_like_cols and numeric_cols:
        return [{
            "type": "line", "x": date_like_cols[0], "y": numeric_cols[0],
            "title": f"{numeric_cols[0]} over {date_like_cols[0]}",
        }]

    return []