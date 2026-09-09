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
    ARTIFACT_STORAGE_PROVIDER: str = "local"        # local | s3 | gcs | azure
    # Path resolved via Path(...).resolve() so both relative and absolute work.
    # Dev default: .artifacts/ inside the backend directory.
    # Production: override with ARTIFACT_LOCAL_BASE_PATH=/var/lib/assureden/artifacts
    ARTIFACT_LOCAL_BASE_PATH: str = ".artifacts"

    # ── Realtime / SSE ────────────────────────────────────────────
    # Short-lived ticket for SSE connections (JWT Bearer tokens can't be sent
    # via the browser's native EventSource API).
    SSE_TICKET_EXPIRE_SECONDS: int = 60

    # ── Execution Defaults ────────────────────────────────────────
    DEFAULT_EXECUTION_TIMEOUT_SECONDS: int = 3600
    DEFAULT_STARTUP_TIMEOUT_SECONDS: int = 30
    WATCHDOG_INTERVAL_SECONDS: int = 30
    DEPENDENCY_REBUILD_ASYNC_THRESHOLD: int = 10_000

    # ── Phase 3: Variable Encryption ──────────────────────────────
    # JSON map of key_id → base64-encoded Fernet key.
    # Generate with: from cryptography.fernet import Fernet; Fernet.generate_key()
    # Example: '{"v1": "base64key..."}'
    # The LAST key in insertion order is the active key for new writes.
    VARIABLE_ENCRYPTION_KEYS: str = "{}"          # JSON string; override in .env
    VARIABLE_ENCRYPTION_ACTIVE_KEY_ID: str = "v1" # Key ID used for new encryptions

    # ── Phase 3: Agent Protocol ───────────────────────────────────
    MINIMUM_SUPPORTED_AGENT_PROTOCOL: int = 1
    MAXIMUM_SUPPORTED_AGENT_PROTOCOL: int = 4
    AGENT_LEASE_DURATION_SECONDS: int = 300        # 5 minutes

    # ── Phase 3: Agent Heartbeat Status Thresholds ────────────────
    AGENT_STALE_SECONDS: int = 30
    AGENT_OFFLINE_SECONDS: int = 90

    # ── Phase 3: Execution Snapshot Limits ───────────────────────
    MAX_EXPANDED_STEPS: int = 1000
    MAX_SNAPSHOT_BYTES: int = 5 * 1024 * 1024     # 5 MB

    # ── Phase 3: Variable Resolution ─────────────────────────────
    VARIABLE_MAX_RECURSION_DEPTH: int = 20
    RUN_EVENT_MAX_METADATA_BYTES: int = 16 * 1024  # 16 KB

    # ── Phase 4: Orchestration ────────────────────────────────────
    # Watchdog: how many times an agent can fail to pick up a run before TIMED_OUT
    MAX_DISPATCH_ATTEMPTS: int = 3
    # Preferred agent: after this many seconds offline, release run to pool
    PREFERRED_AGENT_WAIT_SECONDS: int = 300
    # Agent offline detection threshold (seconds without heartbeat → OFFLINE)
    AGENT_OFFLINE_THRESHOLD_SECONDS: int = 120
    # Scheduler: minimum cron interval in seconds (prevent queue floods)
    CRON_MIN_INTERVAL_SECONDS: int = 60
    # Dashboard metrics: cache TTL in seconds
    DASHBOARD_METRICS_CACHE_TTL_SECONDS: int = 20
    # Testing: when True, Celery tasks run synchronously (no broker required)
    TESTING: bool = False

    # ── Phase 8: Reports ──────────────────────────────────────────────
    # Hard upper bound for any report time range (protects expensive aggregations)
    REPORT_MAX_RANGE_DAYS: int = 90
    # Minimum eligible terminal runs for a test case to appear in the flakiness report
    FLAKINESS_MIN_ELIGIBLE_RUNS: int = 3


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
