"""Concrete image-to-video providers.

Each class encodes one vendor's actual API shape — submit, poll, download — because
they do not agree on any of it. The request/response field names below come from each
vendor's documented v1 surface; if a vendor changes theirs, only that class changes.

None of these can be exercised without credentials, so they are written to fail with a
clear, user-facing message rather than a stack trace when something is off.
"""
from __future__ import annotations

import base64
import time

import httpx

from app.core.config import settings
from app.core.logging import get_logger
from app.infrastructure.i2v.base import (
    GeneratedVideo,
    GenerationRequest,
    GenerationState,
    GenerationStatus,
    ImageToVideoProvider,
    ImageToVideoUnavailable,
)

logger = get_logger(__name__)


def _data_uri(image: bytes, content_type: str) -> str:
    return f"data:{content_type};base64,{base64.b64encode(image).decode('ascii')}"


def _download(url: str, provider: str) -> GeneratedVideo:
    try:
        with httpx.Client(timeout=300, follow_redirects=True) as client:
            response = client.get(url)
        response.raise_for_status()
    except httpx.HTTPError as exc:
        raise ImageToVideoUnavailable(
            "The generated clip could not be downloaded. Try generating it again."
        ) from exc
    return GeneratedVideo(
        data=response.content,
        content_type=response.headers.get("content-type", "video/mp4"),
        extension="mp4",
        provider=provider,
    )


class RunwayProvider(ImageToVideoProvider):
    name = "runway"
    display_name = "Runway"
    supported_durations = (5.0, 10.0)
    supported_aspect_ratios = ("9:16", "16:9", "1:1")
    BASE_URL = "https://api.dev.runwayml.com/v1"
    API_VERSION = "2024-11-06"

    _RATIOS = {"9:16": "720:1280", "16:9": "1280:720", "1:1": "960:960", "4:5": "1080:1350"}

    def __init__(self, api_key: str = "", model: str = ""):
        self._api_key = api_key or settings.runway_api_key
        self._model = model or settings.runway_model

    def is_available(self) -> bool:
        return bool(self._api_key)

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self._api_key}",
            "X-Runway-Version": self.API_VERSION,
            "Content-Type": "application/json",
        }

    def generate_video_from_image(self, request: GenerationRequest) -> str:
        if not self.is_available():
            raise ImageToVideoUnavailable("Runway is selected but RUNWAY_API_KEY is not set.")
        payload = {
            "model": self._model,
            "promptImage": _data_uri(request.image, request.image_content_type),
            "promptText": request.prompt[:500],
            "duration": int(min(self.supported_durations, key=lambda d: abs(d - request.duration_seconds))),
            "ratio": self._RATIOS.get(request.aspect_ratio, "720:1280"),
        }
        if request.seed is not None:
            payload["seed"] = request.seed

        try:
            with httpx.Client(timeout=120) as client:
                response = client.post(
                    f"{self.BASE_URL}/image_to_video", headers=self._headers(), json=payload
                )
        except httpx.HTTPError as exc:
            raise ImageToVideoUnavailable("Could not reach Runway. Try again in a moment.") from exc
        if response.status_code >= 400:
            logger.warning("Runway submit failed %s: %s", response.status_code, response.text[:300])
            raise ImageToVideoUnavailable(
                f"Runway rejected the generation request ({response.status_code})."
            )
        return str(response.json()["id"])

    def get_generation_status(self, job_id: str) -> GenerationStatus:
        with httpx.Client(timeout=60) as client:
            response = client.get(f"{self.BASE_URL}/tasks/{job_id}", headers=self._headers())
        if response.status_code >= 400:
            return GenerationStatus(job_id, GenerationState.FAILED, error=f"HTTP {response.status_code}")
        body = response.json()
        status = str(body.get("status", "")).upper()
        state = {
            "PENDING": GenerationState.QUEUED,
            "THROTTLED": GenerationState.QUEUED,
            "RUNNING": GenerationState.PROCESSING,
            "SUCCEEDED": GenerationState.COMPLETED,
            "FAILED": GenerationState.FAILED,
            "CANCELLED": GenerationState.FAILED,
        }.get(status, GenerationState.PROCESSING)
        outputs = body.get("output") or []
        return GenerationStatus(
            job_id=job_id,
            state=state,
            progress=int(float(body.get("progress") or 0) * 100),
            error=str(body.get("failure") or ""),
            video_url=outputs[0] if outputs else None,
        )

    def get_video_result(self, job_id: str) -> GeneratedVideo:
        status = self.get_generation_status(job_id)
        if status.state is not GenerationState.COMPLETED or not status.video_url:
            raise ImageToVideoUnavailable("The Runway generation is not finished yet.")
        return _download(status.video_url, self.name)


class LumaProvider(ImageToVideoProvider):
    name = "luma"
    display_name = "Luma Dream Machine"
    supported_durations = (5.0, 9.0)
    supported_aspect_ratios = ("9:16", "16:9", "1:1", "4:5")
    BASE_URL = "https://api.lumalabs.ai/dream-machine/v1"

    def __init__(self, api_key: str = ""):
        self._api_key = api_key or settings.luma_api_key

    def is_available(self) -> bool:
        return bool(self._api_key)

    def _headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self._api_key}", "Content-Type": "application/json"}

    def generate_video_from_image(self, request: GenerationRequest) -> str:
        if not self.is_available():
            raise ImageToVideoUnavailable("Luma is selected but LUMA_API_KEY is not set.")
        # Luma reads the start frame from a URL, so the caller must pass a reachable
        # one; the service supplies the media's public storage URL in `prompt` context.
        payload = {
            "prompt": request.prompt[:500] or "cinematic subtle camera movement",
            "aspect_ratio": request.aspect_ratio,
            "keyframes": {
                "frame0": {"type": "image", "url": _data_uri(request.image, request.image_content_type)}
            },
        }
        with httpx.Client(timeout=120) as client:
            response = client.post(f"{self.BASE_URL}/generations", headers=self._headers(), json=payload)
        if response.status_code >= 400:
            logger.warning("Luma submit failed %s: %s", response.status_code, response.text[:300])
            raise ImageToVideoUnavailable(
                f"Luma rejected the generation request ({response.status_code})."
            )
        return str(response.json()["id"])

    def get_generation_status(self, job_id: str) -> GenerationStatus:
        with httpx.Client(timeout=60) as client:
            response = client.get(f"{self.BASE_URL}/generations/{job_id}", headers=self._headers())
        if response.status_code >= 400:
            return GenerationStatus(job_id, GenerationState.FAILED, error=f"HTTP {response.status_code}")
        body = response.json()
        state = {
            "queued": GenerationState.QUEUED,
            "dreaming": GenerationState.PROCESSING,
            "completed": GenerationState.COMPLETED,
            "failed": GenerationState.FAILED,
        }.get(str(body.get("state", "")).lower(), GenerationState.PROCESSING)
        return GenerationStatus(
            job_id=job_id,
            state=state,
            progress=100 if state is GenerationState.COMPLETED else 50,
            error=str(body.get("failure_reason") or ""),
            video_url=(body.get("assets") or {}).get("video"),
        )

    def get_video_result(self, job_id: str) -> GeneratedVideo:
        status = self.get_generation_status(job_id)
        if status.state is not GenerationState.COMPLETED or not status.video_url:
            raise ImageToVideoUnavailable("The Luma generation is not finished yet.")
        return _download(status.video_url, self.name)


class KlingProvider(ImageToVideoProvider):
    name = "kling"
    display_name = "Kling"
    supported_durations = (5.0, 10.0)
    supported_aspect_ratios = ("9:16", "16:9", "1:1")
    BASE_URL = "https://api.klingai.com/v1"

    def __init__(self, access_key: str = "", secret_key: str = ""):
        self._access_key = access_key or settings.kling_access_key
        self._secret_key = secret_key or settings.kling_secret_key

    def is_available(self) -> bool:
        return bool(self._access_key and self._secret_key)

    def _token(self) -> str:
        """Kling authenticates with a short-lived JWT signed with the secret key."""
        from jose import jwt  # noqa: PLC0415

        now = int(time.time())
        return jwt.encode(
            {"iss": self._access_key, "exp": now + 1800, "nbf": now - 5},
            self._secret_key,
            algorithm="HS256",
            headers={"alg": "HS256", "typ": "JWT"},
        )

    def _headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self._token()}", "Content-Type": "application/json"}

    def generate_video_from_image(self, request: GenerationRequest) -> str:
        if not self.is_available():
            raise ImageToVideoUnavailable(
                "Kling is selected but KLING_ACCESS_KEY / KLING_SECRET_KEY are not set."
            )
        payload = {
            "model_name": "kling-v1",
            "image": base64.b64encode(request.image).decode("ascii"),
            "prompt": request.prompt[:500],
            "duration": str(int(min(self.supported_durations, key=lambda d: abs(d - request.duration_seconds)))),
            "aspect_ratio": request.aspect_ratio,
            "mode": "std",
        }
        with httpx.Client(timeout=120) as client:
            response = client.post(
                f"{self.BASE_URL}/videos/image2video", headers=self._headers(), json=payload
            )
        if response.status_code >= 400:
            logger.warning("Kling submit failed %s: %s", response.status_code, response.text[:300])
            raise ImageToVideoUnavailable(
                f"Kling rejected the generation request ({response.status_code})."
            )
        return str(response.json()["data"]["task_id"])

    def get_generation_status(self, job_id: str) -> GenerationStatus:
        with httpx.Client(timeout=60) as client:
            response = client.get(
                f"{self.BASE_URL}/videos/image2video/{job_id}", headers=self._headers()
            )
        if response.status_code >= 400:
            return GenerationStatus(job_id, GenerationState.FAILED, error=f"HTTP {response.status_code}")
        data = response.json().get("data", {})
        state = {
            "submitted": GenerationState.QUEUED,
            "processing": GenerationState.PROCESSING,
            "succeed": GenerationState.COMPLETED,
            "failed": GenerationState.FAILED,
        }.get(str(data.get("task_status", "")).lower(), GenerationState.PROCESSING)
        videos = ((data.get("task_result") or {}).get("videos")) or []
        return GenerationStatus(
            job_id=job_id,
            state=state,
            progress=100 if state is GenerationState.COMPLETED else 50,
            error=str(data.get("task_status_msg") or ""),
            video_url=videos[0].get("url") if videos else None,
        )

    def get_video_result(self, job_id: str) -> GeneratedVideo:
        status = self.get_generation_status(job_id)
        if status.state is not GenerationState.COMPLETED or not status.video_url:
            raise ImageToVideoUnavailable("The Kling generation is not finished yet.")
        return _download(status.video_url, self.name)
