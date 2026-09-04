from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base

from db_agent.core.config import get_settings

settings = get_settings()

engine = create_engine(
    settings.metadata_db_url,
    connect_args={"check_same_thread": False} if settings.metadata_db_url.startswith("sqlite") else {},
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db() -> None:
    from db_agent.db import models  # noqa: F401  ensure models are registered
    Base.metadata.create_all(bind=engine)