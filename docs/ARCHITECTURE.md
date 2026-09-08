# Reelcraft — Architecture

AI Short-Form Video Creator from Images.

## 1. Layering rule

```
UI (Next.js components)          -> presentation only, no business logic
  |
API (FastAPI routers)            -> auth, DTO validation, HTTP concerns only
  |
Application Services             -> use-cases, orchestration, transactions
  |
Domain                           -> VideoPlan, Scene, animation math, style presets.
  |                                 Pure Python, no I/O, no framework imports.
Infrastructure                   -> ffmpeg, storage, llm, tts, i2v, jobs, db
```

Enforced conventions:
- `app/domain/**` imports nothing from `app/api`, `app/models`, `app/infrastructure`.
- Routers never build ffmpeg commands and never call providers directly.
- Providers are resolved through factories in `app/infrastructure/<x>/factory.py`.

## 2. Provider abstractions

| Interface | Location | Implementations | Fallback when unconfigured |
|---|---|---|---|
| `StorageProvider` | `infrastructure/storage` | `LocalStorageProvider`, `S3StorageProvider` | Local (always works) |
| `LLMProvider` | `infrastructure/llm` | `AnthropicLLMProvider`, `OpenAICompatibleLLMProvider`, `HeuristicPlanner` | `HeuristicPlanner` — a real rule-based planner, not a stub |
| `VoiceProvider` | `infrastructure/tts` | `ElevenLabsVoiceProvider`, `OpenAITTSVoiceProvider` | `NullVoiceProvider` — reports unavailable, UI disables the feature |
| `ImageToVideoProvider` | `infrastructure/i2v` | `RunwayProvider`, `KlingProvider`, `LumaProvider` | `NullImageToVideoProvider` — AI Motion mode disabled gracefully |
| `JobQueue` | `infrastructure/jobs` | `CeleryJobQueue` (Redis) | `ThreadPoolJobQueue` — in-process worker, same semantics |
| `RenderEngine` | `infrastructure/render` | `FFmpegRenderEngine` | — (ffmpeg binary auto-resolved) |

Every provider exposes `is_available()`; `GET /api/v1/capabilities` reports the live
matrix so the frontend can disable features instead of failing at click time.

## 3. Rendering pipeline (FFmpeg)

The LLM never touches ffmpeg. It emits a JSON `VideoPlan`, validated by Pydantic,
which the deterministic compiler turns into ffmpeg arguments (argv lists, never shell
strings — no command injection surface). User text never enters a filter string: it is
rasterised by Pillow into RGBA PNG layers.

```
VideoPlan (validated)
  |
  |-- per scene ------------------------------------------------.
  |     1. Pillow: fit image to WxH*SS (supersample, cover-crop) |
  |     2. ffmpeg zoompan: linear (zoom, cx, cy) interpolation   |  -> scene_N.mp4
  |     3. optional rotate (render 1.06x, rotate, centre-crop)   |
  |     4. Pillow text layers -> overlay w/ time expressions     |
  |        (typewriter/pop/zoom -> short PNG seq + tpad clone)   |
  |__________________________________________________________'
  |
  |-- xfade chain between consecutive scenes (offset accumulation)
  |-- audio graph: music (aloop/atrim/afade/volume) + voiceover -> amix
  |-- mux -> H.264 yuv420p + AAC -> 1080x1920 MP4 (faststart)
```

Animation is a pure-domain function `KenBurns(start, end, duration)` producing
`(zoom, center_x, center_y)` keyframes; the same math is re-implemented in TypeScript
for the browser preview so preview and render agree.

## 4. Render job lifecycle

`QUEUED -> PROCESSING -> COMPLETED | FAILED`, with `progress` 0..100 persisted after
each pipeline stage (scenes weighted 0-60, transitions 60-80, audio 80-90, mux 90-100).
The client polls `GET /render-jobs/{id}`. Cancellation sets a flag the worker checks
between stages. Temp dirs are removed in a `finally` block.

## 5. Data model

```
User 1--* Project 1--* Media
                1--* Scene 1--* TextOverlay (embedded JSON)
                1--0..1 AudioTrack
                1--0..1 VoiceOver
                1--* RenderJob
Template (global or user-owned)
```

## 6. Phases

1. Auth, projects, media upload/ordering
2. Scenes, animations, transitions, text, templates
3. FFmpeg render, preview, export
4. AI planner
5. Voice-over
6. AI Motion (image-to-video providers)
