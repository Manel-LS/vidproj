"""Concrete lip-sync providers: Sync Labs, HeyGen, Replicate.

Each converts provider-specific failures into `LipSyncUnavailable` carrying a
message safe to show a user — never the raw response, which can echo the key or
account details back to the browser.
"""
from __future__ import annotations

import base64

import httpx

from app.core.config import settings
from app.core.logging import get_logger
from app.infrastructure.lipsync.base import (
    GeneratedLipSync,
    LipSyncProvider,
    LipSyncRequest,
    LipSyncState,
    LipSyncStatus,
    LipSyncUnavailable,
)

logger = get_logger(__name__)


def _guard(response: httpx.Response, provider: str) -> None:
    if response.status_code in (401, 403):
        raise LipSyncUnavailable(
            f"{provider} rejected the API key. Check the key configured on the server."
        )
    if response.status_code == 429:
        raise LipSyncUnavailable(f"{provider} is rate limiting. Wait a moment and try again.")
    if response.status_code >= 400:
        logger.warning("%s returned %s: %s", provider, response.status_code, response.text[:400])
        raise LipSyncUnavailable(f"{provider} could not process this clip. Try again shortly.")


def _download(url: str, provider: str) -> GeneratedLipSync:
    try:
        with httpx.Client(timeout=300, follow_redirects=True) as client:
            response = client.get(url)
        response.raise_for_status()
    except httpx.HTTPError as exc:
        logger.warning("%s result download failed: %s", provider, exc)
        raise LipSyncUnavailable(
            "The lip-synced clip could not be downloaded. Try generating it again."
        ) from exc
    return GeneratedLipSync(
        data=response.content,
        content_type=response.headers.get("content-type", "video/mp4"),
        extension="mp4",
        provider=provider,
    )


def _data_uri(payload: bytes, content_type: str) -> str:
    return f"data:{content_type};base64,{base64.b64encode(payload).decode('ascii')}"


class SyncLabsProvider(LipSyncProvider):
    name = "synclabs"
    display_name = "Sync Labs"
    max_clip_seconds = 60.0
    #: The API fetches both inputs itself; it has no upload endpoint.
    needs_public_urls = True

    BASE_URL = "https://api.sync.so/v2"

    def __init__(self, api_key: str = "", model: str = ""):
        self._api_key = api_key or settings.synclabs_api_key
        self._model = model or settings.synclabs_model

    def is_available(self) -> bool:
        return bool(self._api_key)

    def _headers(self) -> dict[str, str]:
        return {"x-api-key": self._api_key, "Content-Type": "application/json"}

    def generate_lipsync(self, request: LipSyncRequest) -> str:
        if not self.is_available():
            raise LipSyncUnavailable("Sync Labs lip sync needs SYNCLABS_API_KEY.")
        if not request.video_url or not request.audio_url:
            raise LipSyncUnavailable(
                "Sync Labs downloads the clip and the voice itself, so both need a public "
                "URL. Configure S3 storage (or a public base URL) and try again."
            )

        payload = {
            "model": self._model,
            "input": [
                {"type": "video", "url": request.video_url},
                {"type": "audio", "url": request.audio_url},
            ],
            "options": {"output_format": "mp4"},
        }
        try:
            with httpx.Client(timeout=120) as client:
                response = client.post(
                    f"{self.BASE_URL}/generate", headers=self._headers(), json=payload
                )
        except httpx.HTTPError as exc:
            raise LipSyncUnavailable("Sync Labs is unreachable. Try again shortly.") from exc
        _guard(response, self.display_name)
        job_id = response.json().get("id")
        if not job_id:
            raise LipSyncUnavailable("Sync Labs did not return a job reference.")
        return str(job_id)

    def get_status(self, job_id: str) -> LipSyncStatus:
        try:
            with httpx.Client(timeout=60) as client:
                response = client.get(f"{self.BASE_URL}/generate/{job_id}", headers=self._headers())
        except httpx.HTTPError as exc:
            raise LipSyncUnavailable("Sync Labs is unreachable. Try again shortly.") from exc
        _guard(response, self.display_name)
        body = response.json()

        state = {
            "PENDING": LipSyncState.QUEUED,
            "PROCESSING": LipSyncState.PROCESSING,
            "COMPLETED": LipSyncState.COMPLETED,
            "FAILED": LipSyncState.FAILED,
            "REJECTED": LipSyncState.FAILED,
            "CANCELED": LipSyncState.FAILED,
        }.get(str(body.get("status", "")).upper(), LipSyncState.PROCESSING)

        return LipSyncStatus(
            job_id=job_id,
            state=state,
            error=str(body.get("error") or ""),
            result_url=body.get("outputUrl"),
        )

    def get_result(self, job_id: str) -> GeneratedLipSync:
        status = self.get_status(job_id)
        if not status.result_url:
            raise LipSyncUnavailable("Sync Labs reported no output for this job.")
        return _download(status.result_url, self.name)


class HeyGenProvider(LipSyncProvider):
    name = "heygen"
    display_name = "HeyGen"
    max_clip_seconds = 120.0
    needs_public_urls = True

    BASE_URL = "https://api.heygen.com/v2"
    STATUS_URL = "https://api.heygen.com/v1"

    def __init__(self, api_key: str = ""):
        self._api_key = api_key or settings.heygen_api_key

    def is_available(self) -> bool:
        return bool(self._api_key)

    def _headers(self) -> dict[str, str]:
        return {"X-Api-Key": self._api_key, "Content-Type": "application/json"}

    def generate_lipsync(self, request: LipSyncRequest) -> str:
        if not self.is_available():
            raise LipSyncUnavailable("HeyGen lip sync needs HEYGEN_API_KEY.")
        if not request.video_url or not request.audio_url:
            raise LipSyncUnavailable(
                "HeyGen downloads the clip and the voice itself, so both need a public "
                "URL. Configure S3 storage (or a public base URL) and try again."
            )

        payload = {
            "video_inputs": [
                {
                    "character": {"type": "video", "video_url": request.video_url},
                    "voice": {"type": "audio", "audio_url": request.audio_url},
                }
            ],
            "dimension": {"width": 1080, "height": 1920},
        }
        try:
            with httpx.Client(timeout=120) as client:
                response = client.post(
                    f"{self.BASE_URL}/video/generate", headers=self._headers(), json=payload
                )
        except httpx.HTTPError as exc:
            raise LipSyncUnavailable("HeyGen is unreachable. Try again shortly.") from exc
        _guard(response, self.display_name)
        job_id = (response.json().get("data") or {}).get("video_id")
        if not job_id:
            raise LipSyncUnavailable("HeyGen did not return a job reference.")
        return str(job_id)

    def get_status(self, job_id: str) -> LipSyncStatus:
        try:
            with httpx.Client(timeout=60) as client:
                response = client.get(
                    f"{self.STATUS_URL}/video_status.get",
                    headers=self._headers(),
                    params={"video_id": job_id},
                )
        except httpx.HTTPError as exc:
            raise LipSyncUnavailable("HeyGen is unreachable. Try again shortly.") from exc
        _guard(response, self.display_name)
        body = response.json().get("data") or {}

        state = {
            "pending": LipSyncState.QUEUED,
            "waiting": LipSyncState.QUEUED,
            "processing": LipSyncState.PROCESSING,
            "completed": LipSyncState.COMPLETED,
            "failed": LipSyncState.FAILED,
        }.get(str(body.get("status", "")).lower(), LipSyncState.PROCESSING)

        return LipSyncStatus(
            job_id=job_id,
            state=state,
            error=str((body.get("error") or {}).get("message") or ""),
            result_url=body.get("video_url"),
        )

    def get_result(self, job_id: str) -> GeneratedLipSync:
        status = self.get_status(job_id)
        if not status.result_url:
            raise LipSyncUnavailable("HeyGen reported no output for this job.")
        return _download(status.result_url, self.name)


class ReplicateLipSyncProvider(LipSyncProvider):
    name = "replicate"
    display_name = "Replicate"
    max_clip_seconds = 60.0
    #: Takes inline data URIs, so it works with local storage too — the only one
    #: of the three that does.
    needs_public_urls = False

    BASE_URL = "https://api.replicate.com/v1"

    def __init__(self, api_token: str = "", model: str = ""):
        self._token = api_token or settings.replicate_api_token
        self._model = model or settings.replicate_lipsync_model

    def is_available(self) -> bool:
        return bool(self._token)

    def _headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self._token}", "Content-Type": "application/json"}

    def generate_lipsync(self, request: LipSyncRequest) -> str:
        if not self.is_available():
            raise LipSyncUnavailable("Replicate lip sync needs REPLICATE_API_TOKEN.")

        payload = {
            "input": {
                "video": request.video_url
                or _data_uri(request.video, request.video_content_type or "video/mp4"),
                "audio": request.audio_url
                or _data_uri(request.audio, request.audio_content_type or "audio/mpeg"),
            }
        }
        try:
            with httpx.Client(timeout=180) as client:
                response = client.post(
                    f"{self.BASE_URL}/models/{self._model}/predictions",
                    headers=self._headers(),
                    json=payload,
                )
        except httpx.HTTPError as exc:
            raise LipSyncUnavailable("Replicate is unreachable. Try again shortly.") from exc
        _guard(response, self.display_name)
        job_id = response.json().get("id")
        if not job_id:
            raise LipSyncUnavailable("Replicate did not return a job reference.")
        return str(job_id)

    def get_status(self, job_id: str) -> LipSyncStatus:
        try:
            with httpx.Client(timeout=60) as client:
                response = client.get(
                    f"{self.BASE_URL}/predictions/{job_id}", headers=self._headers()
                )
        except httpx.HTTPError as exc:
            raise LipSyncUnavailable("Replicate is unreachable. Try again shortly.") from exc
        _guard(response, self.display_name)
        body = response.json()

        state = {
            "starting": LipSyncState.QUEUED,
            "processing": LipSyncState.PROCESSING,
            "succeeded": LipSyncState.COMPLETED,
            "failed": LipSyncState.FAILED,
            "canceled": LipSyncState.FAILED,
        }.get(str(body.get("status", "")), LipSyncState.PROCESSING)

        output = body.get("output")
        url = output[0] if isinstance(output, list) and output else output
        return LipSyncStatus(
            job_id=job_id,
            state=state,
            error=str(body.get("error") or ""),
            result_url=url if isinstance(url, str) else None,
        )

    def get_result(self, job_id: str) -> GeneratedLipSync:
        status = self.get_status(job_id)
        if not status.result_url:
            raise LipSyncUnavailable("Replicate reported no output for this job.")
        return _download(status.result_url, self.name)
