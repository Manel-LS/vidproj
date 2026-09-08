/**
 * Canvas text rendering, mirrored from `backend/app/infrastructure/imaging/text_renderer.py`.
 *
 * The renderer rasterises text with Pillow; the preview draws it with the Canvas 2D
 * API. The layout rules (anchors, padding, wrapping, backgrounds) and the animation
 * curves are the same on both sides so what you see is what gets encoded. Fonts
 * differ slightly — the browser has its own — which is the one honest gap, and the
 * editor says so.
 */
import type { FontFamily, TextAlign, TextAnimation, TextOverlay, TextPosition } from "@/lib/api/types";

const SLIDE_TRAVEL = 130;
const RISE_TRAVEL = 80;
const ZOOM_START = 1.35;

const POSITION_ANCHORS: Record<TextPosition, { anchor: "top" | "center" | "bottom"; ratio: number }> = {
  top: { anchor: "top", ratio: 0.065 },
  upper_third: { anchor: "center", ratio: 0.27 },
  center: { anchor: "center", ratio: 0.5 },
  lower_third: { anchor: "center", ratio: 0.72 },
  bottom: { anchor: "bottom", ratio: 0.935 },
};

/** Unicode blocks whose scripts read right to left and join their letters. */
const RTL_RANGES: Array<[number, number]> = [
  [0x0590, 0x05ff], // Hebrew
  [0x0600, 0x06ff], // Arabic
  [0x0700, 0x074f], // Syriac
  [0x0750, 0x077f], // Arabic Supplement
  [0x08a0, 0x08ff], // Arabic Extended-A
  [0xfb1d, 0xfdff], // Hebrew/Arabic presentation forms
  [0xfe70, 0xfeff], // Arabic presentation forms-B
];

/**
 * True for a right-to-left, letter-joining script.
 *
 * Such text must be handed to the shaper whole: Arabic letters change shape
 * according to their neighbours, so drawing them one at a time to apply letter
 * spacing severs every ligature and reverses the reading order.
 */
export function isRtl(text: string): boolean {
  for (const char of text) {
    const code = char.codePointAt(0) ?? 0;
    for (const [low, high] of RTL_RANGES) if (code >= low && code <= high) return true;
  }
  return false;
}

/** Families that actually carry Arabic glyphs — Georgia and Consolas do not. */
const RTL_FONT_STACKS: Record<FontFamily, string> = {
  sans_bold: '"Dubai", "Noto Sans Arabic", "Segoe UI", Tahoma, Arial, sans-serif',
  sans: '"Dubai", "Noto Sans Arabic", "Segoe UI", Tahoma, Arial, sans-serif',
  serif: '"Noto Naskh Arabic", "Traditional Arabic", "Amiri", "Times New Roman", serif',
  condensed: '"Dubai", "Segoe UI", Tahoma, Arial, sans-serif',
  mono: '"Noto Sans Arabic", "Segoe UI", Tahoma, Arial, sans-serif',
};

const FONT_STACKS: Record<FontFamily, string> = {
  sans_bold: '"Segoe UI", Inter, system-ui, -apple-system, Arial, sans-serif',
  sans: '"Segoe UI", Inter, system-ui, -apple-system, Arial, sans-serif',
  serif: 'Georgia, "Times New Roman", serif',
  condensed: '"Arial Narrow", "Oswald", Impact, sans-serif',
  mono: 'Consolas, "SF Mono", ui-monospace, monospace',
};

function easeOutCubic(t: number): number {
  return 1 - Math.pow(1 - t, 3);
}

function easeOutBack(t: number): number {
  const c1 = 1.70158;
  const c3 = c1 + 1;
  return 1 + c3 * Math.pow(t - 1, 3) + c1 * Math.pow(t - 1, 2);
}

function popScale(t: number): number {
  return 0.55 + (1 - 0.55) * easeOutBack(t);
}

export function hexToRgb(hex: string): [number, number, number] {
  let value = hex.replace("#", "");
  if (value.length === 3) value = value.split("").map((c) => c + c).join("");
  const int = parseInt(value.slice(0, 6), 16);
  return [(int >> 16) & 255, (int >> 8) & 255, int & 255];
}

export function rgba(hex: string, alpha: number): string {
  const [r, g, b] = hexToRgb(hex);
  return `rgba(${r}, ${g}, ${b}, ${Math.max(0, Math.min(1, alpha))})`;
}

function fontString(overlay: TextOverlay): string {
  const stacks = isRtl(overlay.content) ? RTL_FONT_STACKS : FONT_STACKS;
  return `${overlay.font_weight} ${overlay.font_size}px ${stacks[overlay.font_family] ?? stacks.sans}`;
}

function measure(ctx: CanvasRenderingContext2D, text: string, spacing: number): number {
  if (!text) return 0;
  const base = ctx.measureText(text).width;
  // Letter spacing does not apply to joining scripts — see `isRtl`.
  if (isRtl(text)) return base;
  return spacing ? base + spacing * Math.max(0, text.length - 1) : base;
}

function wrap(
  ctx: CanvasRenderingContext2D,
  text: string,
  maxWidth: number,
  spacing: number,
): string[] {
  const lines: string[] = [];
  for (const paragraph of text.split("\n")) {
    const words = paragraph.split(/\s+/).filter(Boolean);
    if (!words.length) {
      lines.push("");
      continue;
    }
    let current = words[0];
    for (const word of words.slice(1)) {
      const candidate = `${current} ${word}`;
      if (measure(ctx, candidate, spacing) <= maxWidth) current = candidate;
      else {
        lines.push(current);
        current = word;
      }
    }
    lines.push(current);
  }
  return lines.length ? lines : [""];
}

function drawSpaced(
  ctx: CanvasRenderingContext2D,
  text: string,
  x: number,
  y: number,
  spacing: number,
) {
  // The browser shapes right-to-left text itself, but only if it is given the whole
  // run at once. Splitting it to apply spacing would break the ligatures.
  if (!spacing || isRtl(text)) {
    ctx.fillText(text, x, y);
    return;
  }
  let cursor = x;
  for (const char of text) {
    ctx.fillText(char, cursor, y);
    cursor += ctx.measureText(char).width + spacing;
  }
}

function paddingFor(overlay: TextOverlay): [number, number] {
  const size = overlay.font_size;
  switch (overlay.background) {
    case "none":
      return [0, 0];
    case "pill":
      return [size * 0.55, size * 0.28];
    case "box":
      return [size * 0.4, size * 0.26];
    default:
      return [size * 0.5, size * 0.55];
  }
}

export interface TextLayout {
  lines: string[];
  lineWidths: number[];
  width: number;
  height: number;
  lineHeight: number;
  padX: number;
  padY: number;
  blockWidth: number;
  blockHeight: number;
  centerX: number;
  centerY: number;
}

export function layoutText(
  ctx: CanvasRenderingContext2D,
  overlay: TextOverlay,
  frameWidth: number,
  frameHeight: number,
): TextLayout {
  ctx.save();
  ctx.font = fontString(overlay);
  const [padX, padY] = paddingFor(overlay);
  const content = overlay.uppercase ? overlay.content.toUpperCase() : overlay.content;
  const maxWidth = frameWidth * overlay.max_width_pct - padX * 2;
  const lines = wrap(ctx, content, maxWidth, overlay.letter_spacing);
  const lineWidths = lines.map((line) => measure(ctx, line, overlay.letter_spacing));
  const width = lineWidths.length ? Math.max(...lineWidths) : 0;
  // Pillow's (ascent + descent) is approximated by the font size times the standard
  // 1.2 metric ratio; the difference is under a pixel at these sizes.
  const lineHeight = overlay.font_size * 1.2 * overlay.line_height;
  const height = lineHeight * lines.length;
  ctx.restore();

  const blockWidth = width + padX * 2;
  const blockHeight = height + padY * 2;

  const { anchor, ratio } = POSITION_ANCHORS[overlay.position] ?? POSITION_ANCHORS.center;
  let centerY: number;
  if (anchor === "top") centerY = frameHeight * ratio + blockHeight / 2;
  else if (anchor === "bottom") centerY = frameHeight * ratio - blockHeight / 2;
  else centerY = frameHeight * ratio;
  centerY += overlay.offset_y_pct * frameHeight;

  let centerX: number;
  if (overlay.align === "left") centerX = frameWidth * 0.06 + blockWidth / 2;
  else if (overlay.align === "right") centerX = frameWidth * 0.94 - blockWidth / 2;
  else centerX = frameWidth / 2;
  centerX += overlay.offset_x_pct * frameWidth;

  return {
    lines,
    lineWidths,
    width,
    height,
    lineHeight,
    padX,
    padY,
    blockWidth,
    blockHeight,
    centerX,
    centerY,
  };
}

interface Transform {
  scale: number;
  dx: number;
  dy: number;
  alpha: number;
  visibleChars: number | null;
}

function transformAt(animation: TextAnimation, t: number, align: TextAlign): Transform {
  const eased = easeOutCubic(t);
  switch (animation) {
    case "none":
      return { scale: 1, dx: 0, dy: 0, alpha: 1, visibleChars: null };
    case "fade":
      return { scale: 1, dx: 0, dy: 0, alpha: eased, visibleChars: null };
    case "slide": {
      const direction = align === "right" ? 1 : -1;
      return { scale: 1, dx: direction * SLIDE_TRAVEL * (1 - eased), dy: 0, alpha: eased, visibleChars: null };
    }
    case "rise":
      return {
        scale: 1,
        dx: 0,
        dy: RISE_TRAVEL * (1 - eased),
        alpha: Math.min(1, eased * 1.3),
        visibleChars: null,
      };
    case "pop":
      return { scale: popScale(t), dx: 0, dy: 0, alpha: Math.min(1, t * 2.2), visibleChars: null };
    case "zoom":
      return {
        scale: ZOOM_START + (1 - ZOOM_START) * eased,
        dx: 0,
        dy: 0,
        alpha: Math.min(1, t * 1.8),
        visibleChars: null,
      };
    case "typewriter":
      return { scale: 1, dx: 0, dy: 0, alpha: 1, visibleChars: -1 };
    default:
      return { scale: 1, dx: 0, dy: 0, alpha: 1, visibleChars: null };
  }
}

function roundedRect(
  ctx: CanvasRenderingContext2D,
  x: number,
  y: number,
  width: number,
  height: number,
  radius: number,
) {
  const r = Math.min(radius, width / 2, height / 2);
  ctx.beginPath();
  ctx.moveTo(x + r, y);
  ctx.arcTo(x + width, y, x + width, y + height, r);
  ctx.arcTo(x + width, y + height, x, y + height, r);
  ctx.arcTo(x, y + height, x, y, r);
  ctx.arcTo(x, y, x + width, y, r);
  ctx.closePath();
  ctx.fill();
}

/**
 * Draw one overlay at `sceneTime` seconds into its scene.
 * Returns false when the overlay is not on screen at that moment.
 */
export function drawTextOverlay(
  ctx: CanvasRenderingContext2D,
  overlay: TextOverlay,
  frameWidth: number,
  frameHeight: number,
  sceneTime: number,
  sceneDuration: number,
  parallaxPx = 0,
): boolean {
  const start = overlay.start;
  const end = overlay.duration == null ? sceneDuration : Math.min(start + overlay.duration, sceneDuration);
  if (sceneTime < start || sceneTime > end) return false;

  const animationSeconds = Math.max(0.05, Math.min(overlay.animation_duration, end - start));
  const t = Math.max(0, Math.min(1, (sceneTime - start) / animationSeconds));

  const layout = layoutText(ctx, overlay, frameWidth, frameHeight);
  const transform = transformAt(overlay.animation, t, overlay.align);
  const totalChars = layout.lines.reduce((sum, line) => sum + line.length, 0);
  const visibleChars =
    overlay.animation === "typewriter" ? Math.max(1, Math.ceil(totalChars * t)) : null;

  const drift =
    parallaxPx && end > start
      ? -parallaxPx * Math.max(0, Math.min(1, (sceneTime - start) / (end - start)))
      : 0;

  ctx.save();
  ctx.globalAlpha = transform.alpha * overlay.opacity;
  ctx.translate(layout.centerX + transform.dx + drift, layout.centerY + transform.dy);
  ctx.scale(transform.scale, transform.scale);
  ctx.translate(-layout.blockWidth / 2, -layout.blockHeight / 2);

  // Background scrim
  if (overlay.background !== "none") {
    const alpha = overlay.background_opacity;
    if (overlay.background === "gradient") {
      const gradient = ctx.createLinearGradient(0, 0, 0, layout.blockHeight);
      gradient.addColorStop(0, rgba(overlay.background_color, 0));
      gradient.addColorStop(0.5, rgba(overlay.background_color, alpha));
      gradient.addColorStop(1, rgba(overlay.background_color, 0));
      ctx.fillStyle = gradient;
      ctx.fillRect(0, 0, layout.blockWidth, layout.blockHeight);
    } else {
      const radius =
        overlay.background === "pill" ? layout.blockHeight / 2 : Math.max(8, layout.blockHeight * 0.1);
      ctx.fillStyle = rgba(overlay.background_color, alpha);
      roundedRect(ctx, 0, 0, layout.blockWidth, layout.blockHeight, radius);
    }
  }

  ctx.font = fontString(overlay);
  ctx.textBaseline = "top";
  ctx.fillStyle = overlay.color;
  if (overlay.shadow) {
    ctx.shadowColor = "rgba(0, 0, 0, 0.6)";
    ctx.shadowBlur = Math.max(4, overlay.font_size * 0.07);
    ctx.shadowOffsetY = Math.max(2, overlay.font_size * 0.045);
  }

  let remaining = visibleChars;
  let y = layout.padY;
  for (let index = 0; index < layout.lines.length; index += 1) {
    let line = layout.lines[index];
    if (remaining !== null) {
      if (remaining <= 0) break;
      line = line.slice(0, remaining);
      remaining -= layout.lines[index].length;
    }
    const lineWidth = layout.lineWidths[index];
    let x = layout.padX;
    if (overlay.align === "right") x = layout.padX + (layout.width - lineWidth);
    else if (overlay.align === "center") x = layout.padX + (layout.width - lineWidth) / 2;
    drawSpaced(ctx, line, x, y, overlay.letter_spacing);
    y += layout.lineHeight;
  }

  ctx.restore();
  return true;
}
