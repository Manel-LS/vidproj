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
from dataclasses import dataclass, field
from pathlib import Path

from app.core.config import settings
from app.core.errors import RenderError
from app.core.logging import get_logger
from app.domain.animation import Motion, build_motion
from app.domain.enums import AnimationType, TransitionType
from app.domain.plan import PlanScene, VideoPlan
from app.domain.subtitles import (
    build_cues,
    cues_from_sentences,
    get_subtitle_preset,
    parse_words,
)
from app.infrastructure.depth.base import DepthUnavailable
from app.infrastructure.depth.factory import get_depth_provider
from app.infrastructure.imaging.parallax import ParallaxLayer, build_parallax_layers
from app.infrastructure.imaging.subtitle_renderer import (
    SubtitleTrackAsset,
    render_subtitle_track,
)
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
    """H.264 needs even dimensions; odd ones are rejected by the encoder."""
    return max(2, int(round(value / 2)) * 2)


#: How much the planes separate, as a fraction of the base move.
#:
#: Applied to the **zoom**, not to the pan. The pan cannot carry it: the camera
#: paths this engine builds are already clamped to the edge of the source
#: (`span = min(0.10 * intensity, 0.5 - half)`), so asking a near plane to travel
#: further is silently clamped straight back — measured, and the effect was
#: invisible until this moved to zoom. Zoom has headroom, and a plane that
#: magnifies more also gains pan headroom as a side effect.
#:
#: 0.30 puts roughly six percent between the nearest and furthest plane by the end
#: of a shot. Below ~0.15 nobody sees it; above ~0.5 the planes visibly slide.
PARALLAX_SEPARATION = 0.30


def _plane_motion(motion: Motion, depth_offset: float) -> Motion:
    """The scene's camera move, differentiated for one depth plane.

    `depth_offset` is the plane's depth minus the mean, so it is negative for
    planes behind the subject and positive for those in front.

    Both ends are *not* scaled: the start is left alone so every plane opens on
    exactly the original photograph, and they separate as the shot progresses.
    Offsetting them at frame one would show the picture already broken into
    slabs, which reads as a printing fault rather than as depth.
    """
    import dataclasses

    factor = 1.0 + PARALLAX_SEPARATION * depth_offset
    start, end = motion.start, motion.end
    scaled_end = dataclasses.replace(
        end,
        # A near plane ends larger than it began, a far plane smaller. This is the
        # separation; the pan below only adds to it where the crop allows.
        zoom=max(1.0, start.zoom * factor),
        cx=start.cx + (end.cx - start.cx) * factor,
        cy=start.cy + (end.cy - start.cy) * factor,
    )
    return dataclasses.replace(motion, end=scaled_end)


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
    #: Depth planes for true 2.5D parallax. Empty means the scene falls back to
    #: the flat camera move, which is what every scene did before depth existed.
    parallax_layers: list[ParallaxLayer] = field(default_factory=list)


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

            parallax_layers = self._prepare_parallax(scene, image_path, work, index)

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
                    parallax_layers=parallax_layers,
                )
            )
            self._report_span(on_progress, _STAGE_PREPARE, (index + 1) / len(plan.scenes), "Preparing images")

        return assets


    def _prepare_parallax(
        self, scene: PlanScene, image_path: Path, work: Path, index: int
    ) -> list[ParallaxLayer]:
        """Depth planes for a PARALLAX scene, when an estimator is configured.

        Every failure here returns an empty list rather than raising. The scene
        then animates exactly as it did before depth existed — a flatter shot is a
        lesser result, a failed render is no result at all.

        The depth is read from the *prepared* frame, which is the cover-cropped
        photograph and nothing else. Text overlays are composited later, and a
        model shown a frame that already carries them reads the caption panels as
        physical objects and peels them off the picture.
        """
        if scene.animation is not AnimationType.PARALLAX:
            return []

        provider = get_depth_provider()
        if not provider.is_available():
            return []

        try:
            depth = provider.estimate(image_path)
            return build_parallax_layers(
                image_path, depth, work / "parallax" / f"scene-{index:03d}"
            )
        except DepthUnavailable as exc:
            logger.info("Parallax unavailable for scene %s: %s", index + 1, exc)
        except Exception:  # noqa: BLE001
            logger.exception("Parallax preparation failed for scene %s", index + 1)
        return []

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
        elif asset.parallax_layers:
            # True 2.5D: one input per depth plane, each sampled through its own
            # camera window. Planes nearer the lens travel further, which is the
            # entire effect — the picture stops being a postcard being pushed
            # around and starts being a space the camera moves through.
            args, chains = self._parallax_inputs(asset, plan, width, height)
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
        # Text inputs come after every input the base consumed: one image, one clip,
        # or one per depth plane.
        base_inputs = max(1, len(asset.parallax_layers)) if asset.video_source is None else 1
        for layer_index, layer in enumerate(asset.text_layers):
            input_index = layer_index + base_inputs
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


    def _parallax_inputs(
        self, asset: _SceneAssets, plan: VideoPlan, width: int, height: int
    ) -> tuple[list[str], list[str]]:
        """One zoompan per depth plane, composited furthest first.

        The differential is applied to the camera's *travel*, not to the plane's
        position: each plane runs the same move scaled by how near it is, so they
        start aligned and separate as the shot progresses. Displacing the planes
        outright would show them misregistered on the very first frame, which reads
        as a printing error rather than as depth.

        Nothing can expose the frame edge either, because every plane is sampled by
        its own zoompan and zoompan cannot sample outside its input.
        """
        args: list[str] = []
        chains: list[str] = []
        fps = plan.fps
        layers = asset.parallax_layers
        mean_depth = sum(layer.depth for layer in layers) / len(layers)

        current = ""
        for index, layer in enumerate(layers):
            args += [
                "-loop", "1",
                "-framerate", str(fps),
                "-t", f"{asset.duration:.3f}",
                "-i", str(layer.path),
            ]
            motion = _plane_motion(asset.motion, layer.depth - mean_depth)
            label = f"plane{index}"
            chains.append(
                f"[{index}:v]"
                f"{zoompan_filter(motion, frames=asset.frames, out_w=width, out_h=height, fps=fps)},"
                f"format=rgba,setsar=1[{label}]"
            )
            if not current:
                current = label
                continue
            merged = f"stack{index}"
            chains.append(f"[{current}][{label}]overlay=0:0:format=auto[{merged}]")
            current = merged

        chains.append(f"[{current}]format=rgba,setsar=1[base]")
        return args, chains

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

        # Subtitles are burned in here rather than in a pass of their own. This is
        # the only stage that encodes at final quality, and a separate burn-in pass
        # would put the whole picture through a second generation of compression to
        # add a strip of text.
        subtitles = self._prepare_subtitles(request, on_progress)

        if len(assets) == 1 and subtitles is None:
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

        if subtitles is not None:
            args += ["-framerate", str(subtitles.fps), "-i", subtitles.sequence_pattern]
            index = len(assets)
            chains.append(f"[{index}:v]format=rgba,setpts=PTS-STARTPTS[subs]")
            chains.append(
                f"[{current}][subs]overlay=x={subtitles.x}:y={subtitles.y}"
                ":eof_action=pass:shortest=0[subbed]"
            )
            current = "subbed"

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

    # -- stage B2: subtitles -------------------------------------------------

    def _prepare_subtitles(
        self, request: RenderRequest, on_progress: ProgressReporter
    ) -> SubtitleTrackAsset | None:
        """Rasterise the subtitle band, or return None when there is none to draw.

        Falls back to whole-line cards when the provider reported no word timings.
        That is a visible difference — no word is highlighted — and it is the right
        one: highlighting a word whose start time was guessed is worse than not
        highlighting at all.
        """
        plan = request.plan
        preset = get_subtitle_preset(plan.subtitles.style)
        if preset is None:
            return None

        voice = plan.voiceover
        if voice is None or not voice.enabled:
            return None

        words = parse_words([entry.model_dump() for entry in voice.word_timings])
        if words:
            cues = build_cues(
                words,
                max_chars=preset.max_chars,
                max_words=preset.max_words,
                limit=plan.total_duration,
            )
        else:
            cues = cues_from_sentences(voice.script, plan.total_duration)
        if not cues:
            return None

        on_progress(_STAGE_TRANSITIONS[0], "Adding subtitles")
        width, height = plan.dimensions
        try:
            return render_subtitle_track(
                cues,
                preset,
                frame_size=(width, height),
                fps=plan.fps,
                total_duration=plan.total_duration,
                output_dir=Path(request.work_dir) / "subtitles",
            )
        except Exception:  # noqa: BLE001
            # A video without subtitles is a lesser result than one with them; a
            # video that failed to render is no result at all.
            logger.exception("Subtitle rasterisation failed; rendering without subtitles")
            return None

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
