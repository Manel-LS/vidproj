"""Concrete image providers: OpenAI, Replicate, Google.

Every adapter converts provider-specific failures into `ImageUnavailable` with a
message safe to show a user — never the raw response, which can carry the key or
account details back to the browser.
"""
from __future__ import annotations

import base64
import time

import httpx

from app.core.config import settings
from app.core.logging import get_logger
from app.infrastructure.image.base import (
    GeneratedImage,
    ImageProvider,
    ImageRequest,
    ImageUnavailable,
)

logger = get_logger(__name__)

_RETRYABLE = {408, 429, 500, 502, 503, 504}


def _fail(provider: str, exc: Exception | None = None, detail: str = "") -> ImageUnavailable:
    if exc is not None:
        logger.warning("%s image generation failed: %s", provider, exc)
    return ImageUnavailable(
        detail or "The image could not be generated. Try again, or adjust the prompt."
    )


def _guard(response: httpx.Response, provider: str) -> None:
    if response.status_code == 401 or response.status_code == 403:
        raise ImageUnavailable(
            f"{provider} rejected the API key. Check the key configured on the server."
        )
    if response.status_code == 429:
        raise ImageUnavailable(f"{provider} is rate limiting. Wait a moment and try again.")
    if response.status_code >= 400:
        # The body can quote the prompt and the account; log it, do not return it.
        logger.warning("%s returned %s: %s", provider, response.status_code, response.text[:400])
        if response.status_code == 400:
            raise ImageUnavailable(
                f"{provider} refused this prompt. Rephrase it and try again."
            )
        raise ImageUnavailable(f"{provider} is unavailable right now. Try again shortly.")


def _download(url: str, provider: str) -> tuple[bytes, str]:
    try:
        with httpx.Client(timeout=120, follow_redirects=True) as client:
            response = client.get(url)
        response.raise_for_status()
    except httpx.HTTPError as exc:
        raise _fail(provider, exc, "The generated image could not be downloaded.") from exc
    return response.content, response.headers.get("content-type", "image/png")


def _extension(content_type: str) -> str:
    return {"image/jpeg": "jpg", "image/webp": "webp"}.get(content_type, "png")


class OpenAIImageProvider(ImageProvider):
    name = "openai"
    display_name = "OpenAI Images"
    supported_aspect_ratios = ("9:16", "1:1", "16:9")
    #: gpt-image-1 accepts input images on the /edits endpoint; the plain
    #: generations call used here does not, so references are not honoured.
    supports_reference_image = False

    #: The API accepts only this fixed set, so aspect ratios snap to the nearest.
    _SIZES = {"9:16": "1024x1536", "4:5": "1024x1536", "1:1": "1024x1024", "16:9": "1536x1024"}

    def __init__(self, api_key: str = "", model: str = ""):
        self._api_key = api_key or settings.openai_api_key
        self._model = model or settings.openai_image_model
        self._base_url = settings.openai_base_url.rstrip("/")

    def is_available(self) -> bool:
        return bool(self._api_key)

    def generate(self, request: ImageRequest) -> GeneratedImage:
        if not self.is_available():
            raise ImageUnavailable("OpenAI image generation needs OPENAI_API_KEY.")

        payload = {
            "model": self._model,
            "prompt": request.prompt,
            "size": self._SIZES.get(request.aspect_ratio, "1024x1536"),
            "n": 1,
        }
        try:
            with httpx.Client(timeout=settings.image_timeout_seconds) as client:
                response = client.post(
                    f"{self._base_url}/images/generations",
                    headers={"Authorization": f"Bearer {self._api_key}"},
                    json=payload,
                )
        except httpx.HTTPError as exc:
            raise _fail(self.display_name, exc) from exc

        _guard(response, self.display_name)
        item = (response.json().get("data") or [{}])[0]

        if item.get("b64_json"):
            data = base64.b64decode(item["b64_json"])
            content_type = "image/png"
        elif item.get("url"):
            data, content_type = _download(item["url"], self.display_name)
        else:
            raise _fail(self.display_name, detail="The provider returned no image.")

        return GeneratedImage(
            data=data,
            content_type=content_type,
            extension=_extension(content_type),
            provider=self.name,
            revised_prompt=str(item.get("revised_prompt") or ""),
        )


class ReplicateImageProvider(ImageProvider):
    name = "replicate"
    display_name = "Replicate"
    supported_aspect_ratios = ("9:16", "1:1", "4:5", "16:9")
    #: Most Replicate image models take an `image_prompt` for subject consistency.
    supports_reference_image = True

    BASE_URL = "https://api.replicate.com/v1"

    def __init__(self, api_token: str = "", model: str = ""):
        self._token = api_token or settings.replicate_api_token
        self._model = model or settings.replicate_image_model

    def is_available(self) -> bool:
        return bool(self._token)

    def _headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self._token}", "Content-Type": "application/json"}

    def generate(self, request: ImageRequest) -> GeneratedImage:
        if not self.is_available():
            raise ImageUnavailable("Replicate image generation needs REPLICATE_API_TOKEN.")

        payload: dict[str, object] = {
            "input": {
                "prompt": request.prompt,
                "aspect_ratio": request.aspect_ratio,
                "output_format": "png",
            }
        }
        if request.seed is not None:
            payload["input"]["seed"] = request.seed  # type: ignore[index]
        if request.reference_image:
            payload["input"]["image_prompt"] = (  # type: ignore[index]
                f"data:{request.reference_content_type or 'image/png'};base64,"
                + base64.b64encode(request.reference_image).decode("ascii")
            )

        try:
            with httpx.Client(timeout=120) as client:
                response = client.post(
                    f"{self.BASE_URL}/models/{self._model}/predictions",
                    headers={**self._headers(), "Prefer": "wait"},
                    json=payload,
                )
        except httpx.HTTPError as exc:
            raise _fail(self.display_name, exc) from exc
        _guard(response, self.display_name)

        prediction = response.json()
        # `Prefer: wait` usually returns a finished prediction, but it is a hint,
        # not a guarantee — poll when it comes back still running.
        deadline = time.monotonic() + settings.image_timeout_seconds
        while prediction.get("status") in ("starting", "processing"):
            if time.monotonic() > deadline:
                raise ImageUnavailable(
                    "Image generation timed out. Try again, or simplify the prompt."
                )
            time.sleep(2)
            try:
                with httpx.Client(timeout=60) as client:
                    poll = client.get(
                        f"{self.BASE_URL}/predictions/{prediction['id']}", headers=self._headers()
                    )
            except httpx.HTTPError as exc:
                raise _fail(self.display_name, exc) from exc
            _guard(poll, self.display_name)
            prediction = poll.json()

        if prediction.get("status") != "succeeded":
            logger.warning("Replicate prediction failed: %s", str(prediction.get("error"))[:400])
            raise _fail(self.display_name, detail="The image generation failed. Try again.")

        output = prediction.get("output")
        url = output[0] if isinstance(output, list) and output else output
        if not isinstance(url, str):
            raise _fail(self.display_name, detail="The provider returned no image.")

        data, content_type = _download(url, self.display_name)
        return GeneratedImage(
            data=data,
            content_type=content_type,
            extension=_extension(content_type),
            provider=self.name,
        )


class GoogleImageProvider(ImageProvider):
    name = "google"
    display_name = "Google Imagen"
    supported_aspect_ratios = ("9:16", "1:1", "4:5", "16:9")
    supports_reference_image = False

    BASE_URL = "https://generativelanguage.googleapis.com/v1beta"

    def __init__(self, api_key: str = "", model: str = ""):
        self._api_key = api_key or settings.google_api_key
        self._model = model or settings.google_image_model

    def is_available(self) -> bool:
        return bool(self._api_key)

    def generate(self, request: ImageRequest) -> GeneratedImage:
        if not self.is_available():
            raise ImageUnavailable("Google image generation needs GOOGLE_API_KEY.")

        payload = {
            "instances": [{"prompt": request.prompt}],
            "parameters": {
                "sampleCount": 1,
                "aspectRatio": request.aspect_ratio,
            },
        }
        try:
            with httpx.Client(timeout=settings.image_timeout_seconds) as client:
                response = client.post(
                    f"{self.BASE_URL}/models/{self._model}:predict",
                    headers={"x-goog-api-key": self._api_key, "Content-Type": "application/json"},
                    json=payload,
                )
        except httpx.HTTPError as exc:
            raise _fail(self.display_name, exc) from exc
        _guard(response, self.display_name)

        predictions = response.json().get("predictions") or []
        if not predictions or not predictions[0].get("bytesBase64Encoded"):
            raise _fail(self.display_name, detail="The provider returned no image.")

        item = predictions[0]
        content_type = item.get("mimeType") or "image/png"
        return GeneratedImage(
            data=base64.b64decode(item["bytesBase64Encoded"]),
            content_type=content_type,
            extension=_extension(content_type),
            provider=self.name,
        )
