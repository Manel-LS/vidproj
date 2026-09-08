"""The FFmpeg rendering pipeline (requirement 15).

    images -> scene animation -> transitions -> text -> audio -> voice-over -> MP4

Implemented as three passes so that failures are attributable and progress is
reportable:

  A. one intermediate clip per scene (animation + its text layers)
  B. the transition chain (xfade / concat) encoded to the final video settings
  C. the audio graph muxed in with `-c:v copy`

Only pass B re-encodes at final quality, so text and motion survive exactly one
generation of compression.
"""
from __future__ import annotations

import shutil
from dataclasses import dataclass
from pathlib import Path

from app.core.config import settings
from app.core.errors import RenderError
from app.core.logging import get_logger
from app.domain.animation import Motion, build_motion
from app.domain.enums import AnimationType, TransitionType
from app.domain.plan import PlanScene, VideoPlan
from app.infrastructure.imaging.text_renderer import TextLayerAsset, render_text_layer
from app.infrastructure.render.base import (
    ProgressReporter,
    RenderEngine,
    RenderRequest,
    RenderResult,
)
from app.infrastructure.render.ffmpeg import (
    FFmpegNotAvailableError,
    extract_poster,
    ffmpeg_path,
    probe_duration,
    run_ffmpeg,
)
from app.infrastructure.render.filters import (
    music_filter_chain,
    overlay_filter,
    rotate_filter,
    voice_filter_chain,
    xfade_filter,
    zoompan_filter,
)
from app.infrastructure.render.image_prep import prepare_scene_image, solid_frame

logger = get_logger(__name__)

# Progress budget per stage, as cumulative percentages.
_STAGE_PREPARE = (0, 6)
_STAGE_SCENES = (6, 62)
_STAGE_TRANSITIONS = (62, 84)
_STAGE_AUDIO = (84, 96)
_STAGE_FINALISE = (96, 100)

_ROTATION_OVERSCAN = 1.12


def _even(value: float) -> int:
    return max(2, int(round(value / 2)) * 2)


@dataclass
class _SceneAssets:
    scene: PlanScene
    index: int
    image_path: Path
    motion: Motion
    frames: int
    duration: float
    text_layers: list[TextLayerAsset]
    clip_path: Path
    video_source: Path | None = None  # an AI Motion clip, when one was generated


class FFmpegRenderEngine(RenderEngine):
    name = "ffmpeg"

    def is_available(self) -> bool:
        try:
            ffmpeg_path()
            return True
        except FFmpegNotAvailableError:
            return False

    # -- public API ----------------------------------------------------------

    def render(self, request: RenderRequest, on_progress: ProgressReporter) -> RenderResult:
        plan = request.plan
        width, height = plan.dimensions
        work = Path(request.work_dir)
        work.mkdir(parents=True, exist_ok=True)

        self._check_cancelled(request)
        on_progress(_STAGE_PREPARE[0], "Preparing images")
        assets = self._prepare_scenes(request, width, height, on_progress)

        self._check_cancelled(request)
        self._render_scene_clips(request, assets, width, height, on_progress)

        self._check_cancelled(request)
        silent_video = work / "video.mp4"
        self._compose_transitions(request, assets, silent_video, on_progress)

        self._check_cancelled(request)
        final_video = Path(request.output_path)
        final_video.parent.mkdir(parents=True, exist_ok=True)
        self._mux_audio(request, silent_video, final_video, on_progress)

        on_progress(_STAGE_FINALISE[0], "Finalising")
        poster = None
        if request.poster_path:
            try:
                poster = extract_poster(final_video, Path(request.poster_path), at_seconds=min(0.8, plan.total_duration / 3))
            except RenderError:  # a missing poster must not fail an otherwise good render
                logger.warning("Poster extraction failed for %s", final_video)

        duration = probe_duration(final_video) or plan.total_duration
        on_progress(100, "Completed")
        return RenderResult(
            video_path=final_video,
            poster_path=poster,
            duration=round(duration, 3),
            width=width,
            height=height,
            size_bytes=final_video.stat().st_size,
        )

    # -- stage A: per-scene assets -------------------------------------------

    def _prepare_scenes(
        self, request: RenderRequest, width: int, height: int, on_progress: ProgressReporter
    ) -> list[_SceneAssets]:
        plan = request.plan
        work = Path(request.work_dir)
        images_dir = work / "images"
        text_dir = work / "text"
        assets: list[_SceneAssets] = []

        for index, scene in enumerate(plan.scenes):
            self._check_cancelled(request)
            duration = float(scene.duration)
            frames = max(2, int(round(duration * plan.fps)))

            motion = build_motion(
                scene.animation,
                intensity=scene.animation_intensity,
                focus=scene.focus,
            )

            video_source: Path | None = None
            if scene.ai_motion and scene.ai_motion.generated_media_id:
                video_source = request.media_paths.get(scene.ai_motion.generated_media_id)

            source = request.media_paths.get(scene.media_id or "")
            target = images_dir / f"scene-{index:03d}.jpg"
            if video_source is not None:
                image_path = target
                solid_frame(image_path, width=width, height=height, color=scene.background_color)
            elif source is None or not Path(source).is_file():
                # A CTA/outro scene legitimately has no image of its own; reuse the
                # previous scene's frame so the video never flashes black.
                if assets:
                    image_path = assets[-1].image_path
                else:
                    image_path = solid_frame(
                        target, width=_even(width * settings.render_supersample),
                        height=_even(height * settings.render_supersample),
                        color=scene.background_color,
                    )
            else:
                image_path, new_focus = prepare_scene_image(
                    Path(source),
                    target,
                    frame_width=width,
                    frame_height=height,
                    supersample=settings.render_supersample,
                    focus=scene.focus,
                    max_zoom=motion.max_zoom,
                )
                motion = build_motion(
                    scene.animation, intensity=scene.animation_intensity, focus=new_focus
                )

            layers: list[TextLayerAsset] = []
            for text_index, overlay in enumerate(scene.texts):
                layers.append(
                    render_text_layer(
                        overlay,
                        frame_size=(width, height),
                        output_dir=text_dir / f"scene-{index:03d}",
                        layer_id=f"layer-{text_index}",
                        fps=plan.fps,
                        scene_duration=duration,
                    )
                )

            assets.append(
                _SceneAssets(
                    scene=scene,
                    index=index,
                    image_path=image_path,
                    motion=motion,
                    frames=frames,
                    duration=duration,
                    text_layers=layers,
                    clip_path=work / "clips" / f"scene-{index:03d}.mp4",
                    video_source=video_source,
                )
            )
            self._report_span(on_progress, _STAGE_PREPARE, (index + 1) / len(plan.scenes), "Preparing images")

        return assets

    # -- stage A2: encode each scene -----------------------------------------

    def _render_scene_clips(
        self,
        request: RenderRequest,
        assets: list[_SceneAssets],
        width: int,
        height: int,
        on_progress: ProgressReporter,
    ) -> None:
        plan = request.plan
        for asset in assets:
            self._check_cancelled(request)
            asset.clip_path.parent.mkdir(parents=True, exist_ok=True)
            args, filter_complex = self._scene_command(asset, plan, width, height)
            args += ["-filter_complex", filter_complex, "-map", "[vout]"]
            args += [
                "-frames:v", str(asset.frames),
                "-r", str(plan.fps),
                "-c:v", "libx264",
                "-preset", "veryfast",
                "-crf", "16",
                "-pix_fmt", "yuv420p",
                "-an",
                str(asset.clip_path),
            ]

            base = (asset.index) / max(1, len(assets))
            step = 1 / max(1, len(assets))
            run_ffmpeg(
                args,
                expected_duration=asset.duration,
                on_progress=lambda fraction, b=base, s=step: self._report_span(
                    on_progress, _STAGE_SCENES, b + s * fraction,
                    f"Animating scene {asset.index + 1} of {len(assets)}",
                ),
                cancel_check=request.cancel_check,
            )

    def _scene_command(
        self, asset: _SceneAssets, plan: VideoPlan, width: int, height: int
    ) -> tuple[list[str], str]:
        """Build the argv and filtergraph for one scene."""
        args: list[str] = []
        chains: list[str] = []
        fps = plan.fps

        if asset.video_source is not None:
            # AI Motion: the provider produced a clip; fit it to the canvas and
            # trim/pad it to the scene's duration.
            args += ["-i", str(asset.video_source)]
            chains.append(
                f"[0:v]scale={width}:{height}:force_original_aspect_ratio=increase,"
                f"crop={width}:{height},fps={fps},"
                f"tpad=stop_mode=clone:stop_duration={asset.duration:.3f},"
                f"trim=duration={asset.duration:.3f},setpts=PTS-STARTPTS,"
                f"format=rgba,setsar=1[base]"
            )
        else:
            args += [
                "-loop", "1",
                "-framerate", str(fps),
                "-t", f"{asset.duration:.3f}",
                "-i", str(asset.image_path),
            ]
            if asset.motion.needs_rotation:
                over_w, over_h = _even(width * _ROTATION_OVERSCAN), _even(height * _ROTATION_OVERSCAN)
                chains.append(
                    f"[0:v]{zoompan_filter(asset.motion, frames=asset.frames, out_w=over_w, out_h=over_h, fps=fps)},"
                    f"{rotate_filter(asset.motion, duration=asset.duration)},"
                    f"crop={width}:{height},format=rgba,setsar=1[base]"
                )
            else:
                chains.append(
                    f"[0:v]{zoompan_filter(asset.motion, frames=asset.frames, out_w=width, out_h=height, fps=fps)},"
                    f"format=rgba,setsar=1[base]"
                )

        current = "base"
        for layer_index, layer in enumerate(asset.text_layers):
            input_index = layer_index + 1
            if layer.is_sequence:
                args += ["-framerate", str(layer.fps), "-i", layer.sequence_pattern]  # type: ignore[list-item]
            else:
                args += [
                    "-loop", "1",
                    "-framerate", str(layer.fps),
                    "-t", f"{max(layer.duration, 0.05):.3f}",
                    "-i", str(layer.path),
                ]
            label_in = f"txt{layer_index}"
            chains.append(
                f"[{input_index}:v]format=rgba,setpts=PTS-STARTPTS+{layer.start:.3f}/TB[{label_in}]"
            )
            label_out = f"ov{layer_index}"
            chains.append(
                f"[{current}][{label_in}]"
                + overlay_filter(
                    x=layer.x,
                    y=layer.y,
                    start=layer.start,
                    end=min(layer.end, asset.duration),
                    drift_px=-asset.motion.parallax_px
                    if asset.scene.animation is AnimationType.PARALLAX
                    else 0.0,
                )
                + f"[{label_out}]"
            )
            current = label_out

        chains.append(f"[{current}]format=yuv420p[vout]")
        return args, ";".join(chains)

    # -- stage B: transitions ------------------------------------------------

    def _compose_transitions(
        self,
        request: RenderRequest,
        assets: list[_SceneAssets],
        target: Path,
        on_progress: ProgressReporter,
    ) -> None:
        plan = request.plan
        on_progress(_STAGE_TRANSITIONS[0], "Applying transitions")

        if len(assets) == 1:
            shutil.copyfile(assets[0].clip_path, target)
            self._report_span(on_progress, _STAGE_TRANSITIONS, 1.0, "Applying transitions")
            return

        args: list[str] = []
        for asset in assets:
            args += ["-i", str(asset.clip_path)]

        starts = plan.scene_start_times()
        chains: list[str] = []
        current = "0:v"
        for index in range(1, len(assets)):
            scene = plan.scenes[index]
            duration = plan.effective_transition_duration(index)
            label = f"x{index}"
            if scene.transition is TransitionType.NONE or duration <= 0:
                chains.append(f"[{current}][{index}:v]concat=n=2:v=1:a=0[{label}]")
            else:
                chains.append(
                    f"[{current}][{index}:v]"
                    + xfade_filter(scene.transition, duration=duration, offset=starts[index])
                    + f"[{label}]"
                )
            current = label
        chains.append(f"[{current}]format=yuv420p,fps={plan.fps}[vout]")

        args += ["-filter_complex", ";".join(chains), "-map", "[vout]"]
        args += self._video_encode_args(plan)
        args += [str(target)]

        run_ffmpeg(
            args,
            expected_duration=plan.total_duration,
            on_progress=lambda fraction: self._report_span(
                on_progress, _STAGE_TRANSITIONS, fraction, "Applying transitions"
            ),
            cancel_check=request.cancel_check,
        )

    def _video_encode_args(self, plan: VideoPlan) -> list[str]:
        args = [
            "-c:v", "libx264",
            "-profile:v", "high",
            "-level", "4.2",
            "-preset", settings.render_preset,
            "-crf", str(settings.render_crf),
            "-pix_fmt", "yuv420p",
            "-g", str(plan.fps * 2),
            "-movflags", "+faststart",
        ]
        if settings.render_threads:
            args += ["-threads", str(settings.render_threads)]
        return args

    # -- stage C: audio ------------------------------------------------------

    def _mux_audio(
        self,
        request: RenderRequest,
        video: Path,
        target: Path,
        on_progress: ProgressReporter,
    ) -> None:
        plan = request.plan
        on_progress(_STAGE_AUDIO[0], "Mixing audio")
        total = plan.total_duration

        music_path: Path | None = None
        if plan.audio and plan.audio.media_id:
            music_path = request.media_paths.get(plan.audio.media_id)
            if music_path is not None and not Path(music_path).is_file():
                music_path = None

        voice_path: Path | None = None
        if plan.voiceover and plan.voiceover.enabled and plan.voiceover.media_id:
            voice_path = request.media_paths.get(plan.voiceover.media_id)
            if voice_path is not None and not Path(voice_path).is_file():
                voice_path = None

        args: list[str] = ["-i", str(video)]
        chains: list[str] = []
        mix_labels: list[str] = []
        next_index = 1

        if music_path is not None:
            # `-stream_loop -1` lets a short track cover a long video; `atrim` in the
            # filter chain cuts it back to the exact video length.
            if plan.audio and plan.audio.loop:
                args += ["-stream_loop", "-1"]
            args += ["-i", str(music_path)]
            volume = (plan.audio.volume if plan.audio else 0.7)
            if voice_path is not None and plan.voiceover:
                volume *= plan.voiceover.duck_music_to
            chains.append(
                f"[{next_index}:a]"
                + music_filter_chain(
                    total_duration=total,
                    volume=volume,
                    fade_in=plan.audio.fade_in if plan.audio else 0.6,
                    fade_out=plan.audio.fade_out if plan.audio else 1.0,
                    start_offset=plan.audio.start_offset if plan.audio else 0.0,
                )
                + "[music]"
            )
            mix_labels.append("music")
            next_index += 1

        if voice_path is not None:
            args += ["-i", str(voice_path)]
            chains.append(
                f"[{next_index}:a]"
                + voice_filter_chain(total_duration=total, volume=plan.voiceover.volume)
                + "[voice]"
            )
            mix_labels.append("voice")
            next_index += 1

        if not mix_labels:
            # Always ship an audio track: several platforms reject silent-track-less MP4s.
            args += ["-f", "lavfi", "-t", f"{total:.3f}", "-i", "anullsrc=r=48000:cl=stereo"]
            mix_labels.append(f"{next_index}:a")
            chains.append(f"[{next_index}:a]anull[silence]")
            mix_labels = ["silence"]

        if len(mix_labels) == 1:
            chains.append(f"[{mix_labels[0]}]aformat=sample_fmts=fltp:sample_rates=48000:channel_layouts=stereo[aout]")
        else:
            inputs = "".join(f"[{label}]" for label in mix_labels)
            chains.append(
                f"{inputs}amix=inputs={len(mix_labels)}:duration=longest:normalize=0,"
                f"alimiter=limit=0.95,"
                f"aformat=sample_fmts=fltp:sample_rates=48000:channel_layouts=stereo[aout]"
            )

        args += [
            "-filter_complex", ";".join(chains),
            "-map", "0:v",
            "-map", "[aout]",
            "-c:v", "copy",
            "-c:a", "aac",
            "-b:a", "192k",
            "-ar", "48000",
            "-t", f"{total:.3f}",
            "-movflags", "+faststart",
            str(target),
        ]

        run_ffmpeg(
            args,
            expected_duration=total,
            on_progress=lambda fraction: self._report_span(
                on_progress, _STAGE_AUDIO, fraction, "Mixing audio"
            ),
            cancel_check=request.cancel_check,
        )

    # -- helpers -------------------------------------------------------------

    @staticmethod
    def _report_span(
        on_progress: ProgressReporter, span: tuple[int, int], fraction: float, stage: str
    ) -> None:
        low, high = span
        value = int(low + (high - low) * max(0.0, min(1.0, fraction)))
        on_progress(value, stage)

    @staticmethod
    def _check_cancelled(request: RenderRequest) -> None:
        if request.cancel_check():
            raise RenderError("Rendering was cancelled.", code="render_cancelled")
