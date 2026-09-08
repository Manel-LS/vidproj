"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import {
  Maximize2,
  Pause,
  Play,
  RotateCcw,
  Volume2,
  VolumeX,
} from "lucide-react";
import { Button } from "@/components/ui/Button";
import type { AudioTrack, Scene, VideoFormat, VoiceOver } from "@/lib/api/types";
import { PreviewPlayer } from "@/lib/video/player";
import { FORMAT_DIMENSIONS, buildTimeline, formatTime } from "@/lib/video/timeline";
import { useEditorStore } from "@/lib/store/editor";
import { cn } from "@/lib/utils";

/**
 * The preview.
 *
 * A canvas driven by `PreviewPlayer`, which reimplements the render pipeline in the
 * browser: the same animation viewports, the same transitions, the same text layout.
 * React owns the chrome; the player owns the frame loop.
 */
export function PreviewStage({
  scenes,
  format,
  audio,
  voiceOver,
  className,
}: {
  scenes: Scene[];
  format: VideoFormat;
  audio: AudioTrack | null;
  voiceOver: VoiceOver | null;
  className?: string;
}) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const playerRef = useRef<PreviewPlayer | null>(null);
  const containerRef = useRef<HTMLDivElement>(null);

  const { time, playing, muted, volume, setTime, setPlaying, setMuted, setVolume, select } =
    useEditorStore();
  const [ready, setReady] = useState(false);

  const [width, height] = FORMAT_DIMENSIONS[format] ?? FORMAT_DIMENSIONS["9:16"];
  const timeline = buildTimeline(scenes);
  const duration = timeline.length ? Math.max(...timeline.map((item) => item.end)) : 0;

  // Create the player once per canvas.
  useEffect(() => {
    if (!canvasRef.current) return;
    const player = new PreviewPlayer({
      canvas: canvasRef.current,
      frameWidth: width,
      frameHeight: height,
      onTime: (value) => setTime(value),
      onPlayingChange: (value) => setPlaying(value),
    });
    playerRef.current = player;
    setReady(true);
    return () => {
      player.destroy();
      playerRef.current = null;
    };
    // The canvas element is stable for the life of this component.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    playerRef.current?.setFrameSize(width, height);
  }, [width, height]);

  useEffect(() => {
    playerRef.current?.setScenes(scenes);
  }, [scenes]);

  useEffect(() => {
    playerRef.current?.setAudio(audio?.media?.url ?? null, {
      volume: audio?.volume ?? 0.7,
      startOffset: audio?.start_offset ?? 0,
    });
  }, [audio?.media?.url, audio?.volume, audio?.start_offset]);

  useEffect(() => {
    const url = voiceOver?.enabled ? (voiceOver.media?.url ?? null) : null;
    playerRef.current?.setVoiceOver(url, voiceOver?.volume ?? 1);
  }, [voiceOver]);

  useEffect(() => {
    playerRef.current?.setMuted(muted);
  }, [muted]);

  useEffect(() => {
    playerRef.current?.setVolume(volume);
  }, [volume]);

  // Keep the selected scene in step with the playhead.
  useEffect(() => {
    const active = timeline.find((item) => time >= item.start && time < item.end);
    if (active) {
      const { selectedSceneId } = useEditorStore.getState();
      if (playing && selectedSceneId !== active.scene.id) select(active.scene.id);
    }
  }, [time, playing, timeline, select]);

  const seek = useCallback((value: number) => playerRef.current?.seek(value), []);
  const toggle = useCallback(() => playerRef.current?.toggle(), []);

  // Space plays/pauses, arrows scrub — the shortcuts every editor has.
  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent) => {
      const target = event.target as HTMLElement | null;
      if (target && ["INPUT", "TEXTAREA", "SELECT"].includes(target.tagName)) return;
      if (target?.isContentEditable) return;

      if (event.code === "Space") {
        event.preventDefault();
        toggle();
      } else if (event.code === "ArrowLeft") {
        event.preventDefault();
        seek(Math.max(0, time - (event.shiftKey ? 1 : 1 / 30)));
      } else if (event.code === "ArrowRight") {
        event.preventDefault();
        seek(Math.min(duration, time + (event.shiftKey ? 1 : 1 / 30)));
      } else if (event.code === "KeyM") {
        setMuted(!muted);
      }
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [toggle, seek, time, duration, muted, setMuted]);

  function requestFullscreen() {
    const node = containerRef.current;
    if (!node) return;
    if (document.fullscreenElement) void document.exitFullscreen();
    else void node.requestFullscreen?.().catch(() => undefined);
  }

  return (
    <div className={cn("flex min-h-0 flex-col items-center gap-3", className)}>
      <div
        ref={containerRef}
        className="relative flex min-h-0 flex-1 items-center justify-center"
      >
        <canvas
          ref={canvasRef}
          width={width}
          height={height}
          className="h-full max-h-full w-auto max-w-full rounded-xl border border-line bg-black shadow-lifted"
          style={{ aspectRatio: `${width} / ${height}` }}
          onClick={toggle}
          role="img"
          aria-label="Video preview"
        />

        {!playing && ready ? (
          <button
            type="button"
            onClick={toggle}
            className="absolute inset-0 flex items-center justify-center"
            aria-label="Play preview"
          >
            <span className="flex h-14 w-14 items-center justify-center rounded-full bg-black/55 backdrop-blur transition-transform hover:scale-105">
              <Play className="ml-1 h-6 w-6 text-white" aria-hidden />
            </span>
          </button>
        ) : null}
      </div>

      {/* Transport */}
      <div className="flex w-full max-w-md items-center gap-2.5 rounded-xl border border-line bg-surface px-3 py-2">
        <Button variant="ghost" size="icon" onClick={toggle} aria-label={playing ? "Pause" : "Play"}>
          {playing ? <Pause className="h-4 w-4" /> : <Play className="h-4 w-4" />}
        </Button>
        <Button
          variant="ghost"
          size="icon"
          onClick={() => playerRef.current?.restart()}
          aria-label="Restart"
        >
          <RotateCcw className="h-4 w-4" />
        </Button>

        <span className="font-mono text-2xs tabular-nums text-muted">{formatTime(time)}</span>

        <input
          type="range"
          min={0}
          max={Math.max(duration, 0.01)}
          step={0.01}
          value={time}
          onChange={(event) => seek(Number(event.target.value))}
          aria-label="Playhead"
          className="h-1 flex-1 cursor-pointer appearance-none rounded-full outline-none
            [&::-webkit-slider-thumb]:h-3 [&::-webkit-slider-thumb]:w-3
            [&::-webkit-slider-thumb]:appearance-none [&::-webkit-slider-thumb]:rounded-full
            [&::-webkit-slider-thumb]:bg-accent"
          style={{
            background: `linear-gradient(to right, rgb(var(--accent)) ${
              duration ? (time / duration) * 100 : 0
            }%, rgb(var(--line)) ${duration ? (time / duration) * 100 : 0}%)`,
          }}
        />

        <span className="font-mono text-2xs tabular-nums text-faint">{formatTime(duration)}</span>

        <Button
          variant="ghost"
          size="icon"
          onClick={() => setMuted(!muted)}
          aria-label={muted ? "Unmute" : "Mute"}
        >
          {muted ? <VolumeX className="h-4 w-4" /> : <Volume2 className="h-4 w-4" />}
        </Button>
        <input
          type="range"
          min={0}
          max={1}
          step={0.05}
          value={volume}
          onChange={(event) => setVolume(Number(event.target.value))}
          aria-label="Volume"
          className="hidden h-1 w-16 cursor-pointer appearance-none rounded-full bg-line outline-none sm:block
            [&::-webkit-slider-thumb]:h-2.5 [&::-webkit-slider-thumb]:w-2.5
            [&::-webkit-slider-thumb]:appearance-none [&::-webkit-slider-thumb]:rounded-full
            [&::-webkit-slider-thumb]:bg-muted"
        />
        <Button variant="ghost" size="icon" onClick={requestFullscreen} aria-label="Fullscreen">
          <Maximize2 className="h-4 w-4" />
        </Button>
      </div>
    </div>
  );
}
