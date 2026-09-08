"""Reelcraft API entry point."""
from __future__ import annotations

import sys
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.api.v1.router import api_router
from app.core.config import settings
from app.core.errors import AppError
from app.core.logging import configure_logging, get_logger

logger = get_logger("app")

DESCRIPTION = """
Turn a handful of photos into a finished vertical video.

**Auth** — call `POST /api/v1/auth/register` or `/auth/login`, then send
`Authorization: Bearer <access_token>` on every other request.

**The shape of a session**

1. `POST /projects` — create a project
2. `POST /projects/{id}/media` — upload images (a scene is created per image)
3. `POST /projects/{id}/plan/generate` — let the planner write the video
4. `PATCH /projects/{id}/scenes/{scene_id}` — edit anything you like
5. `POST /projects/{id}/render` — queue the render, then poll `GET /render-jobs/{job_id}`
6. `GET /render-jobs/{job_id}/download` — take the MP4

**Capabilities** — `GET /api/v1/capabilities` reports which optional providers
(AI planner, voice-over, AI Motion) are configured in this deployment.
"""


@asynccontextmanager
async def lifespan(app: FastAPI):
    configure_logging("DEBUG" if settings.debug else "INFO")

    problems = settings.validate_production()
    if problems:
        for problem in problems:
            logger.error("Configuration error: %s", problem)
        raise RuntimeError("Refusing to start with an unsafe production configuration.")

    from app.db.base import Base, engine, session_scope
    from app.services import generation_job_service
    from app.services.render_service import recover_orphaned_jobs

    if settings.is_sqlite:
        # Development convenience: PostgreSQL deployments run `alembic upgrade head`.
        import app.models  # noqa: F401  (register the mappings)

        Base.metadata.create_all(engine)

    session = session_scope()
    try:
        recovered = recover_orphaned_jobs(session)
        # Same treatment for the unified registry, or a crashed generation would
        # sit at "processing" and the editor would poll it forever.
        stranded = generation_job_service.recover_orphaned(session)
        if recovered or stranded:
            logger.warning(
                "Marked %s render job(s) and %s generation job(s) as failed after a restart.",
                recovered, stranded,
            )
    finally:
        session.close()

    from app.infrastructure.render.engine import FFmpegRenderEngine

    if not FFmpegRenderEngine().is_available():
        logger.warning("FFmpeg was not found — rendering will be unavailable.")

    logger.info(
        "%s ready · env=%s · db=%s · storage=%s",
        settings.app_name,
        settings.environment,
        settings.database_backend,
        settings.storage_provider,
    )
    yield

    from app.infrastructure.jobs.factory import get_job_queue

    get_job_queue().shutdown()
    # Drop the cached instance too: a shut-down queue must never be handed to a
    # subsequent startup in the same process (which is exactly what tests do).
    get_job_queue.cache_clear()


app = FastAPI(
    title=f"{settings.app_name} API",
    description=DESCRIPTION,
    version="1.0.0",
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["Content-Disposition"],
)


@app.middleware("http")
async def security_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("X-Frame-Options", "DENY")
    response.headers.setdefault("Referrer-Policy", "same-origin")
    return response


@app.exception_handler(AppError)
async def app_error_handler(request: Request, exc: AppError) -> JSONResponse:
    if exc.status_code >= 500:
        logger.error("%s on %s: %s", exc.code, request.url.path, exc.message)
    return JSONResponse(status_code=exc.status_code, content=exc.to_payload())


@app.exception_handler(RequestValidationError)
async def validation_error_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    details = [
        {"field": ".".join(str(part) for part in error["loc"][1:]), "problem": error["msg"]}
        for error in exc.errors()[:10]
    ]
    return JSONResponse(
        status_code=422,
        content={
            "error": {
                "code": "validation_error",
                "message": "Some of the information you sent isn't valid.",
                "details": details,
            }
        },
    )


@app.exception_handler(StarletteHTTPException)
async def http_error_handler(request: Request, exc: StarletteHTTPException) -> JSONResponse:
    return JSONResponse(
        status_code=exc.status_code,
        content={"error": {"code": "http_error", "message": str(exc.detail)}},
    )


@app.exception_handler(Exception)
async def unhandled_error_handler(request: Request, exc: Exception) -> JSONResponse:
    logger.exception("Unhandled error on %s", request.url.path)
    return JSONResponse(
        status_code=500,
        content={
            "error": {
                "code": "internal_error",
                "message": "Something went wrong on our side. Please try again.",
            }
        },
    )


@app.get("/health", tags=["system"], summary="Liveness and dependency check")
def health() -> dict:
    from sqlalchemy import text

    from app.db.base import session_scope
    from app.infrastructure.render.engine import FFmpegRenderEngine

    database_ok = True
    session = session_scope()
    try:
        session.execute(text("SELECT 1"))
    except Exception:  # pragma: no cover
        database_ok = False
    finally:
        session.close()

    ffmpeg_ok = FFmpegRenderEngine().is_available()
    return {
        "status": "ok" if database_ok else "degraded",
        "database": database_ok,
        "database_backend": settings.database_backend,
        "ffmpeg": ffmpeg_ok,
        "environment": settings.environment,
        "python": sys.version.split()[0],
    }


app.include_router(api_router, prefix=settings.api_v1_prefix)
