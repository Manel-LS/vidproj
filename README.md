# Reelcraft

Turn a handful of photos into a finished short-form video: animated scenes,
transitions, captions, music and voice-over, rendered by FFmpeg to a
1080 × 1920 H.264 MP4 ready for TikTok, Reels and Shorts.

It is a working application, not a prototype. Uploads are validated and re-encoded,
scenes are edited against a validated domain model, and the render is a real FFmpeg
pipeline that produces a file you can play.

---

## What it does

| | |
|---|---|
| **Formats** | 9:16 (default, 1080 × 1920), 1:1, 16:9, 4:5 — TikTok, Reels, Shorts, Stories |
| **Animation** | Zoom in/out, slow zoom, dynamic zoom, pan in four directions, Ken Burns, slight rotation, parallax |
| **Transitions** | Fade, cross dissolve, slide left/right, zoom, blur, push, wipe, hard cut |
| **Text** | Title / subtitle / CTA / caption with font, size, weight, position, alignment, letter spacing, background scrim, opacity, and fade / slide / pop / typewriter / zoom / rise animations |
| **Scripts** | Latin and right-to-left (Arabic, Hebrew): letters are shaped and joined, and the font is chosen per script so no style renders empty boxes |
| **Audio** | Upload MP3 or WAV, volume, fade in/out, start offset, auto-loop to the video length |
| **AI planning** | Scene order, durations, copy, camera moves and transitions — Claude or any OpenAI-compatible endpoint, with a deterministic planner as the fallback |
| **Voice-over** | Script drafting, then synthesis through a pluggable TTS provider — including a **free, key-less** option with 300+ voices (Arabic and Tunisian Arabic included) |
| **AI Motion** | Optional image-to-video generation through Runway, Kling or Luma |
| **Styles** | 10 presets, from luxury slow-burn to TikTok whip-cuts |
| **Templates** | 10 scene blueprints (product, sale, real estate, before/after, educational, …) |

**Everything optional degrades gracefully.** With no API keys at all the app still
plans, edits and renders videos — it just tells you which AI features are off and why.
`GET /api/v1/capabilities` is the single source of truth the UI reads for this.

---

## Quick start

Requirements: **Python 3.12+** and **Node 20+**. FFmpeg is resolved automatically
(system PATH first, then the binary bundled with `imageio-ffmpeg`), so there is
nothing else to install. A database server and Redis are optional in development —
with no `DATABASE_URL` the app uses a local SQLite file.

```bash
# 1. Backend
cd backend
python -m venv .venv
.venv/Scripts/activate          # Windows;  source .venv/bin/activate on macOS/Linux
pip install -r requirements-dev.txt
python -m app.seed              # creates the schema and a demo project
uvicorn app.main:app --reload --port 8000

# 2. Frontend (in a second terminal)
cd frontend
npm install
npm run dev
```

Open <http://localhost:3000> and sign in with the demo account the seeder printed
(`demo@reelcraft.app` / `demo1234`), or create your own.

API documentation is at <http://localhost:8000/docs>.

### Using MySQL or MariaDB

Both are supported alongside PostgreSQL. Create the database, point `DATABASE_URL`
at it in `backend/.env`, then migrate and seed:

```sql
CREATE DATABASE reelcraft CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
```

```ini
# backend/.env  — XAMPP/WAMP defaults to user `root` with no password
DATABASE_URL=mysql+pymysql://root@127.0.0.1:3306/reelcraft
```

```bash
cd backend
alembic upgrade head      # MySQL is migrated with Alembic, not auto-created
python -m app.seed
```

A bare `mysql://` URL is rewritten to use PyMySQL — a pure-Python driver, so no C
toolchain is needed on Windows — and `charset=utf8mb4` is appended automatically.
`GET /health` reports which backend is live.

Two details the code handles for you: MySQL's `DATETIME` carries no time zone, so
timestamps are stored as UTC and re-attached on read (otherwise every project would
appear created hours ago); and MySQL's `utf8` is a three-byte encoding that would
silently drop the emoji in captions, which is why `utf8mb4` is forced end to end.

### With Docker

The compose stack is the production shape: PostgreSQL, Redis, a Celery worker and
the API and web containers.

```bash
cp .env.example .env            # set SECRET_KEY at minimum
docker compose up --build
docker compose exec api alembic upgrade head
docker compose exec api python -m app.seed
```

---

## The workflow

1. **Create a project** — name, description, target platform.
2. **Upload images** — drag and drop; each becomes a scene. Reorder, crop, replace or delete.
3. **Pick a style** — sets pacing, camera moves, transitions and typography.
4. **Generate the plan** — the planner writes the hook, the per-scene copy and the CTA,
   and chooses a camera move and transition for each shot.
5. **Edit** — every scene's duration, animation, focal point, transition and text is editable.
6. **Preview** — a canvas player that reimplements the render pipeline in the browser.
7. **Render** — queued in the background; poll for progress, then download the MP4.

---

## Architecture

```
UI (Next.js)  →  API (FastAPI)  →  Application services  →  Domain  →  Infrastructure
```

The rule the codebase holds to: **`app/domain/**` imports nothing from the API, the
ORM models or infrastructure.** Routers do not build FFmpeg commands; services do not
know which AI provider is configured.

```
backend/app/
  core/            config, errors, security, logging
  domain/          VideoPlan, animation math, style presets, templates, planner  ← pure
  models/          SQLAlchemy entities
  schemas/         Pydantic request/response DTOs
  services/        use-cases: projects, media, scenes, plans, renders, workers
  api/v1/routes/   thin HTTP controllers
  infrastructure/
    storage/       StorageProvider          — local | S3-compatible
    llm/           LLMProvider              — Anthropic | OpenAI-compatible | heuristic
    tts/           VoiceProvider            — ElevenLabs | OpenAI | none
    i2v/           ImageToVideoProvider     — Runway | Kling | Luma | none
    render/        FFmpeg engine, filters, image prep
    imaging/       Pillow analysis, text rasterisation, fonts
    jobs/          JobQueue                 — Celery/Redis | in-process threads

frontend/src/
  app/             routes (auth, dashboard, create, templates, media, settings, editor)
  components/      UI kit, media, editor panels, timeline, preview
  lib/video/       the animation engine and canvas player, mirrored from the backend
  lib/api/         the single typed API client
```

See [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) for the rendering pipeline and
provider matrix, and [`docs/API.md`](docs/API.md) for the endpoint reference.

### The rendering pipeline

The LLM never touches FFmpeg. It emits a JSON `VideoPlan`, validated by Pydantic,
which a deterministic compiler turns into argv lists — never shell strings.
User-supplied text never enters a filtergraph: it is rasterised to RGBA PNG layers by
Pillow first, which removes the entire filter-escaping injection surface and gives
better typography than `drawtext`.

```
VideoPlan (validated)
  ├── per scene: cover-crop → zoompan (linear zoom/centre interpolation) → text overlays  → scene_N.mp4
  ├── xfade / concat chain between consecutive scenes                                     → video.mp4
  └── music (loop, trim, fade, duck) + voice-over → amix → mux with -c:v copy              → output.mp4
```

Supersampling the source before `zoompan` is what removes the jitter that filter is
known for. The same animation math is mirrored in TypeScript for the browser preview,
and a [parity test](frontend/src/lib/video/animation.test.ts) asserts the two agree —
regenerate its fixture with `python backend/scripts/export_animation_parity.py`.

---

## Configuration

Every setting lives in [`.env.example`](.env.example); nothing outside
`app/core/config.py` reads the environment directly.

| Variable | Effect if unset |
|---|---|
| `SECRET_KEY` | Random per boot in development; **required** in production |
| `DATABASE_URL` | Falls back to a local SQLite file. PostgreSQL and MySQL/MariaDB are both supported |
| `ANTHROPIC_API_KEY` / `OPENAI_API_KEY` | AI planning off; the deterministic planner runs and the UI says so |
| `TTS_PROVIDER` | Voice-over disabled, with an explanation in the UI. `edge` needs no key at all |
| `I2V_PROVIDER` | AI Motion disabled; Standard mode is unaffected |
| `JOB_QUEUE` | In-process thread pool instead of Celery |
| `STORAGE_PROVIDER` | Local disk instead of S3 |

The app refuses to start in `ENVIRONMENT=production` without an explicit `SECRET_KEY`,
a real `DATABASE_URL` (PostgreSQL or MySQL — not the SQLite fallback), and
`DEBUG=false`.

---

## Testing

```bash
cd backend  && pytest              # 142 tests
cd frontend && npm test            # 120 tests
cd frontend && npm run lint        # ESLint flat config
cd frontend && npm run typecheck   # tsc --noEmit
```

The backend suite calls FFmpeg for real: every animation, every transition and every
text animation is rendered and the output verified. It ends with a full journey —
create a project, upload images, generate a plan, edit a scene, render, and confirm
the downloaded MP4 opens and has the planned duration.

It runs on SQLite by default so it needs no services. Point it at a scratch database
to run the identical suite against the engine you deploy on — the target is dropped
and recreated, so never aim it at real data:

```bash
TEST_DATABASE_URL=mysql+pymysql://root@127.0.0.1:3306/reelcraft_test pytest
```

---

## Security

- JWT auth; bcrypt password hashing; constant-time comparison on sign-in.
- Every project, media file and render job is scoped to its owner — a resource owned
  by someone else returns 404, so ownership cannot be probed.
- Uploads are validated by **decoding** them, not by trusting the declared MIME type
  or extension, then re-encoded through Pillow, which discards EXIF and any embedded
  payload. Audio is checked against magic numbers.
- FFmpeg is invoked with argv lists and `shell=False`; no user string reaches a
  filtergraph.
- Storage keys are sanitised and resolved inside the storage root, so path traversal
  cannot escape it.
- Per-IP rate limiting, with a tighter bucket on sign-in and sign-up.
- Render temp directories are removed in a `finally` block, including on failure.
- API keys are read server-side only and never sent to the browser.

---

## Licensing note

Reelcraft ships **no bundled music**. The library endpoint exists so a licensed
catalogue can be connected, and returns an empty list until one is. Sample images and
the demo audio bed are generated procedurally at runtime, so there is nothing
copyrighted in the repository.
