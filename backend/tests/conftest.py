"""Test fixtures.

The environment is configured *before* `app` is imported, because `Settings` is read
once at import time. Each test session gets a throwaway SQLite database and a throwaway
storage root, so tests never touch a developer's real data.
"""
from __future__ import annotations

import os
import shutil
import tempfile
from pathlib import Path

import pytest

_TMP_ROOT = Path(tempfile.mkdtemp(prefix="reelcraft-tests-"))

# Defaults to a throwaway SQLite file so the suite needs no services. Point
# TEST_DATABASE_URL at a scratch database to run the same tests against the real
# engine, e.g.:
#   TEST_DATABASE_URL=mysql+pymysql://root@127.0.0.1:3306/reelcraft_test pytest
# The target is dropped and recreated by `_database`, so never aim it at real data.
_TEST_DATABASE_URL = os.environ.get(
    "TEST_DATABASE_URL", f"sqlite:///{(_TMP_ROOT / 'test.db').as_posix()}"
)

os.environ.update(
    {
        "ENVIRONMENT": "test",
        "DEBUG": "false",
        "SECRET_KEY": "test-secret-key-not-for-production",
        "DATABASE_URL": _TEST_DATABASE_URL,
        "STORAGE_PROVIDER": "local",
        "STORAGE_LOCAL_ROOT": str(_TMP_ROOT / "storage"),
        "RENDER_WORK_DIR": str(_TMP_ROOT / "work"),
        "RATE_LIMIT_ENABLED": "false",
        "JOB_QUEUE": "thread",
        "LLM_PROVIDER": "heuristic",
        "TTS_PROVIDER": "none",
        "I2V_PROVIDER": "none",
        # Pinned like every other provider: the suite must describe the code,
        # not whatever the developer happens to have enabled in their .env.
        "DEPTH_PROVIDER": "none",
        "IMAGE_PROVIDER": "none",
        "LIPSYNC_PROVIDER": "none",
        # Keep renders quick: a smaller supersample and a faster preset.
        "RENDER_SUPERSAMPLE": "1.25",
        "RENDER_PRESET": "ultrafast",
        "RENDER_CRF": "28",
    }
)

from fastapi.testclient import TestClient  # noqa: E402

from app.db.base import Base, engine  # noqa: E402
from app.infrastructure.imaging.samples import (  # noqa: E402
    generate_sample_image,
    generate_silent_wav,
)
import app.models  # noqa: E402,F401  (register the mappings before create_all)
from app.main import app as fastapi_app  # noqa: E402


@pytest.fixture(scope="session", autouse=True)
def _database():
    # Drop first: a previous run that crashed would otherwise leave tables behind and
    # the suite would test against a stale schema.
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    yield
    Base.metadata.drop_all(engine)
    shutil.rmtree(_TMP_ROOT, ignore_errors=True)


@pytest.fixture()
def client() -> TestClient:
    with TestClient(fastapi_app) as test_client:
        yield test_client


_counter = {"n": 0}


@pytest.fixture()
def user_factory(client):
    def make(password: str = "password123") -> dict:
        _counter["n"] += 1
        email = f"tester{_counter['n']}@example.com"
        response = client.post(
            "/api/v1/auth/register",
            json={"email": email, "password": password, "full_name": "Test User"},
        )
        assert response.status_code == 201, response.text
        body = response.json()
        return {
            "email": email,
            "password": password,
            "token": body["access_token"],
            "id": body["user"]["id"],
            "headers": {"Authorization": f"Bearer {body['access_token']}"},
        }

    return make


@pytest.fixture()
def auth(user_factory) -> dict:
    return user_factory()


@pytest.fixture()
def sample_images():
    def make(count: int = 3) -> list[tuple[str, tuple[str, bytes, str]]]:
        return [
            ("files", (f"sample-{i}.jpg", generate_sample_image(i, width=720, height=960), "image/jpeg"))
            for i in range(count)
        ]

    return make


@pytest.fixture()
def sample_audio():
    def make(seconds: float = 6.0) -> tuple[str, bytes, str]:
        return ("tone.wav", generate_silent_wav(seconds), "audio/wav")

    return make


@pytest.fixture()
def project(client, auth) -> dict:
    response = client.post(
        "/api/v1/projects",
        json={
            "name": "School supplies launch",
            "description": "New school supplies collection for back to school",
            "topic": "school supplies",
            "style": "tiktok_trend",
            "target_duration": 8,
        },
        headers=auth["headers"],
    )
    assert response.status_code == 201, response.text
    return response.json()


@pytest.fixture()
def project_with_images(client, auth, project, sample_images) -> dict:
    response = client.post(
        f"/api/v1/projects/{project['id']}/media",
        files=sample_images(3),
        headers=auth["headers"],
    )
    assert response.status_code == 201, response.text
    detail = client.get(f"/api/v1/projects/{project['id']}", headers=auth["headers"])
    return detail.json()
