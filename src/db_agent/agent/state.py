from typing import TypedDict

from db_agent.adapters.base import TableInfo


class AgentState(TypedDict, total=False):
    connection_id: str
    question: str
    dialect: str
    allowed_tables: list[str]
    semantic_snippets: list[dict]
    schema_snippets: list[dict]
    schema: list[TableInfo]
    generated_query: str
    validation_error: str | None
    execution_error: str | None
    result: dict | None
    retry_count: int
    max_retries: int
    answer: str | None
    visualizations: list[dict]  # was: visualization: dict | None
    error: str | None