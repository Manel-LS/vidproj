"""Low-level ffmpeg access: binary resolution, safe invocation, capability probing.

Two rules hold everywhere in this package:

  * commands are argv **lists**, never shell strings, and `shell=False` — there is no
    shell to inject into;
  * no user-controlled string is ever interpolated into a filtergraph. Text is
    rasterised to PNG first, file paths reach ffmpeg as their own argv entries, and
    every number written into a filter is formatted from a validated float/int.
"""
from __future__ import annotations

import re
import shutil
import subprocess
import threading
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Callable, Iterable, Sequence

from app.core.config import settings
from app.core.errors import RenderError
from app.core.logging import get_logger

logger = get_logger(__name__)

ProgressCallback = Callable[[float], None]


class FFmpegNotAvailableError(RenderError):
    code = "ffmpeg_unavailable"


@lru_cache(maxsize=1)
def ffmpeg_path() -> str:
    """Resolve the ffmpeg binary: explicit setting, then PATH, then the bundled one."""
    if settings.ffmpeg_binary:
        candidate = Path(settings.ffmpeg_binary)
        if candidate.is_file():
            return str(candidate)
        found = shutil.which(settings.ffmpeg_binary)
        if found:
            return found
        raise FFmpegNotAvailableError(
            f"FFMPEG_BINARY is set to '{settings.ffmpeg_binary}' but no such executable exists."
        )

    found = shutil.which("ffmpeg")
    if found:
        return found

    try:  # imageio-ffmpeg ships a static build; this is why local dev needs no install
        import imageio_ffmpeg  # noqa: PLC0415

        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception as exc:  # pragma: no cover - only when nothing is installed
        raise FFmpegNotAvailableError(
            "FFmpeg was not found. Install it and put it on PATH, or set FFMPEG_BINARY."
        ) from exc


@lru_cache(maxsize=1)
def ffprobe_path() -> str | None:
    if settings.ffprobe_binary and Path(settings.ffprobe_binary).is_file():
        return settings.ffprobe_binary
    return shutil.which("ffprobe")


@lru_cache(maxsize=1)
def ffmpeg_version() -> str:
    try:
        out = subprocess.run(
            [ffmpeg_path(), "-hide_banner", "-version"],
            capture_output=True, text=True, timeout=30, check=False,
        ).stdout
        return out.splitlines()[0] if out else "unknown"
    except Exception:  # pragma: no cover
        return "unknown"


@lru_cache(maxsize=1)
def supported_xfade_transitions() -> frozenset[str]:
    """Which `xfade` transition names this build accepts.

    Builds differ; the compiler falls back to `fade` for anything missing rather
    than failing a render with a cryptic ffmpeg error.
    """
    try:
        out = subprocess.run(
            [ffmpeg_path(), "-hide_banner", "-h", "filter=xfade"],
            capture_output=True, text=True, timeout=30, check=False,
        )
        text = f"{out.stdout}\n{out.stderr}"
    except Exception:  # pragma: no cover
        return frozenset({"fade"})
    names = set(re.findall(r"^\s{2,}(\w+)\s+\d+\s+", text, flags=re.MULTILINE))
    names |= set(re.findall(r"\b(fade|dissolve|wipe\w+|slide\w+|smooth\w+|circle\w+|zoomin|hblur|pixelize|fadeblack|fadewhite|radial|distance|squeeze\w+)\b", text))
    return frozenset(names) or frozenset({"fade"})


@lru_cache(maxsize=1)
def has_filter(name: str = "") -> bool:  # pragma: no cover - convenience probe
    try:
        out = subprocess.run(
            [ffmpeg_path(), "-hide_banner", "-filters"],
            capture_output=True, text=True, timeout=30, check=False,
        ).stdout
    except Exception:
        return False
    return bool(re.search(rf"\s{re.escape(name)}\s", out))


@dataclass
class FFmpegResult:
    args: list[str]
    returncode: int
    stderr: str


_PROGRESS_TIME = re.compile(r"out_time_us=(\d+)")


def run_ffmpeg(
    args: Sequence[str],
    *,
    expected_duration: float | None = None,
    on_progress: ProgressCallback | None = None,
    timeout: int | None = None,
    cancel_check: Callable[[], bool] | None = None,
) -> FFmpegResult:
    """Run ffmpeg with `-progress` wired up. Raises RenderError on failure.

    `on_progress` receives 0.0..1.0 for this single invocation.
    """
    binary = ffmpeg_path()
    command = [binary, "-hide_banner", "-nostdin", "-loglevel", "error", "-y"]
    command += list(args)
    if on_progress and expected_duration:
        command += ["-progress", "pipe:2", "-nostats"]

    logger.debug("ffmpeg %s", " ".join(command[1:]))

    process = subprocess.Popen(
        command,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        stdin=subprocess.DEVNULL,
        text=True,
        shell=False,
        bufsize=1,
    )

    stderr_chunks: list[str] = []
    cancelled = threading.Event()

    def _pump() -> None:
        assert process.stderr is not None
        for line in process.stderr:
            stderr_chunks.append(line)
            if on_progress and expected_duration:
                match = _PROGRESS_TIME.search(line)
                if match:
                    seconds = int(match.group(1)) / 1_000_000
                    on_progress(max(0.0, min(1.0, seconds / max(expected_duration, 0.001))))
            if cancel_check and cancel_check():
                cancelled.set()
                process.terminate()
                return

    pump = threading.Thread(target=_pump, daemon=True)
    pump.start()

    try:
        process.wait(timeout=timeout or settings.render_timeout_seconds)
    except subprocess.TimeoutExpired:
        process.kill()
        pump.join(timeout=5)
        raise RenderError(
            "Video rendering timed out. Try a shorter video or fewer scenes."
        ) from None
    pump.join(timeout=10)

    stderr = "".join(stderr_chunks)[-8000:]
    if cancelled.is_set():
        raise RenderError("Rendering was cancelled.", code="render_cancelled")
    if process.returncode != 0:
        logger.error("ffmpeg failed (%s): %s", process.returncode, stderr)
        raise RenderError(
            "Video rendering failed. Try again, or simplify the scene that failed.",
            details=_summarise_ffmpeg_error(stderr),
        )
    if on_progress:
        on_progress(1.0)
    return FFmpegResult(args=command, returncode=process.returncode, stderr=stderr)


def _summarise_ffmpeg_error(stderr: str) -> str:
    """Pick the most informative lines out of ffmpeg's stderr for the API response."""
    lines = [line.strip() for line in stderr.splitlines() if line.strip()]
    interesting = [
        line for line in lines
        if any(token in line.lower() for token in ("error", "invalid", "no such", "failed", "unable"))
    ]
    return " | ".join((interesting or lines)[-4:])[:600]


def probe_duration(path: Path) -> float | None:
    """Media duration in seconds, or None when ffprobe is unavailable."""
    probe = ffprobe_path()
    if probe:
        try:
            out = subprocess.run(
                [probe, "-v", "error", "-show_entries", "format=duration",
                 "-of", "default=noprint_wrappers=1:nokey=1", str(path)],
                capture_output=True, text=True, timeout=60, check=False,
            ).stdout.strip()
            return float(out) if out else None
        except (ValueError, OSError, subprocess.SubprocessError):
            return None

    # No ffprobe (the imageio build ships ffmpeg only): read the duration ffmpeg
    # prints while decoding to null.
    try:
        result = subprocess.run(
            [ffmpeg_path(), "-hide_banner", "-nostdin", "-i", str(path),
             "-f", "null", "-"],
            capture_output=True, text=True, timeout=120, check=False,
        )
        match = re.search(r"Duration:\s*(\d+):(\d+):(\d+\.\d+)", result.stderr)
        if match:
            h, m, s = match.groups()
            return int(h) * 3600 + int(m) * 60 + float(s)
        match = re.search(r"time=(\d+):(\d+):(\d+\.\d+)", result.stderr)
        if match:
            h, m, s = match.groups()
            return int(h) * 3600 + int(m) * 60 + float(s)
    except (OSError, subprocess.SubprocessError):
        return None
    return None


#: Below these a file is a still image, not a clip — see `probe_video`.
MIN_CLIP_FRAMES = 2
MIN_CLIP_SECONDS = 0.2


@dataclass(frozen=True)
class VideoProbe:
    """What a decoder could actually read out of a file claiming to be a video."""

    duration: float
    width: int
    height: int


def probe_video(path: Path) -> VideoProbe | None:
    """Decode the file's header and return its real dimensions, or None.

    Uploads are trusted only after a decoder has agreed they are what they claim,
    exactly as images are re-decoded through Pillow. A container with no video
    stream — an MP3 renamed to .mp4, a crafted file — returns None here rather
    than reaching the filtergraph as a scene's `video_source`.
    """
    try:
        result = subprocess.run(
            [ffmpeg_path(), "-hide_banner", "-nostdin", "-i", str(path), "-f", "null", "-"],
            capture_output=True, text=True, timeout=120, check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return None

    stream = re.search(r"Stream #\d+:\d+.*?: Video: .*?(\d{2,5})x(\d{2,5})", result.stderr)
    if not stream:
        return None

    # A JPEG or PNG also decodes as a "video stream" — of exactly one frame. Counting
    # the frames ffmpeg actually decoded is what separates a clip from a still, and a
    # still smuggled in here would freeze the scene it was attached to.
    frames = re.findall(r"frame=\s*(\d+)", result.stderr)
    if not frames or int(frames[-1]) < MIN_CLIP_FRAMES:
        return None

    duration = probe_duration(path) or 0.0
    if duration < MIN_CLIP_SECONDS:
        return None
    return VideoProbe(duration=duration, width=int(stream.group(1)), height=int(stream.group(2)))


def extract_poster(video: Path, target: Path, *, at_seconds: float = 0.6) -> Path:
    """Grab a still from a rendered video to use as the project thumbnail."""
    target.parent.mkdir(parents=True, exist_ok=True)
    run_ffmpeg([
        "-ss", f"{max(0.0, at_seconds):.3f}",
        "-i", str(video),
        "-frames:v", "1",
        "-q:v", "3",
        str(target),
    ])
    return target


def concat_demuxer_file(paths: Iterable[Path], target: Path) -> Path:
    """Write a concat-demuxer list. Paths are quoted per the demuxer's own escaping."""
    lines = []
    for path in paths:
        escaped = str(path).replace("\\", "/").replace("'", r"'\''")
        lines.append(f"file '{escaped}'")
    target.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return target
