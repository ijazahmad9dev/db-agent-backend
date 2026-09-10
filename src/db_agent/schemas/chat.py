from pydantic import BaseModel


class ChatRequest(BaseModel):
    connection_id: str
    question: str


class Visualization(BaseModel):
    type: str
    x: str
    y: str
    title: str


class ChatResponse(BaseModel):
    answer: str | None
    query: str | None
    columns: list[str] | None = None
    rows: list[dict] | None = None
    metadata: dict | None = None
    visualizations: list[Visualization] | None = None
    error: str | None = None