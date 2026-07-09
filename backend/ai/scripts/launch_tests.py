#!/usr/bin/env python3
"""
Launch smoke-tests for the FoodMaps AI stack.

Exercises:
  * /api/ai/health
  * Public (anonymous) chat  - English + Spanish
  * Authenticated chat        - for each role (donor, recipient, volunteer,
                                driver, dispatcher, admin)  English + Spanish
  * Voice (Whisper)           - English + Spanish (requires test WAV files)
  * TTS                       - English + Spanish
  * Broadcast admin endpoints - list pending, run_now

Usage:
    # Required env:
    #   AI_TEST_BASE_URL      default http://localhost:8000
    #   AI_TEST_TOKENS        JSON map of role -> JWT, e.g.
    #       '{"donor":"eyJ...","recipient":"eyJ...","admin":"eyJ..."}'
    #   AI_TEST_USER_IDS      JSON map of role -> integer user_id
    # Optional:
    #   AI_TEST_VOICE_EN      path to short WAV (English, ~2-3s)
    #   AI_TEST_VOICE_ES      path to short WAV (Spanish, ~2-3s)
    #   AI_TEST_BROWSERS      comma-separated User-Agent strings to simulate

    python -m backend.ai.scripts.launch_tests

Exit code is non-zero when any test fails.
"""
from __future__ import annotations

import json
import os
import sys
from dataclasses import dataclass, field

try:
    import httpx
except ImportError:
    print("httpx is required: pip install httpx", file=sys.stderr)
    sys.exit(2)


BASE_URL = os.getenv("AI_TEST_BASE_URL", "http://localhost:8000").rstrip("/")
TOKENS = json.loads(os.getenv("AI_TEST_TOKENS", "{}"))
USER_IDS = {k: int(v) for k, v in json.loads(os.getenv("AI_TEST_USER_IDS", "{}")).items()}
VOICE_EN = os.getenv("AI_TEST_VOICE_EN", "")
VOICE_ES = os.getenv("AI_TEST_VOICE_ES", "")
BROWSERS = [
    s.strip() for s in os.getenv(
        "AI_TEST_BROWSERS",
        # Default: modern Chrome on macOS + Firefox on Windows + Safari iOS
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 13_5) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0 Safari/537.36|"
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:124.0) Gecko/20100101 Firefox/124.0|"
        "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Mobile/15E148"
    ).split("|")
    if s.strip()
]

PROMPT_EN = "Hi, what food can I find near me today?"
PROMPT_ES = "Hola, ¿qué comida puedo encontrar cerca de mí hoy?"


@dataclass
class TestResult:
    name: str
    ok: bool
    detail: str = ""


@dataclass
class Report:
    results: list[TestResult] = field(default_factory=list)

    def add(self, name: str, ok: bool, detail: str = "") -> None:
        status = "PASS" if ok else "FAIL"
        print(f"[{status}] {name}  {('- ' + detail) if detail else ''}")
        self.results.append(TestResult(name, ok, detail))

    @property
    def failed(self) -> int:
        return sum(1 for r in self.results if not r.ok)


# ---------------------------------------------------------------------------
# Individual tests
# ---------------------------------------------------------------------------

def test_health(client: httpx.Client, report: Report) -> None:
    try:
        r = client.get(f"{BASE_URL}/api/ai/health", timeout=10)
        data = r.json()
        report.add(
            "health",
            r.status_code == 200 and data.get("status") == "ok",
            f"status={r.status_code} openai={data.get('openai_configured')}",
        )
    except Exception as exc:
        report.add("health", False, str(exc))


def test_public_chat(client: httpx.Client, report: Report) -> None:
    for lang, prompt in (("en", PROMPT_EN), ("es", PROMPT_ES)):
        for ua in BROWSERS:
            try:
                r = client.post(
                    f"{BASE_URL}/api/ai/public_chat",
                    json={"message": prompt},
                    headers={"User-Agent": ua},
                    timeout=30,
                )
                data = r.json() if r.headers.get("content-type", "").startswith("application/json") else {}
                ok = r.status_code == 200 and bool(data.get("text"))
                if lang == "es" and ok:
                    ok = data.get("lang") == "es"
                report.add(
                    f"public_chat/{lang}/{ua[:25]}",
                    ok,
                    f"status={r.status_code} lang={data.get('lang')}",
                )
            except Exception as exc:
                report.add(f"public_chat/{lang}", False, str(exc))


def test_auth_chat(client: httpx.Client, report: Report) -> None:
    if not TOKENS:
        report.add("auth_chat", False, "AI_TEST_TOKENS env not set - skipping role tests")
        return
    for role, token in TOKENS.items():
        uid = USER_IDS.get(role)
        if uid is None:
            report.add(f"auth_chat/{role}", False, "missing user_id")
            continue
        for lang, prompt in (("en", PROMPT_EN), ("es", PROMPT_ES)):
            try:
                r = client.post(
                    f"{BASE_URL}/api/ai/chat",
                    json={"user_id": str(uid), "message": prompt, "include_audio": False},
                    headers={"Authorization": f"Bearer {token}"},
                    timeout=45,
                )
                data = r.json() if r.headers.get("content-type", "").startswith("application/json") else {}
                ok = r.status_code == 200 and bool(data.get("text"))
                report.add(
                    f"auth_chat/{role}/{lang}",
                    ok,
                    f"status={r.status_code} lang={data.get('lang')}",
                )
            except Exception as exc:
                report.add(f"auth_chat/{role}/{lang}", False, str(exc))


def test_voice(client: httpx.Client, report: Report) -> None:
    for lang, path in (("en", VOICE_EN), ("es", VOICE_ES)):
        if not path:
            report.add(f"voice/{lang}", True, "skipped (no sample file)")
            continue
        if not os.path.isfile(path):
            report.add(f"voice/{lang}", False, f"file not found: {path}")
            continue
        # pick the admin or any token
        token = TOKENS.get("admin") or (next(iter(TOKENS.values()), None))
        uid = USER_IDS.get("admin") or next(iter(USER_IDS.values()), None)
        if not token or uid is None:
            report.add(f"voice/{lang}", False, "no auth token/uid")
            continue
        try:
            with open(path, "rb") as fh:
                r = client.post(
                    f"{BASE_URL}/api/ai/voice",
                    data={"user_id": str(uid), "include_audio": "false"},
                    files={"audio": (os.path.basename(path), fh, "audio/wav")},
                    headers={"Authorization": f"Bearer {token}"},
                    timeout=60,
                )
            data = r.json() if r.headers.get("content-type", "").startswith("application/json") else {}
            report.add(
                f"voice/{lang}",
                r.status_code == 200 and bool(data.get("transcript")),
                f"status={r.status_code} transcript={str(data.get('transcript'))[:60]}",
            )
        except Exception as exc:
            report.add(f"voice/{lang}", False, str(exc))


def test_tts(client: httpx.Client, report: Report) -> None:
    for lang, text in (("en", "Hello world."), ("es", "Hola mundo.")):
        try:
            r = client.post(
                f"{BASE_URL}/api/ai/tts",
                json={"text": text, "lang": lang},
                timeout=30,
            )
            data = r.json() if r.headers.get("content-type", "").startswith("application/json") else {}
            report.add(
                f"tts/{lang}",
                r.status_code == 200 and str(data.get("audio_url", "")).startswith("data:audio"),
                f"status={r.status_code}",
            )
        except Exception as exc:
            report.add(f"tts/{lang}", False, str(exc))


def test_broadcast_admin(client: httpx.Client, report: Report) -> None:
    token = TOKENS.get("admin")
    if not token:
        report.add("broadcast_admin", True, "skipped (no admin token)")
        return
    headers = {"Authorization": f"Bearer {token}"}
    try:
        r = client.get(f"{BASE_URL}/api/ai/broadcasts?status=pending&limit=5",
                       headers=headers, timeout=15)
        report.add("broadcast/list_pending", r.status_code == 200, f"status={r.status_code}")
    except Exception as exc:
        report.add("broadcast/list_pending", False, str(exc))
    try:
        r = client.post(f"{BASE_URL}/api/ai/broadcasts/run_now",
                        headers=headers, timeout=60)
        report.add("broadcast/run_now", r.status_code == 200, f"status={r.status_code}")
    except Exception as exc:
        report.add("broadcast/run_now", False, str(exc))


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> int:
    print(f"== FoodMaps AI launch tests ==  base={BASE_URL}")
    report = Report()
    with httpx.Client() as client:
        test_health(client, report)
        test_public_chat(client, report)
        test_auth_chat(client, report)
        test_voice(client, report)
        test_tts(client, report)
        test_broadcast_admin(client, report)

    print()
    total = len(report.results)
    print(f"Summary: {total - report.failed}/{total} passed, {report.failed} failed")
    return 0 if report.failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
