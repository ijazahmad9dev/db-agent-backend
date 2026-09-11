from functools import lru_cache

from langgraph.checkpoint.postgres import PostgresSaver
from psycopg_pool import ConnectionPool

from db_agent.core.config import get_settings

settings = get_settings()


@lru_cache
def get_checkpointer() -> PostgresSaver:
    pool = ConnectionPool(
        conninfo=settings.metadata_db_url,
        max_size=5,
        min_size=1,
        max_idle=60,  # proactively recycle idle connections before Supabase's pooler drops them itself
        reconnect_timeout=10,
        check=ConnectionPool.check_connection,  # validates a connection is alive before handing it out — the psycopg_pool equivalent of SQLAlchemy's pool_pre_ping
        kwargs={"autocommit": True, "prepare_threshold": None},
    )
    checkpointer = PostgresSaver(pool)
    checkpointer.setup()
    return checkpointer