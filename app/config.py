from typing import Literal

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    dev_mode: bool = False

    database_url: str = "postgresql+asyncpg://groundline_app:groundline_app@localhost:5433/groundline"
    migration_database_url: str = ""

    groq_api_key: str = ""
    llm_base_url: str = "https://api.groq.com/openai/v1"
    llm_model: str = "llama-3.3-70b-versatile"
    llm_timeout: float = 30.0

    embedding_provider: Literal["local", "api"] = "local"
    embedding_model: str = "BAAI/bge-m3"
    embedding_dim: int = 1024
    embedding_batch_size: int = 16
    embedding_api_base_url: str = "https://api.deepinfra.com/v1/openai"
    embedding_api_key: str = ""

    rerank_provider: Literal["local", "api"] = "local"
    reranker_model: str = "BAAI/bge-reranker-v2-m3"
    rerank_api_url: str = "https://api.pinecone.io/rerank"
    rerank_api_model: str = "bge-reranker-v2-m3"
    rerank_api_key: str = ""

    preload_models: bool = True

    chunk_size: int = 700
    chunk_overlap: int = 100
    max_upload_mb: int = 20

    retrieval_candidates: int = 20
    rerank_top_k: int = 5
    max_rewrites: int = 2
    cache_similarity_threshold: float = 0.95

    queries_per_day: int = 50
    max_documents: int = 100
    max_storage_mb: int = 200

    jwt_secret: str
    jwt_ttl_minutes: int = 60 * 24 * 7
    otp_ttl_minutes: int = 10
    otp_max_attempts: int = 5
    otp_resend_cooldown_seconds: int = 60
    otp_max_per_ip_per_hour: int = 20

    cookie_name: str = "groundline_session"
    cookie_domain: str = ""
    cookie_secure: bool = True

    resend_api_key: str = ""
    resend_from: str = "Groundline <onboarding@resend.dev>"

    cors_origins: str = "http://localhost:5173"

    @field_validator("jwt_secret")
    @classmethod
    def _strong_secret(cls, value: str) -> str:
        if len(value) < 32:
            raise ValueError("JWT_SECRET must be at least 32 characters")
        return value


settings = Settings()
