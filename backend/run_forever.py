"""
Run DoGoods backend forever with an hourly new-listings monitor.

This script starts two things in the same container/process:
1) FastAPI server (uvicorn)
2) Background async loop that checks for newly posted, still-fresh listings every hour

Use this as the runtime entrypoint in production so the automated listing check
is always active.
"""

from __future__ import annotations

import asyncio
from base64 import b64encode
import logging
import os
import signal
import threading
from datetime import datetime, timedelta, timezone

import uvicorn
import httpx

from backend.ai_engine import SUPABASE_SERVICE_KEY, SUPABASE_TIMEOUT, SUPABASE_URL
from backend.tools import _listing_is_fresh_enough

logger = logging.getLogger("run_forever")

AUTOMATION_INTERVAL_SECONDS = int(
    os.getenv("NEW_LISTINGS_CHECK_INTERVAL_SECONDS", "3600")
)
NEW_LISTINGS_MAX_RESULTS = int(os.getenv("NEW_LISTINGS_MAX_RESULTS", "200"))
DRAFT_REMINDER_MIN_HOURS = int(os.getenv("DRAFT_REMINDER_MIN_HOURS", "24"))
DRAFT_REMINDER_COOLDOWN_HOURS = int(os.getenv("DRAFT_REMINDER_COOLDOWN_HOURS", "24"))
ADMIN_BROADCAST_BATCH = int(os.getenv("ADMIN_BROADCAST_BATCH", "20"))

TWILIO_ACCOUNT_SID = os.getenv("TWILIO_ACCOUNT_SID", "")
TWILIO_AUTH_TOKEN = os.getenv("TWILIO_AUTH_TOKEN", "")
TWILIO_PHONE_NUMBER = os.getenv("TWILIO_PHONE_NUMBER", "")

_warned_missing_broadcast_table = False


async def _supabase_get_rows(table: str, params: dict) -> list[dict]:
    """Fetch rows from Supabase using a local AsyncClient.

    Uses a fresh client per call to avoid sharing async transports across
    event loops/threads (this monitor runs in its own thread).
    """
    if not SUPABASE_URL or not SUPABASE_SERVICE_KEY:
        logger.warning("Supabase not configured; automation workers are disabled")
        return []

    headers = {
        "apikey": SUPABASE_SERVICE_KEY,
        "Authorization": f"Bearer {SUPABASE_SERVICE_KEY}",
        "Accept": "application/json",
    }

    async with httpx.AsyncClient(timeout=SUPABASE_TIMEOUT) as client:
        resp = await client.get(
            f"{SUPABASE_URL}/rest/v1/{table}",
            params=params,
            headers=headers,
        )
        resp.raise_for_status()
        payload = resp.json()
        return payload if isinstance(payload, list) else []


async def _supabase_patch_rows(table: str, params: dict, body: dict) -> list[dict]:
    if not SUPABASE_URL or not SUPABASE_SERVICE_KEY:
        return []

    headers = {
        "apikey": SUPABASE_SERVICE_KEY,
        "Authorization": f"Bearer {SUPABASE_SERVICE_KEY}",
        "Accept": "application/json",
        "Content-Type": "application/json",
        "Prefer": "return=representation",
    }
    async with httpx.AsyncClient(timeout=SUPABASE_TIMEOUT) as client:
        resp = await client.patch(
            f"{SUPABASE_URL}/rest/v1/{table}",
            params=params,
            headers=headers,
            json=body,
        )
        resp.raise_for_status()
        payload = resp.json()
        return payload if isinstance(payload, list) else []


async def _supabase_insert_row(table: str, body: dict) -> dict:
    if not SUPABASE_URL or not SUPABASE_SERVICE_KEY:
        return {}

    headers = {
        "apikey": SUPABASE_SERVICE_KEY,
        "Authorization": f"Bearer {SUPABASE_SERVICE_KEY}",
        "Accept": "application/json",
        "Content-Type": "application/json",
        "Prefer": "return=representation,resolution=ignore-duplicates",
    }
    async with httpx.AsyncClient(timeout=SUPABASE_TIMEOUT) as client:
        resp = await client.post(
            f"{SUPABASE_URL}/rest/v1/{table}",
            headers=headers,
            json=body,
        )
        resp.raise_for_status()
        payload = resp.json()
        if isinstance(payload, list) and payload:
            return payload[0]
        return payload if isinstance(payload, dict) else {}


def _pref_enabled(user: dict, keys: tuple[str, ...], default: bool = True) -> bool:
    for k in keys:
        if k in user and user.get(k) is not None:
            return bool(user.get(k))
    return default


def _to_lower_set(value) -> set[str]:
    if not value:
        return set()
    if isinstance(value, str):
        return {v.strip().lower() for v in value.split(",") if v.strip()}
    if isinstance(value, list):
        return {str(v).strip().lower() for v in value if str(v).strip()}
    return set()


def _user_wants_in_app(user: dict) -> bool:
    return _pref_enabled(
        user,
        (
            "in_app_notifications_enabled",
            "chat_notifications_enabled",
            "notifications_enabled",
        ),
        default=True,
    )


def _user_wants_sms(user: dict) -> bool:
    sms_opt_in = _pref_enabled(user, ("sms_opt_in",), default=False)
    sms_enabled = _pref_enabled(user, ("sms_notifications_enabled",), default=False)
    return sms_opt_in and sms_enabled and bool(user.get("phone"))


async def _recent_notification_exists(
    *,
    user_id: str,
    event: str,
    ref_key: str,
    ref_value: str,
    lookback_hours: int,
) -> bool:
    cutoff = (datetime.now(timezone.utc) - timedelta(hours=lookback_hours)).isoformat()
    rows = await _supabase_get_rows(
        "notifications",
        {
            "user_id": f"eq.{user_id}",
            "data->>event": f"eq.{event}",
            f"data->>{ref_key}": f"eq.{ref_value}",
            "created_at": f"gte.{cutoff}",
            "select": "id",
            "limit": "1",
        },
    )
    return bool(rows)


async def _send_in_app_notification(
    *,
    user_id: str,
    title: str,
    message: str,
    notification_type: str,
    data: dict,
) -> bool:
    try:
        row = await _supabase_insert_row(
            "notifications",
            {
                "user_id": user_id,
                "title": title,
                "message": message,
                "type": notification_type,
                "read": False,
                "data": data,
            },
        )
        return bool(row)
    except Exception as exc:
        logger.error("Failed to create in-app notification for user=%s: %s", user_id, exc)
        return False


async def _send_sms_notification(*, to_phone: str, message: str, sms_type: str = "notification") -> bool:
    if not all([TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN, TWILIO_PHONE_NUMBER]):
        return False
    url = f"https://api.twilio.com/2010-04-01/Accounts/{TWILIO_ACCOUNT_SID}/Messages.json"
    auth_str = b64encode(f"{TWILIO_ACCOUNT_SID}:{TWILIO_AUTH_TOKEN}".encode()).decode()
    sent_ok = False
    error_msg = None
    sid = None
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.post(
                url,
                data={
                    "To": to_phone,
                    "From": TWILIO_PHONE_NUMBER,
                    "Body": message[:1600],
                },
                headers={"Authorization": f"Basic {auth_str}"},
            )
            data = resp.json() if resp.headers.get("content-type", "").startswith("application/json") else {}
            sid = data.get("sid")
            error_msg = data.get("error_message")
            sent_ok = resp.status_code in (200, 201) and not error_msg
    except Exception as exc:
        error_msg = str(exc)

    try:
        await _supabase_insert_row(
            "sms_logs",
            {
                "phone_number": to_phone,
                "message": message[:1600],
                "type": sms_type,
                "status": "sent" if sent_ok else "failed",
                "twilio_sid": sid,
                "error_message": error_msg,
            },
        )
    except Exception:
        pass

    return sent_ok


async def _load_notification_users() -> list[dict]:
    # Pull only fields used for preference checks + targeting.
    return await _supabase_get_rows(
        "users",
        {
            "select": (
                "id,name,phone,role,community_role,community_id,"
                "sms_opt_in,sms_notifications_enabled,"
                "notifications_enabled,in_app_notifications_enabled,chat_notifications_enabled,"
                "dietary_restrictions,allergies"
            ),
            "limit": "1000",
        },
    )


async def check_new_listings_once(last_check_at: datetime) -> tuple[datetime, int]:
    """Check fresh new listings and send personalized notifications."""
    now = datetime.now(timezone.utc)
    since_iso = last_check_at.isoformat()

    try:
        listings = await _supabase_get_rows(
            "food_listings",
            {
                "select": (
                    "id,title,category,status,user_id,community_id,"
                    "dietary_tags,allergens,created_at,expiry_date,pickup_by"
                ),
                "status": "in.(approved,active)",
                "created_at": f"gte.{since_iso}",
                "order": "created_at.desc",
                "limit": str(max(1, NEW_LISTINGS_MAX_RESULTS)),
            },
        )
    except Exception as exc:
        logger.error("Hourly listing check failed: %s", exc)
        return now, 0

    fresh = [row for row in listings if _listing_is_fresh_enough(row, now=now)]

    if not fresh:
        logger.info("Hourly listing check: no new fresh listings since %s", since_iso)
        return now, 0

    users = await _load_notification_users()
    if not users:
        logger.info("Hourly listing check: no users available for notifications")
        return now, 0

    notified_count = 0
    for listing in fresh:
        listing_id = str(listing.get("id"))
        listing_title = listing.get("title") or "New food listing"
        listing_tags = _to_lower_set(listing.get("dietary_tags"))
        listing_allergens = _to_lower_set(listing.get("allergens"))
        listing_owner = str(listing.get("user_id")) if listing.get("user_id") else None
        listing_community = listing.get("community_id")

        for user in users:
            uid = user.get("id")
            if not uid:
                continue
            uid_str = str(uid)
            if listing_owner and uid_str == listing_owner:
                continue

            user_role = str(user.get("community_role") or user.get("role") or "").lower()
            if user_role in {"donor", "admin", "organizer"}:
                continue

            # If both sides have a community assignment, keep notifications local.
            if listing_community is not None and user.get("community_id") is not None:
                if str(user.get("community_id")) != str(listing_community):
                    continue

            user_dietary = _to_lower_set(user.get("dietary_restrictions"))
            user_allergies = _to_lower_set(user.get("allergies"))
            if user_dietary and listing_tags and user_dietary.isdisjoint(listing_tags):
                continue
            if user_allergies and listing_allergens and not user_allergies.isdisjoint(listing_allergens):
                continue

            already_notified = await _recent_notification_exists(
                user_id=uid_str,
                event="new_listing",
                ref_key="listing_id",
                ref_value=listing_id,
                lookback_hours=48,
            )
            if already_notified:
                continue

            msg = f"New listing: {listing_title} is now available. Open DoGoods to view details."
            sent_any = False

            if _user_wants_in_app(user):
                sent_any = await _send_in_app_notification(
                    user_id=uid_str,
                    title="New listing available",
                    message=msg,
                    notification_type="alert",
                    data={
                        "event": "new_listing",
                        "listing_id": listing_id,
                        "category": listing.get("category"),
                    },
                ) or sent_any

            if _user_wants_sms(user):
                sms_ok = await _send_sms_notification(
                    to_phone=str(user.get("phone")),
                    message=msg,
                    sms_type="notification",
                )
                sent_any = sms_ok or sent_any

            if sent_any:
                notified_count += 1

    logger.info(
        "Hourly listing check: %d fresh listing(s), %d notification delivery action(s)",
        len(fresh),
        notified_count,
    )

    return now, len(fresh)


async def check_draft_listings_once() -> int:
    """Find stale drafts and remind owners to publish or discard."""
    now = datetime.now(timezone.utc)
    try:
        drafts = await _supabase_get_rows(
            "food_listings",
            {
                "status": "eq.draft",
                "select": "id,title,user_id,created_at,updated_at",
                "order": "updated_at.asc",
                "limit": "200",
            },
        )
    except Exception as exc:
        # Some environments may not support a draft status; fail soft.
        logger.info("Draft listing check skipped: %s", exc)
        return 0

    users = await _load_notification_users()
    users_by_id = {str(u.get("id")): u for u in users if u.get("id")}

    reminders_sent = 0
    for draft in drafts:
        owner_id = draft.get("user_id")
        if not owner_id:
            continue
        owner = users_by_id.get(str(owner_id))
        if not owner:
            continue

        ts = draft.get("updated_at") or draft.get("created_at")
        updated_dt = datetime.fromisoformat(str(ts).replace("Z", "+00:00")) if ts else None
        if not updated_dt:
            continue
        if updated_dt.tzinfo is None:
            updated_dt = updated_dt.replace(tzinfo=timezone.utc)

        age_hours = (now - updated_dt).total_seconds() / 3600
        if age_hours < DRAFT_REMINDER_MIN_HOURS:
            continue

        listing_id = str(draft.get("id"))
        already = await _recent_notification_exists(
            user_id=str(owner_id),
            event="draft_listing_reminder",
            ref_key="listing_id",
            ref_value=listing_id,
            lookback_hours=max(1, DRAFT_REMINDER_COOLDOWN_HOURS),
        )
        if already:
            continue

        title = draft.get("title") or "your draft listing"
        msg = f"Your draft '{title}' is still unpublished. Publish it if it's ready, or discard it if not needed."
        sent_any = False

        if _user_wants_in_app(owner):
            sent_any = await _send_in_app_notification(
                user_id=str(owner_id),
                title="Draft listing reminder",
                message=msg,
                notification_type="system",
                data={
                    "event": "draft_listing_reminder",
                    "listing_id": listing_id,
                },
            ) or sent_any

        if _user_wants_sms(owner):
            sent_any = await _send_sms_notification(
                to_phone=str(owner.get("phone")),
                message=msg,
                sms_type="notification",
            ) or sent_any

        if sent_any:
            reminders_sent += 1

    if reminders_sent:
        logger.info("Draft listing check: sent %d reminder(s)", reminders_sent)
    return reminders_sent


async def process_admin_broadcasts_once() -> int:
    """Deliver queued admin broadcasts and mark them sent."""
    global _warned_missing_broadcast_table
    try:
        broadcasts = await _supabase_get_rows(
            "admin_broadcasts",
            {
                "sent": "eq.false",
                "select": "id,title,message,channel,target_role,community_id,created_at",
                "order": "created_at.asc",
                "limit": str(max(1, ADMIN_BROADCAST_BATCH)),
            },
        )
    except Exception as exc:
        if not _warned_missing_broadcast_table:
            logger.warning("Admin broadcasts disabled: %s", exc)
            _warned_missing_broadcast_table = True
        return 0

    if not broadcasts:
        return 0

    users = await _load_notification_users()
    delivered_total = 0
    now_iso = datetime.now(timezone.utc).isoformat()

    for b in broadcasts:
        bid = str(b.get("id"))
        title = b.get("title") or "Admin message"
        message = b.get("message") or ""
        channel = str(b.get("channel") or "in_app").lower()
        target_role = str(b.get("target_role") or "").lower().strip()
        target_community = b.get("community_id")

        delivered_for_broadcast = 0
        for user in users:
            uid = user.get("id")
            if not uid:
                continue
            uid_str = str(uid)

            if target_role:
                role = str(user.get("community_role") or user.get("role") or "").lower()
                if role != target_role:
                    continue
            if target_community is not None and user.get("community_id") is not None:
                if str(user.get("community_id")) != str(target_community):
                    continue

            if channel in {"in_app", "both"} and _user_wants_in_app(user):
                ok = await _send_in_app_notification(
                    user_id=uid_str,
                    title=title,
                    message=message,
                    notification_type="system",
                    data={
                        "event": "admin_broadcast",
                        "broadcast_id": bid,
                    },
                )
                delivered_for_broadcast += 1 if ok else 0

            if channel in {"sms", "both"} and _user_wants_sms(user):
                ok = await _send_sms_notification(
                    to_phone=str(user.get("phone")),
                    message=f"{title}: {message}",
                    sms_type="notification",
                )
                delivered_for_broadcast += 1 if ok else 0

        # Mark as sent after processing to avoid replaying every hour.
        try:
            await _supabase_patch_rows(
                "admin_broadcasts",
                {"id": f"eq.{bid}"},
                {
                    "sent": True,
                    "sent_at": now_iso,
                    "delivered_count": delivered_for_broadcast,
                },
            )
        except Exception as exc:
            logger.error("Failed to mark admin broadcast %s as sent: %s", bid, exc)

        delivered_total += delivered_for_broadcast

    logger.info(
        "Admin broadcast processor: %d broadcast(s), %d delivery action(s)",
        len(broadcasts),
        delivered_total,
    )

    return delivered_total


async def new_listings_monitor_loop(stop_event: threading.Event) -> None:
    """Background forever-loop that runs hourly automation workers."""
    interval = max(60, AUTOMATION_INTERVAL_SECONDS)
    logger.info("Automation monitor started (interval=%ds)", interval)

    # On first run, look back one interval so we do not miss recent posts.
    last_check_at = datetime.now(timezone.utc) - timedelta(seconds=interval)

    while not stop_event.is_set():
        cycle_start = datetime.now(timezone.utc)
        try:
            last_check_at, _ = await check_new_listings_once(last_check_at)
        except Exception as exc:
            logger.error("New-listings worker failed: %s", exc)

        try:
            await check_draft_listings_once()
        except Exception as exc:
            logger.error("Draft reminder worker failed: %s", exc)

        try:
            await process_admin_broadcasts_once()
        except Exception as exc:
            logger.error("Admin broadcast worker failed: %s", exc)

        elapsed = (datetime.now(timezone.utc) - cycle_start).total_seconds()
        wait_seconds = max(1, int(interval - elapsed))

        # Sleep in short chunks so shutdown is responsive.
        for _ in range(wait_seconds):
            if stop_event.is_set():
                break
            await asyncio.sleep(1)

    logger.info("Automation monitor stopped")


def start_new_listings_monitor(stop_event: threading.Event) -> threading.Thread:
    """Run async monitor loop on a dedicated daemon thread."""

    def _runner() -> None:
        asyncio.run(new_listings_monitor_loop(stop_event))

    thread = threading.Thread(
        target=_runner,
        name="new-listings-monitor",
        daemon=True,
    )
    thread.start()
    return thread


def main() -> None:
    logging.basicConfig(level=logging.INFO)

    host = os.getenv("HOST", "0.0.0.0")
    port = int(os.getenv("PORT", "8000"))
    log_level = os.getenv("LOG_LEVEL", "info")

    stop_event = threading.Event()

    def _handle_stop(signum, _frame):
        logger.info("Received signal %s, shutting down background monitor", signum)
        stop_event.set()

    signal.signal(signal.SIGINT, _handle_stop)
    signal.signal(signal.SIGTERM, _handle_stop)

    monitor_thread = start_new_listings_monitor(stop_event)

    try:
        uvicorn.run("backend.app:app", host=host, port=port, log_level=log_level)
    finally:
        stop_event.set()
        monitor_thread.join(timeout=5)


if __name__ == "__main__":
    main()
