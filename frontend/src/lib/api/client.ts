/**
 * The single place the frontend talks to the backend.
 *
 * Everything else calls these functions — no component builds a URL or reads the
 * token itself. Errors arrive as `ApiError`, which carries the backend's
 * user-facing message so the UI never has to invent one.
 */
import type {
  ApiErrorBody,
  AudioTrack,
  AuthResponse,
  Capabilities,
  Character,
  CharacterDraft,
  EditorOptions,
  FormatOption,
  GenerationJob,
  MediaItem,
  Page,
  PlanResponse,
  PlatformOption,
  ProjectDetail,
  ProjectJobs,
  ProjectSummary,
  RenderJob,
  Scene,
  StylePreset,
  TemplateSummary,
  User,
  VideoPlan,
  VoiceOver,
} from "./types";

export const API_BASE =
  process.env.NEXT_PUBLIC_API_URL?.replace(/\/$/, "") || "http://localhost:8000";
const API = `${API_BASE}/api/v1`;

const TOKEN_KEY = "reelcraft.token";

export class ApiError extends Error {
  readonly status: number;
  readonly code: string;
  readonly details: unknown;

  constructor(status: number, code: string, message: string, details?: unknown) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.code = code;
    this.details = details;
  }

  /** True when the user simply needs to sign in again. */
  get isAuthError() {
    return this.status === 401;
  }

  /** True when a capability is not configured in this deployment. */
  get isUnavailable() {
    return this.status === 503;
  }
}

export function getToken(): string | null {
  if (typeof window === "undefined") return null;
  try {
    return window.localStorage.getItem(TOKEN_KEY);
  } catch {
    return null;
  }
}

export function setToken(token: string | null) {
  if (typeof window === "undefined") return;
  try {
    if (token) window.localStorage.setItem(TOKEN_KEY, token);
    else window.localStorage.removeItem(TOKEN_KEY);
  } catch {
    /* private browsing — the session simply won't persist */
  }
}

type RequestOptions = Omit<RequestInit, "body"> & {
  body?: unknown;
  auth?: boolean;
  raw?: boolean;
};

async function request<T>(path: string, options: RequestOptions = {}): Promise<T> {
  const { body, auth = true, raw = false, headers, ...rest } = options;
  const finalHeaders = new Headers(headers);

  let payload: BodyInit | undefined;
  if (body instanceof FormData) {
    payload = body; // let the browser set the multipart boundary
  } else if (body !== undefined) {
    finalHeaders.set("Content-Type", "application/json");
    payload = JSON.stringify(body);
  }

  if (auth) {
    const token = getToken();
    if (token) finalHeaders.set("Authorization", `Bearer ${token}`);
  }

  let response: Response;
  try {
    response = await fetch(`${API}${path}`, { ...rest, headers: finalHeaders, body: payload });
  } catch {
    throw new ApiError(
      0,
      "network_error",
      "Could not reach the server. Check that the backend is running and try again.",
    );
  }

  if (response.status === 204) return undefined as T;

  if (!response.ok) {
    let code = "http_error";
    let message = `Request failed (${response.status}).`;
    let details: unknown;
    try {
      const parsed = (await response.json()) as ApiErrorBody;
      if (parsed?.error) {
        code = parsed.error.code ?? code;
        message = parsed.error.message ?? message;
        details = parsed.error.details;
      }
    } catch {
      /* the body was not JSON; keep the generic message */
    }
    if (response.status === 401) setToken(null);
    throw new ApiError(response.status, code, message, details);
  }

  if (raw) return (await response.blob()) as T;
  return absolutiseMediaUrls(await response.json()) as T;
}

/** Fields the backend fills with a link to a stored file. */
const URL_FIELDS = new Set(["url", "thumbnail_url", "download_url"]);

/**
 * Rewrite relative media links to absolute ones.
 *
 * Local storage returns `/api/v1/files/...` so the backend never has to know which
 * hostname the browser used. Doing the join here — once, at the boundary — means no
 * component has to remember to, and a `<canvas>` drawing the image gets a URL whose
 * origin matches the one the CORS headers were issued for.
 */
function absolutiseMediaUrls<T>(value: T): T {
  if (Array.isArray(value)) return value.map((item) => absolutiseMediaUrls(item)) as T;
  if (value === null || typeof value !== "object") return value;

  const record = value as Record<string, unknown>;
  for (const [key, entry] of Object.entries(record)) {
    if (URL_FIELDS.has(key) && typeof entry === "string" && entry.startsWith("/")) {
      record[key] = `${API_BASE}${entry}`;
    } else if (entry && typeof entry === "object") {
      record[key] = absolutiseMediaUrls(entry);
    }
  }
  return value;
}

/** Upload with real progress events — `fetch` cannot report upload progress. */
function upload<T>(
  path: string,
  form: FormData,
  onProgress?: (percent: number) => void,
  method: "POST" | "PUT" = "POST",
): Promise<T> {
  return new Promise<T>((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    xhr.open(method, `${API}${path}`);
    const token = getToken();
    if (token) xhr.setRequestHeader("Authorization", `Bearer ${token}`);

    xhr.upload.addEventListener("progress", (event) => {
      if (onProgress && event.lengthComputable) {
        onProgress(Math.round((event.loaded / event.total) * 100));
      }
    });

    xhr.addEventListener("load", () => {
      let parsed: unknown;
      try {
        parsed = JSON.parse(xhr.responseText);
      } catch {
        parsed = undefined;
      }
      if (xhr.status >= 200 && xhr.status < 300) {
        onProgress?.(100);
        resolve(parsed as T);
      } else {
        const body = parsed as ApiErrorBody | undefined;
        if (xhr.status === 401) setToken(null);
        reject(
          new ApiError(
            xhr.status,
            body?.error?.code ?? "http_error",
            body?.error?.message ?? `Upload failed (${xhr.status}).`,
            body?.error?.details,
          ),
        );
      }
    });
    xhr.addEventListener("error", () =>
      reject(new ApiError(0, "network_error", "The upload could not reach the server.")),
    );
    xhr.addEventListener("abort", () =>
      reject(new ApiError(0, "aborted", "The upload was cancelled.")),
    );

    xhr.send(form);
  });
}

export const api = {
  // ---------------------------------------------------------------- auth --
  register: (email: string, password: string, fullName: string) =>
    request<AuthResponse>("/auth/register", {
      method: "POST",
      auth: false,
      body: { email, password, full_name: fullName },
    }),

  login: (email: string, password: string) =>
    request<AuthResponse>("/auth/login", {
      method: "POST",
      auth: false,
      body: { email, password },
    }),

  me: () => request<User>("/auth/me"),

  // ------------------------------------------------------------- catalog --
  capabilities: () => request<Capabilities>("/capabilities", { auth: false }),
  styles: () => request<StylePreset[]>("/styles", { auth: false }),
  templates: (category?: string) =>
    request<{ categories: string[]; items: TemplateSummary[] }>(
      `/templates${category ? `?category=${encodeURIComponent(category)}` : ""}`,
      { auth: false },
    ),
  formats: () =>
    request<{ formats: FormatOption[]; platforms: PlatformOption[] }>("/formats", { auth: false }),
  options: () => request<EditorOptions>("/options", { auth: false }),

  // ------------------------------------------------------------ projects --
  listProjects: (params: { limit?: number; offset?: number; search?: string } = {}) => {
    const query = new URLSearchParams();
    if (params.limit) query.set("limit", String(params.limit));
    if (params.offset) query.set("offset", String(params.offset));
    if (params.search) query.set("search", params.search);
    const suffix = query.toString() ? `?${query}` : "";
    return request<Page<ProjectSummary>>(`/projects${suffix}`);
  },

  createProject: (payload: {
    name: string;
    description?: string;
    topic?: string;
    platform?: string;
    language?: string;
    format?: string | null;
    style?: string;
    template_key?: string | null;
    target_duration?: number | null;
  }) => request<ProjectDetail>("/projects", { method: "POST", body: payload }),

  getProject: (id: string) => request<ProjectDetail>(`/projects/${id}`),

  updateProject: (id: string, payload: Record<string, unknown>) =>
    request<ProjectDetail>(`/projects/${id}`, { method: "PATCH", body: payload }),

  duplicateProject: (id: string) =>
    request<ProjectDetail>(`/projects/${id}/duplicate`, { method: "POST" }),

  deleteProject: (id: string) => request<void>(`/projects/${id}`, { method: "DELETE" }),

  // --------------------------------------------------------------- media --
  uploadImages: (projectId: string, files: File[], onProgress?: (percent: number) => void) => {
    const form = new FormData();
    files.forEach((file) => form.append("files", file));
    return upload<MediaItem[]>(`/projects/${projectId}/media`, form, onProgress);
  },

  replaceImage: (projectId: string, mediaId: string, file: File, onProgress?: (p: number) => void) => {
    const form = new FormData();
    form.append("file", file);
    return upload<MediaItem>(`/projects/${projectId}/media/${mediaId}`, form, onProgress, "PUT");
  },

  listMedia: (projectId: string) => request<MediaItem[]>(`/projects/${projectId}/media`),

  reorderMedia: (projectId: string, mediaIds: string[]) =>
    request<MediaItem[]>(`/projects/${projectId}/media/reorder`, {
      method: "POST",
      body: { media_ids: mediaIds },
    }),

  cropMedia: (
    projectId: string,
    mediaId: string,
    rect: { x: number; y: number; width: number; height: number },
  ) =>
    request<MediaItem>(`/projects/${projectId}/media/${mediaId}/crop`, {
      method: "POST",
      body: rect,
    }),

  deleteMedia: (projectId: string, mediaId: string) =>
    request<void>(`/projects/${projectId}/media/${mediaId}`, { method: "DELETE" }),

  // --------------------------------------------------------------- audio --
  uploadAudio: (projectId: string, file: File, onProgress?: (p: number) => void) => {
    const form = new FormData();
    form.append("file", file);
    return upload<AudioTrack>(`/projects/${projectId}/audio`, form, onProgress);
  },

  updateAudio: (projectId: string, payload: Record<string, unknown>) =>
    request<AudioTrack>(`/projects/${projectId}/audio`, { method: "PATCH", body: payload }),

  // -------------------------------------------------------------- scenes --
  listScenes: (projectId: string) => request<Scene[]>(`/projects/${projectId}/scenes`),

  createScene: (projectId: string, payload: { media_id?: string | null; position?: number }) =>
    request<Scene[]>(`/projects/${projectId}/scenes`, { method: "POST", body: payload }),

  updateScene: (projectId: string, sceneId: string, payload: Record<string, unknown>) =>
    request<Scene>(`/projects/${projectId}/scenes/${sceneId}`, { method: "PATCH", body: payload }),

  reorderScenes: (projectId: string, sceneIds: string[]) =>
    request<Scene[]>(`/projects/${projectId}/scenes/reorder`, {
      method: "POST",
      body: { scene_ids: sceneIds },
    }),

  duplicateScene: (projectId: string, sceneId: string) =>
    request<Scene[]>(`/projects/${projectId}/scenes/${sceneId}/duplicate`, { method: "POST" }),

  deleteScene: (projectId: string, sceneId: string) =>
    request<Scene[]>(`/projects/${projectId}/scenes/${sceneId}`, { method: "DELETE" }),

  // ----------------------------------------------------------------- ai --
  generatePlan: (
    projectId: string,
    payload: {
      instruction?: string;
      style?: string | null;
      template_key?: string | null;
      target_duration?: number | null;
      include_voiceover?: boolean;
      use_ai?: boolean;
      apply?: boolean;
    },
  ) => request<PlanResponse>(`/projects/${projectId}/plan/generate`, { method: "POST", body: payload }),

  getPlan: (projectId: string) => request<PlanResponse>(`/projects/${projectId}/plan`),

  applyPlan: (projectId: string, plan: VideoPlan) =>
    request<ProjectDetail>(`/projects/${projectId}/plan`, { method: "PUT", body: { plan } }),

  applyTemplate: (projectId: string, templateKey: string, targetDuration?: number) => {
    const suffix = targetDuration ? `?target_duration=${targetDuration}` : "";
    return request<ProjectDetail>(
      `/projects/${projectId}/apply-template/${templateKey}${suffix}`,
      { method: "POST" },
    );
  },

  // ---------------------------------------------------------- voice-over --
  getVoiceOver: (projectId: string) => request<VoiceOver>(`/projects/${projectId}/voiceover`),

  updateVoiceOver: (projectId: string, payload: Record<string, unknown>) =>
    request<VoiceOver>(`/projects/${projectId}/voiceover`, { method: "PATCH", body: payload }),

  draftVoiceOverScript: (projectId: string) =>
    request<VoiceOver>(`/projects/${projectId}/voiceover/script`, { method: "POST" }),

  generateVoiceOver: (projectId: string) =>
    request<VoiceOver>(`/projects/${projectId}/voiceover/generate`, { method: "POST" }),

  generateAiMotion: (projectId: string, sceneId: string, prompt: string) =>
    request<{ status: string; message: string; scene_id: string }>(
      `/projects/${projectId}/scenes/${sceneId}/ai-motion?prompt=${encodeURIComponent(prompt)}`,
      { method: "POST" },
    ),

  /**
   * Queue this scene's still image. The prompt is stored on the scene before the
   * job starts, so regenerating reproduces the same shot; sending an empty one
   * deliberately re-runs the prompt already saved there.
   */
  generateSceneImage: (projectId: string, sceneId: string, prompt: string) =>
    request<{ status: string; message: string; scene_id: string; provider: string }>(
      `/projects/${projectId}/scenes/${sceneId}/image?prompt=${encodeURIComponent(prompt)}`,
      { method: "POST" },
    ),

  /** Takes no body: the clip is on the scene and the narration on the project. */
  generateLipsync: (projectId: string, sceneId: string) =>
    request<{ status: string; message: string; scene_id: string; provider: string }>(
      `/projects/${projectId}/scenes/${sceneId}/lipsync`,
      { method: "POST" },
    ),

  // ---------------------------------------------------------- characters --
  listCharacters: () => request<Character[]>("/characters"),

  getCharacter: (id: string) => request<Character>(`/characters/${id}`),

  createCharacter: (payload: CharacterDraft) =>
    request<Character>("/characters", { method: "POST", body: payload }),

  updateCharacter: (id: string, payload: Partial<CharacterDraft>) =>
    request<Character>(`/characters/${id}`, { method: "PATCH", body: payload }),

  deleteCharacter: (id: string) => request<void>(`/characters/${id}`, { method: "DELETE" }),

  /** The reference picture providers use to keep the subject recognisable. */
  uploadCharacterReference: (id: string, file: File, onProgress?: (p: number) => void) => {
    const form = new FormData();
    form.append("file", file);
    return upload<Character>(`/characters/${id}/reference`, form, onProgress);
  },

  // ---------------------------------------------------------------- jobs --
  /**
   * Everything the project has generated or is generating, in one call.
   *
   * `activeOnly` is for the polling path: while work is in flight the editor only
   * needs what is still running, and asking for the whole history every 1.2 s
   * would grow with the project instead of staying flat.
   */
  projectJobs: (projectId: string, options: { activeOnly?: boolean; limit?: number } = {}) => {
    const query = new URLSearchParams();
    if (options.activeOnly) query.set("active_only", "true");
    if (options.limit) query.set("limit", String(options.limit));
    const suffix = query.toString() ? `?${query}` : "";
    return request<ProjectJobs>(`/projects/${projectId}/jobs${suffix}`);
  },

  getJob: (jobId: string) => request<GenerationJob>(`/jobs/${jobId}`),

  // -------------------------------------------------------------- render --
  startRender: (projectId: string) =>
    request<RenderJob>(`/projects/${projectId}/render`, { method: "POST" }),

  listRenders: (projectId: string) => request<RenderJob[]>(`/projects/${projectId}/renders`),

  getRenderJob: (jobId: string) => request<RenderJob>(`/render-jobs/${jobId}`),

  cancelRenderJob: (jobId: string) =>
    request<RenderJob>(`/render-jobs/${jobId}/cancel`, { method: "POST" }),

  downloadUrl: (jobId: string) => `${API}/render-jobs/${jobId}/download`,

  downloadRender: (jobId: string) => request<Blob>(`/render-jobs/${jobId}/download`, { raw: true }),
};
