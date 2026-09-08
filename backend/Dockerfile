# syntax=docker/dockerfile:1

# ---------------------------------------------------------------- builder ---
FROM python:3.12-slim AS builder

ENV PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# psycopg[binary] ships wheels, so no build toolchain is needed for the default
# dependency set. Kept as its own stage so the runtime image has no pip cache.
COPY requirements.txt ./
RUN python -m venv /opt/venv \
 && /opt/venv/bin/pip install --upgrade pip \
 && /opt/venv/bin/pip install -r requirements.txt

# ---------------------------------------------------------------- runtime ---
FROM python:3.12-slim AS runtime

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PATH="/opt/venv/bin:$PATH"

# ffmpeg does the rendering; the DejaVu fonts are what Pillow rasterises text with.
# `imageio-ffmpeg` would supply a fallback binary, but a system ffmpeg is faster to
# start and easier to pin.
RUN apt-get update \
 && apt-get install -y --no-install-recommends \
      ffmpeg \
      fonts-dejavu-core \
      fonts-liberation \
      curl \
 && rm -rf /var/lib/apt/lists/*

COPY --from=builder /opt/venv /opt/venv

WORKDIR /app

# Run unprivileged, and own the directories the app writes to.
RUN useradd --create-home --uid 10001 reelcraft \
 && mkdir -p /app/var/storage /app/var/work \
 && chown -R reelcraft:reelcraft /app

COPY --chown=reelcraft:reelcraft . .

USER reelcraft

ENV STORAGE_LOCAL_ROOT=/app/var/storage \
    RENDER_WORK_DIR=/app/var/work

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
  CMD curl -fsS http://localhost:8000/health || exit 1

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
