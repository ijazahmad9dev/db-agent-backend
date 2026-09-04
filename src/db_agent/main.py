from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from db_agent.core.config import get_settings
from db_agent.core.logging import configure_logging
from db_agent.api.routes import connections, schema, erd, chat, health, semantic


from db_agent.db.session import init_db

settings = get_settings()
configure_logging()
init_db()

app = FastAPI(
    title=settings.app_name,
    debug=settings.debug,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health.router, prefix=settings.api_prefix, tags=["health"])
app.include_router(connections.router, prefix=settings.api_prefix, tags=["connections"])
app.include_router(schema.router, prefix=settings.api_prefix, tags=["schema"])
app.include_router(erd.router, prefix=settings.api_prefix, tags=["erd"])
app.include_router(chat.router, prefix=settings.api_prefix, tags=["chat"])
app.include_router(semantic.router, prefix=settings.api_prefix, tags=["semantic"])