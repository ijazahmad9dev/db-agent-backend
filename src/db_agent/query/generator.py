import sqlglot
from langchain_ollama import ChatOllama

from db_agent.core.config import get_settings
from db_agent.adapters.base import TableInfo

settings = get_settings()

_REFERENCE_DIALECT = "postgres"

_GENERATION_PROMPT = """You are a SQL query generator. Given a business question, the available table
schemas, and business context, write ONE SQL query that answers the question.

Write the query in standard PostgreSQL syntax — it will be automatically translated
to whichever database actually runs it, so always write PostgreSQL-style SQL here
regardless of what the underlying data source actually is.

Available tables and columns:
{schema_context}

Business/semantic context (use these descriptions to map business terms to actual columns):
{semantic_context}

Question: {question}

Rules:
- Return ONLY the SQL query, no explanation, no markdown code fences.
- Use ONLY the tables and columns listed above — never invent a table or column name.
- Never write INSERT, UPDATE, DELETE, DROP, ALTER, TRUNCATE, or any statement other than SELECT.
- Prefer explicit column names over SELECT *.
"""


def generate_query(
    question: str,
    dialect: str,
    schema: list[TableInfo],
    semantic_snippets: list[dict],
    previous_error: str | None = None,
) -> str:
    llm = ChatOllama(base_url=settings.ollama_base_url, model=settings.ollama_model, temperature=0)

    schema_context = "\n".join(
        f"- {t.name}({', '.join(c.name + ' ' + c.data_type for c in t.columns)})" for t in schema
    )
    semantic_context = "\n\n".join(s["text"] for s in semantic_snippets) or "(no semantic context available)"

    prompt = _GENERATION_PROMPT.format(
        schema_context=schema_context, semantic_context=semantic_context, question=question
    )
    if previous_error:
        prompt += f"\n\nYour previous attempt failed validation with this error — fix it:\n{previous_error}"

    raw = llm.invoke(prompt, config={"run_name": "query_generation", "tags": ["query-pipeline"]}).content
    reference_sql = _strip_fence(raw).strip().rstrip(";")

    return _to_target_dialect(reference_sql, dialect)


def _to_target_dialect(sql: str, target_dialect: str) -> str:
    """The model always writes PostgreSQL-flavored SQL; this mechanically converts
    it to whatever the actual adapter needs, instead of trusting the model to get
    MySQL/DuckDB syntax right on its own — the exact class of bug that previously
    let Postgres's "SET statement_timeout" syntax run against a MySQL connection."""
    if target_dialect == _REFERENCE_DIALECT:
        return sql
    try:
        return sqlglot.transpile(sql, read=_REFERENCE_DIALECT, write=target_dialect)[0]
    except Exception:
        # Transpile failed — fall back to the untranslated SQL rather than crashing
        # generation. validate_syntax() in the validator catches it if it's
        # genuinely invalid for the target, feeding a clear error into the retry loop.
        return sql


def _strip_fence(text: str) -> str:
    text = text.strip()
    if text.startswith("```"):
        lines = text.splitlines()
        lines = lines[1:-1] if lines[-1].strip().startswith("```") else lines[1:]
        text = "\n".join(lines)
    return text