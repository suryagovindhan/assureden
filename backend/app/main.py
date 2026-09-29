"""
main.py — FastAPI application factory
"""

import redis as redis_client
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import settings
from app.api.auth.router import router as auth_router
from app.api.organizations.router import router as org_router
from app.api.users.router import router as user_router
from app.api.agents.router import router as agent_router
from app.api.object_repository.router import router as object_repo_router
from app.api.test_cases.router import router as test_cases_router
from app.api.environments.router import router as environments_router
from app.api.flows.router import router as flows_router
from app.api.executions.router import router as executions_router
from app.api.schedules.router import router as schedules_router
from app.api.metrics.router import router as metrics_router
from app.api.realtime.router import router as realtime_router    # Phase 5: SSE
from app.api.artifacts.router import router as artifacts_router  # Phase 5: Artifact storage
from app.api.reports.router import router as reports_router      # Phase 8: Reports


@asynccontextmanager
async def lifespan(app: FastAPI):
    # ── Startup checks ─────────────────────────────────────────
    import logging
    log = logging.getLogger("assureden.startup")

    try:
        from app.db.session import engine
        from sqlalchemy import text
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        log.info("✓ PostgreSQL connection OK")
    except Exception as e:
        log.error(f"✗ PostgreSQL connection FAILED: {e}")
        raise

    try:
        r = redis_client.from_url(settings.REDIS_URL)
        r.ping()
        log.info("✓ Redis connection OK")
    except Exception as e:
        log.warning(f"⚠ Redis unavailable (Celery tasks will fail): {e}")
        # Don't raise — app still serves HTTP requests without Redis

    yield

    # ── Shutdown ───────────────────────────────────────────────
    from app.db.session import engine
    engine.dispose()


def create_app() -> FastAPI:
    from app.api.drafts import router as drafts_router
    from app.api.agent_control import router as agent_control_router
    app = FastAPI(
        title=settings.APP_NAME,
        version=settings.APP_VERSION,
        docs_url="/api/docs",
        redoc_url="/api/redoc",
        lifespan=lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:5173", "http://localhost:3000"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(auth_router,  prefix="/api")
    app.include_router(drafts_router, prefix="/api")
    app.include_router(agent_control_router, prefix="/api")
    app.include_router(org_router,   prefix="/api")
    app.include_router(user_router,  prefix="/api")
    app.include_router(agent_router,       prefix="/api")
    app.include_router(object_repo_router,  prefix="/api")
    app.include_router(test_cases_router,    prefix="/api")
    app.include_router(environments_router,  prefix="/api")
    app.include_router(flows_router,         prefix="/api")
    app.include_router(executions_router,    prefix="/api")
    app.include_router(schedules_router,     prefix="/api")
    app.include_router(metrics_router,       prefix="/api")
    app.include_router(realtime_router,      prefix="/api")  # SSE ticket + stream
    app.include_router(artifacts_router,     prefix="/api")  # Artifact upload + serve
    app.include_router(reports_router,       prefix="/api")  # Phase 8: Reports

    @app.get("/api/health")
    def health():
        return {"status": "ok", "version": settings.APP_VERSION}

    return app


app = create_app()
