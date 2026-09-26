import os
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
    llm_model: str = "openai/gpt-oss-120b"
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

    jev_enabled: bool = False
    jev_provider: Literal["openrouter", "typesafe"] = "openrouter"
    jev_model: str = "jev-1.13"
    jev_timeout_critical_ms: int = 1500
    jev_timeout_ms: int = 2000
    openrouter_api_key: str = ""
    typesafe_api_key: str = ""
    jev_price_per_1m: float = 0.042
    jev_monthly_budget_usd: float = 1.0
    jev_sufficient_threshold: float = 0.85
    jev_cache_verify_from: float = 0.85
    jev_cache_verify_below: float = 0.97
    jev_same_question_threshold: float = 0.5
    jev_grounded_threshold: float = 0.9

    preload_models: bool = True

    chunk_size: int = 700
    chunk_overlap: int = 100
    max_upload_mb: float = 0.3

    retrieval_candidates: int = 20
    rerank_top_k: int = 5
    max_rewrites: int = 2
    cache_similarity_threshold: float = 0.90

    events_heartbeat_seconds: float = 15.0
    events_queue_size: int = 200
    events_max_subscribers: int = 5

    torch_num_threads: int = 0

    ingest_workers: int = 1
    ingest_queue_size: int = 100

    queries_per_day: int = 50
    user_tokens_per_day: int = 20_000
    query_min_interval_seconds: int = 15
    max_documents: int = 1
    max_storage_mb: int = 200
    resend_per_user_per_day: int = 3

    deepinfra_price_per_1m: float = 0.01
    deepinfra_monthly_budget_usd: float = 5.0

    limits_autocheck_enabled: bool = True
    limits_check_model: str = "openai/gpt-oss-20b"
    limits_check_spacing_seconds: float = 60.0
    telegram_bot_token: str = ""
    telegram_chat_id: str = ""

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

    telemetry_redaction: bool = True

    langfuse_public_key: str = ""
    langfuse_secret_key: str = ""
    langfuse_host: str = "https://cloud.langfuse.com"

    turnstile_site_key: str = ""
    turnstile_secret_key: str = ""

    upstash_redis_rest_url: str = ""
    upstash_redis_rest_token: str = ""

    @field_validator("jwt_secret")
    @classmethod
    def _strong_secret(cls, value: str) -> str:
        if len(value) < 32:
            raise ValueError("JWT_SECRET must be at least 32 characters")
        return value


settings = Settings()

CURRENT_TERMS_VERSION = "2026-09-20"

SDK_ENV_VARS = ("LANGFUSE_PUBLIC_KEY", "LANGFUSE_SECRET_KEY", "LANGFUSE_HOST")


def export_sdk_env(target: dict | None = None) -> None:
    environment = os.environ if target is None else target
    for name in SDK_ENV_VARS:
        value = getattr(settings, name.lower())
        if value and not environment.get(name):
            environment[name] = value


export_sdk_env()
