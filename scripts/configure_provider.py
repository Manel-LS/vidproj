"""Validate a provider key against the real API, then write it to backend/.env.

Written because the failure mode of "paste the key and restart" is silent: a
typo, a wrong base URL, or a model name the provider does not serve all leave the
capability panel saying "not configured", with nothing to say which of the three
went wrong.

This makes the round trip explicit — it calls the provider before writing
anything, and refuses to write a key that does not work.

Usage:
    python scripts/configure_provider.py groq        gsk_...
    python scripts/configure_provider.py openrouter  sk-or-...
    python scripts/configure_provider.py gemini      AIza...
    python scripts/configure_provider.py anthropic   sk-ant-...
    python scripts/configure_provider.py ollama                  (no key needed)

The key is read from argv here for convenience on a personal machine. It is
written only to backend/.env, which is git-ignored, and never logged in full.
"""
from __future__ import annotations

import pathlib
import sys

import httpx

ROOT = pathlib.Path(__file__).resolve().parent.parent
ENV_FILE = ROOT / "backend" / ".env"

#: base_url, default model, and the env var the app reads the key from.
PRESETS = {
    "groq": {
        "base_url": "https://api.groq.com/openai/v1",
        "model": "llama-3.3-70b-versatile",
        "label": "Groq (free tier, no card)",
    },
    "openrouter": {
        "base_url": "https://openrouter.ai/api/v1",
        "model": "meta-llama/llama-3.3-70b-instruct:free",
        "label": "OpenRouter (free models)",
    },
    "gemini": {
        "base_url": "https://generativelanguage.googleapis.com/v1beta/openai",
        "model": "gemini-2.0-flash",
        "label": "Google Gemini (free tier)",
    },
    "openai": {
        "base_url": "https://api.openai.com/v1",
        "model": "gpt-4o-mini",
        "label": "OpenAI (paid)",
    },
    "ollama": {
        "base_url": "http://localhost:11434/v1",
        "model": "qwen2.5:3b",
        "label": "Ollama (local, no key)",
    },
}


def check_openai_compatible(base_url: str, api_key: str, model: str) -> tuple[bool, str]:
    """One real completion. Anything less does not prove the key works."""
    try:
        with httpx.Client(timeout=60) as client:
            response = client.post(
                f"{base_url.rstrip('/')}/chat/completions",
                headers={"Authorization": f"Bearer {api_key or 'local'}"},
                json={
                    "model": model,
                    "messages": [{"role": "user", "content": "Reply with the single word: ready"}],
                    "max_tokens": 8,
                },
            )
    except httpx.HTTPError as exc:
        return False, f"could not reach {base_url} ({type(exc).__name__})"

    if response.status_code == 401:
        return False, "the provider rejected the key (401)"
    if response.status_code == 404:
        return False, f"the model '{model}' is not served here (404)"
    if response.status_code == 429:
        return False, "rate limited (429) — the key works but the quota is spent"
    if response.status_code >= 400:
        return False, f"HTTP {response.status_code}: {response.text[:160]}"

    try:
        reply = response.json()["choices"][0]["message"]["content"].strip()
    except Exception:  # noqa: BLE001
        return False, "the response did not look like a chat completion"
    return True, f"model replied {reply[:40]!r}"


def check_anthropic(api_key: str, model: str) -> tuple[bool, str]:
    try:
        with httpx.Client(timeout=60) as client:
            response = client.post(
                "https://api.anthropic.com/v1/messages",
                headers={
                    "x-api-key": api_key,
                    "anthropic-version": "2023-06-01",
                    "content-type": "application/json",
                },
                json={
                    "model": model,
                    "max_tokens": 8,
                    "messages": [{"role": "user", "content": "Reply with the single word: ready"}],
                },
            )
    except httpx.HTTPError as exc:
        return False, f"could not reach the Anthropic API ({type(exc).__name__})"
    if response.status_code == 401:
        return False, "the provider rejected the key (401)"
    if response.status_code >= 400:
        return False, f"HTTP {response.status_code}: {response.text[:160]}"
    return True, "Anthropic answered"


def write_env(updates: dict[str, str]) -> list[str]:
    """Merge settings into backend/.env, preserving everything already there."""
    existing: list[str] = []
    if ENV_FILE.exists():
        existing = ENV_FILE.read_text(encoding="utf-8").splitlines()

    seen: set[str] = set()
    output: list[str] = []
    for line in existing:
        key = line.split("=", 1)[0].strip() if "=" in line and not line.lstrip().startswith("#") else ""
        if key in updates:
            output.append(f"{key}={updates[key]}")
            seen.add(key)
        else:
            output.append(line)

    added = [key for key in updates if key not in seen]
    if added:
        if output and output[-1].strip():
            output.append("")
        output.append("# AI planner — written by scripts/configure_provider.py")
        output.extend(f"{key}={updates[key]}" for key in added)

    ENV_FILE.parent.mkdir(parents=True, exist_ok=True)
    ENV_FILE.write_text("\n".join(output) + "\n", encoding="utf-8")
    return added


def main() -> int:
    if len(sys.argv) < 2 or sys.argv[1] not in PRESETS:
        print("Choose a provider:")
        for name, preset in PRESETS.items():
            print(f"  {name:12} {preset['label']}")
        print("\n  python scripts/configure_provider.py <provider> <api-key>")
        return 2

    name = sys.argv[1]
    preset = PRESETS[name]
    api_key = sys.argv[2] if len(sys.argv) > 2 else ""
    model = sys.argv[3] if len(sys.argv) > 3 else preset["model"]

    if name != "ollama" and not api_key:
        print(f"{preset['label']} needs a key: python scripts/configure_provider.py {name} <key>")
        return 2

    print(f"Checking {preset['label']} with model {model} …")
    if name == "anthropic":
        ok, detail = check_anthropic(api_key, model)
    else:
        ok, detail = check_openai_compatible(preset["base_url"], api_key, model)

    if not ok:
        print(f"  FAILED: {detail}")
        print("  Nothing was written to backend/.env.")
        return 1
    print(f"  OK: {detail}")

    if name == "anthropic":
        updates = {"ANTHROPIC_API_KEY": api_key, "ANTHROPIC_MODEL": model, "LLM_PROVIDER": "anthropic"}
    else:
        updates = {
            "LLM_PROVIDER": "openai_compatible",
            "OPENAI_API_KEY": api_key or "local",
            "OPENAI_BASE_URL": preset["base_url"],
            "OPENAI_MODEL": model,
        }

    added = write_env(updates)
    print(f"  Written to {ENV_FILE} ({len(added)} new line(s), the rest updated in place).")
    print("\nRestart the backend — the provider factories are cached at start-up, so")
    print("without a restart the capability panel will keep saying 'not configured'.")
    print("Then verify:  curl -s http://127.0.0.1:8000/api/v1/capabilities")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
