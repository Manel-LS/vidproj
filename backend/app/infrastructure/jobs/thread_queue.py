"""In-process job queue.

Semantically equivalent to the Celery queue from the caller's point of view: submit
and return, the worker updates the database row. The trade-off is that jobs do not
survive a process restart — `recover_orphaned_jobs()` marks any job left mid-flight as
failed on the next boot so nothing is stuck in PROCESSING forever.
"""
from __future__ import annotations

import threading
from concurrent.futures import ThreadPoolExecutor

from app.core.config import settings
from app.core.logging import get_logger
from app.infrastructure.jobs.base import JobQueue

logger = get_logger(__name__)


class ThreadPoolJobQueue(JobQueue):
    name = "thread"

    def __init__(self, workers: int | None = None):
        self._executor = ThreadPoolExecutor(
            max_workers=workers or settings.thread_queue_workers,
            thread_name_prefix="reelcraft-worker",
        )
        self._lock = threading.Lock()
        self._closed = False

    def is_available(self) -> bool:
        return not self._closed

    def _submit(self, func, *args) -> None:
        with self._lock:
            if self._closed:
                raise RuntimeError("The job queue is shutting down.")
            future = self._executor.submit(func, *args)
        future.add_done_callback(self._log_failure)

    @staticmethod
    def _log_failure(future) -> None:
        exception = future.exception()
        if exception is not None:  # the worker already recorded it on the row
            logger.exception("Background job raised", exc_info=exception)

    def enqueue_render(self, job_id: str) -> None:
        from app.services.render_worker import execute_render_job  # noqa: PLC0415

        self._submit(execute_render_job, job_id)

    def enqueue_voiceover(self, project_id: str, user_id: str) -> None:
        from app.services.voiceover_worker import execute_voiceover_job  # noqa: PLC0415

        self._submit(execute_voiceover_job, project_id, user_id)

    def enqueue_ai_motion(self, project_id: str, user_id: str, scene_id: str) -> None:
        from app.services.ai_motion_worker import execute_ai_motion_job  # noqa: PLC0415

        self._submit(execute_ai_motion_job, project_id, user_id, scene_id)

    def enqueue_image(self, project_id: str, user_id: str, scene_id: str) -> None:
        from app.services.image_worker import execute_image_job  # noqa: PLC0415

        self._submit(execute_image_job, project_id, user_id, scene_id)

    def enqueue_lipsync(self, project_id: str, user_id: str, scene_id: str) -> None:
        from app.services.lipsync_worker import execute_lipsync_job  # noqa: PLC0415

        self._submit(execute_lipsync_job, project_id, user_id, scene_id)

    def shutdown(self) -> None:
        with self._lock:
            self._closed = True
        self._executor.shutdown(wait=False, cancel_futures=True)
