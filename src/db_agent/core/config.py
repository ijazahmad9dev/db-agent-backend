from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # App
    app_name: str = "db-agent"
    app_env: str = "development"  # development | production
    debug: bool = True

    # API
    api_prefix: str = "/api/v1"
    cors_origins: list[str] = ["http://localhost:3000"]

    # LLM / Agent
    ollama_base_url: str = "https://subscriptions-persons-emission-thus.trycloudflare.com"
    ollama_model: str = "gpt-oss:latest"
    agent_max_retries: int = 3

    # App's own metadata DB (stores connections, table selections — NOT user data)
    metadata_db_url: str = "sqlite:///./db_agent_metadata.db"

    # Security
    credential_encryption_key: str  # required — generate with cryptography.fernet.Fernet.generate_key()
    query_row_limit: int = 1000
    query_timeout_seconds: int = 30

    # Google Sheets
    google_service_account_json: str | None = None

    # uploads files
    upload_dir: str = "./storage/uploads"

    semantic_mappings_dir: str = "./storage/semantic"
    qdrant_url: str = "http://localhost:6333"
    embedding_model: str = "qwen3-embedding:latest"
    semantic_top_k_default: int = 8

@lru_cache
def get_settings() -> Settings:
    return Settings()