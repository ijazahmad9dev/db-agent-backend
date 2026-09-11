from datetime import datetime

from pydantic import BaseModel


class ChatRequest(BaseModel):
    connection_id: str
    question: str


class Visualization(BaseModel):
    type: str  # "bar" | "line" | "pie" | "scatter" | "area" | "kpi"
    title: str
    # Chart types (bar/line/pie/scatter/area): x/y are column names to plot.
    x: str | None = None
    y: str | None = None
    # "kpi" type: a single-value dashboard tile. "value" is the column name holding
    # the number (look it up in the result's first row) and "label" is the short
    # human-readable name for the metric (e.g. "Average Order Value").
    value: str | None = None
    label: str | None = None


class ChatResponse(BaseModel):
    answer: str | None
    query: str | None
    columns: list[str] | None = None
    rows: list[dict] | None = None
    metadata: dict | None = None
    visualizations: list[Visualization] | None = None
    error: str | None = None


class ChatHistoryMessage(BaseModel):
    role: str
    question: str | None = None
    response: ChatResponse | None = None
    created_at: datetime

    class Config:
        from_attributes = True