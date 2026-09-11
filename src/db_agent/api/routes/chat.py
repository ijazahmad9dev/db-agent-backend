from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from db_agent.core.config import get_settings
from db_agent.db.session import get_db
from db_agent.db.models import Connection, ChatMessage, User
from db_agent.agent.graph import get_agent
from db_agent.schemas.chat import ChatRequest, ChatResponse, ChatHistoryMessage
from db_agent.auth.dependencies import get_current_user

router = APIRouter(prefix="/chat")
settings = get_settings()


def _get_owned_connection(connection_id: str, current_user: User, db: Session) -> Connection:
    connection = db.query(Connection).filter(
        Connection.id == connection_id, Connection.user_id == current_user.id
    ).first()
    if connection is None:
        raise HTTPException(status_code=404, detail="Connection not found")
    return connection


@router.post("", response_model=ChatResponse)
def chat(
    payload: ChatRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    connection = _get_owned_connection(payload.connection_id, current_user, db)

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
            # One thread per connection -- this is what makes the checkpointer's
            # state persistence apply at all; without a thread_id every invoke()
            # would be fully independent regardless of the checkpointer being wired in.
            "configurable": {"thread_id": payload.connection_id},
        },
    )

    result_data = result.get("result")
    response = ChatResponse(
        answer=result.get("answer"),
        query=result.get("generated_query"),
        columns=result_data["columns"] if result_data else None,
        rows=result_data["rows"] if result_data else None,
        metadata={"row_count": result_data["row_count"], "truncated": result_data["truncated"]} if result_data else None,
        visualizations=result.get("visualizations") or [],
        error=result.get("error"),
    )

    # Persist both sides of the exchange for the human-readable history endpoint below.
    # Rows are capped for storage -- history is for reviewing past conversation, not
    # re-analyzing full result sets (the live Table tab already showed the complete result).
    stored_response = response.model_dump()
    if stored_response.get("rows"):
        stored_response["rows"] = stored_response["rows"][:50]

    db.add(ChatMessage(connection_id=payload.connection_id, role="user", question=payload.question))
    db.add(ChatMessage(connection_id=payload.connection_id, role="assistant", response_json=stored_response))
    db.commit()

    return response


@router.get("/{connection_id}/history", response_model=list[ChatHistoryMessage])
def get_chat_history(
    connection_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _get_owned_connection(connection_id, current_user, db)
    messages = (
        db.query(ChatMessage)
        .filter(ChatMessage.connection_id == connection_id)
        .order_by(ChatMessage.created_at.asc())
        .all()
    )
    return [
        ChatHistoryMessage(
            role=m.role, question=m.question,
            response=ChatResponse(**m.response_json) if m.response_json else None,
            created_at=m.created_at,
        )
        for m in messages
    ]


@router.delete("/{connection_id}/history")
def clear_chat_history(
    connection_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _get_owned_connection(connection_id, current_user, db)
    db.query(ChatMessage).filter(ChatMessage.connection_id == connection_id).delete()
    db.commit()
    return {"status": "cleared"}