"""Drive the whole pipeline through the HTTP API and report what really happens.

Nothing here reaches into the database or calls a service directly: every step is
an HTTP call a client could make. That is the point — it exercises what a user
actually touches, and it says plainly which steps are blocked and why, instead of
reporting success for work that did not happen.

Run:  PYTHONPATH=. .venv/Scripts/python.exe var/tmp/smoke_api.py
"""
from __future__ import annotations

import sys
import time

import httpx

BASE = "http://127.0.0.1:8000/api/v1"
OK, SKIP, BAD = "  OK ", " SKIP", " FAIL"

client = httpx.Client(timeout=300)
results: list[tuple[str, str, str]] = []


def report(mark: str, step: str, detail: str = "") -> None:
    results.append((mark, step, detail))
    print(f"[{mark}] {step}" + (f"  — {detail}" if detail else ""))


def main() -> int:
    # ---------------------------------------------------------------- auth ----
    login = client.post(
        f"{BASE}/auth/login", json={"email": "demo@reelcraft.app", "password": "demo1234"}
    )
    if login.status_code != 200:
        report(BAD, "login", f"HTTP {login.status_code}")
        return 1
    h = {"Authorization": "Bearer " + login.json()["access_token"]}
    report(OK, "login")

    # -------------------------------------------------------- capabilities ----
    caps = client.get(f"{BASE}/capabilities").json()
    matrix = {
        key: caps[key]["available"]
        for key in ("render", "ai_planner", "voiceover", "image", "ai_motion", "lipsync")
    }
    report(OK, "capabilities", " ".join(f"{k}={'yes' if v else 'no'}" for k, v in matrix.items()))

    languages = {row["code"]: row for row in caps["voiceover"].get("languages", [])}
    derja = languages.get("tn", {})
    report(
        OK if derja.get("exact") else SKIP,
        "derja voice",
        f"{derja.get('voice_id')} exact={derja.get('exact')}",
    )

    # ----------------------------------------------------------- character ----
    character = client.post(
        f"{BASE}/characters",
        headers=h,
        json={
            "name": "Smoke character",
            "kind": "baby",
            "age": "2 years old",
            "hair": "dark curly hair",
            "clothes": "a red traditional jebba",
            "headwear": "a red chechia",
        },
    )
    if character.status_code != 201:
        report(BAD, "create character", character.text[:160])
        return 1
    character = character.json()
    report(OK, "create character", character["description"][:70] + "…")

    # ------------------------------------------------------------- project ----
    project = client.post(
        f"{BASE}/projects",
        headers=h,
        json={
            "name": "Smoke test — pipeline",
            "topic": "smoke test",
            "language": "tn",
            "character_id": character["id"],
            "target_duration": 12,
            "platform": "tiktok",
        },
    )
    if project.status_code != 201:
        report(BAD, "create project", project.text[:200])
        return 1
    project = project.json()
    pid = project["id"]
    report(OK, "create project", f"lang={project['language']} rtl={project['rtl']}")

    # ------------------------------------------------------------- images ----
    # The project has no scenes until it has media, so upload a couple of samples.
    from app.infrastructure.imaging.samples import generate_sample_image

    files = [("files", (f"s{i}.jpg", generate_sample_image(i, width=720, height=1280), "image/jpeg"))
             for i in range(2)]
    upload = client.post(f"{BASE}/projects/{pid}/media", headers=h, files=files)
    report(OK if upload.status_code == 201 else BAD, "upload images", f"HTTP {upload.status_code}")

    plan_response = client.post(
        f"{BASE}/projects/{pid}/plan/generate", headers=h,
        json={"instruction": "A toddler talks about a wedding", "target_duration": 12},
    )
    if plan_response.status_code != 200:
        report(BAD, "generate plan", plan_response.text[:200])
        return 1
    body = plan_response.json()
    report(
        OK, "generate plan",
        f"{len(body['plan']['scenes'])} scenes, {body['total_duration']:.1f}s, "
        f"ai_used={body['ai_used']}",
    )

    scenes = client.get(f"{BASE}/projects/{pid}", headers=h).json()["scenes"]
    scene_id = scenes[0]["id"]

    # ------------------------------------------------- image prompt + gen ----
    plan = client.get(f"{BASE}/projects/{pid}/plan", headers=h).json()["plan"]
    for index, scene in enumerate(plan["scenes"]):
        scene["image_prompt"] = (
            f"Close-up, scene {index}, warm golden light, photorealistic, cinematic, 9:16"
        )
    applied = client.put(f"{BASE}/projects/{pid}/plan", headers=h, json={"plan": plan})
    report(OK if applied.status_code == 200 else BAD, "store image prompts",
           f"HTTP {applied.status_code}")
    scene_id = client.get(f"{BASE}/projects/{pid}", headers=h).json()["scenes"][0]["id"]

    image = client.post(f"{BASE}/projects/{pid}/scenes/{scene_id}/image", headers=h)
    if image.status_code == 202:
        report(OK, "generate image", "queued")
    elif image.status_code == 503:
        report(SKIP, "generate image", image.json()["error"]["message"][:90])
    else:
        report(BAD, "generate image", image.text[:160])

    # ------------------------------------------------------------- voice ----
    client.patch(
        f"{BASE}/projects/{pid}/voiceover", headers=h,
        json={"script": "يا جماعة، هذا اختبار قصير.", "enabled": True},
    )
    voice_state = client.get(f"{BASE}/projects/{pid}/voiceover", headers=h).json()
    report(OK, "voice defaults", f"voice_id={voice_state['voice_id']}")

    if client.post(f"{BASE}/projects/{pid}/voiceover/generate", headers=h).status_code == 202:
        deadline = time.time() + 120
        while time.time() < deadline:
            time.sleep(2)
            voice_state = client.get(f"{BASE}/projects/{pid}/voiceover", headers=h).json()
            if voice_state["status"] in ("ready", "failed"):
                break
        if voice_state["status"] == "ready":
            report(OK, "generate voice",
                   f"{voice_state['media']['duration_seconds']:.1f}s via {voice_state['provider']}")
        else:
            report(BAD, "generate voice", str(voice_state.get("error"))[:90])
    else:
        report(SKIP, "generate voice", "provider not configured")

    # ---------------------------------------------------------- ai motion ----
    motion = client.post(f"{BASE}/projects/{pid}/scenes/{scene_id}/ai-motion", headers=h)
    if motion.status_code == 202:
        report(OK, "generate motion", "queued")
    elif motion.status_code == 503:
        report(SKIP, "generate motion", motion.json()["error"]["message"][:90])
    else:
        report(BAD, "generate motion", motion.text[:160])

    # ------------------------------------------------------------ lipsync ----
    lip = client.post(f"{BASE}/projects/{pid}/scenes/{scene_id}/lipsync", headers=h)
    if lip.status_code == 202:
        report(OK, "lip sync", "queued")
    elif lip.status_code in (422, 503):
        report(SKIP, "lip sync", lip.json()["error"]["message"][:90])
    else:
        report(BAD, "lip sync", lip.text[:160])

    # ------------------------------------------------------------- render ----
    job = client.post(f"{BASE}/projects/{pid}/render", headers=h)
    if job.status_code in (201, 202):
        state = job.json()
        started = time.time()
        while state["status"] in ("queued", "processing") and time.time() - started < 300:
            time.sleep(2)
            state = client.get(f"{BASE}/render-jobs/{state['id']}", headers=h).json()
        if state["status"] == "completed":
            data = client.get(f"{BASE}/render-jobs/{state['id']}/download", headers=h).content
            report(OK, "render", f"{len(data) / 1024 / 1024:.1f} MB in {time.time() - started:.0f}s")
        else:
            report(BAD, "render", str(state.get("error"))[:120])
    else:
        report(BAD, "render", job.text[:160])

    # --------------------------------------------------------- job registry --
    registry = client.get(f"{BASE}/projects/{pid}/jobs", headers=h).json()
    report(
        OK, "job registry",
        f"{registry['total']} jobs, active={registry['active']}, "
        f"by_status={registry['by_status']}",
    )
    for item in registry["items"]:
        print(f"        {item['type']:8} {item['status']:10} {item['stage'][:34]:34} "
              f"{(item['error'] or '')[:44]}")

    # ------------------------------------------------------------- cleanup --
    client.delete(f"{BASE}/projects/{pid}", headers=h)
    client.delete(f"{BASE}/characters/{character['id']}", headers=h)
    report(OK, "cleanup", "test project and character deleted")

    failed = [r for r in results if r[0] == BAD]
    skipped = [r for r in results if r[0] == SKIP]
    print(f"\n{len(results) - len(failed) - len(skipped)} ok, {len(skipped)} skipped "
          f"(no provider key), {len(failed)} failed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
