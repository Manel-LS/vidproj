"""Application configuration.

Every externally-configurable value lives here and is sourced from the environment
(see `.env.example`). Nothing else in the codebase reads `os.environ` directly.
"""
from __future__ import annotations

import secrets
from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(BACKEND_ROOT / ".env", BACKEND_ROOT.parent / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # ---- General -----------------------------------------------------------
    app_name: str = "Reelcraft"
    environment: Literal["development", "test", "production"] = "development"
    api_v1_prefix: str = "/api/v1"
    debug: bool = True

    # ---- Security ----------------------------------------------------------
    # MUST be set explicitly in production; a random value would invalidate all
    # sessions on restart, so `validate_production()` refuses to start without it.
    secret_key: str = Field(default_factory=lambda: secrets.token_urlsafe(48))
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 60 * 24 * 7
    cors_origins: list[str] = ["http://localhost:3000", "http://127.0.0.1:3000"]

    rate_limit_enabled: bool = True
    rate_limit_requests: int = 120
    rate_limit_window_seconds: int = 60
    rate_limit_upload_requests: int = 60

    # ---- Database ----------------------------------------------------------
    # PostgreSQL: postgresql+psycopg://user:pass@host:5432/reelcraft
    # MySQL / MariaDB: mysql+pymysql://user:pass@host:3306/reelcraft
    #   (a bare `mysql://` is rewritten to use PyMySQL, and utf8mb4 is forced)
    # Development fallback: local SQLite file, so the app runs with zero services.
    database_url: str = ""

    # ---- Storage -----------------------------------------------------------
    storage_provider: Literal["local", "s3"] = "local"
    storage_local_root: Path = BACKEND_ROOT / "var" / "storage"
    #: Where the browser fetches stored files from. Relative by default, so media URLs
    #: resolve against whatever host the API is reached on — no hostname to keep in
    #: sync, and it works unchanged behind a reverse proxy. Set an absolute URL only
    #: when files are served from a different origin (a CDN, for example).
    storage_public_base_url: str = "/api/v1/files"
    s3_bucket: str = ""
    s3_region: str = ""
    s3_endpoint_url: str = ""
    s3_access_key_id: str = ""
    s3_secret_access_key: str = ""
    s3_public_base_url: str = ""

    # ---- Uploads -----------------------------------------------------------
    max_image_bytes: int = 15 * 1024 * 1024
    max_audio_bytes: int = 25 * 1024 * 1024
    max_images_per_project: int = 40
    allowed_image_mimes: list[str] = [
        "image/jpeg",
        "image/png",
        "image/webp",
    ]
    allowed_audio_mimes: list[str] = [
        "audio/mpeg",
        "audio/mp3",
        "audio/wav",
        "audio/x-wav",
        "audio/wave",
    ]
    #: An imported AI Motion clip: a few seconds of 1080p, so far above the image cap.
    max_video_bytes: int = 100 * 1024 * 1024
    allowed_video_mimes: list[str] = [
        "video/mp4",
        "video/quicktime",
        "video/webm",
    ]
    image_max_dimension: int = 2560  # uploads are downscaled to this on the long edge

    # ---- Rendering ---------------------------------------------------------
    ffmpeg_binary: str = ""      # empty => auto-resolve (PATH, then imageio-ffmpeg)
    ffprobe_binary: str = ""
    render_fps: int = 30
    render_supersample: float = 2.0
    render_crf: int = 20
    render_preset: str = "medium"
    render_threads: int = 0      # 0 => ffmpeg decides
    render_font_path: str = ""   # empty => auto-resolve from a known font list
    render_timeout_seconds: int = 900
    render_work_dir: Path = BACKEND_ROOT / "var" / "work"
    keep_render_workdir: bool = False

    # ---- Jobs --------------------------------------------------------------
    job_queue: Literal["thread", "celery"] = "thread"
    redis_url: str = "redis://localhost:6379/0"
    thread_queue_workers: int = 2

    # ---- AI: LLM planner ---------------------------------------------------
    llm_provider: Literal["auto", "anthropic", "openai_compatible", "heuristic"] = "auto"
    anthropic_api_key: str = ""
    anthropic_model: str = "claude-sonnet-5"
    openai_api_key: str = ""
    openai_base_url: str = "https://api.openai.com/v1"
    openai_model: str = "gpt-4o-mini"
    llm_timeout_seconds: int = 90

    # ---- AI: text to speech ------------------------------------------------
    tts_provider: Literal["none", "edge", "elevenlabs", "openai"] = "none"
    #: `edge` : voix neuronales gratuites, sans clé. Voir EdgeVoiceProvider pour ce
    #: que cela implique. Vide => la voix est choisie selon l'écriture du script.
    edge_tts_voice: str = ""
    edge_tts_rate: str = "-8%"   # un récit se lit un peu plus lentement
    elevenlabs_api_key: str = ""
    elevenlabs_voice_id: str = "21m00Tcm4TlvDq8ikWAM"
    elevenlabs_model: str = "eleven_multilingual_v2"
    openai_tts_model: str = "gpt-4o-mini-tts"
    openai_tts_voice: str = "alloy"

    # ---- depth (still -> 2.5D parallax) ------------------------------------
    #: `onnx` runs Depth Anything V2 Small locally on the CPU. It needs the optional
    #: dependencies (`requirements-depth.txt`) and the model file; without either it
    #: reports unavailable and scenes keep their flat camera moves.
    depth_provider: Literal["none", "onnx"] = "none"
    depth_model_path: str = str(BACKEND_ROOT / "var" / "models" / "depth-anything-v2-small-q8.onnx")
    #: Input side in pixels, rounded down to a multiple of 14 by the provider.
    #: 518 is the model's training size; smaller is faster and visibly coarser.
    depth_input_size: int = 518
    #: Kept low on purpose: depth runs while ffmpeg wants the cores.
    depth_threads: int = 2

    # ---- AI: image to video ------------------------------------------------
    # ---- image generation (text -> still) --------------------------------
    image_provider: Literal["none", "openai", "replicate", "google"] = "none"
    openai_image_model: str = "gpt-image-1"
    replicate_api_token: str = ""
    replicate_image_model: str = "black-forest-labs/flux-1.1-pro"
    google_api_key: str = ""
    google_image_model: str = "imagen-4.0-generate-001"
    #: Generation is seconds, not minutes; a request stuck past this is a failure.
    image_timeout_seconds: int = 180

    # ---- lip sync (silent clip + voice -> speaking clip) ------------------
    lipsync_provider: Literal["none", "synclabs", "heygen", "replicate"] = "none"
    synclabs_api_key: str = ""
    synclabs_model: str = "lipsync-2"
    heygen_api_key: str = ""
    replicate_lipsync_model: str = "sync/lipsync-2"
    lipsync_poll_interval_seconds: float = 5.0
    lipsync_timeout_seconds: int = 900

    i2v_provider: Literal["none", "runway", "kling", "luma", "replicate"] = "none"
    #: Replicate hosts many vendors' models; the payload is built from whichever
    #: one this names, by reading its published input schema.
    replicate_i2v_model: str = "bytedance/seedance-1-lite"
    runway_api_key: str = ""
    runway_model: str = "gen4_turbo"
    kling_access_key: str = ""
    kling_secret_key: str = ""
    luma_api_key: str = ""
    i2v_poll_interval_seconds: int = 5
    i2v_timeout_seconds: int = 600

    # ---- Seed --------------------------------------------------------------
    seed_demo_user_email: str = "demo@reelcraft.app"
    seed_demo_user_password: str = "demo1234"

    @field_validator(
        "cors_origins", "allowed_image_mimes", "allowed_audio_mimes", "allowed_video_mimes",
        mode="before",
    )
    @classmethod
    def _split_csv(cls, value):
        if isinstance(value, str):
            return [item.strip() for item in value.split(",") if item.strip()]
        return value

    @property
    def resolved_database_url(self) -> str:
        if self.database_url:
            return self._normalise_database_url(self.database_url)
        db_path = BACKEND_ROOT / "var" / "reelcraft.db"
        db_path.parent.mkdir(parents=True, exist_ok=True)
        return f"sqlite:///{db_path.as_posix()}"

    @staticmethod
    def _normalise_database_url(url: str) -> str:
        """Fill in the details a MySQL URL needs but people rarely type.

        `mysql://` with no driver would pick MySQLdb, which needs a C toolchain on
        Windows, so it is redirected to the pure-Python PyMySQL driver. `utf8mb4` is
        forced because plain `utf8` in MySQL is only three bytes and silently mangles
        emoji — which social captions are full of.
        """
        if url.startswith("mysql://"):
            url = url.replace("mysql://", "mysql+pymysql://", 1)
        if url.startswith(("mysql+pymysql://", "mariadb+pymysql://")) and "charset=" not in url:
            url += ("&" if "?" in url else "?") + "charset=utf8mb4"
        return url

    @property
    def is_sqlite(self) -> bool:
        return self.resolved_database_url.startswith("sqlite")

    @property
    def is_mysql(self) -> bool:
        return self.resolved_database_url.startswith(("mysql", "mariadb"))

    @property
    def database_backend(self) -> str:
        """Short name for logs and the health endpoint."""
        if self.is_sqlite:
            return "sqlite"
        if self.is_mysql:
            return "mysql"
        return "postgresql"

    def validate_production(self) -> list[str]:
        """Return a list of misconfigurations that must be fixed before prod boot."""
        problems: list[str] = []
        if self.environment != "production":
            return problems
        import os

        if not os.environ.get("SECRET_KEY"):
            problems.append("SECRET_KEY must be set explicitly in production.")
        if not self.database_url:
            problems.append(
                "DATABASE_URL must point at PostgreSQL or MySQL in production; "
                "the SQLite fallback is for development only."
            )
        if self.debug:
            problems.append("DEBUG must be false in production.")
        return problems


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
