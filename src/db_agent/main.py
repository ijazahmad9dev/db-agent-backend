from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.sessions import SessionMiddleware

from db_agent.core.config import get_settings
from db_agent.core.logging import configure_logging
from db_agent.db.session import init_db
from db_agent.api.routes import connections, schema, erd, chat, health, semantic, auth

from db_agent.core.observability import configure_langsmith
configure_langsmith()

settings = get_settings()
configure_logging()

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

app.add_middleware(SessionMiddleware, secret_key=settings.jwt_secret_key)

init_db()

app.include_router(health.router, prefix=settings.api_prefix, tags=["health"])
app.include_router(auth.router, prefix=settings.api_prefix, tags=["auth"])
app.include_router(connections.router, prefix=settings.api_prefix, tags=["connections"])
app.include_router(schema.router, prefix=settings.api_prefix, tags=["schema"])
app.include_router(erd.router, prefix=settings.api_prefix, tags=["erd"])
app.include_router(semantic.router, prefix=settings.api_prefix, tags=["semantic"])
app.include_router(chat.router, prefix=settings.api_prefix, tags=["chat"])