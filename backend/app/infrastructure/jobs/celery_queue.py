"""Celery + Redis job queue — the production path.

Run a worker with:

    celery -A app.infrastructure.jobs.celery_queue.celery_app worker --loglevel=info

The tasks are thin: they call the same service functions the thread queue calls, so
switching queues changes nothing about how a render behaves.
"""
from __future__ import annotations

from functools import lru_cache

from app.core.config import settings
from app.core.logging import get_logger
from app.infrastructure.jobs.base import JobQueue

logger = get_logger(__name__)


@lru_cache(maxsize=1)
def _build_celery_app():
    from celery import Celery  # noqa: PLC0415

    app = Celery(
        "reelcraft",
        broker=settings.redis_url,
        backend=settings.redis_url,
    )
    app.conf.update(
        task_serializer="json",
        result_serializer="json",
        accept_content=["json"],
        timezone="UTC",
        enable_utc=True,
        task_acks_late=True,
        worker_prefetch_multiplier=1,
        task_time_limit=settings.render_timeout_seconds + 300,
        task_soft_time_limit=settings.render_timeout_seconds + 120,
        broker_connection_retry_on_startup=True,
    )

    @app.task(name="reelcraft.render", bind=True)
    def render_task(self, job_id: str):  # pragma: no cover - requires a worker
        from app.services.render_worker import execute_render_job

        return execute_render_job(job_id)

    @app.task(name="reelcraft.voiceover", bind=True)
    def voiceover_task(self, project_id: str, user_id: str):  # pragma: no cover
        from app.services.voiceover_worker import execute_voiceover_job

        return execute_voiceover_job(project_id, user_id)

    @app.task(name="reelcraft.ai_motion", bind=True)
    def ai_motion_task(self, project_id: str, user_id: str, scene_id: str):  # pragma: no cover
        from app.services.ai_motion_worker import execute_ai_motion_job

        return execute_ai_motion_job(project_id, user_id, scene_id)

    @app.task(name="reelcraft.image", bind=True)
    def image_task(self, project_id: str, user_id: str, scene_id: str):  # pragma: no cover
        from app.services.image_worker import execute_image_job

        return execute_image_job(project_id, user_id, scene_id)

    @app.task(name="reelcraft.lipsync", bind=True)
    def lipsync_task(self, project_id: str, user_id: str, scene_id: str):  # pragma: no cover
        from app.services.lipsync_worker import execute_lipsync_job

        return execute_lipsync_job(project_id, user_id, scene_id)

    return app


celery_app = _build_celery_app() if settings.job_queue == "celery" else None


class CeleryJobQueue(JobQueue):
    name = "celery"

    def __init__(self):
        self._app = _build_celery_app()

    def is_available(self) -> bool:
        try:
            connection = self._app.connection()
            connection.ensure_connection(max_retries=1, timeout=3)
            connection.release()
            return True
        except Exception as exc:  # pragma: no cover - depends on Redis
            logger.warning("Celery broker unreachable: %s", exc)
            return False

    def enqueue_render(self, job_id: str) -> None:
        self._app.send_task("reelcraft.render", args=[job_id])

    def enqueue_voiceover(self, project_id: str, user_id: str) -> None:
        self._app.send_task("reelcraft.voiceover", args=[project_id, user_id])

    def enqueue_ai_motion(self, project_id: str, user_id: str, scene_id: str) -> None:
        self._app.send_task("reelcraft.ai_motion", args=[project_id, user_id, scene_id])

    def enqueue_image(self, project_id: str, user_id: str, scene_id: str) -> None:
        self._app.send_task("reelcraft.image", args=[project_id, user_id, scene_id])

    def enqueue_lipsync(self, project_id: str, user_id: str, scene_id: str) -> None:
        self._app.send_task("reelcraft.lipsync", args=[project_id, user_id, scene_id])
