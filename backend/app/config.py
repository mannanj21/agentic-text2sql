from typing import Literal

from cryptography.fernet import Fernet
from pydantic import SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # --- Application ---
    APP_ENV: Literal["development", "production", "test"] = "development"
    REPLICA_ID: str = "local"

    # --- App Database (Postgres with pgvector) ---
    DATABASE_URL: SecretStr

    # --- Security ---
    ENCRYPTION_KEY: SecretStr
    SESSION_SECRET: SecretStr

    @field_validator("ENCRYPTION_KEY")
    @classmethod
    def encryption_key_must_be_a_fernet_key(cls, value: SecretStr) -> SecretStr:
        """Fail at startup rather than when a connection is first saved."""
        try:
            Fernet(value.get_secret_value().encode("ascii"))
        except (AttributeError, ValueError) as exc:
            raise ValueError("ENCRYPTION_KEY must be a valid Fernet key.") from exc
        return value

    # --- SSRF ---
    ALLOW_PRIVATE_HOSTS: bool = False

    # --- LLM ---
    LLM_PROVIDER: Literal["gemini", "ollama", "fake"] = "fake"
    LLM_API_KEY: SecretStr | None = None
    FAST_MODEL: str = "gemini-2.5-flash"
    STRONG_MODEL: str = "gemini-2.5-pro"
    LLM_TIMEOUT_SECONDS: float = 30.0
    LLM_MAX_RETRIES: int = 3

    # --- Ollama ---
    OLLAMA_BASE_URL: str = "http://localhost:11434"

    # --- Embeddings ---
    EMBEDDING_MODEL: str = "bge-m3"
    EMBEDDING_DIM: int = 1024

    # --- Agent ---
    PLANNER_ENABLED: bool = False
    MAX_REPAIR_ATTEMPTS: int = 3
    MAX_RESULT_ROWS: int = 500
    STATEMENT_TIMEOUT_MS: int = 30000
    LOCK_TIMEOUT_MS: int = 5000
    HISTORY_TURNS: int = 5

    # --- Retrieval ---
    RETRIEVAL_TOP_K: int = 10
    RETRIEVAL_MIN_TABLES: int = 15

    # --- Display ---
    RESULT_PREVIEW_ROWS: int = 20

    # --- Validator ---
    FUNCTION_ALLOWLIST_MODE: bool = True

    # --- Rate Limiting ---
    RATE_LIMIT_PER_MIN: int = 30
    LOGIN_RATE_LIMIT_PER_MIN: int = 10
    MAX_QUESTION_LENGTH: int = 2000  # characters; enforced by input_guard before LLM call

    # --- Enrichment ---
    ENRICHMENT_TOKEN_CAP: int = 50000

    # --- Evaluation ---
    EVAL_AS_OF_DATE: str | None = None
    LLM_CACHE_MODE: Literal["off", "record", "replay"] = "off"


def get_settings() -> Settings:
    return Settings()  # type: ignore
