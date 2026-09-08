/**
 * The preview player.
 *
 * Draws the same frame the renderer would produce: the cover-cropped image sampled
 * through the animation viewport, the transition between the outgoing and incoming
 * scene, then the text layers. Audio is a plain `<audio>` element kept in step with
 * the playhead.
 *
 * It is framework-free on purpose — a React component (`PreviewStage`) owns the
 * canvas and drives this class, which keeps the render loop out of React's way.
 */
import type { Scene, SubtitleStyleKey, TransitionType, WordTiming } from "@/lib/api/types";
import { buildMotion, rotationAt, sourceRect, viewportAt } from "./animation";
import { drawTextOverlay } from "./text";
import {
  activeIndex,
  buildCues,
  cueAt,
  cuesFromSentences,
  getSubtitlePreset,
  parseWords,
  type SubtitleCue,
  type SubtitlePreset,
} from "./subtitles";
import { buildTimeline, frameAt, totalDuration, type TimelineScene } from "./timeline";

export interface PlayerOptions {
  canvas: HTMLCanvasElement;
  frameWidth: number;
  frameHeight: number;
  onTime?: (time: number) => void;
  onEnded?: () => void;
  onPlayingChange?: (playing: boolean) => void;
}

type ImageCache = Map<string, HTMLImageElement>;

export class PreviewPlayer {
  private canvas: HTMLCanvasElement;
  private ctx: CanvasRenderingContext2D;
  private frameWidth: number;
  private frameHeight: number;

  private timeline: TimelineScene[] = [];
  private duration = 0;
  private images: ImageCache = new Map();
  private pending = new Set<string>();

  private playing = false;
  private time = 0;
  private rafId: number | null = null;
  private lastTick = 0;

  private audio: HTMLAudioElement | null = null;
  private voice: HTMLAudioElement | null = null;
  private muted = false;
  private volume = 1;

  private subtitlePreset: SubtitlePreset | null = null;
  private cues: SubtitleCue[] = [];

  private onTime?: (time: number) => void;
  private onEnded?: () => void;
  private onPlayingChange?: (playing: boolean) => void;

  constructor(options: PlayerOptions) {
    this.canvas = options.canvas;
    const context = options.canvas.getContext("2d", { alpha: false });
    if (!context) throw new Error("This browser cannot provide a 2D canvas context.");
    this.ctx = context;
    this.frameWidth = options.frameWidth;
    this.frameHeight = options.frameHeight;
    this.onTime = options.onTime;
    this.onEnded = options.onEnded;
    this.onPlayingChange = options.onPlayingChange;

    this.canvas.width = options.frameWidth;
    this.canvas.height = options.frameHeight;
  }

  // -------------------------------------------------------------- content --

  setFrameSize(width: number, height: number) {
    this.frameWidth = width;
    this.frameHeight = height;
    this.canvas.width = width;
    this.canvas.height = height;
    this.draw();
  }

  setScenes(scenes: Scene[]) {
    this.timeline = buildTimeline(scenes);
    this.duration = totalDuration(scenes);
    if (this.time > this.duration) this.seek(this.duration);
    this.preload(scenes);
    this.draw();
  }

  /**
   * The subtitle band, built from the same numbers the renderer uses.
   *
   * Cues are computed once here rather than per frame: the grouping does not
   * depend on the playhead, and redoing it sixty times a second would be the one
   * expensive thing in an otherwise cheap loop.
   */
  setSubtitles(
    style: SubtitleStyleKey | undefined,
    words: WordTiming[] | undefined,
    script = "",
  ) {
    this.subtitlePreset = getSubtitlePreset(style);
    if (!this.subtitlePreset) {
      this.cues = [];
      this.draw();
      return;
    }
    const parsed = parseWords(words);
    this.cues = parsed.length
      ? buildCues(parsed, {
          maxChars: this.subtitlePreset.maxChars,
          maxWords: this.subtitlePreset.maxWords,
          limit: this.duration || undefined,
        })
      : cuesFromSentences(script, this.duration);
    this.draw();
  }

  setAudio(url: string | null, options: { volume?: number; startOffset?: number } = {}) {
    if (!url) {
      this.audio?.pause();
      this.audio = null;
      return;
    }
    if (this.audio?.dataset.src !== url) {
      this.audio?.pause();
      const element = new Audio(url);
      element.dataset.src = url;
      element.preload = "auto";
      element.crossOrigin = "anonymous";
      this.audio = element;
    }
    if (this.audio) {
      this.audio.volume = Math.max(0, Math.min(1, (options.volume ?? 0.7) * this.volume));
      this.audio.muted = this.muted;
      this.audio.dataset.offset = String(options.startOffset ?? 0);
    }
  }

  setVoiceOver(url: string | null, volume = 1) {
    if (!url) {
      this.voice?.pause();
      this.voice = null;
      return;
    }
    if (this.voice?.dataset.src !== url) {
      this.voice?.pause();
      const element = new Audio(url);
      element.dataset.src = url;
      element.preload = "auto";
      element.crossOrigin = "anonymous";
      this.voice = element;
    }
    if (this.voice) {
      this.voice.volume = Math.max(0, Math.min(1, volume * this.volume));
      this.voice.muted = this.muted;
    }
  }

  private preload(scenes: Scene[]) {
    for (const scene of scenes) {
      const url = scene.media?.url;
      if (!url || this.images.has(url) || this.pending.has(url)) continue;
      this.pending.add(url);
      const image = new Image();
      image.crossOrigin = "anonymous";
      image.decoding = "async";
      image.onload = () => {
        this.images.set(url, image);
        this.pending.delete(url);
        this.draw();
      };
      image.onerror = () => {
        this.pending.delete(url);
      };
      image.src = url;
    }
  }

  // -------------------------------------------------------------- controls --

  get isPlaying() {
    return this.playing;
  }

  get currentTime() {
    return this.time;
  }

  get totalTime() {
    return this.duration;
  }

  play() {
    if (this.playing || this.duration <= 0) return;
    if (this.time >= this.duration - 0.01) this.time = 0;
    this.playing = true;
    this.lastTick = performance.now();
    this.syncAudio(true);
    this.onPlayingChange?.(true);
    this.loop();
  }

  pause() {
    if (!this.playing) return;
    this.playing = false;
    if (this.rafId !== null) cancelAnimationFrame(this.rafId);
    this.rafId = null;
    this.audio?.pause();
    this.voice?.pause();
    this.onPlayingChange?.(false);
  }

  toggle() {
    if (this.playing) this.pause();
    else this.play();
  }

  restart() {
    this.seek(0);
    this.play();
  }

  seek(time: number) {
    this.time = Math.max(0, Math.min(time, this.duration));
    this.onTime?.(this.time);
    this.syncAudio(this.playing);
    this.draw();
  }

  setMuted(muted: boolean) {
    this.muted = muted;
    if (this.audio) this.audio.muted = muted;
    if (this.voice) this.voice.muted = muted;
  }

  setVolume(volume: number) {
    this.volume = Math.max(0, Math.min(1, volume));
    if (this.audio) this.audio.volume = this.volume;
    if (this.voice) this.voice.volume = this.volume;
  }

  destroy() {
    this.pause();
    this.audio = null;
    this.voice = null;
    this.images.clear();
  }

  private syncAudio(shouldPlay: boolean) {
    for (const element of [this.audio, this.voice]) {
      if (!element) continue;
      const offset = element === this.audio ? Number(element.dataset.offset ?? 0) : 0;
      const target = offset + this.time;
      const source = element.duration;
      // A short bed loops under a longer video, exactly as the renderer does.
      const position = Number.isFinite(source) && source > 0 ? target % source : target;
      if (Math.abs(element.currentTime - position) > 0.2) {
        try {
          element.currentTime = position;
        } catch {
          /* the media is not seekable yet */
        }
      }
      if (shouldPlay) void element.play().catch(() => undefined);
      else element.pause();
    }
  }

  private loop = () => {
    if (!this.playing) return;
    const now = performance.now();
    const delta = (now - this.lastTick) / 1000;
    this.lastTick = now;

    this.time += delta;
    if (this.time >= this.duration) {
      this.time = this.duration;
      this.draw();
      this.onTime?.(this.time);
      this.pause();
      this.onEnded?.();
      return;
    }

    this.onTime?.(this.time);
    this.draw();

    // Nudge the audio back in step if it has drifted (tab throttling, buffering).
    if (this.audio && !this.audio.paused) {
      const offset = Number(this.audio.dataset.offset ?? 0);
      const source = this.audio.duration;
      const expected =
        Number.isFinite(source) && source > 0 ? (offset + this.time) % source : offset + this.time;
      if (Math.abs(this.audio.currentTime - expected) > 0.35) this.syncAudio(true);
    }

    this.rafId = requestAnimationFrame(this.loop);
  };

  // ---------------------------------------------------------------- render --

  draw() {
    const ctx = this.ctx;
    const { frameWidth: width, frameHeight: height } = this;

    ctx.save();
    ctx.fillStyle = "#000000";
    ctx.fillRect(0, 0, width, height);

    const state = frameAt(this.timeline, this.time);
    if (!state) {
      this.drawEmptyState(ctx, width, height);
      ctx.restore();
      return;
    }

    if (state.previous && state.transition !== "none") {
      this.drawTransition(ctx, state.previous, state.current, state.transition, state.progress);
    } else {
      this.drawScene(ctx, state.current, this.time - state.current.start, 1);
    }

    // Subtitles sit on the finished frame, above the scene and its text, exactly
    // as the renderer overlays them after the transition chain.
    this.drawSubtitles(ctx);

    ctx.restore();
  }

  /**
   * The subtitle card for the current instant.
   *
   * A simplified mirror of `subtitle_renderer.py`: same cards, same lit word, same
   * band position. It does not try to match the rasteriser glyph for glyph — the
   * canvas has no control over hinting or the exact font file — but the things a
   * user judges from a preview (which words, when, where, which one is lit) come
   * from the shared engine, so they agree.
   */
  private drawSubtitles(ctx: CanvasRenderingContext2D) {
    const preset = this.subtitlePreset;
    if (!preset || !this.cues.length) return;
    const cue = cueAt(this.cues, this.time);
    if (!cue) return;

    const { frameWidth: width, frameHeight: height } = this;
    const scale = width / 1080;
    const fontSize = preset.fontSize * scale;
    const lit = activeIndex(cue, this.time);
    const rtl = /[֐-ࣿיִ-﷿ﹰ-﻿]/.test(
      cue.words.map((w) => w.text).join(""),
    );

    ctx.save();
    ctx.textBaseline = "top";
    ctx.textAlign = "left";
    const font = (size: number) => `700 ${size}px system-ui, "Segoe UI", sans-serif`;

    const label = (text: string) => (preset.uppercase ? text.toUpperCase() : text);
    ctx.font = font(fontSize);
    const spaceWidth =
      ctx.measureText(" ").width + (preset.activeBackground ? preset.fontSize * 0.34 * scale * 2 : 0);

    // Wrap into lines the same way the rasteriser does: by measured width.
    const maxWidth = width * preset.maxWidthPct;
    const rows: { text: string; index: number; width: number }[][] = [[]];
    let used = 0;
    cue.words.forEach((word, index) => {
      const text = label(word.text);
      const w = ctx.measureText(text).width;
      const extra = rows[rows.length - 1].length ? spaceWidth + w : w;
      if (rows[rows.length - 1].length && used + extra > maxWidth) {
        rows.push([]);
        used = 0;
      }
      rows[rows.length - 1].push({ text, index, width: w });
      used += rows[rows.length - 1].length === 1 ? w : extra;
    });

    const lineHeight = fontSize * preset.lineHeight;
    const blockHeight = lineHeight * rows.length;
    const bandHeight = blockHeight + 28 * scale * 2;
    const bandTop = Math.max(
      0,
      Math.min(preset.positionY * height - bandHeight / 2, height - bandHeight),
    );

    if (preset.backgroundOpacity > 0) {
      if (preset.gradientBackground) {
        const gradient = ctx.createLinearGradient(0, bandTop, 0, bandTop + bandHeight);
        gradient.addColorStop(0, this.rgba(preset.backgroundColor, 0));
        gradient.addColorStop(1, this.rgba(preset.backgroundColor, preset.backgroundOpacity));
        ctx.fillStyle = gradient;
      } else {
        ctx.fillStyle = this.rgba(preset.backgroundColor, preset.backgroundOpacity);
      }
      ctx.fillRect(0, bandTop, width, bandHeight);
    }

    const top = bandTop + (bandHeight - blockHeight) / 2;
    rows.forEach((row, rowIndex) => {
      const total = row.reduce((sum, item) => sum + item.width, 0) + spaceWidth * (row.length - 1);
      let cursor = (width - total) / 2;
      const ordered = rtl ? [...row].reverse() : row;
      ordered.forEach((item) => {
        const isLit = item.index === lit;
        const size = isLit && preset.activeScale !== 1 ? fontSize * preset.activeScale : fontSize;
        ctx.font = font(size);
        const drawn = ctx.measureText(item.text).width;
        const x = cursor - (drawn - item.width) / 2;
        const y = top + rowIndex * lineHeight - (size - fontSize) * 0.5;

        if (isLit && preset.activeBackground) {
          const padX = preset.fontSize * 0.34 * scale;
          const padY = preset.fontSize * 0.08 * scale;
          ctx.fillStyle = preset.activeBackground;
          ctx.beginPath();
          const box = [x - padX, y - padY, drawn + padX * 2, size * 1.2 + padY * 2] as const;
          // `roundRect` is recent; a square pill is a far better fallback than a
          // preview that throws mid-frame on an older browser.
          if (typeof ctx.roundRect === "function") {
            ctx.roundRect(...box, preset.fontSize * 0.22 * scale);
          } else {
            ctx.rect(...box);
          }
          ctx.fill();
        } else if (preset.outlinePx) {
          ctx.lineWidth = preset.outlinePx * scale * 2;
          ctx.strokeStyle = this.rgba(preset.outlineColor, isLit ? 1 : preset.inactiveOpacity);
          ctx.lineJoin = "round";
          ctx.strokeText(item.text, x, y);
        }

        ctx.fillStyle = this.rgba(
          isLit ? preset.activeColor : preset.color,
          isLit ? 1 : preset.inactiveOpacity,
        );
        ctx.fillText(item.text, x, y);
        cursor += item.width + spaceWidth;
      });
    });
    ctx.restore();
  }

  private rgba(hex: string, alpha: number): string {
    const value = hex.replace("#", "");
    const full = value.length === 3 ? value.split("").map((c) => c + c).join("") : value;
    const r = parseInt(full.slice(0, 2), 16);
    const g = parseInt(full.slice(2, 4), 16);
    const b = parseInt(full.slice(4, 6), 16);
    return `rgba(${r}, ${g}, ${b}, ${alpha})`;
  }

  private drawEmptyState(ctx: CanvasRenderingContext2D, width: number, height: number) {
    const gradient = ctx.createLinearGradient(0, 0, width, height);
    gradient.addColorStop(0, "#161923");
    gradient.addColorStop(1, "#0d0f16");
    ctx.fillStyle = gradient;
    ctx.fillRect(0, 0, width, height);

    ctx.fillStyle = "rgba(255,255,255,0.45)";
    ctx.font = "500 44px system-ui, sans-serif";
    ctx.textAlign = "center";
    ctx.fillText("Upload images to start", width / 2, height / 2);
    ctx.textAlign = "left";
  }

  /** Draw one scene's image (through its animation viewport) plus its text. */
  private drawScene(
    ctx: CanvasRenderingContext2D,
    item: TimelineScene,
    sceneTime: number,
    alpha: number,
    offsetX = 0,
    offsetY = 0,
    blurPx = 0,
    extraScale = 1,
  ) {
    const { scene } = item;
    const { frameWidth: width, frameHeight: height } = this;
    const progress = scene.duration > 0 ? Math.max(0, Math.min(1, sceneTime / scene.duration)) : 0;

    const motion = buildMotion(scene.animation, {
      intensity: scene.animation_intensity,
      focus: [scene.focus_x, scene.focus_y],
    });
    const viewport = viewportAt(motion, progress);

    ctx.save();
    ctx.globalAlpha = alpha;
    if (blurPx > 0) ctx.filter = `blur(${blurPx}px)`;
    ctx.translate(offsetX, offsetY);

    if (extraScale !== 1) {
      ctx.translate(width / 2, height / 2);
      ctx.scale(extraScale, extraScale);
      ctx.translate(-width / 2, -height / 2);
    }

    const url = scene.media?.url;
    const image = url ? this.images.get(url) : undefined;

    if (image && image.complete && image.naturalWidth > 0) {
      const rect = sourceRect(viewport, image.naturalWidth, image.naturalHeight, width, height, [
        scene.focus_x,
        scene.focus_y,
      ]);
      const rotation = rotationAt(motion, progress);
      if (Math.abs(rotation) > 1e-3) {
        ctx.translate(width / 2, height / 2);
        ctx.rotate((rotation * Math.PI) / 180);
        // Overscan so rotation never reveals the corners, matching the renderer.
        ctx.scale(1.12, 1.12);
        ctx.translate(-width / 2, -height / 2);
      }
      ctx.drawImage(image, rect.sx, rect.sy, rect.sw, rect.sh, 0, 0, width, height);
    } else {
      ctx.fillStyle = scene.background_color || "#000000";
      ctx.fillRect(0, 0, width, height);
      if (url) {
        // The bitmap is still downloading; a placeholder beats a black flash.
        ctx.fillStyle = "rgba(255,255,255,0.12)";
        ctx.fillRect(width * 0.3, height * 0.46, width * 0.4, 6);
      }
    }

    ctx.filter = "none";
    for (const overlay of scene.texts) {
      drawTextOverlay(ctx, overlay, width, height, sceneTime, scene.duration, motion.parallaxPx);
    }

    ctx.restore();
  }

  private drawTransition(
    ctx: CanvasRenderingContext2D,
    previous: TimelineScene,
    current: TimelineScene,
    transition: TransitionType,
    progress: number,
  ) {
    const { frameWidth: width, frameHeight: height } = this;
    const t = Math.max(0, Math.min(1, progress));
    const outgoingTime = this.time - previous.start;
    const incomingTime = this.time - current.start;

    switch (transition) {
      case "fade":
      case "cross_dissolve":
        this.drawScene(ctx, previous, outgoingTime, 1);
        this.drawScene(ctx, current, incomingTime, t);
        break;

      case "slide_left":
      case "push":
        this.drawScene(ctx, previous, outgoingTime, 1, -width * t, 0);
        this.drawScene(ctx, current, incomingTime, 1, width * (1 - t), 0);
        break;

      case "slide_right":
        this.drawScene(ctx, previous, outgoingTime, 1, width * t, 0);
        this.drawScene(ctx, current, incomingTime, 1, -width * (1 - t), 0);
        break;

      case "wipe": {
        this.drawScene(ctx, previous, outgoingTime, 1);
        ctx.save();
        ctx.beginPath();
        ctx.rect(0, 0, width * t, height);
        ctx.clip();
        this.drawScene(ctx, current, incomingTime, 1);
        ctx.restore();
        break;
      }

      case "zoom":
        this.drawScene(ctx, previous, outgoingTime, 1, 0, 0, 0, 1 + 0.35 * t);
        this.drawScene(ctx, current, incomingTime, t, 0, 0, 0, 1.35 - 0.35 * t);
        break;

      case "blur": {
        const bell = Math.sin(Math.PI * t);
        this.drawScene(ctx, previous, outgoingTime, 1, 0, 0, 26 * bell);
        this.drawScene(ctx, current, incomingTime, t, 0, 0, 26 * bell);
        break;
      }

      default:
        this.drawScene(ctx, current, incomingTime, 1);
    }
  }

  /** A still frame at a given time, for scene thumbnails. */
  snapshot(time: number): string {
    const previousTime = this.time;
    this.time = time;
    this.draw();
    const data = this.canvas.toDataURL("image/jpeg", 0.6);
    this.time = previousTime;
    this.draw();
    return data;
  }
}
