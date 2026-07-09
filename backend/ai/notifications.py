"""
Automated-messaging system for DoGoods AI (Nouri).

Responsibilities
----------------
1. Hourly job: scan newly-posted FoodResource listings, match them to
   interested users (respecting notification / SMS consent / dietary
   preferences / allergies), and draft a personalised message per user.
2. Persist each draft as an :class:`AIBroadcast` row in status ``pending``
   so an administrator can review and approve before delivery.
3. Admin approval triggers :func:`send_broadcast`, which delivers the
   message by SMS (Twilio) and/or in-app chat (``messages`` table).

The hourly loop is spawned from ``backend.ai.routes.start_background_jobs``
so it runs inside the same FastAPI process that ``run_forever.py`` keeps
alive.  A second manual entry-point (``python -m backend.ai.notifications``)
is provided so the job can also be run ad-hoc from cron / run_forever.
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional

logger = logging.getLogger("ai_notifications")


def _utcnow() -> datetime:
    """Naive UTC datetime replacement for the deprecated ``_utcnow()``.

    See ``backend/ai/ai_engine.py::_utcnow`` for why we stay on naive
    timestamps until the DB columns get a tz-aware migration.
    """
    return datetime.now(timezone.utc).replace(tzinfo=None)

# How often the scan/draft job runs (seconds).  Default = 1 hour.
BROADCAST_INTERVAL = int(os.getenv("AI_BROADCAST_INTERVAL", "3600"))
# Lookback window when searching for "new" listings.  Slightly larger than
# the interval so we never miss one on the boundary.
BROADCAST_LOOKBACK_MIN = int(os.getenv("AI_BROADCAST_LOOKBACK_MIN", "75"))
# Safety cap so a runaway job can't spam thousands of rows.
BROADCAST_MAX_PER_RUN = int(os.getenv("AI_BROADCAST_MAX_PER_RUN", "500"))
# If True, approved broadcasts auto-send without a human click.  Default False
# (per product spec: "Admin approves broadcasts").
AI_BROADCAST_AUTO_APPROVE = os.getenv("AI_BROADCAST_AUTO_APPROVE", "0") in ("1", "true", "yes")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _safe_json_loads(raw: Optional[str]) -> list | dict | None:
    if not raw:
        return None
    try:
        return json.loads(raw)
    except (TypeError, ValueError):
        return None


def _as_lower_set(value) -> set[str]:
    if not value:
        return set()
    if isinstance(value, str):
        value = _safe_json_loads(value) or [v.strip() for v in value.split(",")]
    if isinstance(value, (list, tuple, set)):
        return {str(v).strip().lower() for v in value if str(v).strip()}
    return set()


def _user_prefers_language(user) -> str:
    """Best-effort: infer 'en' vs 'es' from notification_preferences."""
    prefs = _safe_json_loads(getattr(user, "notification_preferences", None)) or {}
    lang = str(prefs.get("language", "en")).lower()
    return "es" if lang.startswith("es") else "en"


def _user_wants_new_listings(user) -> bool:
    """Respect notification_preferences.new_listings if present (default: True)."""
    prefs = _safe_json_loads(getattr(user, "notification_preferences", None)) or {}
    if "new_listings" in prefs:
        return bool(prefs["new_listings"])
    # Secondary opt-in: SMS notification_types array
    sms_types = _safe_json_loads(getattr(user, "sms_notification_types", None)) or []
    if isinstance(sms_types, list) and sms_types:
        return any(t in ("new_listings", "listings", "all") for t in sms_types)
    return True  # default: opted-in


def _user_sms_ok(user) -> bool:
    if not getattr(user, "sms_consent_given", False):
        return False
    if getattr(user, "sms_opt_out_date", None):
        return False
    return bool(getattr(user, "phone", None))


def _allergen_conflict(user, food) -> bool:
    user_allergies = _as_lower_set(getattr(user, "allergies", None))
    if not user_allergies:
        return False
    food_allergens = _as_lower_set(getattr(food, "allergens", None))
    return bool(user_allergies & food_allergens)


def _dietary_conflict(user, food) -> bool:
    """A listing conflicts when the user has a restriction the listing does not satisfy.

    We only enforce a few well-defined restrictions.  Missing info => no conflict.
    """
    user_restrictions = _as_lower_set(getattr(user, "dietary_restrictions", None))
    if not user_restrictions:
        return False
    food_tags = _as_lower_set(getattr(food, "dietary_tags", None))
    for req in user_restrictions:
        if req in {"vegetarian", "vegan", "halal", "kosher", "gluten-free",
                   "dairy-free", "nut-free"}:
            if req not in food_tags:
                return True
    return False


def _category_match(user, food) -> bool:
    prefs = _as_lower_set(getattr(user, "preferred_categories", None))
    if not prefs:
        return True  # user didn't narrow it down -> match everything
    food_cat = getattr(food, "category", None)
    if food_cat is None:
        return True
    food_cat_str = (food_cat.value if hasattr(food_cat, "value") else str(food_cat)).lower()
    return food_cat_str in prefs


# ---------------------------------------------------------------------------
# Template drafting (fallback when OpenAI is unavailable / disabled)
# ---------------------------------------------------------------------------

def _template_en(user_name: str, food, donor_name: str) -> str:
    title = getattr(food, "title", "fresh food")
    addr = getattr(food, "address", "") or ""
    short_addr = addr.split(",")[0] if addr else ""
    name = (user_name or "there").split()[0]
    window = ""
    if getattr(food, "pickup_window_end", None):
        window = f" Pickup by {food.pickup_window_end.strftime('%a %I:%M %p')}."
    location = f" at {short_addr}" if short_addr else ""
    return (
        f"Hi {name}! {donor_name or 'A donor'} just posted \"{title}\"{location}.{window} "
        f"Open DoGoods to claim it. Reply STOP to opt out."
    )


def _template_es(user_name: str, food, donor_name: str) -> str:
    title = getattr(food, "title", "comida disponible")
    addr = getattr(food, "address", "") or ""
    short_addr = addr.split(",")[0] if addr else ""
    name = (user_name or "hola").split()[0]
    window = ""
    if getattr(food, "pickup_window_end", None):
        window = f" Recoger antes de {food.pickup_window_end.strftime('%a %I:%M %p')}."
    location = f" en {short_addr}" if short_addr else ""
    return (
        f"¡Hola {name}! {donor_name or 'Un donante'} acaba de publicar \"{title}\"{location}.{window} "
        f"Abre DoGoods para reclamarlo. Responde STOP para cancelar."
    )


async def _ai_personalize(base_text: str, user, food, lang: str) -> str:
    """Ask the LLM to lightly personalise the template. Falls back on error."""
    try:
        from backend.ai.ai_engine import conversation_engine, OPENAI_API_KEY
    except Exception:
        return base_text
    if not OPENAI_API_KEY:
        return base_text

    allergies = _as_lower_set(getattr(user, "allergies", None))
    diets = _as_lower_set(getattr(user, "dietary_restrictions", None))
    hints = []
    if allergies:
        hints.append(f"user allergies: {', '.join(sorted(allergies))}")
    if diets:
        hints.append(f"dietary: {', '.join(sorted(diets))}")
    if getattr(user, "household_size", None):
        hints.append(f"household size: {user.household_size}")

    system = (
        "You refine outbound SMS notifications for a food-sharing app. "
        "Keep it under 320 characters, friendly, actionable, include the "
        "'Reply STOP to opt out' line, and respond ONLY with the final message text. "
        + ("Respond in Spanish." if lang == "es" else "Respond in English.")
    )
    user_msg = (
        f"Draft (rewrite lightly, do NOT add facts):\n{base_text}\n\n"
        f"Listing title: {getattr(food, 'title', '')}\n"
        f"User hints: {'; '.join(hints) if hints else 'none'}"
    )
    try:
        reply = await conversation_engine.public_chat_reply(
            [{"role": "system", "content": system},
             {"role": "user", "content": user_msg}],
            lang=lang,
        )
        reply = (reply or "").strip()
        if 10 <= len(reply) <= 500:
            return reply
    except Exception as exc:  # pragma: no cover - network-ish path
        logger.warning("AI personalisation failed, using template: %s", exc)
    return base_text


async def _draft_message(user, food, donor_name: str) -> tuple[str, str]:
    lang = _user_prefers_language(user)
    base = _template_es(user.name, food, donor_name) if lang == "es" \
        else _template_en(user.name, food, donor_name)
    refined = await _ai_personalize(base, user, food, lang)
    return refined, lang


# ---------------------------------------------------------------------------
# Core job
# ---------------------------------------------------------------------------

def _collect_candidates() -> list[dict]:
    """DB work: find new listings + matching users. Returns plain dicts."""
    from backend.app import SessionLocal
    from backend.models import User, FoodResource, UserRole
    from backend.ai.models import AIBroadcast

    out: list[dict] = []
    db = SessionLocal()
    try:
        since = _utcnow() - timedelta(minutes=BROADCAST_LOOKBACK_MIN)
        listings = (
            db.query(FoodResource)
            .filter(FoodResource.created_at >= since)
            .filter(FoodResource.status == "available")
            .order_by(FoodResource.created_at.asc())
            .all()
        )
        if not listings:
            return []

        # Already-broadcasted listing IDs (skip to avoid duplicates).
        already = {
            row[0]
            for row in db.query(AIBroadcast.food_resource_id)
            .filter(AIBroadcast.food_resource_id.in_([l.id for l in listings]))
            .distinct()
            .all()
            if row[0] is not None
        }

        # Candidate recipients: recipients + drivers + admins who opted in.
        # (Donors get notified via existing favourite-location path already.)
        try:
            candidate_roles = [UserRole.RECIPIENT, UserRole.DRIVER]
        except AttributeError:
            candidate_roles = None  # if enum differs, fall through to 'all non-admin'

        q = db.query(User)
        if candidate_roles:
            q = q.filter(User.role.in_(candidate_roles))
        users = q.all()

        for food in listings:
            if food.id in already:
                continue
            donor = db.query(User).filter(User.id == food.donor_id).first()
            donor_name = donor.name if donor else ""
            for u in users:
                if u.id == food.donor_id:
                    continue
                if not _user_wants_new_listings(u):
                    continue
                if _allergen_conflict(u, food):
                    continue
                if _dietary_conflict(u, food):
                    continue
                if not _category_match(u, food):
                    continue
                sms_ok = _user_sms_ok(u)
                # If SMS not allowed AND user has no app channel, skip (still
                # keep in-app chat as a fallback - every user has an inbox).
                channel = "sms" if sms_ok else "chat"
                out.append({
                    "food_id": food.id,
                    "user_id": u.id,
                    "user_name": u.name,
                    "donor_name": donor_name,
                    "channel": channel,
                    "_food": food,    # detached-but-usable within this session
                    "_user": u,
                })
                if len(out) >= BROADCAST_MAX_PER_RUN:
                    return out
    finally:
        db.close()
    return out


def _persist_drafts(batch_id: str, drafts: list[dict]) -> int:
    from backend.app import SessionLocal
    from backend.ai.models import AIBroadcast

    db = SessionLocal()
    inserted = 0
    try:
        for d in drafts:
            row = AIBroadcast(
                food_resource_id=d["food_id"],
                user_id=d["user_id"],
                channel=d["channel"],
                language=d["language"],
                message=d["message"],
                status="pending",
                batch_id=batch_id,
            )
            db.add(row)
            inserted += 1
        db.commit()
    except Exception as exc:
        logger.error("Failed to persist broadcast drafts: %s", exc)
        db.rollback()
    finally:
        db.close()
    return inserted


async def scan_and_draft_new_listings() -> dict:
    """One pass of the hourly job.  Returns stats dict."""
    loop = asyncio.get_event_loop()
    candidates = await loop.run_in_executor(None, _collect_candidates)
    if not candidates:
        logger.info("Broadcast job: no new listings needing notification")
        return {"listings": 0, "drafts": 0, "batch_id": None}

    batch_id = uuid.uuid4().hex[:16]
    drafts: list[dict] = []
    for c in candidates:
        message, lang = await _draft_message(c["_user"], c["_food"], c["donor_name"])
        drafts.append({
            "food_id": c["food_id"],
            "user_id": c["user_id"],
            "channel": c["channel"],
            "language": lang,
            "message": message,
        })

    inserted = await loop.run_in_executor(None, _persist_drafts, batch_id, drafts)

    if AI_BROADCAST_AUTO_APPROVE:
        await auto_send_pending(batch_id=batch_id)

    logger.info(
        "Broadcast job: %d draft(s) created for %d candidate match(es) (batch=%s)",
        inserted, len(candidates), batch_id,
    )
    return {
        "listings": len({c["food_id"] for c in candidates}),
        "drafts": inserted,
        "batch_id": batch_id,
    }


# ---------------------------------------------------------------------------
# Delivery
# ---------------------------------------------------------------------------

async def _deliver_sms(phone: str, text: str) -> bool:
    try:
        from backend.sms_service import send_sms_real  # type: ignore
    except ImportError:
        logger.warning("sms_service not available; cannot send SMS")
        return False
    try:
        return bool(await asyncio.get_event_loop().run_in_executor(
            None, send_sms_real, phone, text
        ))
    except Exception as exc:
        logger.error("SMS send failed: %s", exc)
        return False


def _deliver_chat(user_id: int, text: str) -> bool:
    """Insert an in-app chat message from 'the system' to the user."""
    from backend.app import SessionLocal
    from backend.models import Message
    db = SessionLocal()
    try:
        msg = Message(
            sender_id=user_id,             # single-user conversation convention
            conversation_id=f"user_{user_id}",
            content=text,
            is_from_admin=True,
            is_read=False,
        )
        db.add(msg)
        db.commit()
        return True
    except Exception as exc:
        logger.error("Chat deliver failed: %s", exc)
        db.rollback()
        return False
    finally:
        db.close()


async def send_broadcast(broadcast_id: int) -> dict:
    """Deliver an already-approved broadcast.  Idempotent."""
    from backend.app import SessionLocal
    from backend.ai.models import AIBroadcast
    from backend.models import User

    def _load():
        db = SessionLocal()
        try:
            b = db.query(AIBroadcast).filter(AIBroadcast.id == broadcast_id).first()
            if not b:
                return None
            u = db.query(User).filter(User.id == b.user_id).first()
            return {
                "id": b.id,
                "status": b.status,
                "channel": b.channel,
                "message": b.message,
                "user_id": b.user_id,
                "phone": u.phone if u else None,
                "sms_ok": _user_sms_ok(u) if u else False,
            }
        finally:
            db.close()

    def _mark(status: str, error: Optional[str] = None) -> None:
        db = SessionLocal()
        try:
            b = db.query(AIBroadcast).filter(AIBroadcast.id == broadcast_id).first()
            if not b:
                return
            b.status = status
            b.error = error
            if status == "sent":
                b.sent_at = _utcnow()
            db.commit()
        finally:
            db.close()

    loop = asyncio.get_event_loop()
    info = await loop.run_in_executor(None, _load)
    if not info:
        return {"ok": False, "error": "not_found"}
    if info["status"] not in ("approved", "pending"):  # allow replay of 'failed'?
        return {"ok": False, "error": f"bad_status:{info['status']}"}

    sent_any = False
    errors: list[str] = []

    if info["channel"] in ("sms", "both") and info["sms_ok"] and info["phone"]:
        if await _deliver_sms(info["phone"], info["message"]):
            sent_any = True
        else:
            errors.append("sms_failed")

    if info["channel"] in ("chat", "both"):
        ok = await loop.run_in_executor(None, _deliver_chat, info["user_id"], info["message"])
        if ok:
            sent_any = True
        else:
            errors.append("chat_failed")

    if sent_any:
        await loop.run_in_executor(None, _mark, "sent", None)
        return {"ok": True, "errors": errors}
    await loop.run_in_executor(None, _mark, "failed", ",".join(errors) or "no_channel")
    return {"ok": False, "error": ",".join(errors) or "no_channel"}


async def auto_send_pending(batch_id: Optional[str] = None) -> int:
    """Approve + send all pending broadcasts (used when AUTO_APPROVE=1)."""
    from backend.app import SessionLocal
    from backend.ai.models import AIBroadcast

    def _ids():
        db = SessionLocal()
        try:
            q = db.query(AIBroadcast.id).filter(AIBroadcast.status == "pending")
            if batch_id:
                q = q.filter(AIBroadcast.batch_id == batch_id)
            return [r[0] for r in q.all()]
        finally:
            db.close()

    def _approve(ids: list[int]):
        db = SessionLocal()
        try:
            db.query(AIBroadcast).filter(AIBroadcast.id.in_(ids)).update(
                {"status": "approved", "approved_at": _utcnow()},
                synchronize_session=False,
            )
            db.commit()
        finally:
            db.close()

    loop = asyncio.get_event_loop()
    ids = await loop.run_in_executor(None, _ids)
    if not ids:
        return 0
    await loop.run_in_executor(None, _approve, ids)
    sent = 0
    for bid in ids:
        res = await send_broadcast(bid)
        if res.get("ok"):
            sent += 1
    return sent


# ---------------------------------------------------------------------------
# Background loop
# ---------------------------------------------------------------------------

async def broadcast_loop() -> None:
    """Hourly loop: drafts new-listing notifications for admin approval."""
    logger.info("AI broadcast loop started (interval=%ds)", BROADCAST_INTERVAL)
    # Small initial delay so the server finishes warming up first.
    await asyncio.sleep(30)
    consecutive_failures = 0
    while True:
        try:
            await scan_and_draft_new_listings()
            consecutive_failures = 0
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            consecutive_failures += 1
            logger.error("Broadcast loop error (#%d): %s", consecutive_failures, exc)

        backoff = BROADCAST_INTERVAL
        if consecutive_failures:
            backoff = min(BROADCAST_INTERVAL * (2 ** consecutive_failures), 6 * 3600)
        await asyncio.sleep(backoff)


# ---------------------------------------------------------------------------
# Entry-point for manual / cron runs
# ---------------------------------------------------------------------------

async def _main() -> None:  # pragma: no cover
    logging.basicConfig(level=logging.INFO)
    stats = await scan_and_draft_new_listings()
    print(json.dumps(stats, indent=2))


if __name__ == "__main__":  # pragma: no cover
    asyncio.run(_main())
