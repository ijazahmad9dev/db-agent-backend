import uuid
from datetime import datetime, timezone

from sqlalchemy import Column, String, DateTime, Boolean, ForeignKey, JSON, Integer
from sqlalchemy.orm import relationship

from db_agent.db.session import Base


def _uuid() -> str:
    return str(uuid.uuid4())


class User(Base):
    __tablename__ = "users"

    id = Column(String, primary_key=True, default=_uuid)
    google_sub = Column(String, unique=True, nullable=False, index=True)
    email = Column(String, unique=True, nullable=False)
    name = Column(String, nullable=True)
    picture_url = Column(String, nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    google_refresh_token_encrypted = Column(String, nullable=True)
    google_sheets_scope_granted = Column(Boolean, default=False)

    connections = relationship("Connection", back_populates="owner")


class Connection(Base):
    __tablename__ = "connections"

    id = Column(String, primary_key=True, default=_uuid)
    user_id = Column(String, ForeignKey("users.id"), nullable=False, index=True)
    name = Column(String, nullable=False)
    source_type = Column(String, nullable=False)
    encrypted_config = Column(String, nullable=False)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    is_active = Column(Boolean, default=True)
    semantic_top_k = Column(Integer, default=8)

    owner = relationship("User", back_populates="connections")
    table_selections = relationship("TableSelection", back_populates="connection", cascade="all, delete-orphan")
    chat_sessions = relationship("ChatSession", back_populates="connection", cascade="all, delete-orphan")


class TableSelection(Base):
    __tablename__ = "table_selections"

    id = Column(String, primary_key=True, default=_uuid)
    connection_id = Column(String, ForeignKey("connections.id"), nullable=False)
    table_name = Column(String, nullable=False)
    selected_columns = Column(JSON, nullable=True)
    is_selected = Column(Boolean, default=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    connection = relationship("Connection", back_populates="table_selections")


class ChatSession(Base):
    __tablename__ = "chat_sessions"

    id = Column(String, primary_key=True, default=_uuid)
    connection_id = Column(String, ForeignKey("connections.id"), nullable=False, index=True)
    title = Column(String, nullable=True)  # auto-set from the first question; renamable later
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    connection = relationship("Connection", back_populates="chat_sessions")
    messages = relationship(
        "ChatMessage", back_populates="session", cascade="all, delete-orphan", order_by="ChatMessage.created_at"
    )


class ChatMessage(Base):
    __tablename__ = "chat_messages"

    id = Column(String, primary_key=True, default=_uuid)
    session_id = Column(String, ForeignKey("chat_sessions.id"), nullable=False, index=True)
    role = Column(String, nullable=False)
    question = Column(String, nullable=True)
    response_json = Column(JSON, nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), index=True)

    session = relationship("ChatSession", back_populates="messages")