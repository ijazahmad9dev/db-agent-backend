from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from db_agent.core.config import get_settings
from db_agent.db.session import get_db
from db_agent.db.models import Connection, User
from db_agent.agent.graph import get_agent
from db_agent.schemas.chat import ChatRequest, ChatResponse
from db_agent.auth.dependencies import get_current_user

router = APIRouter(prefix="/chat")
settings = get_settings()


@router.post("", response_model=ChatResponse)
def chat(
    payload: ChatRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    connection = db.query(Connection).filter(
        Connection.id == payload.connection_id, Connection.user_id == current_user.id
    ).first()
    if connection is None:
        raise HTTPException(status_code=404, detail="Connection not found")

    agent = get_agent()
    result = agent.invoke(
        {
            "connection_id": payload.connection_id,
            "question": payload.question,
            "max_retries": settings.agent_max_retries,
        },
        config={
            "run_name": "chat_query",
            "tags": ["agent-run", connection.source_type],
            "metadata": {"connection_id": payload.connection_id},
        },
    )

    result_data = result.get("result")
    return ChatResponse(
        answer=result.get("answer"),
        query=result.get("generated_query"),
        columns=result_data["columns"] if result_data else None,
        rows=result_data["rows"] if result_data else None,
        metadata={"row_count": result_data["row_count"], "truncated": result_data["truncated"]} if result_data else None,
        visualizations=result.get("visualizations") or [],
        error=result.get("error"),
    )