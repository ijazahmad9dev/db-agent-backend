"""Central LLM/embedding client factories, each with an automatic fallback provider
so the whole agent doesn't go down just because the primary Ollama endpoint is
unreachable. Every node gets its chat model via get_chat_llm() and its embeddings via
get_embeddings() rather than instantiating ChatOllama/OllamaEmbeddings directly, so
the fallback behavior is consistent everywhere instead of ad hoc per call site.
"""
from langchain_core.embeddings import Embeddings
from langchain_ollama import ChatOllama, OllamaEmbeddings

from db_agent.core.config import get_settings

settings = get_settings()


def get_chat_llm(temperature: float | None = 0):
    """Returns a LangChain chat model that transparently retries against Groq if
    Ollama is unreachable or errors out. Uses LangChain's built-in `.with_fallbacks()`
    — the returned object has the exact same `.invoke(prompt, config=...)` interface
    as a plain ChatOllama, so no call site needs to change beyond construction.
    temperature=None means "don't set it" (let the provider's own default apply) —
    result_analysis relies on this for more natural-sounding prose.
    """
    ollama_kwargs = {"base_url": settings.ollama_base_url, "model": settings.ollama_model}
    if temperature is not None:
        ollama_kwargs["temperature"] = temperature
    primary = ChatOllama(**ollama_kwargs)

    if not settings.groq_api_key:
        return primary

    from langchain_groq import ChatGroq  # lazy import: optional dependency, only needed when configured

    groq_kwargs = {"api_key": settings.groq_api_key, "model": settings.groq_model}
    if temperature is not None:
        groq_kwargs["temperature"] = temperature
    fallback = ChatGroq(**groq_kwargs)

    return primary.with_fallbacks([fallback])


class _FallbackEmbeddings(Embeddings):
    """Tries the primary embeddings provider first, falls back to a secondary one on
    any failure.

    IMPORTANT CAVEAT: different embedding models produce different vector
    dimensions. Qdrant collections are created with a fixed dimension the first time
    they're used (see semantic/vectorstore.py::_ensure_collection) — if the primary
    and fallback models don't produce same-dimension vectors, a fallback triggered
    mid-collection-lifetime raises a clear Qdrant dimension-mismatch error rather
    than silently corrupting anything. It also means search won't work again until
    either Ollama recovers, or the collection is deliberately rebuilt against the
    fallback consistently (re-run semantic drafting / schema indexing). There's no
    way to make dimension-mismatched vectors "just work" together — this fails
    loudly and predictably instead of pretending the limitation doesn't exist.
    """

    def __init__(self, primary: Embeddings, fallback: Embeddings | None):
        self._primary = primary
        self._fallback = fallback

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        try:
            return self._primary.embed_documents(texts)
        except Exception:
            if self._fallback is None:
                raise
            return self._fallback.embed_documents(texts)

    def embed_query(self, text: str) -> list[float]:
        try:
            return self._primary.embed_query(text)
        except Exception:
            if self._fallback is None:
                raise
            return self._fallback.embed_query(text)


def get_embeddings() -> Embeddings:
    """Groq has no embeddings API (confirmed by Groq staff on their own community
    forum — no plans to add one), so it can't serve as the embedding fallback.
    Cohere is used instead when configured; see the dimension-mismatch caveat above.
    """
    primary = OllamaEmbeddings(base_url=settings.ollama_base_url, model=settings.embedding_model)

    if not settings.cohere_api_key:
        return primary

    from langchain_cohere import CohereEmbeddings  # lazy import: optional dependency

    fallback = CohereEmbeddings(cohere_api_key=settings.cohere_api_key, model=settings.cohere_embed_model)
    return _FallbackEmbeddings(primary, fallback)