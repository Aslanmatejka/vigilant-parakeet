"""
Live voice round-trip test for the Nouri assistant.

Exercises the real /api/ai/tts, /api/ai/transcribe, and /api/ai/voice
endpoints (hitting the actual OpenAI TTS + Whisper services).

Flow per scenario:
  1. POST text -> /api/ai/tts        -> .mp3 audio bytes saved to disk
  2. POST that .mp3 -> /api/ai/transcribe -> transcript string
  3. Assert transcript fuzzy-matches the original text
  4. POST that .mp3 -> /api/ai/voice -> AI reply text + (optionally) TTS audio

Run from repo root with the .venv active and the backend running:
    python -m backend.tests.test_voice_live
"""
from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path
from typing import Any

import httpx
from dotenv import load_dotenv

load_dotenv()

SUPABASE_URL = (os.environ.get("SUPABASE_URL") or os.environ["VITE_SUPABASE_URL"]).rstrip("/")
SERVICE_KEY = os.environ["SUPABASE_SERVICE_ROLE_KEY"]
BACKEND_URL = os.environ.get("BACKEND_URL", "http://localhost:8000").rstrip("/")
TEST_USER_ID = "c4dcbd93-081e-4160-87eb-1d51d444413a"

OUT_DIR = Path(__file__).resolve().parent / "voice_artifacts"
OUT_DIR.mkdir(exist_ok=True)


def _admin_headers() -> dict[str, str]:
    return {
        "apikey": SERVICE_KEY,
        "Authorization": f"Bearer {SERVICE_KEY}",
        "Content-Type": "application/json",
    }


def _lookup_email(user_id: str) -> str:
    r = httpx.get(
        f"{SUPABASE_URL}/auth/v1/admin/users/{user_id}",
        headers=_admin_headers(),
        timeout=10,
    )
    r.raise_for_status()
    return r.json()["email"]


def _mint_access_token(email: str) -> str:
    r = httpx.post(
        f"{SUPABASE_URL}/auth/v1/admin/generate_link",
        headers=_admin_headers(),
        json={"type": "magiclink", "email": email},
        timeout=15,
    )
    r.raise_for_status()
    body = r.json()
    hashed = body.get("hashed_token") or body.get("token_hash") or body["properties"]["hashed_token"]
    r = httpx.post(
        f"{SUPABASE_URL}/auth/v1/verify",
        headers={"apikey": SERVICE_KEY, "Content-Type": "application/json"},
        json={"type": "magiclink", "token_hash": hashed},
        timeout=15,
    )
    r.raise_for_status()
    return r.json()["access_token"]


def _clear_history(token: str) -> None:
    httpx.delete(
        f"{BACKEND_URL}/api/ai/history/{TEST_USER_ID}",
        headers={"Authorization": f"Bearer {token}"},
        timeout=15,
    )


# --------------------------------------------------------------------------
# Endpoint wrappers
# --------------------------------------------------------------------------


def tts(token: str, text: str, lang: str = "en") -> bytes:
    r = httpx.post(
        f"{BACKEND_URL}/api/ai/tts",
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        json={"text": text, "lang": lang},
        timeout=60,
    )
    r.raise_for_status()
    assert r.headers.get("content-type", "").startswith("audio/"), \
        f"expected audio response, got {r.headers.get('content-type')}"
    return r.content


def transcribe(token: str, audio_bytes: bytes, filename: str = "clip.mp3",
               language: str | None = None) -> str:
    files = {"audio": (filename, audio_bytes, "audio/mpeg")}
    data: dict[str, str] = {}
    if language:
        data["language"] = language
    r = httpx.post(
        f"{BACKEND_URL}/api/ai/transcribe",
        headers={"Authorization": f"Bearer {token}"},
        files=files,
        data=data,
        timeout=60,
    )
    r.raise_for_status()
    return r.json().get("transcript", "")


def voice_chat(token: str, audio_bytes: bytes, filename: str = "clip.mp3",
               include_audio: bool = False,
               language: str | None = None) -> dict[str, Any]:
    files = {"audio": (filename, audio_bytes, "audio/mpeg")}
    data = {
        "user_id": TEST_USER_ID,
        "include_audio": "true" if include_audio else "false",
        "silent": "false",
    }
    if language:
        data["language"] = language
    r = httpx.post(
        f"{BACKEND_URL}/api/ai/voice",
        headers={"Authorization": f"Bearer {token}"},
        files=files,
        data=data,
        timeout=120,
    )
    if r.status_code >= 400:
        return {"_error": True, "status": r.status_code, "body": r.text[:500]}
    return r.json()


# --------------------------------------------------------------------------
# Scenarios
# --------------------------------------------------------------------------

SCENARIOS = [
    {
        "name": "V1-english-find-food",
        "lang": "en",
        "text": "Find food near me please.",
        "min_overlap": 0.6,  # fraction of original words that must appear in transcript
        "expect_voice_reply": True,
    },
    {
        "name": "V2-english-share-intent",
        "lang": "en",
        "text": "I want to share twelve apples with my community.",
        "min_overlap": 0.5,
        "expect_voice_reply": True,
    },
    {
        "name": "V3-spanish-share-intent",
        "lang": "es",
        "text": "Quiero compartir seis huevos con mi comunidad.",
        "min_overlap": 0.5,
        "expect_voice_reply": True,
    },
    {
        "name": "V4-spanish-claim",
        "lang": "es",
        "text": "Quisiera reclamar las manzanas que tienes disponibles.",
        "min_overlap": 0.5,
        "expect_voice_reply": True,
    },
    {
        "name": "V5-tts-only-shortform",
        "lang": "en",
        "text": "Got it, claiming six eggs for you now.",
        "min_overlap": 0.6,
        "expect_voice_reply": False,
    },
]


# --------------------------------------------------------------------------
# Fuzzy match: do enough of the original words show up in the transcript?
# --------------------------------------------------------------------------

import re

_PUNCT_RE = re.compile(r"[^\w\s]")


def _normalize(s: str) -> list[str]:
    return _PUNCT_RE.sub(" ", s.lower()).split()


def _word_overlap(spoken: str, heard: str) -> float:
    a = set(_normalize(spoken))
    b = set(_normalize(heard))
    if not a:
        return 1.0
    return len(a & b) / len(a)


# --------------------------------------------------------------------------
# Runner
# --------------------------------------------------------------------------


def run_scenario(token: str, scn: dict) -> dict:
    name = scn["name"]
    lang = scn["lang"]
    text = scn["text"]
    expect_voice = scn["expect_voice_reply"]
    min_overlap = scn["min_overlap"]

    print(f"\n[{name}] lang={lang}")
    print(f"  SAY     : {text!r}")
    passes, failures = [], []

    # 1. TTS
    t0 = time.time()
    try:
        mp3 = tts(token, text, lang=lang)
    except Exception as exc:
        failures.append(f"tts failed: {exc}")
        return {"scenario": name, "passes": passes, "failures": failures}
    tts_ms = int((time.time() - t0) * 1000)
    mp3_path = OUT_DIR / f"{name}.mp3"
    mp3_path.write_bytes(mp3)
    print(f"  TTS     : {len(mp3)} bytes -> {mp3_path.name}  ({tts_ms} ms)")
    if len(mp3) < 1024:
        failures.append(f"tts audio suspiciously small ({len(mp3)} bytes)")
    else:
        passes.append("tts produced audio")

    # 2. Transcribe round-trip
    t0 = time.time()
    try:
        transcript = transcribe(token, mp3, filename=f"{name}.mp3", language=lang)
    except Exception as exc:
        failures.append(f"transcribe failed: {exc}")
        return {"scenario": name, "passes": passes, "failures": failures}
    stt_ms = int((time.time() - t0) * 1000)
    print(f"  WHISPER : {transcript!r}  ({stt_ms} ms)")

    overlap = _word_overlap(text, transcript)
    print(f"  OVERLAP : {overlap:.2f} (min {min_overlap:.2f})")
    if overlap >= min_overlap:
        passes.append(f"round-trip word overlap {overlap:.2f} >= {min_overlap:.2f}")
    else:
        failures.append(f"round-trip word overlap {overlap:.2f} below threshold {min_overlap:.2f}")

    if not expect_voice:
        return {
            "scenario": name,
            "spoken": text,
            "transcript": transcript,
            "overlap": overlap,
            "passes": passes,
            "failures": failures,
        }

    # 3. /api/ai/voice end-to-end
    _clear_history(token)
    t0 = time.time()
    res = voice_chat(token, mp3, filename=f"{name}.mp3",
                     include_audio=False, language=lang)
    voice_ms = int((time.time() - t0) * 1000)
    if res.get("_error"):
        failures.append(f"voice endpoint {res['status']}: {res['body']}")
        return {
            "scenario": name,
            "spoken": text,
            "transcript": transcript,
            "overlap": overlap,
            "passes": passes,
            "failures": failures,
        }
    reply = (res.get("text") or "").strip()
    reply_lang = res.get("lang") or ""
    reply_transcript = res.get("transcript") or ""
    print(f"  REPLY   : {reply[:160]!r}{'...' if len(reply) > 160 else ''}")
    print(f"  LANG    : {reply_lang}  ({voice_ms} ms)")

    if reply:
        passes.append("voice endpoint returned reply text")
    else:
        failures.append("voice endpoint returned empty reply")

    if reply_lang.lower().startswith(lang):
        passes.append(f"reply language matches input ({reply_lang})")
    else:
        failures.append(f"reply language {reply_lang!r} does not match input {lang!r}")

    # Whisper transcript echoed by /voice should match the standalone transcribe
    if reply_transcript:
        rt_overlap = _word_overlap(transcript, reply_transcript)
        if rt_overlap >= 0.6:
            passes.append(f"voice transcript matches standalone ({rt_overlap:.2f})")
        else:
            failures.append(
                f"voice transcript diverges from standalone ({rt_overlap:.2f})"
            )

    return {
        "scenario": name,
        "spoken": text,
        "transcript": transcript,
        "overlap": overlap,
        "reply": reply,
        "reply_lang": reply_lang,
        "voice_transcript": reply_transcript,
        "passes": passes,
        "failures": failures,
    }


def main() -> int:
    print(f"[setup] backend={BACKEND_URL}")
    email = _lookup_email(TEST_USER_ID)
    print(f"[setup] minting token for {email}")
    token = _mint_access_token(email)
    print(f"[setup] artifacts dir: {OUT_DIR}")

    results = []
    for scn in SCENARIOS:
        try:
            results.append(run_scenario(token, scn))
        except Exception as exc:
            print(f"  EXCEPTION: {exc}")
            results.append({"scenario": scn["name"], "exception": str(exc)})

    out = OUT_DIR / "voice_live_results.json"
    out.write_text(json.dumps(results, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\n[done] results -> {out}")

    print("\n" + "=" * 78)
    print("SUMMARY")
    print("=" * 78)
    total_pass = total_fail = 0
    failing_scenarios = 0
    for r in results:
        if "exception" in r:
            print(f"  EXC  {r['scenario']:<32} {r['exception']}")
            failing_scenarios += 1
            continue
        p, f = len(r["passes"]), len(r["failures"])
        total_pass += p
        total_fail += f
        flag = "OK  " if f == 0 else "FAIL"
        if f:
            failing_scenarios += 1
        print(f"  {flag} {r['scenario']:<32} pass={p} fail={f}")
        for msg in r["failures"]:
            print(f"        - {msg}")

    print(f"\n  totals: pass={total_pass} fail={total_fail}")
    return 0 if failing_scenarios == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
