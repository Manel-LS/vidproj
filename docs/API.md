# Reelcraft API

Base URL: `http://localhost:8000/api/v1`
Interactive reference: `http://localhost:8000/docs` (OpenAPI at `/openapi.json`)

Authenticate with `Authorization: Bearer <access_token>` on every endpoint except
`/auth/register`, `/auth/login` and the read-only catalogue.

## Errors

Every failure returns the same envelope, with a message written for the person who
will read it:

```json
{
  "error": {
    "code": "validation_error",
    "message": "Please upload at least one image.",
    "details": [{ "field": "scenes", "problem": "List should have at least 1 item" }]
  }
}
```

| Status | Code | Meaning |
|---|---|---|
| 401 | `authentication_error` | Missing, invalid or expired token |
| 403 | `permission_denied` | Authenticated but not allowed |
| 404 | `not_found` | Missing — or owned by someone else |
| 409 | `conflict` | e.g. a render is already running for this project |
| 422 | `validation_error` | Request or plan failed validation; `details` lists fields |
| 429 | `rate_limited` | `details.retry_after` holds the seconds to wait |
| 503 | `provider_unavailable` | An optional capability is not configured |
| 500 | `render_failed`, `internal_error` | Something went wrong server-side |

---

## Auth

| Method | Path | Notes |
|---|---|---|
| `POST` | `/auth/register` | `{email, password, full_name}` → token + user (201) |
| `POST` | `/auth/login` | `{email, password}` → token + user |
| `GET` | `/auth/me` | The signed-in user |

Passwords must be at least 8 characters and at most 72 bytes. Sign-in and sign-up
share a tighter rate-limit bucket than the rest of the API.

---

## Catalogue (no auth)

| Method | Path | Notes |
|---|---|---|
| `GET` | `/capabilities` | **The provider matrix.** Which of rendering, AI planning, voice-over and AI Motion are configured, plus limits and resolved fonts. The UI reads this to decide what to enable. |
| `GET` | `/styles` | The 10 style presets with their gradients, pacing and typography |
| `GET` | `/templates?category=` | Template blueprints and their categories |
| `GET` | `/formats` | Output formats and target platforms |
| `GET` | `/options` | Every enum the editor offers (animations, transitions, text options) |
| `GET` | `/plan-schema` | JSON Schema for a `VideoPlan`, so a client can validate before submitting |

---

## Projects

| Method | Path | Notes |
|---|---|---|
| `GET` | `/projects?limit=&offset=&search=` | Paged list of your projects |
| `POST` | `/projects` | Create (201). `{name, description?, topic?, platform?, format?, style?, template_key?, target_duration?}` |
| `GET` | `/projects/{id}` | Full detail: scenes, media, audio, voice-over, timings |
| `PATCH` | `/projects/{id}` | Partial update |
| `POST` | `/projects/{id}/duplicate` | Deep copy including media blobs (201) |
| `DELETE` | `/projects/{id}` | Delete the project and its files (204) |

---

## Media

| Method | Path | Notes |
|---|---|---|
| `POST` | `/projects/{id}/media` | Multipart `files[]`. Validates, optimises, analyses, and **creates a scene per image** (201) |
| `GET` | `/projects/{id}/media` | All media in the project |
| `POST` | `/projects/{id}/media/reorder` | `{media_ids: [...]}` |
| `PUT` | `/projects/{id}/media/{media_id}` | Replace the bytes, **keeping the id** so scenes still resolve |
| `POST` | `/projects/{id}/media/{media_id}/crop` | `{x, y, width, height}` in normalised [0,1] coordinates |
| `DELETE` | `/projects/{id}/media/{media_id}` | Scenes using it keep their timing and text; they just lose the image (204) |

Images: JPG, PNG, WEBP, 15 MB default. Audio: MP3, WAV, 25 MB default. Both limits
are configurable and reported by `/capabilities`.

`url` and `thumbnail_url` are relative (`/api/v1/files/...`) with local storage, so
they resolve against whatever host serves the API; with S3 they are absolute.

## Audio

| Method | Path | Notes |
|---|---|---|
| `POST` | `/projects/{id}/audio` | Multipart `file` — MP3 or WAV |
| `PATCH` | `/projects/{id}/audio` | `{volume?, fade_in?, fade_out?, start_offset?, loop?, clear?}` |
| `GET` | `/projects/{id}/audio/library` | Royalty-free catalogue slot; empty until one is licensed |

---

## Scenes

| Method | Path | Notes |
|---|---|---|
| `GET` | `/projects/{id}/scenes` | Scenes with their absolute `start_time` on the timeline |
| `POST` | `/projects/{id}/scenes` | Add a scene (201) |
| `PATCH` | `/projects/{id}/scenes/{scene_id}` | Partial update: duration, animation, focal point, transition, texts |
| `POST` | `/projects/{id}/scenes/reorder` | `{scene_ids: [...]}` — must list every scene exactly once |
| `POST` | `/projects/{id}/scenes/{scene_id}/duplicate` | (201) |
| `DELETE` | `/projects/{id}/scenes/{scene_id}` | Refused if it is the last scene |

Every write round-trips through the domain `PlanScene` model, so the database can
never hold a scene the renderer would reject. The first scene never carries an
incoming transition — the API enforces this on create, update, reorder and delete.

---

## Planning and AI

| Method | Path | Notes |
|---|---|---|
| `POST` | `/projects/{id}/plan/generate` | The "Create with AI" call. `{instruction?, style?, template_key?, target_duration?, include_voiceover?, use_ai?, apply?}` |
| `GET` | `/projects/{id}/plan` | The project's current plan |
| `PUT` | `/projects/{id}/plan` | Submit a hand-edited plan; validated before it is applied |
| `POST` | `/projects/{id}/apply-template/{key}` | Rebuild the scenes from a template |

`plan/generate` **never fails because the AI is down.** The response says which path
ran:

```json
{
  "plan": { "...": "..." },
  "generated_by": "heuristic",
  "ai_used": false,
  "notice": "AI generation is temporarily unavailable. Your plan was built with the built-in planner — you can still edit every scene.",
  "applied": true,
  "total_duration": 15.0,
  "scene_start_times": [0.0, 3.8, 7.4, 11.1]
}
```

Set `apply: false` to preview a plan without touching the project.

## Voice-over

| Method | Path | Notes |
|---|---|---|
| `GET` | `/projects/{id}/voiceover` | Current script, status and audio |
| `PATCH` | `/projects/{id}/voiceover` | Edit the script, voice or levels |
| `POST` | `/projects/{id}/voiceover/script` | Draft a script from the scenes' on-screen copy |
| `POST` | `/projects/{id}/voiceover/generate` | Queue synthesis (202), or **503** with an explanation if no TTS provider is configured |

## AI Motion

| Method | Path | Notes |
|---|---|---|
| `POST` | `/projects/{id}/scenes/{scene_id}/ai-motion?prompt=` | Queue image-to-video generation (202), or **503** if no provider is configured |

When a clip is generated the renderer uses it for that scene instead of the local
animation; transitions, text and audio are unchanged.

---

## Rendering

| Method | Path | Notes |
|---|---|---|
| `POST` | `/projects/{id}/render` | Snapshot the plan and queue the render. Returns **202 immediately** |
| `GET` | `/projects/{id}/renders` | Render history |
| `GET` | `/render-jobs/{job_id}` | Poll: `status`, `progress` (0–100), `stage`, `message` |
| `POST` | `/render-jobs/{job_id}/cancel` | Cancel a queued or running render |
| `GET` | `/render-jobs/{job_id}/download` | The MP4, as an attachment |

Statuses are `queued → processing → completed | failed | cancelled`. Progress is
weighted across the pipeline: scene animation 6–62%, transitions 62–84%, audio 84–96%,
finalising 96–100%. Jobs interrupted by a server restart are marked failed on the next
boot rather than being left to poll forever.

---

## Files

| Method | Path | Notes |
|---|---|---|
| `GET` | `/files/{key}` | Serves stored blobs in development. With `STORAGE_PROVIDER=s3` these are served by object storage instead. |

Responses carry a fixed content type and `X-Content-Type-Options: nosniff`, and the
key is resolved through the storage provider, which refuses to leave its root.

---

## The VideoPlan

The contract shared by the planner, the editor and the renderer. Fetch the full JSON
Schema from `/plan-schema`.

```json
{
  "version": 1,
  "format": "9:16",
  "fps": 30,
  "style": "tiktok_trend",
  "mode": "standard",
  "hook": "Looking for the perfect school supplies?",
  "cta": "Shop now",
  "caption": "Everything you need in one place",
  "hashtags": ["backtoschool", "stationery"],
  "generated_by": "heuristic",
  "scenes": [
    {
      "id": "scene-1",
      "order": 0,
      "media_id": "a1b2c3",
      "duration": 3.0,
      "animation": "zoom_in",
      "animation_intensity": 1.6,
      "focus_x": 0.5,
      "focus_y": 0.45,
      "transition": "none",
      "transition_duration": 0.0,
      "background_color": "#000000",
      "texts": [
        {
          "role": "title",
          "content": "Everything you need in one place",
          "position": "lower_third",
          "align": "center",
          "animation": "rise",
          "font_family": "sans_bold",
          "font_size": 88,
          "color": "#FFFFFF",
          "background": "pill",
          "background_opacity": 0.55,
          "start": 0.15
        }
      ]
    }
  ],
  "audio": { "media_id": "d4e5f6", "volume": 0.7, "fade_in": 0.6, "fade_out": 1.0, "loop": true },
  "voiceover": { "enabled": false, "script": "", "volume": 1.0, "duck_music_to": 0.28 }
}
```

Validation rules worth knowing:

- 1–40 scenes, each 0.4–30 s, 180 s total.
- A transition is clamped to 90% of the shorter of the two scenes it joins.
- The first scene's transition is forced to `none`.
- Text is clamped so it cannot outlive its scene.
- Colours must be `#RGB`, `#RRGGBB` or `#RRGGBBAA`.
- Unknown fields are rejected outright, so a malformed AI response cannot smuggle
  anything into the renderer.
