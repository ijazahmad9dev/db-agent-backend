from fastapi import APIRouter

from db_agent.core.config import get_settings
from db_agent.agent.graph import get_agent
from db_agent.schemas.chat import ChatRequest, ChatResponse

router = APIRouter(prefix="/chat")
settings = get_settings()


@router.post("", response_model=ChatResponse)
def chat(payload: ChatRequest):
    agent = get_agent()
    result = agent.invoke({
        "connection_id": payload.connection_id,
        "question": payload.question,
        "max_retries": settings.agent_max_retries,
    })

    result_data = result.get("result")
    return ChatResponse(
        answer=result.get("answer"),
        query=result.get("generated_query"),
        columns=result_data["columns"] if result_data else None,
        rows=result_data["rows"] if result_data else None,
        metadata={"row_count": result_data["row_count"], "truncated": result_data["truncated"]} if result_data else None,
        visualization=result.get("visualization"),
        error=result.get("error"),
    )