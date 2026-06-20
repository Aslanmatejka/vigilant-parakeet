"""
Share-flow stress test for the Nouri chat assistant.

Runs multiple short scripts that exercise:
  • Subject correction mid-intake ('i meant eggs')
  • Quantity correction mid-intake
  • Add-vs-replace ambiguity ('also some apples')
  • Share -> Search switch mid-intake
  • Vague / sloppy input ('i got food')
  • Non-food item (should refuse warmly)
  • Borderline item (unopened pet food -> should accept)
  • One-shot all-in-one ('share 3 loaves of bread expires friday')
  • Abandon mid-flow ('nevermind, forget it')
  • Two consecutive corrections ('i meant apples'... 'wait, oranges')

Run from repo root with the .venv active:
    python -m backend.tests.test_share_flow
"""
from __future__ import annotations

import json
import os
import sys
import textwrap
import time
from typing import Any

import httpx
from dotenv import load_dotenv

load_dotenv()

SUPABASE_URL = (os.environ.get("SUPABASE_URL") or os.environ["VITE_SUPABASE_URL"]).rstrip("/")
SERVICE_KEY = os.environ["SUPABASE_SERVICE_ROLE_KEY"]
BACKEND_URL = os.environ.get("BACKEND_URL", "http://localhost:8000").rstrip("/")
TEST_USER_ID = "c4dcbd93-081e-4160-87eb-1d51d444413a"


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


SCENARIOS: list[dict[str, Any]] = [
    {
        "name": "S1-subject-correction",
        "purpose": "Switch food noun mid-intake. Should drop watermelon, stay in SHARE flow, ask for qty of apples.",
        "turns": [
            "i want to share 6 watermelon",
            "i meant apples",
            "i have 12",
            "tomorrow is fine for expiry",
            "use my saved address",
            "alameda unified is fine",
        ],
        "expect": {
            "should_call_post_food_listing": True,
            "must_not_say": ["watermelon", "claim", "available listings", "grandson"],
            "must_say_at_some_point": ["apples"],
        },
    },
    {
        "name": "S2-quantity-correction",
        "purpose": "Correct quantity mid-flow.",
        "turns": [
            "share 5 loaves of bread",
            "wait make it 10",
            "expires tomorrow",
            "yes, use my saved address",
            "post it to alameda unified",
        ],
        "expect": {
            "should_call_post_food_listing": True,
            "must_say_at_some_point": ["10", "bread"],
        },
    },
    {
        "name": "S3-add-second-item",
        "purpose": "Mid-flow 'also some apples'. Should ask add-as-second vs replace.",
        "turns": [
            "i want to share a dozen eggs",
            "also some apples",
        ],
        "expect": {
            "must_say_at_some_point_any": [
                "second listing", "another listing", "separate listing",
                "add", "replace",
            ],
        },
    },
    {
        "name": "S4-share-to-search-switch",
        "purpose": "Abandon share intake to look for food.",
        "turns": [
            "share 4 oranges",
            "actually find food near me instead",
        ],
        "expect": {
            "should_call": ["search_food_near_user"],
            "must_not_call": ["post_food_listing"],
            "must_not_ask_intake": True,
        },
    },
    {
        "name": "S5-vague-input",
        "purpose": "Vague 'i got food'. Should ask what kind.",
        "turns": [
            "i got some food i want to give away",
        ],
        "expect": {
            "must_not_call": ["post_food_listing"],
            "must_say_at_some_point_any": ["what", "which", "kind", "type"],
        },
    },
    {
        "name": "S6-non-food-refuse",
        "purpose": "Non-food item. Should refuse warmly, suggest Buy Nothing.",
        "turns": [
            "i want to share my old shoes",
        ],
        "expect": {
            "must_not_call": ["post_food_listing"],
            "must_say_at_some_point_any": ["food", "buy nothing", "freecycle"],
        },
    },
    {
        "name": "S7-borderline-pet-food",
        "purpose": "Unopened pet food should be accepted as food.",
        "turns": [
            "i have an unopened bag of dog food, can i share it?",
            "yes a 5 lb bag, expires in 6 months",
        ],
        "expect": {
            "must_not_say": ["can't list", "cannot list", "not food"],
        },
    },
    {
        "name": "S8-all-in-one",
        "purpose": "One-shot share with title+qty+expiry. Should require minimal follow-up.",
        "turns": [
            "i want to share 3 loaves of sourdough bread, expires friday",
        ],
        "expect": {
            "must_say_at_some_point": ["bread"],
        },
    },
    {
        "name": "S9-abandon",
        "purpose": "Abandon listing entirely.",
        "turns": [
            "i want to share some pasta",
            "nevermind, forget it",
        ],
        "expect": {
            "must_not_call": ["post_food_listing"],
            "must_not_ask_intake": True,
        },
    },
    {
        "name": "S10-double-correction",
        "purpose": "Two consecutive subject corrections.",
        "turns": [
            "i want to share 6 watermelon",
            "i meant apples",
            "wait, oranges",
            "8 of them, expires next week",
        ],
        "expect": {
            "must_not_say": ["watermelon", "apples", "grandson"],
            "must_say_at_some_point": ["oranges"],
        },
    },
    {
        "name": "S11-no-fabrication",
        "purpose": "User says nothing about family. Ensure AI does not invent grandson/kids.",
        "turns": [
            "i want to share 4 oranges",
            "tomorrow for expiry",
        ],
        "expect": {
            "must_not_say": ["grandson", "your kids", "your son", "your daughter", "your lunch"],
        },
    },
]


def _summarize_tools(tools: list[dict[str, Any]]) -> str:
    if not tools:
        return "—"
    out = []
    for tr in tools:
        name = tr.get("tool") or "?"
        res = tr.get("result") or {}
        ok = res.get("success") if isinstance(res, dict) else tr.get("ok")
        extra = ""
        if isinstance(res, dict):
            if "title" in res:
                extra = f" title={res['title']!r}"
            if "results" in res and isinstance(res["results"], list):
                extra += f" results={len(res['results'])}"
        out.append(f"{name}(ok={ok}){extra}")
    return " | ".join(out)


_INTAKE_QUESTION_MARKERS = (
    "how much", "how many", "what is the address", "what's the address",
    "when does it expire", "expiry", "which community", "what community",
    "what time", "pickup window",
)


def _grade(scenario: dict[str, Any], turn_records: list[dict[str, Any]]) -> dict[str, Any]:
    expect = scenario.get("expect") or {}
    full_text = " ".join((r.get("nouri") or "").lower() for r in turn_records)
    # For "must_not_say", we only care about what the AI says AFTER the user's
    # last instruction — restating the old food when ACKNOWLEDGING a correction
    # ("got it — apples instead") is correct behavior, not a leak.
    final_text = (turn_records[-1].get("nouri") or "").lower() if turn_records else ""
    tools_called = [t.get("tool") for r in turn_records for t in (r.get("tools") or [])]
    failures: list[str] = []
    passes: list[str] = []

    for tool in expect.get("should_call", []):
        if tool in tools_called:
            passes.append(f"called {tool}")
        else:
            failures.append(f"missing tool call: {tool}")

    for tool in expect.get("must_not_call", []):
        if tool in tools_called:
            failures.append(f"unexpected tool call: {tool}")
        else:
            passes.append(f"did not call {tool}")

    if expect.get("should_call_post_food_listing"):
        if "post_food_listing" in tools_called:
            passes.append("posted listing")
        else:
            failures.append("never called post_food_listing")

    for word in expect.get("must_not_say", []):
        if word.lower() in final_text:
            failures.append(f"final turn said forbidden word: {word!r}")
        else:
            passes.append(f"final turn avoided {word!r}")

    for word in expect.get("must_say_at_some_point", []):
        if word.lower() in full_text:
            passes.append(f"mentioned {word!r}")
        else:
            failures.append(f"never mentioned: {word!r}")

    any_lists = expect.get("must_say_at_some_point_any") or []
    if any_lists:
        if any(w.lower() in full_text for w in any_lists):
            passes.append(f"mentioned one of {any_lists}")
        else:
            failures.append(f"never mentioned any of: {any_lists}")

    if expect.get("must_not_ask_intake"):
        last_text = (turn_records[-1].get("nouri") or "").lower()
        if any(m in last_text for m in _INTAKE_QUESTION_MARKERS):
            failures.append("still asking intake questions after abandon/switch")
        else:
            passes.append("stopped asking intake questions")

    return {"failures": failures, "passes": passes}


def run_scenario(token: str, scenario: dict[str, Any]) -> dict[str, Any]:
    name = scenario["name"]
    print(f"\n{'=' * 78}\nSCENARIO {name}\n  purpose: {scenario['purpose']}\n{'=' * 78}")
    _clear_history(token)
    turn_records = []
    for i, msg in enumerate(scenario["turns"], 1):
        print(f"\n  USER {i}: {msg}")
        t0 = time.time()
        resp = _chat(token, msg)
        dt = time.time() - t0
        if resp.get("_error"):
            print(f"  NOURI: <HTTP {resp['status']}> {resp['body']}")
            turn_records.append({"user": msg, "error": resp})
            continue
        text = (resp.get("text") or "").strip()
        tools = resp.get("tool_results") or []
        print(textwrap.fill(f"  NOURI: {text}", width=92, subsequent_indent="         "))
        print(f"  tools: {_summarize_tools(tools)}  ({dt:.1f}s)")
        turn_records.append({
            "user": msg,
            "nouri": text,
            "tools": [
                {"tool": t.get("tool"),
                 "ok": (t.get("result") or {}).get("success", t.get("ok"))}
                for t in tools
            ],
            "elapsed_s": round(dt, 2),
        })
    grade = _grade(scenario, turn_records)
    print("\n  GRADE:")
    for p in grade["passes"]:
        print(f"    PASS  {p}")
    for f in grade["failures"]:
        print(f"    FAIL  {f}")
    return {"scenario": name, "turns": turn_records, "grade": grade}


def main() -> int:
    print(f"[setup] backend={BACKEND_URL}")
    email = _lookup_email(TEST_USER_ID)
    print(f"[setup] minting token for {email}")
    token = _mint_access_token(email)
    results = []
    for scenario in SCENARIOS:
        try:
            results.append(run_scenario(token, scenario))
        except Exception as exc:
            print(f"  EXCEPTION: {exc}")
            results.append({"scenario": scenario["name"], "exception": str(exc)})

    out_path = os.path.join(os.path.dirname(__file__), "share_flow_transcript.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2)
    print(f"\n[done] transcript saved to {out_path}")

    print("\n" + "=" * 78 + "\nSUMMARY\n" + "=" * 78)
    total_pass = total_fail = 0
    for r in results:
        if "grade" in r:
            p = len(r["grade"]["passes"])
            f = len(r["grade"]["failures"])
            total_pass += p
            total_fail += f
            mark = "OK " if f == 0 else "FAIL"
            print(f"  {mark} {r['scenario']:<28}  pass={p} fail={f}")
        else:
            print(f"  ERR  {r['scenario']}: {r.get('exception')}")
    print(f"\n  totals: pass={total_pass} fail={total_fail}")
    return 0 if total_fail == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
