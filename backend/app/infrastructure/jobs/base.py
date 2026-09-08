"""Background job queue abstraction (requirement 16).

Rendering must never block the HTTP request. The API creates a `RenderJob` row in
`QUEUED`, hands the id to a queue, and returns immediately; the worker moves the row
through `PROCESSING` -> `COMPLETED` / `FAILED` while the client polls.

Two implementations ship:
  * `CeleryJobQueue`  — Redis-backed, the production choice, workers scale out.
  * `ThreadPoolJobQueue` — an in-process pool with identical semantics, so a developer
    (or a small single-node deployment) needs no Redis to render a video.
"""
from __future__ import annotations

import abc


class JobQueue(abc.ABC):
    name: str = "abstract"

    @abc.abstractmethod
    def enqueue_render(self, job_id: str) -> None:
        """Schedule `execute_render_job(job_id)` to run outside the request."""

    @abc.abstractmethod
    def enqueue_voiceover(self, project_id: str, user_id: str) -> None:
        """Schedule voice-over synthesis outside the request."""

    @abc.abstractmethod
    def enqueue_ai_motion(self, project_id: str, user_id: str, scene_id: str) -> None:
        """Schedule an AI Motion clip generation outside the request."""

    @abc.abstractmethod
    def enqueue_image(self, project_id: str, user_id: str, scene_id: str) -> None:
        """Schedule a scene image generation outside the request."""

    @abc.abstractmethod
    def enqueue_lipsync(self, project_id: str, user_id: str, scene_id: str) -> None:
        """Schedule a lip-sync pass for one scene outside the request."""

    @abc.abstractmethod
    def is_available(self) -> bool: ...

    def shutdown(self) -> None:  # pragma: no cover - overridden where it matters
        """Called on application shutdown."""
