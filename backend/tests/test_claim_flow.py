"""
Claim-flow stress test for the Nouri chat assistant.

Covers correction patterns mirroring the share-flow test, but for the
recipient (claim) side:
  • Switch which listing is being claimed mid-flow ('i meant the apples')
  • Change quantity mid-claim
  • Bare-yes affirmation -> full quantity
  • Ordinal + content cue disagree -> AI must ask
  • Mid-claim search switch (claim -> find)
  • Abandon claim mid-flow
  • Cancel already-claimed item
  • Cross-language correction

Run from repo root with the .venv active:
    python -m backend.tests.test_claim_flow
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


# Owner of the seeded listings used as claim targets. Repeated test runs
# drain the pool by claiming items; we reset their status + quantity
# before each scenario via the Supabase REST API.
SEED_OWNER_ID = "d70afda5-d8ad-453f-a3f2-8af899c05219"
SEED_LISTINGS = {
    "Bag of apples": 12,
    "Whole wheat bread loaves": 4,
    "Fresh sandwiches": 16,
    "Hot lasagna tray": 1,
    "Eggs": 6,
    "Watermelon": 1,
}


def _reset_test_data() -> None:
    """Reset claim test state: release the test user's claims and refill
    seed listings to status='active' with original quantities. Runs once
    per test suite invocation, before any scenarios."""
    # Delete the test user's claims (frees the listings server-side).
    httpx.delete(
        f"{SUPABASE_URL}/rest/v1/food_claims",
        headers={**_admin_headers(), "Prefer": "return=minimal"},
        params={"claimer_id": f"eq.{TEST_USER_ID}"},
        timeout=15,
    )
    # Delete any noise listings the test user accidentally posted.
    httpx.delete(
        f"{SUPABASE_URL}/rest/v1/food_listings",
        headers={**_admin_headers(), "Prefer": "return=minimal"},
        params={"user_id": f"eq.{TEST_USER_ID}"},
        timeout=15,
    )
    # Reset each seed listing to active+original-quantity.
    for title, qty in SEED_LISTINGS.items():
        httpx.patch(
            f"{SUPABASE_URL}/rest/v1/food_listings",
            headers={**_admin_headers(), "Prefer": "return=minimal"},
            params={
                "user_id": f"eq.{SEED_OWNER_ID}",
                "title": f"eq.{title}",
            },
            json={"status": "active", "quantity": qty},
            timeout=15,
        )


SCENARIOS: list[dict[str, Any]] = [
    {
        "name": "C1-switch-item-mid-claim",
        "purpose": "Start claim of bread, then 'i meant the apples'. Should switch target listing, not bundle both.",
        "turns": [
            "find food near me",
            "i'll take the bread",
            "i meant the apples",
            "yes please",
        ],
        "expect": {
            "should_call": ["search_food_near_user", "claim_listing"],
            "must_say_at_some_point": ["apples"],
            "must_not_say_in_final": ["bread"],
        },
    },
    {
        "name": "C2-change-quantity",
        "purpose": "Change claim quantity mid-intake.",
        "turns": [
            "find food near me",
            "claim 4 of the eggs",
            "wait, make it 2",
            "yes",
        ],
        "expect": {
            "should_call": ["search_food_near_user", "claim_listing"],
            "must_say_at_some_point": ["2"],
        },
    },
    {
        "name": "C3-bare-yes-full-qty",
        "purpose": "After search, bare 'yes please' should claim full quantity.",
        "turns": [
            "find food near me",
            "the first one please",
            "yes",
        ],
        "expect": {
            "should_call": ["search_food_near_user", "claim_listing"],
        },
    },
    {
        "name": "C4-ordinal-content-disagree",
        "purpose": "'first one + apples' when item #1 isn't apples -> AI must ask which one.",
        "turns": [
            "find food near me",
            "the first one, the apples",
        ],
        "expect": {
            "must_not_call": ["claim_listing"],
            "must_say_at_some_point_any": ["did you mean", "which one", "which did you mean", "clarify"],
        },
    },
    {
        "name": "C5-claim-to-search-switch",
        "purpose": "Mid-claim, user switches to a new search.",
        "turns": [
            "find food near me",
            "i'll take the bread",
            "actually, find me something else nearby",
        ],
        "expect": {
            "should_call": ["search_food_near_user"],
            "must_not_call_after_switch": ["claim_listing"],
        },
    },
    {
        "name": "C6-abandon-mid-claim",
        "purpose": "Abandon claim partway through.",
        "turns": [
            "find food near me",
            "i'll take the bread",
            "nevermind, forget it",
        ],
        "expect": {
            "must_not_call": ["claim_listing"],
            "must_say_at_some_point_any": ["no problem", "ok", "got it", "dropped"],
        },
    },
    {
        "name": "C7-cancel-after-claim",
        "purpose": "Claim then cancel in same conversation.",
        "turns": [
            "find food near me",
            "claim the sandwiches please",
            "yes",
            "actually, cancel that claim",
        ],
        "expect": {
            "should_call": ["search_food_near_user", "claim_listing", "cancel_claim"],
        },
    },
    {
        "name": "C8-spanish-correction",
        "purpose": "Spanish correction phrase 'quise decir' should pivot.",
        "turns": [
            "busca comida cerca",
            "quiero el pan",
            "quise decir los sandwiches",
            "sí por favor",
        ],
        "expect": {
            "should_call": ["search_food_near_user", "claim_listing"],
            "must_say_at_some_point_any": ["sandwich"],
        },
    },
    {
        "name": "C9-double-correction",
        "purpose": "Two corrections in a row.",
        "turns": [
            "find food near me",
            "i'll take the bread",
            "i meant the apples",
            "wait actually the sandwiches",
            "yes",
        ],
        "expect": {
            "should_call": ["search_food_near_user", "claim_listing"],
            "must_say_at_some_point": ["sandwich"],
        },
    },
    {
        "name": "C10-numeric-ref",
        "purpose": "Use #N reference and bare yes -> claim full quantity.",
        "turns": [
            "find food near me",
            "#1",
            "yes",
        ],
        "expect": {
            "should_call": ["search_food_near_user", "claim_listing"],
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
            if "error" in res:
                extra += f" error={res['error']!r}"
        out.append(f"{name}(ok={ok}){extra}")
    return " | ".join(out)


def _grade(scenario: dict[str, Any], turn_records: list[dict[str, Any]]) -> dict[str, Any]:
    expect = scenario.get("expect") or {}
    full_text = " ".join((r.get("nouri") or "").lower() for r in turn_records)
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

    for word in expect.get("must_not_say_in_final", []):
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

    # Specialized check for C5: after the user said 'actually find me something
    # else', claim_listing should not be called in any subsequent turn.
    after_switch = expect.get("must_not_call_after_switch") or []
    if after_switch:
        switch_idx = None
        for i, r in enumerate(turn_records):
            if "actually" in (r.get("user") or "").lower():
                switch_idx = i
                break
        if switch_idx is not None:
            later_tools = [t.get("tool") for r in turn_records[switch_idx:] for t in (r.get("tools") or [])]
            for tool in after_switch:
                if tool in later_tools:
                    failures.append(f"called {tool} after user pivot")
                else:
                    passes.append(f"did not call {tool} after pivot")

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
                 "ok": (t.get("result") or {}).get("success", t.get("ok")),
                 "title": (t.get("result") or {}).get("title") if isinstance(t.get("result"), dict) else None}
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
    print("[setup] resetting seed data")
    _reset_test_data()
    results = []
    for scenario in SCENARIOS:
        _reset_test_data()  # also reset between scenarios to keep them independent
        try:
            results.append(run_scenario(token, scenario))
        except Exception as exc:
            print(f"  EXCEPTION: {exc}")
            results.append({"scenario": scenario["name"], "exception": str(exc)})

    out_path = os.path.join(os.path.dirname(__file__), "claim_flow_transcript.json")
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
