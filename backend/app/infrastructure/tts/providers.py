"""Concrete VoiceProvider implementations.

Each provider owns its own request shape — deliberately, because these APIs are not
interchangeable. Adding another one means adding a class here and a branch in
`factory.get_voice_provider`; nothing above the infrastructure layer changes.
"""
from __future__ import annotations

import httpx

from app.core.config import settings
from app.core.logging import get_logger
from app.infrastructure.tts.base import SynthesisResult, Voice, VoiceProvider, VoiceUnavailable

logger = get_logger(__name__)

MAX_SCRIPT_CHARS = 4000


def _guard_text(text: str) -> str:
    cleaned = (text or "").strip()
    if not cleaned:
        raise VoiceUnavailable("The voice-over script is empty. Write a script first.")
    if len(cleaned) > MAX_SCRIPT_CHARS:
        raise VoiceUnavailable(
            f"The script is {len(cleaned)} characters; the limit is {MAX_SCRIPT_CHARS}. "
            "Shorten it and try again."
        )
    return cleaned


class ElevenLabsVoiceProvider(VoiceProvider):
    name = "elevenlabs"
    display_name = "ElevenLabs"
    BASE_URL = "https://api.elevenlabs.io/v1"

    def __init__(self, api_key: str = "", voice_id: str = "", model: str = ""):
        self._api_key = api_key or settings.elevenlabs_api_key
        self._voice_id = voice_id or settings.elevenlabs_voice_id
        self._model = model or settings.elevenlabs_model

    def is_available(self) -> bool:
        return bool(self._api_key)

    def list_voices(self) -> list[Voice]:
        if not self.is_available():
            return []
        try:
            with httpx.Client(timeout=20) as client:
                response = client.get(
                    f"{self.BASE_URL}/voices", headers={"xi-api-key": self._api_key}
                )
            response.raise_for_status()
            return [
                Voice(
                    id=item["voice_id"],
                    name=item.get("name", item["voice_id"]),
                    description=(item.get("labels") or {}).get("description", ""),
                    gender=(item.get("labels") or {}).get("gender", ""),
                )
                for item in response.json().get("voices", [])
            ]
        except (httpx.HTTPError, KeyError, ValueError) as exc:
            logger.warning("Could not list ElevenLabs voices: %s", exc)
            return [Voice(id=self._voice_id, name="Default voice")]

    def synthesize(self, text: str, *, voice_id: str | None = None) -> SynthesisResult:
        if not self.is_available():
            raise VoiceUnavailable("ElevenLabs is selected but ELEVENLABS_API_KEY is not set.")
        text = _guard_text(text)
        target_voice = voice_id or self._voice_id

        try:
            with httpx.Client(timeout=180) as client:
                response = client.post(
                    f"{self.BASE_URL}/text-to-speech/{target_voice}",
                    headers={"xi-api-key": self._api_key, "accept": "audio/mpeg"},
                    json={
                        "text": text,
                        "model_id": self._model,
                        "voice_settings": {"stability": 0.45, "similarity_boost": 0.75},
                    },
                )
        except httpx.HTTPError as exc:
            raise VoiceUnavailable("Could not reach ElevenLabs. Try again in a moment.") from exc

        if response.status_code >= 400:
            logger.warning("ElevenLabs error %s: %s", response.status_code, response.text[:300])
            raise VoiceUnavailable(
                f"ElevenLabs rejected the request ({response.status_code}). "
                "Check the API key and the selected voice."
            )
        return SynthesisResult(
            audio=response.content,
            content_type="audio/mpeg",
            extension="mp3",
            voice_id=target_voice,
            provider=self.name,
        )


class OpenAITTSVoiceProvider(VoiceProvider):
    name = "openai"
    display_name = "OpenAI TTS"

    #: The published preset voices; this endpoint has no discovery call.
    VOICES = (
        Voice("alloy", "Alloy", "Neutral and even"),
        Voice("echo", "Echo", "Warm and grounded"),
        Voice("fable", "Fable", "Expressive, storytelling"),
        Voice("onyx", "Onyx", "Deep and authoritative"),
        Voice("nova", "Nova", "Bright and energetic"),
        Voice("shimmer", "Shimmer", "Soft and friendly"),
    )

    def __init__(self, api_key: str = "", base_url: str = "", model: str = "", voice: str = ""):
        self._api_key = api_key or settings.openai_api_key
        self._base_url = (base_url or settings.openai_base_url).rstrip("/")
        self._model = model or settings.openai_tts_model
        self._voice = voice or settings.openai_tts_voice

    def is_available(self) -> bool:
        return bool(self._api_key)

    def list_voices(self) -> list[Voice]:
        return list(self.VOICES) if self.is_available() else []

    def synthesize(self, text: str, *, voice_id: str | None = None) -> SynthesisResult:
        if not self.is_available():
            raise VoiceUnavailable("OpenAI TTS is selected but OPENAI_API_KEY is not set.")
        text = _guard_text(text)
        target_voice = voice_id or self._voice

        try:
            with httpx.Client(timeout=180) as client:
                response = client.post(
                    f"{self._base_url}/audio/speech",
                    headers={"Authorization": f"Bearer {self._api_key}"},
                    json={
                        "model": self._model,
                        "voice": target_voice,
                        "input": text,
                        "response_format": "mp3",
                    },
                )
        except httpx.HTTPError as exc:
            raise VoiceUnavailable("Could not reach the OpenAI API. Try again in a moment.") from exc

        if response.status_code >= 400:
            logger.warning("OpenAI TTS error %s: %s", response.status_code, response.text[:300])
            raise VoiceUnavailable(
                f"The text-to-speech request failed ({response.status_code}). Check the API key."
            )
        return SynthesisResult(
            audio=response.content,
            content_type="audio/mpeg",
            extension="mp3",
            voice_id=target_voice,
            provider=self.name,
        )


class EdgeVoiceProvider(VoiceProvider):
    """Voix neuronales de Microsoft Edge — gratuites et sans clé d'API.

    Ce fournisseur s'appuie sur le point d'accès « read aloud » d'Edge via le
    paquet `edge-tts`. Il faut le savoir avant de s'en servir en production :

      * aucune clé n'est requise et la qualité est excellente, y compris en
        arabe (l'arabe tunisien est couvert : ar-TN-HediNeural, ar-TN-ReemNeural) ;
      * mais ce n'est pas une API publique documentée. Elle peut changer ou
        cesser de fonctionner sans préavis, et ses conditions d'utilisation ne
        disent rien d'explicite sur l'usage commercial.

    Pour un produit facturé, ElevenLabs ou OpenAI restent les voies sous contrat.
    Celle-ci existe pour travailler, prototyper et produire sans budget.
    """

    name = "edge"
    display_name = "Microsoft Edge (gratuit, sans clé)"

    #: Voix par défaut quand le script est écrit dans cette écriture.
    _BY_SCRIPT = {
        "arabic": "ar-SA-HamedNeural",
        "latin": "fr-FR-HenriNeural",
    }

    def __init__(self, voice: str = "", rate: str = ""):
        self._voice = voice or settings.edge_tts_voice
        self._rate = rate or settings.edge_tts_rate

    def is_available(self) -> bool:
        try:
            import edge_tts  # noqa: F401, PLC0415
        except ImportError:
            return False
        return True

    @staticmethod
    def _detect_script(text: str) -> str:
        from app.infrastructure.imaging.text_renderer import is_rtl  # noqa: PLC0415

        return "arabic" if is_rtl(text) else "latin"

    def _pick_voice(self, text: str, voice_id: str | None) -> str:
        if voice_id:
            return voice_id
        if self._voice:
            return self._voice
        # Rien n'est configuré : choisir selon l'écriture du script évite de faire
        # lire de l'arabe par une voix française, qui le prononcerait lettre à lettre.
        return self._BY_SCRIPT[self._detect_script(text)]

    def list_voices(self) -> list[Voice]:
        if not self.is_available():
            return []
        import asyncio  # noqa: PLC0415

        import edge_tts  # noqa: PLC0415

        try:
            catalogue = asyncio.run(edge_tts.list_voices())
        except Exception as exc:  # pragma: no cover - dépend du réseau
            logger.warning("Could not list Edge voices: %s", exc)
            return []

        return [
            Voice(
                id=item["ShortName"],
                name=f"{item['ShortName'].split('-')[-1].replace('Neural', '')} · {item['Locale']}",
                description=item.get("FriendlyName", ""),
                language=item["Locale"],
                gender=item.get("Gender", ""),
            )
            for item in sorted(catalogue, key=lambda v: (v["Locale"], v["ShortName"]))
        ]

    def synthesize(self, text: str, *, voice_id: str | None = None) -> SynthesisResult:
        if not self.is_available():
            raise VoiceUnavailable(
                "Le fournisseur Edge est sélectionné mais le paquet `edge-tts` "
                "n'est pas installé. Lancez `pip install edge-tts`."
            )
        text = _guard_text(text)
        target_voice = self._pick_voice(text, voice_id)

        import asyncio  # noqa: PLC0415

        import edge_tts  # noqa: PLC0415

        async def render() -> bytes:
            chunks: list[bytes] = []
            communicate = edge_tts.Communicate(text, target_voice, rate=self._rate)
            async for chunk in communicate.stream():
                if chunk["type"] == "audio":
                    chunks.append(chunk["data"])
            return b"".join(chunks)

        try:
            audio = asyncio.run(render())
        except Exception as exc:
            logger.warning("Edge TTS failed: %s", exc)
            raise VoiceUnavailable(
                "La synthèse vocale a échoué. Le service Edge est peut-être "
                "momentanément indisponible — réessayez dans un instant."
            ) from exc

        if not audio:
            raise VoiceUnavailable("La synthèse vocale n'a produit aucun son.")

        return SynthesisResult(
            audio=audio,
            content_type="audio/mpeg",
            extension="mp3",
            voice_id=target_voice,
            provider=self.name,
        )
