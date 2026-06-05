"""
config.py — Application Settings
All values are read from environment variables.
Copy .env.example to .env and fill in values before running.
"""

from pydantic_settings import BaseSettings, SettingsConfigDict
from functools import lru_cache


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # ── Application ──────────────────────────────────────────────
    APP_NAME: str = "AssureDen"
    APP_VERSION: str = "1.0.0"
    DEBUG: bool = False

    # ── Database (PostgreSQL) ─────────────────────────────────────
    POSTGRES_HOST: str = "localhost"
    POSTGRES_PORT: int = 5432
    POSTGRES_DB: str = "assureden"
    POSTGRES_USER: str = "assureden"
    POSTGRES_PASSWORD: str = "assureden"

    @property
    def DATABASE_URL(self) -> str:
        return (
            f"postgresql+psycopg2://{self.POSTGRES_USER}:{self.POSTGRES_PASSWORD}"
            f"@{self.POSTGRES_HOST}:{self.POSTGRES_PORT}/{self.POSTGRES_DB}"
        )

    @property
    def DATABASE_URL_ASYNC(self) -> str:
        return (
            f"postgresql+asyncpg://{self.POSTGRES_USER}:{self.POSTGRES_PASSWORD}"
            f"@{self.POSTGRES_HOST}:{self.POSTGRES_PORT}/{self.POSTGRES_DB}"
        )

    # ── Redis ─────────────────────────────────────────────────────
    REDIS_HOST: str = "localhost"
    REDIS_PORT: int = 6379
    REDIS_DB: int = 0

    @property
    def REDIS_URL(self) -> str:
        return f"redis://{self.REDIS_HOST}:{self.REDIS_PORT}/{self.REDIS_DB}"

    # ── Celery ────────────────────────────────────────────────────
    @property
    def CELERY_BROKER_URL(self) -> str:
        return self.REDIS_URL

    @property
    def CELERY_RESULT_BACKEND(self) -> str:
        return self.REDIS_URL

    # ── JWT Auth ─────────────────────────────────────────────────
    JWT_SECRET_KEY: str = "CHANGE_THIS_IN_PRODUCTION_USE_32_CHAR_MIN"
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7

    # ── Agent API Keys ────────────────────────────────────────────
    AGENT_API_KEY_HEADER: str = "X-Agent-Api-Key"

    # ── Storage ───────────────────────────────────────────────────
    ARTIFACT_STORAGE_PROVIDER: str = "local"        # local | s3 | azure_blob
    ARTIFACT_LOCAL_BASE_PATH: str = "artifacts"

    # ── Execution Defaults ────────────────────────────────────────
    DEFAULT_EXECUTION_TIMEOUT_SECONDS: int = 3600
    DEFAULT_STARTUP_TIMEOUT_SECONDS: int = 30
    WATCHDOG_INTERVAL_SECONDS: int = 30
    DEPENDENCY_REBUILD_ASYNC_THRESHOLD: int = 10_000


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
