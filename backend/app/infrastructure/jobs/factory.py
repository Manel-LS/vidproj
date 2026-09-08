"""Job queue selection.

`JOB_QUEUE=celery` is the production setting. If Celery is selected but the broker is
unreachable at boot, the in-process queue takes over rather than accepting renders
that would never run — the capabilities endpoint reports which one is live.
"""
from __future__ import annotations

from functools import lru_cache

from app.core.config import settings
from app.core.logging import get_logger
from app.infrastructure.jobs.base import JobQueue
from app.infrastructure.jobs.thread_queue import ThreadPoolJobQueue

logger = get_logger(__name__)


@lru_cache
def get_job_queue() -> JobQueue:
    if settings.job_queue == "celery":
        from app.infrastructure.jobs.celery_queue import CeleryJobQueue

        queue = CeleryJobQueue()
        if queue.is_available():
            return queue
        logger.warning(
            "JOB_QUEUE=celery but the broker at %s is unreachable; "
            "falling back to the in-process queue.",
            settings.redis_url,
        )
    return ThreadPoolJobQueue()


def queue_status() -> dict[str, object]:
    queue = get_job_queue()
    return {
        "provider": queue.name,
        "configured": settings.job_queue,
        "available": queue.is_available(),
    }
