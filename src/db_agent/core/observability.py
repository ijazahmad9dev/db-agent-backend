import os

from db_agent.core.config import get_settings

_configured = False


def configure_langsmith() -> None:
    """Must run before any LangChain/LangGraph component is invoked — tracing is
    controlled by environment variables that the LangSmith SDK reads directly, not
    by anything passed through our own Settings object."""
    global _configured
    if _configured:
        return
    _configured = True

    settings = get_settings()
    if not settings.langsmith_tracing:
        return

    os.environ["LANGSMITH_TRACING"] = "true"
    os.environ["LANGSMITH_API_KEY"] = settings.langsmith_api_key
    os.environ["LANGSMITH_PROJECT"] = settings.langsmith_project
    os.environ["LANGSMITH_ENDPOINT"] = settings.langsmith_endpoint