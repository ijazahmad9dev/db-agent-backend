from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from db_agent.core.config import get_settings
from db_agent.db.session import get_db
from db_agent.db.models import Connection, ChatSession, ChatMessage, User
from db_agent.agent.graph import get_agent
from db_agent.agent.checkpointer import get_checkpointer
from db_agent.schemas.chat import (
    ChatRequest, ChatResponse, ChatHistoryMessage,
    ChatSessionOut, ChatSessionCreate, ChatSessionRename,
)
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


def _get_owned_session(session_id: str, current_user: User, db: Session) -> ChatSession:
    session = (
        db.query(ChatSession)
        .join(Connection, ChatSession.connection_id == Connection.id)
        .filter(ChatSession.id == session_id, Connection.user_id == current_user.id)
        .first()
    )
    if session is None:
        raise HTTPException(status_code=404, detail="Chat session not found")
    return session


@router.post("/sessions", response_model=ChatSessionOut)
def create_session(
    payload: ChatSessionCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _get_owned_connection(payload.connection_id, current_user, db)
    session = ChatSession(connection_id=payload.connection_id)
    db.add(session)
    db.commit()
    db.refresh(session)
    return session


@router.get("/sessions", response_model=list[ChatSessionOut])
def list_sessions(
    connection_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _get_owned_connection(connection_id, current_user, db)
    return (
        db.query(ChatSession)
        .filter(ChatSession.connection_id == connection_id)
        .order_by(ChatSession.updated_at.desc())
        .all()
    )


@router.patch("/sessions/{session_id}", response_model=ChatSessionOut)
def rename_session(
    session_id: str,
    payload: ChatSessionRename,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    session = _get_owned_session(session_id, current_user, db)
    session.title = payload.title
    db.commit()
    db.refresh(session)
    return session


@router.delete("/sessions/{session_id}")
def delete_session(
    session_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    session = _get_owned_session(session_id, current_user, db)

    # Best-effort: also clear this session's LangGraph checkpoint state. Not all
    # langgraph-checkpoint-postgres versions expose delete_thread — if unavailable,
    # this just leaves orphaned (harmless, unreachable) checkpoint rows behind rather
    # than blocking the actual session deletion the user asked for.
    try:
        get_checkpointer().delete_thread(session_id)
    except AttributeError:
        pass

    db.delete(session)  # cascades to chat_messages via ORM relationship
    db.commit()
    return {"status": "deleted"}


@router.get("/sessions/{session_id}/history", response_model=list[ChatHistoryMessage])
def get_session_history(
    session_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    session = _get_owned_session(session_id, current_user, db)
    return [
        ChatHistoryMessage(
            role=m.role, question=m.question,
            response=ChatResponse(**m.response_json) if m.response_json else None,
            created_at=m.created_at,
        )
        for m in session.messages
    ]


@router.post("", response_model=ChatResponse)
def chat(
    payload: ChatRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    connection = _get_owned_connection(payload.connection_id, current_user, db)

    if payload.session_id:
        session = _get_owned_session(payload.session_id, current_user, db)
    else:
        session = ChatSession(connection_id=payload.connection_id)
        db.add(session)
        db.commit()
        db.refresh(session)

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
            "metadata": {"connection_id": payload.connection_id, "session_id": session.id},
            # One LangGraph thread PER SESSION now, not per connection — this is what
            # actually separates one conversation's agent state from another's.
            "configurable": {"thread_id": session.id},
        },
    )

    result_data = result.get("result")
    response = ChatResponse(
        session_id=session.id,
        answer=result.get("answer"),
        query=result.get("generated_query"),
        columns=result_data["columns"] if result_data else None,
        rows=result_data["rows"] if result_data else None,
        metadata={"row_count": result_data["row_count"], "truncated": result_data["truncated"]} if result_data else None,
        visualizations=result.get("visualizations") or [],
        error=result.get("error"),
    )

    stored_response = response.model_dump()
    if stored_response.get("rows"):
        stored_response["rows"] = stored_response["rows"][:50]

    db.add(ChatMessage(session_id=session.id, role="user", question=payload.question))
    db.add(ChatMessage(session_id=session.id, role="assistant", response_json=stored_response))

    if session.title is None:
        session.title = payload.question[:60] + ("..." if len(payload.question) > 60 else "")
    session.updated_at = __import__("datetime").datetime.now(__import__("datetime").timezone.utc)

    db.commit()
    return response