"""
Granny user-test for the Nouri chat assistant.

Simulates a non-technical user who phrases things naturally
("my son is hungry", "got anything to eat?", "the first one please")
and dumps each turn so we can grade understanding.

Run from repo root with the .venv active:
    python -m backend.tests.test_granny_chat
"""
from __future__ import annotations

import json
import os
import sys
import textwrap
import time
import uuid as uuidlib
from typing import Any

import httpx
from dotenv import load_dotenv

load_dotenv()

SUPABASE_URL = (os.environ.get("SUPABASE_URL") or os.environ["VITE_SUPABASE_URL"]).rstrip("/")
SERVICE_KEY = os.environ["SUPABASE_SERVICE_ROLE_KEY"]
BACKEND_URL = os.environ.get("BACKEND_URL", "http://localhost:8000").rstrip("/")
TEST_USER_ID = "c4dcbd93-081e-4160-87eb-1d51d444413a"
TEST_USER_EMAIL = os.environ.get("GRANNY_TEST_EMAIL")  # filled in below if missing


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
    """Use admin generate_link + verify to mint a real access_token."""
    r = httpx.post(
        f"{SUPABASE_URL}/auth/v1/admin/generate_link",
        headers=_admin_headers(),
        json={"type": "magiclink", "email": email},
        timeout=15,
    )
    r.raise_for_status()
    body = r.json()
    # Returned fields differ by Supabase version: hashed_token / token_hash
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


def _chat(token: str, message: str) -> dict[str, Any]:
    r = httpx.post(
        f"{BACKEND_URL}/api/ai/chat",
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        json={"user_id": TEST_USER_ID, "message": message, "include_audio": False},
        timeout=90,
    )
    if r.status_code >= 400:
        return {"_error": True, "status": r.status_code, "body": r.text[:500]}
    return r.json()


# ─── The granny script ─────────────────────────────────────────
# Each entry: (label, user_message). The script intentionally avoids
# app-jargon ("listing", "claim", "filter") so we can see whether the
# AI's natural-language understanding is granny-friendly.
GRANNY_SCRIPT = [
    ("01-hello",       "hi there sweetie"),
    ("02-need-food",   "my grandson is hungry and we got nothing in the fridge. can you help me find some food"),
    ("03-clarify",     "i'm in alameda. don't have a car so close by please"),
    ("04-pick-first",  "the first one sounds good for him, he loves a turkey sandwich"),
    ("05-confirm",     "yes please go ahead"),
    ("06-followup",    "how do i pick it up? i'm not good with this phone stuff"),
    ("07-share",       "actually wait, i got some extra soup at home, can someone come get it?"),
    ("08-pivot",       "nevermind the soup, can i get those apples too for my grandson's lunch tomorrow"),
    ("09-cancel",      "actually i changed my mind on the sandwich, my daughter is bringing dinner"),
    ("10-thanks",      "ok thank you dear, you've been very kind"),
]


def _summarize_tools(tool_results: list[dict[str, Any]]) -> str:
    if not tool_results:
        return "—"
    out = []
    for tr in tool_results:
        name = tr.get("tool") or "?"
        res = tr.get("result") or {}
        ok = res.get("success") if isinstance(res, dict) else tr.get("ok")
        extra = ""
        if isinstance(res, dict):
            if "results" in res and isinstance(res["results"], list):
                extra = f" results={len(res['results'])}"
            elif "listings" in res and isinstance(res["listings"], list):
                extra = f" listings={len(res['listings'])}"
            if "title" in res:
                extra += f" title={res['title']!r}"
            if "error" in res:
                extra += f" error={res['error']!r}"
        out.append(f"{name}(ok={ok}){extra}")
    return " | ".join(out)


def main() -> int:
    print(f"[setup] backend={BACKEND_URL}")
    email = TEST_USER_EMAIL or _lookup_email(TEST_USER_ID)
    print(f"[setup] minting token for {email}")
    token = _mint_access_token(email)
    print(f"[setup] clearing history for {TEST_USER_ID}")
    _clear_history(token)
    print("[setup] starting granny conversation\n" + "=" * 72)

    transcript = []
    for label, msg in GRANNY_SCRIPT:
        print(f"\n── {label} ───────────────────────────────────────────────")
        print(f"GRANNY: {msg}")
        t0 = time.time()
        resp = _chat(token, msg)
        dt = time.time() - t0

        if resp.get("_error"):
            print(f"NOURI: <HTTP {resp['status']}> {resp['body']}")
            transcript.append({"label": label, "user": msg, "error": resp})
            continue

        text = resp.get("text", "").strip()
        tools = resp.get("tool_results") or []
        sugg = resp.get("suggestions") or []
        print(textwrap.fill(f"NOURI: {text}", width=90,
                            subsequent_indent="        "))
        print(f"  tools: {_summarize_tools(tools)}")
        if sugg:
            short = []
            for s in sugg[:3]:
                short.append(s if isinstance(s, str) else (s.get("label") or s.get("text") or str(s)))
            print(f"  suggestions: {short}")
        print(f"  ({dt:.1f}s)")
        transcript.append({
            "label": label,
            "user": msg,
            "nouri": text,
            "tools": [{"tool": t.get("tool"), "ok": (t.get("result") or {}).get("success", t.get("ok"))} for t in tools],
            "elapsed_s": round(dt, 2),
        })

    print("\n" + "=" * 72)
    out_path = os.path.join(os.path.dirname(__file__), "granny_transcript.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(transcript, f, indent=2)
    print(f"[done] transcript saved to {out_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
