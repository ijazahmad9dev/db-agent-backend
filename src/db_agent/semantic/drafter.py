import yaml
from langchain_ollama import ChatOllama

from db_agent.core.config import get_settings
from db_agent.adapters.base import DataSourceAdapter, TableInfo
from db_agent.semantic.models import TableSemantic, ColumnSemantic

settings = get_settings()

_DRAFT_PROMPT = """You are documenting a database table for business users.
Table name: {table_name}
Columns (name: type): {columns}
Sample rows: {samples}

Return ONLY valid YAML, no commentary, no code fences, in this exact shape:
business_name: <short human-friendly table name>
description: <one sentence describing what this table represents>
columns:
  <original_column_name>:
    business_name: <short human-friendly column name>
    description: <one short sentence>
"""


def draft_table_semantic(adapter: DataSourceAdapter, table: TableInfo) -> TableSemantic:
    try:
        return _llm_draft(adapter, table)
    except Exception:
        return _heuristic_fallback(table)


def _llm_draft(adapter: DataSourceAdapter, table: TableInfo) -> TableSemantic:
    llm = ChatOllama(base_url=settings.ollama_base_url, model=settings.ollama_model)
    sample = adapter.sample_rows(table.name, limit=3)
    prompt = _DRAFT_PROMPT.format(
        table_name=table.name,
        columns=", ".join(f"{c.name}: {c.data_type}" for c in table.columns),
        samples=sample.rows,
    )
    raw = llm.invoke(prompt, config={"run_name": "semantic_draft", "tags": ["semantic-layer"]}).content
    parsed = yaml.safe_load(_strip_fence(raw)) or {}

    col_meta = parsed.get("columns") or {}
    columns = {
        c.name: ColumnSemantic(
            original_name=c.name,
            business_name=(col_meta.get(c.name) or {}).get("business_name", c.name.replace("_", " ").title()),
            description=(col_meta.get(c.name) or {}).get("description", ""),
        )
        for c in table.columns
    }
    return TableSemantic(
        original_name=table.name,
        business_name=parsed.get("business_name", table.name.replace("_", " ").title()),
        description=parsed.get("description", ""),
        columns=columns,
    )


def _heuristic_fallback(table: TableInfo) -> TableSemantic:
    columns = {
        c.name: ColumnSemantic(original_name=c.name, business_name=c.name.replace("_", " ").title(), description="")
        for c in table.columns
    }
    return TableSemantic(
        original_name=table.name,
        business_name=table.name.replace("_", " ").title(),
        description="",
        columns=columns,
    )


def _strip_fence(text: str) -> str:
    text = text.strip()
    if text.startswith("```"):
        lines = text.splitlines()
        if lines[-1].strip().startswith("```"):
            lines = lines[1:-1]
        else:
            lines = lines[1:]
        text = "\n".join(lines)
    return text