import uuid
from datetime import datetime, timezone

from sqlalchemy import Column, String, DateTime, Boolean, ForeignKey, JSON, Integer
from sqlalchemy.orm import relationship

from db_agent.db.session import Base


def _uuid() -> str:
    return str(uuid.uuid4())


class Connection(Base):
    __tablename__ = "connections"
    id = Column(String, primary_key=True, default=_uuid)
    name = Column(String, nullable=False)
    source_type = Column(String, nullable=False)
    encrypted_config = Column(String, nullable=False)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    is_active = Column(Boolean, default=True)
    semantic_top_k = Column(Integer, default=8)   # new — per-connection retrieval depth

    table_selections = relationship("TableSelection", back_populates="connection", cascade="all, delete-orphan")


class TableSelection(Base):
    __tablename__ = "table_selections"

    id = Column(String, primary_key=True, default=_uuid)
    connection_id = Column(String, ForeignKey("connections.id"), nullable=False)
    table_name = Column(String, nullable=False)          # original table/sheet name
    selected_columns = Column(JSON, nullable=True)        # null = all columns allowed
    is_selected = Column(Boolean, default=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    connection = relationship("Connection", back_populates="table_selections")