/**
 * Types mirroring the backend DTOs (`backend/app/schemas`).
 *
 * The enum unions are kept in sync by `GET /api/v1/options`, which the editor uses
 * to build its dropdowns — so adding an animation server-side needs no change here.
 */

export type VideoFormat = "9:16" | "1:1" | "16:9" | "4:5";
export type Platform = "tiktok" | "instagram_reels" | "youtube_shorts" | "instagram_story";
export type GenerationMode = "standard" | "ai_motion";
/** Tunisian derja is deliberately separate from Modern Standard Arabic. */
export type Language = "tn" | "ar" | "fr" | "en";

export type VideoStyleKey =
  | "product_showcase"
  | "tiktok_trend"
  | "minimal"
  | "luxury"
  | "sale"
  | "storytelling"
  | "real_estate"
  | "food"
  | "educational"
  | "custom";

export type AnimationType =
  | "none"
  | "zoom_in"
  | "zoom_out"
  | "slow_zoom"
  | "dynamic_zoom"
  | "pan_left"
  | "pan_right"
  | "pan_up"
  | "pan_down"
  | "ken_burns"
  | "rotate_slight"
  | "parallax";

export type TransitionType =
  | "none"
  | "fade"
  | "cross_dissolve"
  | "slide_left"
  | "slide_right"
  | "zoom"
  | "blur"
  | "push"
  | "wipe";

export type TextRole = "title" | "subtitle" | "cta" | "caption";
export type TextPosition = "top" | "upper_third" | "center" | "lower_third" | "bottom";
export type TextAlign = "left" | "center" | "right";
export type TextAnimation = "none" | "fade" | "slide" | "pop" | "typewriter" | "zoom" | "rise";
export type TextBackground = "none" | "box" | "pill" | "gradient";
export type FontFamily = "sans_bold" | "sans" | "serif" | "condensed" | "mono";
export type RenderStatus = "queued" | "processing" | "completed" | "failed" | "cancelled";
export type VoiceOverStatus = "draft" | "generating" | "ready" | "failed";
export type MediaKind = "image" | "audio" | "video";

export interface TextOverlay {
  id: string;
  role: TextRole;
  content: string;
  position: TextPosition;
  align: TextAlign;
  animation: TextAnimation;
  font_family: FontFamily;
  font_size: number;
  font_weight: number;
  color: string;
  letter_spacing: number;
  line_height: number;
  uppercase: boolean;
  opacity: number;
  background: TextBackground;
  background_color: string;
  background_opacity: number;
  shadow: boolean;
  max_width_pct: number;
  offset_y_pct: number;
  offset_x_pct: number;
  start: number;
  duration: number | null;
  animation_duration: number;
}

export interface MediaItem {
  id: string;
  kind: MediaKind;
  source: string;
  url: string;
  thumbnail_url: string | null;
  original_filename: string;
  content_type: string;
  size_bytes: number;
  width: number | null;
  height: number | null;
  duration_seconds: number | null;
  position: number;
  created_at: string;
  analysis: {
    brightness?: number;
    contrast?: number;
    focus_x?: number;
    focus_y?: number;
    dominant_colors?: string[];
    region_brightness?: Record<string, number>;
  };
}

export interface AiMotionSpec {
  enabled: boolean;
  prompt: string;
  generated_media_id: string | null;
  provider: string | null;
  job_reference: string | null;
  /**
   * The clip before lip sync. Kept so a sync can be redone — or undone — without
   * paying to generate the motion again: once lip sync succeeds
   * `generated_media_id` points at the speaking clip and this at the silent one.
   */
  silent_media_id?: string | null;
  lipsync_provider?: string | null;
  lipsync_job_reference?: string | null;
  error?: string;
}

export interface Scene {
  id: string;
  order: number;
  media_id: string | null;
  duration: number;
  animation: AnimationType;
  animation_intensity: number;
  focus_x: number;
  focus_y: number;
  transition: TransitionType;
  transition_duration: number;
  texts: TextOverlay[];
  background_color: string;
  note: string;
  /** What the image provider was asked for; kept so a regeneration repeats the shot. */
  image_prompt: string;
  ai_motion: AiMotionSpec | null;
  start_time: number;
  media: MediaItem | null;
}

export interface AudioTrack {
  id: string;
  media_id: string | null;
  media: MediaItem | null;
  volume: number;
  fade_in: number;
  fade_out: number;
  start_offset: number;
  loop: boolean;
  library_track_key: string | null;
}

export interface VoiceOver {
  id: string;
  enabled: boolean;
  script: string;
  status: VoiceOverStatus;
  provider: string | null;
  voice_id: string | null;
  volume: number;
  duck_music_to: number;
  error: string;
  media: MediaItem | null;
  /** Seconds from the start of the audio; the preview draws the same highlight the renderer burns in. */
  word_timings: WordTiming[];
  has_word_timings: boolean;
}

export interface WordTiming {
  text: string;
  start: number;
  duration: number;
}

export interface RenderJob {
  id: string;
  project_id: string;
  status: RenderStatus;
  progress: number;
  stage: string;
  error: string;
  message: string;
  created_at: string;
  started_at: string | null;
  finished_at: string | null;
  output_media: MediaItem | null;
  download_url: string | null;
}

/**
 * The unified job registry (`GET /projects/{id}/jobs`).
 *
 * Every kind of generation writes here — image, motion, voice, lip sync and the
 * render itself — so the editor can answer "what is this project doing" from one
 * poll instead of five differently-shaped ones.
 */
export type GenerationJobType = "story" | "image" | "video" | "voice" | "lipsync" | "render";

export interface GenerationJob {
  id: string;
  project_id: string;
  scene_id: string | null;
  type: GenerationJobType;
  provider: string;
  status: RenderStatus;
  progress: number;
  stage: string;
  error: string;
  external_job_id: string;
  result_media_id: string | null;
  result_url: string | null;
  created_at: string;
  started_at: string | null;
  completed_at: string | null;
}

export interface ProjectJobs {
  items: GenerationJob[];
  total: number;
  active: number;
  progress: number;
  current_stage: string;
  last_error: string;
  by_status: Record<string, number>;
}

export interface ProjectSummary {
  id: string;
  name: string;
  description: string;
  platform: Platform;
  format: VideoFormat;
  style: VideoStyleKey;
  mode: GenerationMode;
  duration_seconds: number;
  created_at: string;
  updated_at: string;
  scene_count: number;
  image_count: number;
  thumbnail_url: string | null;
  render_status: RenderStatus | null;
  render_progress: number;
  download_url: string | null;
}

export interface ProjectDetail extends ProjectSummary {
  topic: string;
  fps: number;
  /** Drives the planner's wording, the default voice and the subtitle direction. */
  language: Language;
  rtl: boolean;
  character_id: string | null;
  /** The frozen character description replayed verbatim into every image prompt. */
  character_description: string;
  template_key: string | null;
  target_duration: number | null;
  hook: string;
  cta: string;
  caption: string;
  hashtags: string[];
  plan_generated_by: string;
  plan_notes: string;
  scenes: Scene[];
  media: MediaItem[];
  audio: AudioTrack | null;
  voice_over: VoiceOver | null;
  total_duration: number;
}

export interface PlanScene {
  id: string;
  order: number;
  media_id: string | null;
  duration: number;
  animation: AnimationType;
  animation_intensity: number;
  focus_x: number;
  focus_y: number;
  transition: TransitionType;
  transition_duration: number;
  texts: TextOverlay[];
  background_color: string;
  ai_motion: AiMotionSpec | null;
  note: string;
}

export interface VideoPlan {
  version: number;
  format: VideoFormat;
  fps: number;
  style: VideoStyleKey;
  mode: GenerationMode;
  scenes: PlanScene[];
  audio: {
    media_id: string | null;
    volume: number;
    fade_in: number;
    fade_out: number;
    start_offset: number;
    loop: boolean;
  } | null;
  voiceover: {
    enabled: boolean;
    script: string;
    media_id: string | null;
    volume: number;
    duck_music_to: number;
    provider: string | null;
    voice_id: string | null;
  } | null;
  hook: string;
  cta: string;
  caption: string;
  hashtags: string[];
  generated_by: string;
  notes: string;
}

export interface PlanResponse {
  plan: VideoPlan;
  generated_by: string;
  ai_used: boolean;
  notice: string;
  applied: boolean;
  total_duration: number;
  scene_start_times: number[];
}

export interface StylePreset {
  key: VideoStyleKey;
  name: string;
  description: string;
  tagline: string;
  gradient: [string, string];
  scene_seconds: [number, number];
  transition_seconds: number;
  motion_intensity: number;
  animations: AnimationType[];
  transitions: TransitionType[];
  text_position: TextPosition;
  text_animation: TextAnimation;
  default_cta: string;
  typography: {
    family: FontFamily;
    title_size: number;
    subtitle_size: number;
    caption_size: number;
    color: string;
    accent_color: string;
    background: TextBackground;
    background_color: string;
    background_opacity: number;
    letter_spacing: number;
    uppercase: boolean;
    align: TextAlign;
    shadow: boolean;
  };
}

export interface TemplateSummary {
  key: string;
  name: string;
  description: string;
  category: string;
  style: VideoStyleKey;
  format: VideoFormat;
  recommended_duration: number;
  min_images: number;
  max_images: number;
  gradient: [string, string];
  default_cta: string;
  scene_count_hint: number;
  typography: { family: FontFamily; color: string; accent_color: string; uppercase: boolean };
  slots: Array<{
    kind: string;
    duration: number;
    animation: AnimationType | null;
    transition: TransitionType | null;
    text_role: TextRole | null;
    text_template: string;
    repeat: boolean;
    needs_image: boolean;
  }>;
}

/** What the character is, which changes how a prompt should describe it. */
export type CharacterKind = "baby" | "child" | "teen" | "adult" | "elder" | "fictional" | "animal";

export interface Character {
  id: string;
  name: string;
  kind: CharacterKind;
  age: string;
  gender: string;
  skin_tone: string;
  hair: string;
  clothes: string;
  headwear: string;
  expression: string;
  personality: string;
  environment: string;
  /**
   * The frozen sentence replayed verbatim into every image prompt. It is composed
   * once, on create or on a field edit — recomposing it per generation, even from
   * identical fields, drifts towards a different person.
   */
  description: string;
  reference_media_id: string | null;
  reference_image_url: string | null;
  created_at: string;
  updated_at: string;
}

export type CharacterDraft = Partial<Omit<Character, "id" | "created_at" | "updated_at">> & {
  name: string;
};

export interface ProviderStatus {
  available: boolean;
  provider: string | null;
  display_name: string;
  message: string;
}

export interface LanguageSupport {
  code: Language;
  label: string;
  rtl: boolean;
  /** The configured voice provider has a voice for this language at all. */
  supported: boolean;
  /** The voice really is that language, rather than a neighbouring accent. */
  exact: boolean;
  voice_id: string | null;
  note: string;
}

export interface Capabilities {
  render: {
    available: boolean;
    engine: string;
    version: string;
    fps: number;
    transitions: string[];
    message: string;
  };
  ai_planner: ProviderStatus;
  voiceover: ProviderStatus & {
    voices: Array<{ id: string; name: string; description: string; language: string; gender: string }>;
    /**
     * Per language, and honest: a provider with no `ar-TN` voice is not reported as
     * supporting derja just because it has some Arabic. `exact: false` means only a
     * neighbouring accent was found, and `note` says which.
     */
    languages: LanguageSupport[];
    /** Whether this provider reports per-word timings, which word-level subtitles need. */
    supports_word_timings: boolean;
  };
  image: ProviderStatus & {
    supported_aspect_ratios: string[];
    supports_reference_image: boolean;
  };
  lipsync: ProviderStatus & {
    max_clip_seconds: number;
    needs_public_urls: boolean;
  };
  ai_motion: ProviderStatus & {
    supported_durations: number[];
    supported_aspect_ratios: string[];
  };
  queue: { provider: string; configured: string; available: boolean };
  storage: { provider: string };
  fonts: Record<string, string>;
  limits: {
    max_image_bytes: number;
    max_audio_bytes: number;
    max_images_per_project: number;
    allowed_image_types: string[];
    allowed_audio_types: string[];
  };
}

export interface FormatOption {
  key: VideoFormat;
  width: number;
  height: number;
  label: string;
  default: boolean;
}

export interface PlatformOption {
  key: Platform;
  label: string;
  default_format: VideoFormat;
  max_seconds: number;
}

export interface EditorOptions {
  animations: AnimationType[];
  transitions: TransitionType[];
  text_positions: TextPosition[];
  text_animations: TextAnimation[];
  text_roles: TextRole[];
  text_backgrounds: TextBackground[];
  font_families: FontFamily[];
  styles: VideoStyleKey[];
}

export interface User {
  id: string;
  email: string;
  full_name: string;
  created_at: string;
}

export interface AuthResponse {
  access_token: string;
  token_type: string;
  expires_in: number;
  user: User;
}

export interface Page<T> {
  items: T[];
  total: number;
  limit: number;
  offset: number;
}

export interface ApiErrorBody {
  error: {
    code: string;
    message: string;
    details?: unknown;
  };
}
