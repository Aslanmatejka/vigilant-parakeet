"""Unified natural conversation flow detection and per-turn reminders."""
from __future__ import annotations

import difflib
import os
import re
from typing import Literal, Optional

FlowKind = Literal["idle", "posting", "claiming", "finding", "requesting"]
AssistanceMode = Literal["hands_on", "guided"]
AssistanceGoal = Literal["find", "share", "request"]

_PHOTO_URL_RE = re.compile(
    r"(?:^|\s)image:\s*\S+"
    r"|/uploads/ai/\S+"
    r"|https?://\S+/storage/v1/object/public/\S+"
    r"|https?://\S+\.(?:jpg|jpeg|png|webp|gif)(?:\?\S*)?",
    re.IGNORECASE,
)

_PHOTO_DECLINE_PHRASES: tuple[str, ...] = (
    "no photo", "skip photo", "without a photo", "without photo",
    "no picture", "sin foto", "no foto", "skip the photo",
    "don't have a photo", "dont have a photo",
    "post without", "publish without", "post without a photo",
    "post without photo", "sin imagen", "publicar sin foto",
)

_PHOTO_ALREADY_SHARED_PHRASES: tuple[str, ...] = (
    "already shared the photo", "already shared the photos",
    "already sent the photo", "already sent the photos",
    "already uploaded the photo", "already uploaded the photos",
    "already uploaded photo", "already uploaded photos",
    "already gave you the photo", "already gave you the photos",
    "i already shared the photo", "i already shared the photos",
    "i already sent the photo", "i already sent the photos",
    "photos with you", "photo with you",
    "i sent the photo", "i sent the photos", "photos i sent",
    "ya compartí la foto", "ya envié la foto", "ya te mandé la foto",
)

_PHOTO_RECEIVED_ASSISTANT: tuple[str, ...] = (
    "photos received", "photo received", "got both photos", "got your photos",
    "got the photos", "thanks for the photo", "thanks for the photos",
    "fotos recibidas", "recibí las fotos", "gracias por la foto",
)

_DISTRESS_TRIGGERS = (
    "hungry", "hunger", "starving", "nothing to eat", "no food", "need food",
    "hambre", "sin comida", "tengo hambre",
)

_SHARE_TRIGGERS = (
    "share food", "share some", "donate", "giving away", "give away",
    "post a listing", "post listing", "list my", "i have extra",
    "leftover", "left over", "to donate", "want to share",
    "post it", "publish it", "ready to post",
    "compartir comida", "compartir", "donar", "publicar",
    "tengo extra", "sobra comida",
)

_REQUEST_TRIGGERS = (
    "food request", "request food", "post a request", "post food request",
    "ask for food", "solicitar comida", "pedir comida", "publicar solicitud",
)

_CLAIM_TRIGGERS = (
    "claim", "reserve", "i'll take", "ill take", "i will take",
    "grab it", "lock it in", "that one", "number ", "#",
    "the bread", "the kale", "loaf", "loaves",
    "reclamar", "reservar", "lo tomo", "esa",
)

_FIND_TRIGGERS = (
    "find food", "food near", "near me", "what's available", "whats available",
    "show me food", "nearby", "looking for food", "available food",
    "what food is available", "show available", "any food available",
    "food available", "search for food", "new food", "more food",
    "want some food", "want food", "need some food", "need food",
    "get some food", "get food", "some food", "i want food",
    "something easy", "easy to prepare", "easy food", "ready to eat",
    "help me find", "help finding", "what can i claim", "show options",
    "buscar comida", "cerca", "busco comida", "quiero comida",
    "necesito comida", "algo fácil", "algo facil",
)

# User explicitly rejects / questions a phantom mid-claim lock.
_CLAIM_CLEAR_TRIGGERS = (
    "i don't have", "i dont have", "don't have any", "dont have any",
    "we haven't talked", "we havent talked", "haven't talked about",
    "havent talked about", "which claim", "what claim", "no claim",
    "there is no claim", "i'm not claiming", "im not claiming",
    "not claiming", "start over", "start again", "forget that",
    "never mind the claim", "cancel the claim", "no listing",
    "we never", "nothing yet", "no option", "what option",
    "which option", "what food option", "no food option",
    "no tengo", "no hay reclamo", "cuál reclamo", "cual reclamo",
    "no estamos reclamando", "empezar de nuevo",
)

_CLEAR_SHORT_REPLIES: frozenset[str] = frozenset({
    "yes", "y", "yeah", "yep", "ok", "okay", "sure", "no", "n", "si", "sí",
    "thanks", "thank you", "gracias", "hi", "hello", "hey", "hola",
    "1", "2", "3", "4", "5", "#1", "#2", "#3", "#4", "#5",
})

_GREETINGS: frozenset[str] = frozenset({"hi", "hello", "hey", "hola"})


def _history_blob(history: list | None, message: str, limit: int = 12) -> str:
    hist = history or []
    parts = [(m.get("message") or "") for m in hist[-limit:]]
    parts.append(message or "")
    return "\n".join(parts)


def _is_distress(message: str) -> bool:
    t = (message or "").lower()
    if any(k in t for k in (
        "request food", "food request", "post a request", "solicitar comida",
    )):
        return False
    if any(k in t for k in _DISTRESS_TRIGGERS):
        return True
    if "food" in t and any(k in t for k in (
        "need", "hungry", "starving", "family", "kids", "children",
    )):
        return True
    return False


def _search_awaiting_pick(history: list | None) -> bool:
    """True when the last assistant turn is presenting search results to pick from."""
    last = _last_assistant_text(history)
    if not last:
        return False
    if any(k in last for k in _CLAIM_SUCCESS_MARKERS):
        return False
    return any(k in last for k in (
        "here's what's", "here are", "near you", "close to you", "which one",
        "works for you", "found ", "pick a number", "pick one", "number below",
        "opciones", "cerca de ti", "elige un número", "elige un numero",
    ))


def _recent_search_context(history: list | None) -> bool:
    """True when search results were shown recently in the thread."""
    if _search_awaiting_pick(history):
        return True
    blob_l = _history_blob(history, "", 8).lower()
    return any(k in blob_l for k in (
        "here's what's", "here are", "near you", "close to you", "which one",
        "works for you", "found ", "opciones", "cerca de ti", "numbered",
    ))


def _looks_like_listing_pick(message: str) -> bool:
    t = (message or "").strip().lower()
    if t in ("both", "all", "all of them", "both of them"):
        return True
    if re.fullmatch(r"#?\d{1,2}", t):
        return True
    if re.search(r"#\d", t):
        return True
    nums = re.findall(r"\d+", t)
    if len(nums) >= 2:
        return True
    if len(nums) == 1 and any(s in t for s in ("and", "&", "both")):
        return True
    return False


def _looks_like_multi_option_pick(message: str) -> bool:
    """True when user references 2+ listing numbers or says 'both'."""
    t = (message or "").strip().lower()
    if "both" in t:
        return True
    if _looks_like_food_quantity_spec(message):
        return False
    nums = [int(n) for n in re.findall(r"\d+", t)]
    if len(nums) < 2:
        return False
    if any(n > 15 for n in nums):
        return False
    if re.search(r"\b(\d|#)\s*(and|&|,|y)\s*(\d|#)", t):
        return True
    if len(nums) >= 2 and not any(w in _FOOD_WORDS for w in _tokenize_words(message)):
        return True
    return False


def _looks_like_food_quantity_spec(message: str) -> bool:
    """True when user names foods with amounts, e.g. '10 potatoes, 3 tomatoes'."""
    if not re.search(r"\d+", message or ""):
        return False
    return any(w in _FOOD_WORDS for w in _tokenize_words(message))


def is_posting_flow(message: str, history: list | None = None) -> bool:
    """True when the user is sharing/donating food (donor listing flow)."""
    if _is_distress(message):
        return False
    if _looks_like_listing_pick(message) and _recent_search_context(history):
        return False
    t = (message or "").lower()
    if any(k in t for k in _SHARE_TRIGGERS):
        return True
    if not history:
        return False
    for msg in reversed(history[-10:]):
        role = msg.get("role")
        text = (msg.get("message") or "").lower()
        if role == "assistant" and any(k in text for k in (
            "what food and how much", "quick photo", "snap a photo",
            "snap a quick photo", "which school", "which community",
            "list under", "go under", "post it?", "ready to post",
            "best by", "best-by", "when does it expire", "expire",
            "qué comida", "foto rápida", "comunidad", "escuela",
            "¿listo para publicar", "¿publico", "vence", "caduca",
        )):
            return True
        if role == "user" and any(k in text for k in (
            "i have", "i've got", "got some", "loaf", "loaves", "tengo",
        )):
            if not any(k in text for k in _DISTRESS_TRIGGERS):
                return True
    return False


def is_request_flow(message: str, history: list | None = None) -> bool:
    t = (message or "").lower()
    if any(k in t for k in _REQUEST_TRIGGERS):
        if not is_posting_flow(message, history):
            return True
    if history:
        for msg in reversed(history[-8:]):
            text = (msg.get("message") or "").lower()
            if msg.get("role") == "assistant" and any(k in text for k in (
                "food request", "what do you need", "household size",
                "solicitud de comida", "qué necesitas",
            )):
                return True
    return False


def _user_clears_claim_flow(message: str) -> bool:
    """True when the user denies / questions a stuck claim-intake loop."""
    t = (message or "").strip().lower()
    if not t:
        return False
    return any(k in t for k in _CLAIM_CLEAR_TRIGGERS)


# ---------------------------------------------------------------------------
# Assistance mode: "do it for me" vs "guide me step by step"
# ---------------------------------------------------------------------------

_HANDS_ON_MODE_PHRASES: tuple[str, ...] = (
    "do it for me", "do everything for me", "handle it for me",
    "handle everything", "you do it", "you handle it", "just do it",
    "take care of it", "nouri do it", "do it in chat",
    "hazlo por mí", "hazlo por mi", "hazlo todo", "tú hazlo", "tu hazlo",
    "hazlo tú", "hazlo tu", "encárgate", "encargate",
)

_GUIDED_MODE_PHRASES: tuple[str, ...] = (
    "guide me", "guide me step by step", "walk me through",
    "step by step", "show me how", "show me the steps",
    "i'll do it myself", "ill do it myself", "i can do it myself",
    "teach me", "how do i do it myself",
    "guíame", "guiame", "paso a paso", "enséñame", "ensename",
    "yo lo hago", "lo hago yo", "muéstrame cómo", "muestrame como",
)

_ASSIST_MODE_ASK_MARKERS: tuple[str, ...] = (
    "do it for me", "handle everything", "guide me step by step",
    "walk you through", "do everything for you", "yourself step by step",
    "in chat for you", "pages yourself",
    "hazlo por mí", "hazlo por mi", "paso a paso", "guíame", "guiame",
    "yo te guío", "yo te guio", "tú lo haces", "tu lo haces",
)

_FRESH_FIND_ASK_TRIGGERS: tuple[str, ...] = (
    "find food", "find free food", "food near me", "near me",
    "looking for food", "want to find", "i want to find",
    "help me find", "search for food", "available food",
    "show me food", "what food is available", "i want food",
    "want some food", "need some food", "get some food",
    "buscar comida", "comida cerca", "quiero comida", "necesito comida",
)

_FRESH_SHARE_ASK_TRIGGERS: tuple[str, ...] = (
    "share food", "share extra", "share some food", "want to share",
    "i want to share", "donate food", "post a listing", "give away food",
    "have extra food", "food to donate",
    "compartir comida", "donar comida", "quiero compartir", "tengo comida extra",
)

_FRESH_REQUEST_ASK_TRIGGERS: tuple[str, ...] = (
    "request food", "food request", "post a request", "post food request",
    "want to request", "i want to request", "ask for food", "need a request",
    "solicitar comida", "pedir comida", "publicar solicitud", "quiero solicitar",
    "hacer una solicitud",
)


def detect_assistance_mode(message: str) -> Optional[AssistanceMode]:
    """Return hands_on / guided when the user explicitly picks a mode."""
    t = (message or "").strip().lower()
    if not t:
        return None
    # Prefer guided when both match ("guide me" contains no hands-on, but
    # "do it for me step by step" is rare — check hands_on first for clarity).
    if any(k in t for k in _HANDS_ON_MODE_PHRASES):
        return "hands_on"
    if any(k in t for k in _GUIDED_MODE_PHRASES):
        return "guided"
    return None


def detect_assistance_goal(
    message: str,
    history: list | None = None,
) -> Optional[AssistanceGoal]:
    """Fresh find/share/request intent that should offer the assistance-mode fork."""
    if _is_distress(message):
        return None
    t = (message or "").strip().lower()
    if not t:
        # Mode reply after Nouri asked — infer goal from prior user turn.
        if history and _assistant_asked_assistance_mode(history):
            return _goal_from_recent_user_intent(history)
        return None

    mode = detect_assistance_mode(message)
    if mode and _assistant_asked_assistance_mode(history):
        return _goal_from_recent_user_intent(history)

    # Concrete item specs → skip the fork; user already wants hands-on action.
    if _looks_like_food_quantity_spec(message) and any(k in t for k in _SHARE_TRIGGERS):
        return None
    if _looks_like_listing_pick(message) and _recent_search_context(history):
        return None

    request_hit = any(k in t for k in _FRESH_REQUEST_ASK_TRIGGERS) or any(
        k in t for k in _REQUEST_TRIGGERS
    )
    share_hit = any(k in t for k in _FRESH_SHARE_ASK_TRIGGERS)
    find_hit = any(k in t for k in _FRESH_FIND_ASK_TRIGGERS) or (
        is_finding_flow(message, history)
        and not share_hit
        and not request_hit
        and not any(k in t for k in _CLAIM_TRIGGERS)
    )

    if request_hit and not share_hit:
        if _request_already_underway(history):
            return None
        return "request"
    if share_hit and not any(k in t for k in _DISTRESS_TRIGGERS):
        # Mid-post details already in flight → don't re-ask.
        if _posting_already_underway(history):
            return None
        return "share"
    if find_hit and not share_hit and not request_hit:
        if _finding_already_underway(history):
            return None
        return "find"
    return None


def _goal_from_recent_user_intent(history: list | None) -> Optional[AssistanceGoal]:
    if not history:
        return None
    for msg in reversed(history[-8:]):
        if msg.get("role") != "user":
            continue
        text = (msg.get("message") or "").lower()
        if any(k in text for k in _FRESH_REQUEST_ASK_TRIGGERS) or any(
            k in text for k in _REQUEST_TRIGGERS
        ):
            return "request"
        if any(k in text for k in _FRESH_SHARE_ASK_TRIGGERS) or any(
            k in text for k in _SHARE_TRIGGERS
        ):
            return "share"
        if any(k in text for k in _FRESH_FIND_ASK_TRIGGERS) or any(
            k in text for k in _FIND_TRIGGERS
        ):
            return "find"
    return None


def _assistant_asked_assistance_mode(history: list | None) -> bool:
    if not history:
        return False
    for msg in reversed(history[-4:]):
        if msg.get("role") != "assistant":
            continue
        text = (msg.get("message") or "").lower()
        return any(k in text for k in _ASSIST_MODE_ASK_MARKERS)
    return False


def _assistance_mode_from_history(history: list | None) -> Optional[AssistanceMode]:
    """Mode already chosen earlier in this find/share/request session."""
    if not history:
        return None
    asked = False
    for msg in reversed(history[-10:]):
        role = msg.get("role")
        text = (msg.get("message") or "").lower()
        if role == "assistant" and any(k in text for k in _ASSIST_MODE_ASK_MARKERS):
            asked = True
            continue
        if role == "user":
            mode = detect_assistance_mode(text)
            if mode:
                return mode
            # User jumped past the fork with concrete action — treat as hands_on.
            if asked and (
                _looks_like_food_quantity_spec(text)
                or any(k in text for k in (
                    "near me", "search", "post", "claim", "apples", "bread",
                    "request", "solicitud",
                ))
            ):
                return "hands_on"
    return None


def _posting_already_underway(history: list | None) -> bool:
    if not history:
        return False
    blob = " ".join(
        (m.get("message") or "").lower()
        for m in history[-8:]
        if m.get("role") == "assistant"
    )
    return any(k in blob for k in (
        "what food and how much", "quick photo", "snap a photo",
        "which school", "which community", "ready to post", "post it?",
        "best by", "when does it expire", "qué comida", "foto rápida",
        "opened share food", "share food page",
    ))


def _finding_already_underway(history: list | None) -> bool:
    if not history:
        return False
    if _recent_search_context(history):
        return True
    blob = " ".join(
        (m.get("message") or "").lower()
        for m in history[-8:]
        if m.get("role") == "assistant"
    )
    return any(k in blob for k in (
        "found ", "near you", "here's what's", "pick a number",
        "opened find food", "find food page", "opciones", "cerca de ti",
    ))


def _request_already_underway(history: list | None) -> bool:
    if not history:
        return False
    blob = " ".join(
        (m.get("message") or "").lower()
        for m in history[-8:]
        if m.get("role") == "assistant"
    )
    return any(k in blob for k in (
        "what do you need", "food request", "household size",
        "opened request food", "request food page",
        "qué necesitas", "solicitud de comida",
        "post a food request for", "request posted",
    ))


def needs_assistance_mode_choice(
    message: str,
    history: list | None = None,
) -> bool:
    """True when Nouri should ask do-it-for-me vs guide-me before acting."""
    if _is_distress(message):
        return False
    if detect_assistance_mode(message):
        return False
    if _assistance_mode_from_history(history):
        return False
    goal = detect_assistance_goal(message, history)
    return goal is not None


def resolve_assistance_mode(
    message: str,
    history: list | None = None,
) -> Optional[AssistanceMode]:
    """Explicit mode from this turn, or previously chosen in-session."""
    return detect_assistance_mode(message) or _assistance_mode_from_history(history)


def _assistance_action_label(goal: AssistanceGoal, lang: str = "en") -> str:
    if lang == "es":
        if goal == "share":
            return "compartir comida"
        if goal == "request":
            return "solicitar comida"
        return "buscar comida"
    if goal == "share":
        return "share food"
    if goal == "request":
        return "request food"
    return "find food"


def build_assistance_mode_reminder(
    message: str,
    history: list | None = None,
    lang: str = "en",
) -> Optional[str]:
    """Per-turn injection: ask for mode, or run hands_on / guided path."""
    if _is_distress(message):
        return None

    mode = resolve_assistance_mode(message, history)
    goal = detect_assistance_goal(message, history)
    if goal is None and mode and _assistant_asked_assistance_mode(history):
        goal = _goal_from_recent_user_intent(history)

    if mode is None and needs_assistance_mode_choice(message, history):
        goal = goal or detect_assistance_goal(message, history) or "find"
        action = _assistance_action_label(goal, lang)
        if lang == "es":
            return (
                f"MODO DE AYUDA (obligatorio este turno):\n"
                f"El usuario quiere {action}. NO llames search_food_near_user, "
                f"claim_*, ni post_food_* todavía.\n"
                f"Pregunta UNA vez, cálido y breve: ¿quieres que yo lo haga TODO "
                f"por ti aquí en el chat, o te guío paso a paso para que lo hagas "
                f"tú en la app?\n"
                f"Ofrece exactamente dos caminos (los chips cubren las respuestas)."
            )
        return (
            f"ASSISTANCE MODE (required this turn):\n"
            f"The user wants to {action}. Do NOT call search_food_near_user, "
            f"claim_*, or post_food_* yet.\n"
            f"Ask ONCE, warm and brief: want me to handle everything for you "
            f"here in chat, or walk you through doing it yourself step by step "
            f"on the pages?\n"
            f"Offer exactly those two paths (chips will cover the replies)."
        )

    if mode == "guided" and goal:
        if lang == "es":
            if goal == "share":
                return (
                    "MODO GUIADO — COMPARTIR:\n"
                    "El usuario quiere hacerlo en la app. Llama navigate_ui "
                    "action=open target=create ESTE turno. Luego explica 3–5 "
                    "pasos cortos: título/categoría, cantidad, fecha de vencimiento, "
                    "dirección/comunidad, enviar. UNA pregunta si hace falta. "
                    "NO publiques tú con post_food_listing a menos que lo pida."
                )
            if goal == "request":
                return (
                    "MODO GUIADO — SOLICITAR:\n"
                    "El usuario quiere hacerlo en la app. Llama navigate_ui "
                    "action=open target=request ESTE turno. Luego explica 3–5 "
                    "pasos cortos: qué necesita, cantidad, comunidad, fecha, "
                    "enviar. Quédate como guía — NO llames post_food_request "
                    "a menos que pida que lo hagas tú."
                )
            return (
                "MODO GUIADO — BUSCAR:\n"
                "El usuario quiere hacerlo en la app. Llama navigate_ui "
                "action=open target=list ESTE turno. Luego explica 3–5 pasos "
                "cortos: revisar listados, filtrar, tocar Reclamar, confirmar "
                "cantidad, enviar. Quédate como guía — NO llames "
                "search_food_near_user / claim_* a menos que pida que lo hagas tú."
            )
        if goal == "share":
            return (
                "GUIDED MODE — SHARE FOOD:\n"
                "User wants to do it on the pages. Call navigate_ui "
                "action=open target=create THIS turn. Then explain 3–5 short "
                "steps: title/category, quantity, expiry, address/community, "
                "submit. One follow-up question only if needed. Do NOT post "
                "via post_food_listing unless they ask you to take over."
            )
        if goal == "request":
            return (
                "GUIDED MODE — REQUEST FOOD:\n"
                "User wants to do it on the pages. Call navigate_ui "
                "action=open target=request THIS turn. Then explain 3–5 short "
                "steps: what they need, quantity, community, needed-by date, "
                "submit. No photo step — requests never include images. Stay "
                "a coach — do NOT call post_food_request unless they ask you "
                "to take over in chat."
            )
        return (
            "GUIDED MODE — FIND FOOD:\n"
            "User wants to do it on the pages. Call navigate_ui "
            "action=open target=list THIS turn. Then explain 3–5 short steps: "
            "browse listings, filter if needed, tap Claim, confirm quantity, "
            "submit. Stay a coach — do NOT call search_food_near_user / claim_* "
            "unless they ask you to take over in chat."
        )

    if mode == "hands_on" and goal:
        if lang == "es":
            if goal == "share":
                return (
                    "MODO MANOS A LA OBRA — COMPARTIR:\n"
                    "El usuario quiere que lo hagas tú en el chat. Sigue el "
                    "flujo normal de publicación (preguntar solo lo que falte, "
                    "luego post_food_listing). No abras la página Share Food."
                )
            if goal == "request":
                return (
                    "MODO MANOS A LA OBRA — SOLICITAR:\n"
                    "El usuario quiere que lo hagas tú en el chat. Pregunta "
                    "solo lo que falte (qué necesita, cantidad, comunidad) y "
                    "llama post_food_request. No abras Request Food para guiar la UI."
                )
            return (
                "MODO MANOS A LA OBRA — BUSCAR:\n"
                "El usuario quiere que lo hagas tú en el chat. Llama "
                "search_food_near_user ESTE turno y continúa el flujo de "
                "reclamo. No abras Find Food para guiar la UI."
            )
        if goal == "share":
            return (
                "HANDS-ON MODE — SHARE FOOD:\n"
                "User wants you to handle it in chat. Follow the normal "
                "posting flow (ask only what's missing, then post_food_listing). "
                "Do not open the Share Food page for UI coaching."
            )
        if goal == "request":
            return (
                "HANDS-ON MODE — REQUEST FOOD:\n"
                "User wants you to handle it in chat. Ask only what's missing "
                "(what they need, quantity, community) then call "
                "post_food_request. Do not open the Request Food page for UI coaching."
            )
        return (
            "HANDS-ON MODE — FIND FOOD:\n"
            "User wants you to handle it in chat. Call search_food_near_user "
            "THIS turn and continue the claim flow. Do not open Find Food "
            "for UI coaching."
        )

    return None


def assistance_mode_tool_block_reason(
    tool_name: str,
    message: str,
    history: list | None = None,
) -> Optional[str]:
    """Block find/share/request write tools until the user picks assistance mode."""
    if not needs_assistance_mode_choice(message, history):
        return None
    blocked = {
        "search_food_near_user",
        "get_recent_listings",
        "claim_listing",
        "claim_listings",
        "post_food_listing",
        "post_food_listings",
        "post_food_request",
        "bulk_import_listings",
    }
    if tool_name not in blocked:
        return None
    return (
        "Ask the user first: do everything for them in chat, or guide them "
        "step by step on the pages. Do not call this tool until they choose."
    )


def is_finding_flow(message: str, history: list | None = None) -> bool:
    if _is_distress(message):
        return True
    t = (message or "").lower()
    # Explicit food-request posts are a different flow.
    if any(k in t for k in _REQUEST_TRIGGERS):
        return False
    if _user_clears_claim_flow(message):
        return True
    if any(k in t for k in _FIND_TRIGGERS):
        return True
    # Generic "food" + desire verbs — "food" is not in _FOOD_WORDS (produce
    # lexicon), so without this branch "i want some food" never entered finding.
    if "food" in t and any(k in t for k in (
        "want", "need", "find", "get", "looking", "search", "show",
        "busco", "quiero", "necesito", "hay",
    )):
        if not any(k in t for k in _SHARE_TRIGGERS):
            return True
    words = _tokenize_words(message)
    if any(w in _FOOD_WORDS for w in words):
        if any(k in t for k in (
            "want", "need", "find", "get", "looking for", "search",
            "busco", "quiero", "necesito", "hay",
        )):
            return True
    return False


def is_claiming_flow(message: str, history: list | None = None) -> bool:
    if is_posting_flow(message, history):
        return False
    t = (message or "").lower()
    if any(k in t for k in _CLAIM_TRIGGERS):
        return True
    if not _assistant_expects_flow_reply(history):
        return False
    return _looks_like_listing_pick(message)


def _assistant_expects_flow_reply(history: list | None) -> bool:
    """True when the last assistant turn is mid-flow and awaiting a specific answer."""
    if not history:
        return False
    for msg in reversed(history[-4:]):
        if msg.get("role") == "assistant":
            text = (msg.get("message") or "").lower()
            return any(k in text for k in (
                "which one", "how many", "confirm", "photo", "community",
                "ready to post", "did you mean", "which number", "pickup or",
                "which community", "snap a", "post it", "lock it",
                "lock it in", "want me to", "picking up",
                "¿cuál", "¿cuánt", "foto", "comunidad", "confirmar", "quisiste decir",
            ))
    return False


_CLAIM_QTY_ASK_MARKERS = (
    "how many do you want", "how many would you like", "how many of the",
    "how many loaves", "how many units", "how many cans", "how many can you",
    "how much do you want", "how much would you like",
    "how many",  # e.g. "How many tomatoes?" after a listing pick
    "cuántos quieres", "cuántas quieres", "cuantos quieres", "cuantas quieres",
    "cuántos", "cuántas",
    "nice choice", "good pick", "great choice", "buena elección",
)

_CLAIM_SUCCESS_MARKERS = (
    "claimed", "reclamado", "reserved for you", "reservado para ti",
    "pickup at", "recogida en", "all set", "you're set", "you are set",
    "already claimed", "ya reclamaste", "already reserved",
    "got it claimed", "listo — reclamado",
)

_CLAIM_INTAKE_MARKERS = _CLAIM_QTY_ASK_MARKERS + (
    "which one", "which listing", "which number", "which would you",
    "pick a number", "pick one", "works for you", "sounds good",
    "¿cuál", "cual te gustaría", "elige un número", "elige un numero",
)


def _last_assistant_text(history: list | None, limit: int = 8) -> str:
    if not history:
        return ""
    for msg in reversed(history[-limit:]):
        if msg.get("role") == "assistant":
            return (msg.get("message") or "").lower()
    return ""


def _claim_intake_open(message: str, history: list | None) -> bool:
    """True only when a claim pick/qty flow is open and not yet completed."""
    if not history:
        return False
    if _is_distress(message) or is_finding_flow(message, history):
        return False
    if _user_clears_claim_flow(message) or _user_wants_fresh_search(message):
        return False
    # Qty-waiting is only valid after real search results / a listing pick.
    # Without this gate, a mistaken "how many?" from the model traps every
    # later turn in a phantom claim loop (no listings ever shown).
    if _assistant_awaiting_quantity(history):
        return _recent_search_context(history) or _user_picked_listing_in_history(history)

    last_asst = _last_assistant_text(history)
    if not last_asst:
        return False
    if any(k in last_asst for k in _CLAIM_SUCCESS_MARKERS):
        return False
    if not any(k in last_asst for k in _CLAIM_INTAKE_MARKERS):
        return False
    return _recent_search_context(history)


# Back-compat alias used in tests / older imports
def _in_active_claim_conversation(message: str, history: list | None) -> bool:
    return _claim_intake_open(message, history)


def _user_asking_availability(message: str) -> bool:
    """True when the user asks how much/many is left — not a claim qty answer."""
    t = (message or "").strip().lower()
    if not t:
        return False
    if not any(k in t for k in (
        "how much", "how many", "how many left", "how much left",
        "is left", "are left", "remaining", "still available", "still left",
        "cuánto queda", "cuantos quedan", "cuántos quedan", "cuanta queda",
        "cuántas quedan", "disponible", "queda",
    )):
        return False
    if _extract_claim_intent(message).get("quantity") is not None:
        return False
    if any(k in t for k in (
        "do you want", "should i claim", "want to claim", "how many do you",
        "how much do you",
    )):
        return False
    return True


def detect_conversation_flow(message: str, history: list | None = None) -> FlowKind:
    """Pick the dominant active conversation flow for this turn."""
    t = (message or "").strip().lower()
    if t in _GREETINGS:
        return "idle"
    if is_posting_flow(message, history):
        return "posting"
    if _user_asking_availability(message):
        return "finding"
    if is_finding_flow(message, history):
        return "finding"
    if _claim_intake_open(message, history):
        return "claiming"
    if t in _CLEAR_SHORT_REPLIES and len(t.split()) <= 3:
        if not _assistant_expects_flow_reply(history):
            if _looks_like_listing_pick(message) and _search_awaiting_pick(history):
                pass  # e.g. "1" or "#2" after search results — claiming, not idle
            else:
                return "idle"
    if _looks_like_multi_option_pick(message) and (
        _assistant_expects_flow_reply(history) or _search_awaiting_pick(history)
    ):
        return "claiming"
    if _looks_like_listing_pick(message) and (
        _assistant_expects_flow_reply(history) or _search_awaiting_pick(history)
    ):
        return "claiming"

    if is_claiming_flow(message, history):
        return "claiming"
    if is_request_flow(message, history):
        return "requesting"
    return "idle"


def _natural_rhythm(lang: str) -> str:
    if lang == "es":
        return (
            "CONVERSACIÓN NATURAL (este turno):\n"
            "• Habla como un humano servicial — no como un formulario.\n"
            "• UNA pregunta por mensaje; reconoce la respuesta anterior en "
            "1–4 palabras ('Entendido.', 'Perfecto.') antes de la siguiente.\n"
            "• No repitas preguntas ya respondidas en este hilo.\n"
            "• Tras completar una acción: una frase con el resultado, luego "
            "como máximo UN siguiente paso opcional."
        )
    return (
        "NATURAL CONVERSATION (this turn):\n"
        "• Talk like a helpful human — not a form or FAQ.\n"
        "• ONE question per message; acknowledge their last answer briefly "
        "('Got it.', 'Perfect.') before the next question.\n"
        "• Never re-ask for info they already gave in this thread.\n"
        "• After completing an action: one sentence on what happened, then "
        "at most ONE optional next step."
    )


_POST_CONFIRM_PHRASES: tuple[str, ...] = (
    "ready to post", "post it?", "shall i post", "want me to post",
    "go ahead and post", "publish it?", "post this?", "sound good to post",
    "post these?", "ready to share", "shall i share", "want me to share",
    "look right", "look good", "does this look", "sound right",
    "before i post", "before i share", "before i go ahead",
    "just to confirm", "one last check", "shall i go ahead",
    "want me to publish", "ok to post", "okay to post",
    "¿listo para publicar", "¿publico", "¿publicamos", "¿lo publico",
    "¿lo publicamos", "¿te parece", "¿está bien",
)


def posting_flow_state(message: str, history: list | None) -> dict:
    """Structured posting-step state for reminders, logging, and tool guards."""
    # Scope the whole posting checklist to the CURRENT share session so a
    # community/expiry confirmation from bananas doesn't skip those steps
    # when the donor starts a fresh carrot/tomato share.
    boundary = _current_posting_boundary_index(history)
    scoped_hist = (history or [])[boundary:] if boundary else (history or [])
    scoped_blob = _history_blob(scoped_hist, message)
    scoped_blob_l = scoped_blob.lower()
    community_asked = any(p in scoped_blob_l for p in (
        "which community", "which school", "community should",
        "under which", "go under", "comunidad", "escuela",
    ))
    has_photo = bool(_PHOTO_URL_RE.search(scoped_blob))
    # Donor insists photos were already sent, or assistant already ack'd them.
    msg_l = (message or "").lower()
    if any(p in msg_l for p in _PHOTO_ALREADY_SHARED_PHRASES):
        has_photo = True
    if any(p in scoped_blob_l for p in _PHOTO_RECEIVED_ASSISTANT):
        has_photo = True
    photo_asked = any(p in scoped_blob_l for p in (
        "photo", "picture", "snap a", "upload a", "foto", "imagen",
    ))
    photo_declined = _user_declined_photo(scoped_hist, message)
    post_summary_offered = any(p in scoped_blob_l for p in _POST_CONFIRM_PHRASES)
    expiry_asked = any(p in scoped_blob_l for p in (
        "expire", "expiry", "best by", "best-by", "use by", "how fresh",
        "how long", "when was it made", "good until", "best before",
        "vence", "caduca", "fecha de vencimiento", "cuándo vence",
    ))
    expiry_provided = bool(_best_user_expiry_from_thread(message, history)) or bool(
        re.search(r"\d{4}-\d{2}-\d{2}", scoped_blob)
    ) or bool(_extract_expiry_from_text(scoped_blob))
    awaiting_photo = photo_asked and not has_photo and not photo_declined
    return {
        "has_photo": has_photo,
        "photo_asked": photo_asked,
        "photo_declined": photo_declined,
        "awaiting_photo": awaiting_photo,
        "community_asked": community_asked,
        "community_confirmed": _community_was_confirmed(scoped_hist),
        "post_summary_offered": post_summary_offered,
        "expiry_asked": expiry_asked,
        "expiry_provided": expiry_provided,
    }


def _extract_expiry_from_text(text: str) -> Optional[str]:
    """Parse YYYY-MM-DD or common spoken dates from chat text.

    Month-name forms ("24th July", "July 24th this year") are required —
    without them the model invents a wrong year (often a past year) and
    traps the donor in an expiry confirmation loop.
    """
    if not text:
        return None
    m = re.search(r"\b(\d{4}-\d{2}-\d{2})\b", text)
    if m:
        return m.group(1)
    m = re.search(
        r"\b(\d{1,2})[/-](\d{1,2})[/-](\d{2,4})\b",
        text,
    )
    if m:
        from backend.tools import _normalize_expiry_date
        return _normalize_expiry_date(m.group(0))

    blob = text.lower()
    if any(k in blob for k in ("today", "tonight", "hoy", "esta noche")):
        from datetime import date
        return date.today().isoformat()
    if any(k in blob for k in ("tomorrow", "mañana")):
        from datetime import date, timedelta
        return (date.today() + timedelta(days=1)).isoformat()

    relative = _parse_relative_expiry_date(blob)
    if relative:
        return relative

    spoken = _parse_spoken_expiry_date(blob)
    if spoken:
        return spoken
    return None


def _best_user_expiry_from_thread(
    message: str,
    history: list | None,
) -> Optional[str]:
    """Prefer the donor's own spoken/typed expiry over model-invented dates.

    Scanning assistant lines picks up traps like 'July 24th, 2024 is in the
    past' — those must never override 'july 24th this year' from the user.
    """
    exp = _extract_expiry_from_text(message or "")
    if exp:
        return exp
    for msg in reversed(history or []):
        if msg.get("role") != "user":
            continue
        exp = _extract_expiry_from_text(msg.get("message") or "")
        if exp:
            return exp
    return None


_MONTH_NAME_TO_NUM: dict[str, int] = {
    "january": 1, "jan": 1, "febrero": 2, "february": 2, "feb": 2,
    "march": 3, "mar": 3, "marzo": 3, "april": 4, "apr": 4, "abril": 4,
    "may": 5, "mayo": 5, "june": 6, "jun": 6, "junio": 6,
    "july": 7, "jul": 7, "julio": 7, "august": 8, "aug": 8, "agosto": 8,
    "september": 9, "sep": 9, "sept": 9, "septiembre": 9,
    "october": 10, "oct": 10, "octubre": 10,
    "november": 11, "nov": 11, "noviembre": 11,
    "december": 12, "dec": 12, "diciembre": 12,
}


def _parse_spoken_expiry_date(blob: str) -> Optional[str]:
    """Parse '24th july', 'july 24', 'july 24th this year', 'july 24 2026'."""
    from datetime import date
    from calendar import monthrange

    if not blob:
        return None
    months = "|".join(sorted(_MONTH_NAME_TO_NUM.keys(), key=len, reverse=True))
    # Day-first: 24th july [2026|this year]
    m = re.search(
        rf"\b(\d{{1,2}})(?:st|nd|rd|th)?\s+(?:of\s+)?({months})"
        rf"(?:\s*,?\s*(\d{{4}}|this year|next year))?\b",
        blob,
        re.I,
    )
    # Month-first: july 24th [2026|this year]
    if not m:
        m = re.search(
            rf"\b({months})\s+(\d{{1,2}})(?:st|nd|rd|th)?"
            rf"(?:\s*,?\s*(\d{{4}}|this year|next year))?\b",
            blob,
            re.I,
        )
        if not m:
            return None
        month_raw, day_raw, year_raw = m.group(1), m.group(2), m.group(3)
    else:
        day_raw, month_raw, year_raw = m.group(1), m.group(2), m.group(3)

    try:
        day = int(day_raw)
        month = _MONTH_NAME_TO_NUM.get(month_raw.lower())
        if not month or day < 1 or day > 31:
            return None
    except (TypeError, ValueError):
        return None

    today = date.today()
    year_token = (year_raw or "").strip().lower()
    if year_token.isdigit() and len(year_token) == 4:
        year = int(year_token)
    elif year_token == "this year":
        year = today.year
    elif year_token == "next year":
        year = today.year + 1
    else:
        # No year: pick the next upcoming occurrence (never invent a past year).
        year = today.year
        try:
            candidate = date(year, month, day)
        except ValueError:
            return None
        if candidate < today:
            year = today.year + 1

    try:
        last_day = monthrange(year, month)[1]
        if day > last_day:
            return None
        resolved = date(year, month, day)
    except ValueError:
        return None

    # Explicit "this year" that lands in the past — still return it so the
    # validation layer can ask for a correction rather than inventing 2024.
    return resolved.isoformat()


_WEEKDAY_TO_NUM: dict[str, int] = {
    "monday": 0, "mon": 0, "lunes": 0,
    "tuesday": 1, "tue": 1, "tues": 1, "martes": 1,
    "wednesday": 2, "wed": 2, "miercoles": 2, "miércoles": 2,
    "thursday": 3, "thu": 3, "thur": 3, "thurs": 3, "jueves": 3,
    "friday": 4, "fri": 4, "viernes": 4,
    "saturday": 5, "sat": 5, "sabado": 5, "sábado": 5,
    "sunday": 6, "sun": 6, "domingo": 6,
}


def _parse_relative_expiry_date(blob: str) -> Optional[str]:
    """Parse 'in 3 days', 'next friday', 'this friday', bare weekday names."""
    from datetime import date, timedelta

    if not blob:
        return None
    text = blob.lower()

    m = re.search(
        r"\b(?:in|within)\s+(\d{1,3})\s+days?\b",
        text,
    )
    if m:
        try:
            days = int(m.group(1))
            if 0 < days <= 365:
                return (date.today() + timedelta(days=days)).isoformat()
        except (TypeError, ValueError):
            pass

    weekdays = "|".join(sorted(_WEEKDAY_TO_NUM.keys(), key=len, reverse=True))
    m = re.search(rf"\b(?:next|this|on)?\s*({weekdays})\b", text)
    if m:
        target = _WEEKDAY_TO_NUM.get(m.group(1).lower())
        if target is not None:
            today = date.today()
            delta = (target - today.weekday()) % 7
            if delta == 0 and "next" in text:
                delta = 7
            elif delta == 0 and "this" not in text and "on" not in text:
                # Bare "Friday" → next occurrence (today counts if same weekday).
                delta = 7 if today.weekday() == target else delta
            if delta == 0:
                delta = 0
            return (today + timedelta(days=delta)).isoformat()

    return None


def _assistant_last_asked_kind(history: list | None) -> str | None:
    """What the most recent assistant turn was asking about."""
    if not history:
        return None
    for msg in reversed(history[-8:]):
        if msg.get("role") != "assistant":
            continue
        text = (msg.get("message") or "").lower()
        if any(k in text for k in _POST_CONFIRM_PHRASES):
            return "post_confirm"
        if any(k in text for k in (
            "ready to claim", "claim these", "claim both", "claim all of these",
            "shall i claim", "want me to claim", "claim them now",
            "listo para reclamar", "reclamar estos", "reclamo estos",
        )):
            return "claim_confirm"
        if any(k in text for k in (
            "expire", "expiry", "best by", "best-by", "use by", "how fresh",
            "how long", "when was it made", "good until", "vence", "caduca",
        )):
            return "expiry"
        if any(k in text for k in (
            "photo", "picture", "snap a", "upload a", "attach a", "foto", "imagen",
        )):
            return "photo"
        if any(k in text for k in (
            "which community", "which school", "community should", "go under",
            "comunidad", "escuela", "list under",
        )):
            return "community"
        if any(k in text for k in (
            "how many", "how much", "what food", "qué comida", "cuánt",
        )):
            return "food_qty"
        return None
    return None


def _community_was_confirmed(history: list | None) -> bool:
    """True once the donor explicitly picked or confirmed a community."""
    if not history:
        return False
    for i, msg in enumerate(history):
        if msg.get("role") != "assistant":
            continue
        text = (msg.get("message") or "").lower()
        if not any(k in text for k in (
            "community", "school", "comunidad", "escuela", "go under", "list under",
        )):
            continue
        for j in range(i + 1, len(history)):
            if history[j].get("role") == "assistant":
                break
            if history[j].get("role") != "user":
                continue
            u = (history[j].get("message") or "").strip()
            ul = u.lower()
            if _is_affirmative_post_confirm(u) or _is_short_affirmative(u):
                return True
            # Free-text confirmation: look like a school/community name, not
            # qty/expiry/address filler ("5 loaves", "tomorrow", "wait").
            if len(ul) < 3:
                continue
            if re.search(r"\d", ul) and not re.search(
                r"(school|academy|college|community|unified|elementary|middle|high)",
                ul,
            ):
                continue
            if ul in {
                "wait", "hold on", "tomorrow", "later", "idk", "not sure",
                "maybe", "hmm", "ok wait",
            }:
                continue
            if any(k in ul for k in (
                "loaf", "loaves", "egg", "eggs", "pound", "lb", "box",
                "bag", "portion", "serving", "photo", "picture", "address",
            )):
                continue
            # Likely a name answer ("Alameda High", "Ruby Bridges", "my school").
            if len(ul.split()) >= 1 and not ul.startswith(("http", "image:")):
                return True
    return False


def _is_short_affirmative(message: str) -> bool:
    t = (message or "").strip().lower()
    if not t:
        return False
    if t in {"yes", "y", "yeah", "yep", "ok", "okay", "sure", "si", "sí", "yup"}:
        return True
    return len(t.split()) <= 2 and _is_affirmative_post_confirm(message)


_COMMUNITY_IN_MSG_RE = re.compile(
    r"(?:community|neighborhood)\s*(?:to|is|=|:)?\s*['\"]?([a-z0-9][a-z0-9\s\-]{2,40})['\"]?",
    re.I,
)

_COMMUNITY_QUESTION_MARKERS = (
    "which community", "which school", "community should", "go under",
    "list under", "comunidad", "escuela", "school district",
)

_COMMUNITY_FROM_USER_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(
        r"(?:list|put|post)\s+(?:this|it)\s+under\s+(.+?)(?:\?|\.|$)",
        re.I,
    ),
    re.compile(
        r"(?:use|pick|choose|want|put\s+it\s+under)\s+(.+?)\s+instead",
        re.I,
    ),
    re.compile(
        r"instead\s+(?:of\s+[^,.!?]{0,60}?\s+)?(?:use\s+)?(.+?)(?:\?|\.|$)",
        re.I,
    ),
    re.compile(
        r"(?:different|another|other)\s+(?:community|school|one)"
        r"(?:\s+please)?[:\s—-]+(.+?)(?:\?|\.|$)",
        re.I,
    ),
    re.compile(
        r"(?:not\s+that\s+one|no)\s*[,—-]?\s*(?:use\s+)?(.+?)(?:\?|\.|$)",
        re.I,
    ),
    re.compile(
        r"(?:under|list\s+under|go\s+under)\s+(.+?)(?:\?|\.|$)",
        re.I,
    ),
    _COMMUNITY_IN_MSG_RE,
)

_COMMUNITY_FROM_ASSISTANT_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(
        r"(?:go|list|post)\s+under\s+(.+?)\??(?:\s|$)",
        re.I,
    ),
    re.compile(
        r"which community(?:/school)?(?: should|\s+should)[^\n?]*[—:-]\s*(.+?)\??(?:\s|$)",
        re.I,
    ),
    re.compile(
        r"should this go under\s+(.+?)\??(?:\s|$)",
        re.I,
    ),
    re.compile(
        r"list under\s+(.+?)\??(?:\s|$)",
        re.I,
    ),
)


def _clean_community_phrase(text: str) -> str | None:
    """Normalize a raw community phrase from chat text."""
    name = (text or "").strip().strip('"').strip("'").strip()
    name = re.sub(r"\s+", " ", name)
    name = re.sub(
        r"^(?:the|a|an|please|thanks|thank you|yes|yeah|sure|ok|okay)\s+",
        "",
        name,
        flags=re.I,
    )
    name = re.sub(
        r"\s+(?:please|thanks|thank you|instead|not that one)\.?$",
        "",
        name,
        flags=re.I,
    ).strip(" .,;:-—")
    if len(name) < 3:
        return None
    if name.lower() in {"yes", "no", "ok", "okay", "sure", "si", "sí", "y", "n"}:
        return None
    return name


def _extract_community_name_from_text(text: str) -> str | None:
    """Pull a community/school name from a single message."""
    if not text:
        return None
    for pat in _COMMUNITY_FROM_USER_PATTERNS:
        m = pat.search(text)
        if m:
            cleaned = _clean_community_phrase(m.group(1))
            if cleaned:
                return cleaned
    # Bare name when the whole message is short (e.g. "Do Good Warehouse").
    stripped = text.strip()
    if 3 <= len(stripped) <= 80 and stripped.count("\n") == 0:
        lower = stripped.lower()
        if lower not in {"yes", "no", "ok", "okay", "sure", "si", "sí"}:
            if not any(k in lower for k in (
                "photo", "expire", "expiry", "post it", "ready to post",
                "how many", "what food",
            )):
                cleaned = _clean_community_phrase(stripped)
                if cleaned and len(cleaned.split()) <= 8:
                    return cleaned
    return None


def _extract_community_name_from_assistant_question(text: str) -> str | None:
    """Parse the community name the assistant proposed in a question."""
    if not text:
        return None
    for pat in _COMMUNITY_FROM_ASSISTANT_PATTERNS:
        m = pat.search(text)
        if m:
            cleaned = _clean_community_phrase(m.group(1))
            if cleaned:
                return cleaned
    return None


def _communities_from_history(history: list | None) -> list[dict]:
    """Communities returned by get_active_communities earlier in the thread."""
    out: list[dict] = []
    seen: set[str] = set()
    if not history:
        return out
    for msg in history:
        meta = msg.get("metadata") or {}
        for action in meta.get("actions") or []:
            if str(action.get("tool") or "") != "get_active_communities":
                continue
            for row in action.get("communities") or []:
                name = str(row.get("name") or "").strip()
                cid = str(row.get("id") or "").strip()
                key = name.lower()
                if name and key not in seen:
                    seen.add(key)
                    out.append({"id": cid, "name": name})
    return out


def _match_community_in_catalog(
    query: str,
    catalog: list[dict],
) -> dict | None:
    """Fuzzy-match a user phrase against a list of {id, name} communities."""
    if not query or not catalog:
        return None

    q_raw = query.strip()
    num_m = re.fullmatch(r"#?(\d{1,2})", q_raw.lower())
    if num_m:
        idx = int(num_m.group(1)) - 1
        if 0 <= idx < len(catalog):
            return catalog[idx]

    q = _clean_community_phrase(query)
    if not q:
        return None
    q_lower = q.lower()
    q_tokens = set(re.findall(r"[a-z0-9]+", q_lower))

    best_row: dict | None = None
    best_score = 0.0
    for row in catalog:
        name = str(row.get("name") or "").strip()
        if not name:
            continue
        n_lower = name.lower()
        n_tokens = set(re.findall(r"[a-z0-9]+", n_lower))
        if q_lower == n_lower:
            score = 1.0
        elif q_lower in n_lower or n_lower in q_lower:
            score = 0.92
        else:
            score = difflib.SequenceMatcher(None, q_lower, n_lower).ratio()
            if q_tokens and n_tokens:
                overlap = len(q_tokens & n_tokens) / max(len(q_tokens), len(n_tokens))
                score = max(score, overlap)
        if score > best_score:
            best_score = score
            best_row = row
    if best_row and best_score >= 0.55:
        return best_row
    return None


def _latest_community_exchange(
    history: list | None,
    message: str = "",
) -> tuple[str | None, str | None]:
    """Return (assistant_question, user_reply) for the latest community step."""
    if not history:
        reply = (message or "").strip() or None
        return None, reply

    q_idx: int | None = None
    for i in range(len(history) - 1, -1, -1):
        if history[i].get("role") != "assistant":
            continue
        text = (history[i].get("message") or "").lower()
        if any(k in text for k in _COMMUNITY_QUESTION_MARKERS):
            q_idx = i
            break

    if q_idx is None:
        if message and _extract_community_name_from_text(message):
            return None, message.strip()
        return None, None

    assistant_q = history[q_idx].get("message") or ""
    user_reply: str | None = None
    for j in range(q_idx + 1, len(history)):
        role = history[j].get("role")
        if role == "assistant":
            break
        if role == "user" and not user_reply:
            user_reply = (history[j].get("message") or "").strip() or None

    if message and (message or "").strip():
        if _assistant_last_asked_kind(history) == "community":
            user_reply = message.strip()
    return assistant_q, user_reply


def _extract_community_name_from_history(
    history: list | None,
    message: str = "",
) -> str | None:
    """Best-effort community name from an in-progress share conversation.

    Prefers the donor's latest reply after a community question over the
    assistant's earlier suggestion — critical when they pick a different
    school than the profile default.
    """
    assistant_q, user_reply = _latest_community_exchange(history, message)

    if user_reply:
        from_user = _extract_community_name_from_text(user_reply)
        if from_user:
            return from_user
        if _is_affirmative_post_confirm(user_reply) and assistant_q:
            from_assistant = _extract_community_name_from_assistant_question(assistant_q)
            if from_assistant:
                return from_assistant

    if assistant_q:
        from_assistant = _extract_community_name_from_assistant_question(assistant_q)
        if from_assistant:
            return from_assistant

    blob = _history_blob(history, message, limit=16)
    for pat in (
        r"Community:\s*([^\n\.,]{3,80})",
        r"list(?:\s+this)?\s+under[:\s—-]+([^\n\?\.]{3,80})",
    ):
        m = re.search(pat, blob, re.IGNORECASE)
        if m:
            cleaned = _clean_community_phrase(m.group(1))
            if cleaned:
                return cleaned
    return None


def _resolve_community_from_thread(
    history: list | None,
    message: str,
    args: dict,
) -> dict:
    """Fill community_name / community_id from chat + prior community lists."""
    out = dict(args or {})
    catalog = _communities_from_history(history)

    candidates: list[str] = []
    if out.get("community_name"):
        candidates.append(str(out["community_name"]))
    extracted = _extract_community_name_from_history(history, message)
    if extracted:
        candidates.append(extracted)
    from_msg = _extract_community_name_from_text(message or "")
    if from_msg:
        candidates.append(from_msg)

    for raw in candidates:
        if catalog:
            hit = _match_community_in_catalog(raw, catalog)
            if hit:
                out["community_name"] = hit["name"]
                if hit.get("id"):
                    out["community_id"] = hit["id"]
                return out
        cleaned = _clean_community_phrase(raw)
        if cleaned:
            out["community_name"] = cleaned
            return out
    return out


# Assistant lines that mark a completed post — anything before this is
# from a previous listing and must NOT leak into the current post's args.
# Markers are deliberately specific (they only fit Nouri's success
# template) so a casual mention like "have you posted before?" doesn't
# false-trigger the boundary.
_POST_SUCCESS_MARKERS: tuple[str, ...] = (
    "posted!", "posted your", "listing posted", "published!",
    "published your", "your listing is live", "listing is live",
    "listing #", "listing is up", "just posted your", "just shared your",
    "publicado tu", "publicado la", "publicada tu", "listado publicado",
    "listing created", "created listing", "created your listing",
    "done!", "done —", "done -", "all set!", "all set —", "all set -",
    "shared!", "shared your", "successfully posted", "is now live",
    "now live", "went live", "donation is live", "is up under",
    "are live", "listings are live", "both are live", "they're live",
    "they are live", "posted under", "listed under", "went up under",
    "awaiting admin approval", "awaiting approval", "submitted for approval",
    "waiting for admin",
    "listo!", "listo —", "ya está publicado", "ya esta publicado",
)


def _current_posting_boundary_index(history: list | None) -> int:
    """Index of the first history entry that belongs to the *current*
    posting flow.

    We scan from the end backwards looking for the most recent assistant
    "Posted!" / "Listing #…" success marker. Everything at that index and
    earlier is finished — a photo, allergen, or expiry mentioned before
    that marker belongs to a *previous* listing and must not bleed into
    the current one. Returns 0 when no marker is found (fresh session).
    """
    if not history:
        return 0
    for idx in range(len(history) - 1, -1, -1):
        msg = history[idx]
        if msg.get("role") != "assistant":
            continue
        text = str(msg.get("message") or "").lower()
        if any(marker in text for marker in _POST_SUCCESS_MARKERS):
            return idx + 1
    return 0


def _user_declined_photo(history: list | None, message: str = "") -> bool:
    """True only when the donor explicitly skips adding a photo.

    Requires photo context (assistant recently asked for a photo, or the
    phrase itself mentions skipping a photo) so "post now" / bare "without"
    does not accidentally count as a decline after an unrelated turn.
    """
    def _matches(ul: str) -> bool:
        return any(p in ul for p in _PHOTO_DECLINE_PHRASES)

    blob = _history_blob(history or [], message).lower()
    photo_context = any(p in blob for p in (
        "photo", "picture", "snap a", "upload a", "foto", "imagen",
    ))
    ul = (message or "").lower()
    if _matches(ul) and (photo_context or any(
        k in ul for k in ("photo", "picture", "foto", "imagen", "without")
    )):
        # Exclude bare post-confirm phrases that are not photo skips.
        if ul.strip() in {"post now", "publish now", "post it", "post them"}:
            return False
        return True
    for msg in history or []:
        if msg.get("role") != "user":
            continue
        hl = (msg.get("message") or "").lower()
        if _matches(hl) and (
            photo_context
            or any(k in hl for k in ("photo", "picture", "foto", "imagen", "without"))
        ):
            if hl.strip() in {"post now", "publish now", "post it", "post them"}:
                continue
            return True
    return False


def normalize_public_image_url(url: str | None) -> str | None:
    """Return a storable public image URL (absolute https preferred)."""
    if not url:
        return None
    u = str(url).strip().rstrip(").,]")
    if not u:
        return None
    if u.startswith(("http://", "https://")):
        return u[:2000]
    if u.startswith("/"):
        base = (os.getenv("PUBLIC_BASE_URL") or "").rstrip("/")
        if base:
            return f"{base}{u}"[:2000]
    return None


def _extract_photo_url_from_history(
    history: list | None,
    message: str = "",
) -> str | None:
    """Pull the most recent uploaded photo URL from chat history.

    Note: this is deliberately unscoped — used by 'add a photo to an
    existing listing' intent where the whole thread is fair game. For
    the *current posting* flow use
    ``_extract_photo_url_for_current_posting`` which respects the flow
    boundary.
    """
    blob = _history_blob(history, message, limit=16)
    for pat in (
        r"image:\s*(https?://\S+)",
        r"image:\s*(/uploads/\S+)",
        r"(https?://\S+/storage/v1/object/public/\S+)",
        r"(https?://\S+\.(?:jpg|jpeg|png|webp|gif)(?:\?\S*)?)",
    ):
        matches = re.findall(pat, blob, re.IGNORECASE)
        if matches:
            url = matches[-1].strip().rstrip(").,]")
            if url.startswith(("http://", "https://", "/")):
                return url
    return None


def _extract_photo_url_for_current_posting(
    history: list | None,
    message: str = "",
) -> str | None:
    """Return a photo URL that belongs to the CURRENT posting flow only.

    A photo attached before the most recent "Posted!" success marker
    belongs to a completed listing and must not be reused for the next
    post. This is the fix for the classic bug where Nouri silently
    reuses the previous listing's photo on a brand-new listing that
    the donor never attached one to.
    """
    hist = history or []
    boundary = _current_posting_boundary_index(hist)
    scoped = hist[boundary:] if boundary else hist
    return _extract_photo_url_from_history(scoped, message)


def _extract_all_photo_urls_from_history(
    history: list | None,
    message: str = "",
) -> list[str]:
    """Return every photo URL in order (oldest → newest) from the blob."""
    blob = _history_blob(history, message, limit=24)
    found: list[str] = []
    seen: set[str] = set()
    for pat in (
        r"image:\s*(https?://\S+)",
        r"image:\s*(/uploads/\S+)",
        r"(https?://\S+/storage/v1/object/public/\S+)",
    ):
        for match in re.finditer(pat, blob, re.IGNORECASE):
            url = match.group(1).strip().rstrip(").,]")
            if not url.startswith(("http://", "https://", "/")):
                continue
            if url in seen:
                continue
            seen.add(url)
            found.append(url)
    return found


def _extract_all_photo_urls_for_current_posting(
    history: list | None,
    message: str = "",
) -> list[str]:
    hist = history or []
    boundary = _current_posting_boundary_index(hist)
    scoped = hist[boundary:] if boundary else hist
    return _extract_all_photo_urls_from_history(scoped, message)


# ---------------------------------------------------------------------------
# Multi-listing share drafts (queue of items + per-item photos)
# ---------------------------------------------------------------------------

_share_drafts_by_user: dict[str, list[dict]] = {}

_SHARE_ITEM_RE = re.compile(
    r"(?P<qty>\d{1,4}(?:\.\d+)?)\s+"
    r"(?:(?P<unit>loaves?|trays?|boxes?|bags?|baskets?|sacks?|bunches?|pieces?|packs?|"
    r"packets?|cartons?|cans?|jars?|containers?|bottles?|"
    r"pounds?|lbs?|kg|kilos?|grams?|cups?|units?|portions?|"
    r"servings?|slices?|dozen)\s+(?:of\s+)?)?"
    r"(?P<title>[a-zA-Z][a-zA-Z'\-]*(?:\s+[a-zA-Z][a-zA-Z'\-]*){0,3})",
    re.IGNORECASE,
)

_ALSO_FOOD_RE = re.compile(
    r"(?:also|and|plus|y)\s+"
    r"(?:some\s+|a\s+|an\s+)?"
    r"(?:(?P<unit>loaves?|trays?|boxes?|bags?|baskets?|sacks?|bunches?|pieces?|packs?|"
    r"packets?|cartons?|cans?|jars?|containers?|bottles?|"
    r"pounds?|lbs?|dozen)\s+(?:of\s+)?)?"
    r"(?P<title>[a-zA-Z][a-zA-Z'\-]+(?:\s+[a-zA-Z][a-zA-Z'\-]*){0,2})",
    re.IGNORECASE,
)


def get_share_drafts(user_id: str) -> list[dict]:
    return list(_share_drafts_by_user.get(str(user_id or ""), []) or [])


def set_share_drafts(user_id: str, drafts: list[dict] | None) -> None:
    uid = str(user_id or "").strip()
    if not uid:
        return
    if not drafts:
        _share_drafts_by_user.pop(uid, None)
        return
    _share_drafts_by_user[uid] = [dict(d) for d in drafts]


def clear_share_drafts(user_id: str) -> None:
    _share_drafts_by_user.pop(str(user_id or ""), None)


def _normalize_share_title(raw: str) -> str:
    words = [
        w for w in re.findall(r"[a-zA-Z']+", (raw or "").lower())
        if w not in _QTY_UNIT_WORDS
        and w not in {
            "and", "with", "some", "extra", "fresh", "my", "the", "a", "an",
            "want", "share", "donate", "give", "away", "post", "listing",
            "please", "thanks", "expire", "expires", "tomorrow", "today",
            "friday", "monday", "under", "for", "to",
        }
    ]
    if not words:
        return (raw or "").strip()[:80]
    # Prefer a known food word if present.
    food = next((w for w in words if w in _FOOD_WORDS), None)
    if food:
        return food
    return " ".join(words[:3])[:80]


def _parse_share_items_from_text(text: str) -> list[dict]:
    """Parse one or more share items from a donor message."""
    t = (text or "").strip()
    if not t:
        return []
    # Skip pure photo uploads.
    if re.match(r"^\s*image:\s*\S+\s*$", t, re.I):
        return []

    items: list[dict] = []
    seen_titles: set[str] = set()

    for m in _SHARE_ITEM_RE.finditer(t):
        title = _normalize_share_title(m.group("title") or "")
        if not title or len(title) < 2:
            continue
        # Require a food-ish signal to avoid "3 days" / "2 miles".
        title_tokens = set(re.findall(r"[a-zA-Z']+", title.lower()))
        if not (title_tokens & _FOOD_WORDS) and title.lower() not in _FOOD_WORDS:
            # Allow multi-word food phrases even if not in the small lexicon
            # when unit is present (e.g. "3 loaves of sourdough bread").
            if not m.group("unit"):
                continue
        key = title.lower()
        if key in seen_titles:
            continue
        seen_titles.add(key)
        try:
            qty = float(m.group("qty"))
        except (TypeError, ValueError):
            qty = 1.0
        unit = (m.group("unit") or "items").lower().rstrip("s")
        if unit == "loave":
            unit = "loaf"
        elif unit == "lb":
            unit = "lb"
        elif unit.endswith("e") and unit + "s" in {
            "loaves", "boxes", "bunches", "pieces", "slices",
        }:
            pass
        items.append({
            "title": title,
            "qty": qty if qty > 0 else 1.0,
            "unit": unit or "items",
        })

    # "also some oranges" / "and a bag of apples" without a leading quantity.
    if not items or len(items) == 1:
        for m in _ALSO_FOOD_RE.finditer(t):
            title = _normalize_share_title(m.group("title") or "")
            if not title or title.lower() in seen_titles:
                continue
            if title.lower() not in _FOOD_WORDS and not any(
                w in _FOOD_WORDS for w in title.lower().split()
            ):
                continue
            seen_titles.add(title.lower())
            unit = (m.group("unit") or "items").lower().rstrip("s")
            if unit == "loave":
                unit = "loaf"
            items.append({"title": title, "qty": 1.0, "unit": unit or "items"})

    # Bare multi-food without numbers: "share bread and apples"
    if len(items) < 2:
        foods = [
            w for w in re.findall(r"[a-zA-Z']+", t.lower())
            if w in _FOOD_WORDS and w not in _QTY_UNIT_WORDS
        ]
        # Deduplicate while preserving order.
        uniq: list[str] = []
        for f in foods:
            if f not in uniq:
                uniq.append(f)
        if len(uniq) >= 2 and len(items) <= 1:
            items = [{"title": f, "qty": 1.0, "unit": "items"} for f in uniq[:6]]

    return items


_FRESH_SHARE_INTENT = (
    "i want to share", "want to share", "i'm sharing", "im sharing",
    "sharing ", "share some", "share food", "donate", "giving away",
    "give away", "post a listing", "list some",
    "quiero compartir", "voy a compartir", "compartir comida", "donar",
)

_RESTRICT_SHARE_INTENT = (
    "we are listing", "we're listing", "just listing", "only listing",
    "only sharing", "just sharing", "not the", "forget the",
    "don't share", "dont share", "skip the", "not listing",
    "listing tomatoes", "listing carrots", "please just",
    "estamos listando", "solo listando", "solo compartiendo",
)


def _is_fresh_share_intent(message: str) -> bool:
    t = (message or "").strip().lower()
    if not t:
        return False
    return any(k in t for k in _FRESH_SHARE_INTENT)


def _user_restricts_share_foods(message: str) -> bool:
    t = (message or "").strip().lower()
    if not t:
        return False
    return any(k in t for k in _RESTRICT_SHARE_INTENT)


def _food_titles_from_text(text: str) -> set[str]:
    """Normalized food title keys mentioned in text (including singulars)."""
    titles: set[str] = set()
    for item in _parse_share_items_from_text(text or ""):
        key = str(item.get("title") or "").strip().lower()
        if key:
            titles.add(key)
            # Treat carrot/carrots as the same family for pruning.
            if key.endswith("oes"):
                titles.add(key[:-2])  # tomatoes → tomato
            elif key.endswith("s") and len(key) > 3:
                titles.add(key[:-1])
            else:
                titles.add(key + "s")
                if key.endswith("o"):
                    titles.add(key + "es")  # tomato → tomatoes
    # Bare lexicon hits when parser only finds one item.
    for w in re.findall(r"[a-zA-Z']+", (text or "").lower()):
        if w in _FOOD_WORDS and w not in _QTY_UNIT_WORDS:
            titles.add(w)
            if w.endswith("s") and len(w) > 3:
                titles.add(w[:-1])
            else:
                titles.add(w + "s")
    return {t for t in titles if t}


def _scoped_user_food_titles(history: list | None, message: str) -> set[str]:
    boundary = _current_posting_boundary_index(history)
    scoped = (history or [])[boundary:]
    parts = [
        (m.get("message") or "")
        for m in scoped
        if m.get("role") == "user"
    ]
    parts.append(message or "")
    return _food_titles_from_text(" . ".join(parts))


def _draft_title_matches_active(title: str, active: set[str]) -> bool:
    key = str(title or "").strip().lower()
    if not key:
        return False
    if key in active:
        return True
    stem = key[:-1] if key.endswith("s") and len(key) > 3 else key
    return stem in active or (stem + "s") in active or (stem + "es") in active


def _prune_stale_share_drafts(
    user_id: str,
    message: str,
    history: list | None,
) -> None:
    """Drop draft foods that belong to a previous share / aren't in this turn.

    Fixes the banana→carrot/tomato contamination: in-memory drafts survived
    after a prior post (or weak 'Posted!' copy), then stole photos and
    drove reminders about the wrong food.
    """
    uid = str(user_id or "").strip()
    existing = get_share_drafts(uid)
    if not existing:
        return

    active = _scoped_user_food_titles(history, message)
    restrict = _user_restricts_share_foods(message)
    fresh = _is_fresh_share_intent(message)
    msg_foods = _food_titles_from_text(message or "")

    # Explicit "we are listing tomatoes and carrots" → keep only named foods.
    if restrict and msg_foods:
        keep = [
            d for d in existing
            if _draft_title_matches_active(d.get("title") or "", msg_foods)
        ]
        set_share_drafts(uid, keep)
        return

    # New share intent with named foods → replace the queue entirely.
    if fresh and msg_foods:
        clear_share_drafts(uid)
        return

    # After a prior Posted! boundary, drop titles that never appear in the
    # current scoped segment (stale bananas sitting in server memory).
    boundary = _current_posting_boundary_index(history)
    if boundary > 0 and active:
        keep = [
            d for d in existing
            if _draft_title_matches_active(d.get("title") or "", active)
        ]
        if len(keep) != len(existing):
            set_share_drafts(uid, keep)
        return

    # Even without a boundary: if this message names foods and existing
    # drafts include foods NOT in the scoped thread, prune the orphans.
    if msg_foods and active and len(existing) > len(msg_foods):
        keep = [
            d for d in existing
            if _draft_title_matches_active(d.get("title") or "", active)
        ]
        if keep and len(keep) < len(existing):
            set_share_drafts(uid, keep)


def upsert_share_drafts_from_message(
    user_id: str,
    message: str,
    history: list | None = None,
) -> list[dict]:
    """Merge newly mentioned share items into the user's draft queue."""
    uid = str(user_id or "").strip()
    if not uid:
        return []

    parsed = _parse_share_items_from_text(message or "")
    # Also scan recent user turns in the current posting segment for items
    # when the current message is short (qty/photo/confirm).
    if len(parsed) < 2 and history:
        boundary = _current_posting_boundary_index(history)
        scoped = (history or [])[boundary:]
        blob_parts = [
            (m.get("message") or "")
            for m in scoped
            if m.get("role") == "user"
        ]
        blob_parts.append(message or "")
        combined = _parse_share_items_from_text(" . ".join(blob_parts))
        if len(combined) > len(parsed):
            parsed = combined

    existing = get_share_drafts(uid)
    by_title = {str(d.get("title") or "").lower(): dict(d) for d in existing}

    for item in parsed:
        key = str(item.get("title") or "").lower()
        if not key:
            continue
        if key in by_title:
            cur = by_title[key]
            if item.get("qty") and (
                cur.get("qty") is None or float(cur.get("qty") or 0) <= 0
            ):
                cur["qty"] = item["qty"]
            if item.get("unit") and not cur.get("unit"):
                cur["unit"] = item["unit"]
        else:
            by_title[key] = {
                "id": f"d{len(by_title) + 1}",
                "title": item["title"],
                "qty": item.get("qty") or 1.0,
                "unit": item.get("unit") or "items",
                "expiry": None,
                "photo_url": None,
                "photo_declined": False,
                "allergens": [],
                "dietary_tags": [],
            }

    # Apply expiry from this message or earlier donor turns in the thread.
    exp = _best_user_expiry_from_thread(message, history)
    if exp:
        for d in by_title.values():
            if not d.get("expiry"):
                d["expiry"] = exp

    # Per-draft photo decline when the donor says skip while naming the food.
    ul = (message or "").lower()
    if any(p in ul for p in _PHOTO_DECLINE_PHRASES):
        named = _normalize_share_title(message)
        for d in by_title.values():
            title = str(d.get("title") or "").lower()
            if named and named.lower() in ul and title in ul:
                d["photo_declined"] = True
            elif len(by_title) == 1:
                d["photo_declined"] = True

    drafts = list(by_title.values())
    # Stable order: existing titles first, then new ones by parse order.
    order_keys = [str(d.get("title") or "").lower() for d in existing]
    for item in parsed:
        k = str(item.get("title") or "").lower()
        if k and k not in order_keys:
            order_keys.append(k)
    for k in by_title:
        if k not in order_keys:
            order_keys.append(k)
    ordered = [by_title[k] for k in order_keys if k in by_title]
    for i, d in enumerate(ordered, start=1):
        d["id"] = f"d{i}"
    set_share_drafts(uid, ordered)
    return ordered


def assign_photos_to_drafts(
    user_id: str,
    history: list | None,
    message: str = "",
) -> list[dict]:
    """Bind photo URLs in the current posting segment to drafts missing photos."""
    uid = str(user_id or "").strip()
    drafts = get_share_drafts(uid)
    if not drafts:
        return []

    urls = _extract_all_photo_urls_for_current_posting(history, message)
    if not urls:
        return drafts

    # Explicit "photo for the apples" + image in this message.
    ul = (message or "").lower()
    titled = None
    if "photo" in ul or "picture" in ul or "image:" in ul:
        for d in drafts:
            title = str(d.get("title") or "").lower()
            if title and title in ul and not d.get("photo_url"):
                titled = d
                break
    msg_urls = _extract_all_photo_urls_from_history([], message)
    if titled and msg_urls:
        titled["photo_url"] = normalize_public_image_url(msg_urls[-1]) or msg_urls[-1]
        set_share_drafts(uid, drafts)
        drafts = get_share_drafts(uid)

    used = {
        str(d.get("photo_url"))
        for d in drafts
        if d.get("photo_url")
    }
    unused = [
        (normalize_public_image_url(u) or u)
        for u in urls
        if (normalize_public_image_url(u) or u) not in used
    ]
    ui = 0
    for d in drafts:
        if d.get("photo_url") or d.get("photo_declined"):
            continue
        if ui >= len(unused):
            break
        d["photo_url"] = unused[ui]
        ui += 1

    set_share_drafts(uid, drafts)
    return get_share_drafts(uid)


def share_drafts_missing(drafts: list[dict] | None) -> list[dict]:
    """Return per-draft missing required fields (title/qty/expiry/photo)."""
    missing: list[dict] = []
    for d in drafts or []:
        gaps: list[str] = []
        if not d.get("title"):
            gaps.append("title")
        if d.get("qty") is None or float(d.get("qty") or 0) <= 0:
            gaps.append("qty")
        if not d.get("expiry"):
            gaps.append("expiry")
        if not d.get("photo_url") and not d.get("photo_declined"):
            gaps.append("photo")
        if gaps:
            missing.append({
                "id": d.get("id"),
                "title": d.get("title"),
                "missing": gaps,
            })
    return missing


def share_drafts_ready(
    drafts: list[dict] | None,
    *,
    community_confirmed: bool = False,
) -> bool:
    if not drafts or len(drafts) < 1:
        return False
    if not community_confirmed:
        return False
    return len(share_drafts_missing(drafts)) == 0


def sync_share_drafts(
    user_id: str,
    message: str,
    history: list | None = None,
) -> list[dict]:
    """Upsert items from the message, then assign photos. Returns drafts."""
    uid = str(user_id or "").strip()
    if not uid:
        return []
    _prune_stale_share_drafts(uid, message, history)
    drafts = upsert_share_drafts_from_message(uid, message, history)
    if len(drafts) >= 1:
        drafts = assign_photos_to_drafts(uid, history, message)
    return drafts


def build_share_drafts_reminder(
    user_id: str,
    message: str,
    history: list | None = None,
    lang: str = "en",
) -> str | None:
    """System nudge listing multi-share drafts and what's still needed."""
    drafts = get_share_drafts(str(user_id or ""))
    if len(drafts) < 2:
        return None
    state = posting_flow_state(message, history)
    missing = share_drafts_missing(drafts)
    lines = []
    for d in drafts:
        photo = "photo=yes" if d.get("photo_url") else (
            "photo=skipped" if d.get("photo_declined") else "photo=missing"
        )
        exp = d.get("expiry") or "expiry=?"
        lines.append(
            f"- {d.get('title')}: qty={d.get('qty')} {d.get('unit')}, "
            f"{exp}, {photo}"
        )
    body = "\n".join(lines)
    if lang == "es":
        tip = (
            "Cola de publicaciones múltiples. Completa campos faltantes "
            "uno por turno (comunidad compartida una vez; luego vencimiento/"
            "foto por ítem). Cuando todo esté listo, un resumen y "
            "post_food_listings. Nunca reutilices la foto del ítem A en B."
        )
    else:
        tip = (
            "MULTI-SHARE DRAFT QUEUE (2+ items). Ask ONE missing field per "
            "turn (shared community/address once, then per-item expiry/photo). "
            "When all drafts are ready, give one summary and call "
            "post_food_listings with items[] (each with its own images[]). "
            "Never reuse draft A's photo on draft B."
        )
    gap = ""
    if missing:
        gap = " Still missing: " + "; ".join(
            f"{m.get('title')}→{','.join(m.get('missing') or [])}"
            for m in missing
        )
    elif not state.get("community_confirmed"):
        gap = " Community not confirmed yet."
    elif _posting_ready_to_execute(message, history):
        gap = " Donor confirmed — call post_food_listings NOW (no second yes)."
    else:
        gap = (
            " All item fields ready — ONE summary + 'Ready to post these?', "
            "then post on their first yes."
        )
    return f"{tip}\nDrafts:\n{body}.{gap}"


def enrich_post_food_listings_args(
    args: dict,
    message: str,
    history: list | None,
    user_id: str,
) -> dict:
    """Fill batch post args from the share-draft queue + thread context."""
    out = dict(args or {})
    uid = str(user_id or "").strip()
    drafts = sync_share_drafts(uid, message, history) if uid else get_share_drafts(uid)

    # Shared community / address from single-post enrich helpers.
    single = enrich_post_food_listing_args(
        {
            "community_name": out.get("community_name"),
            "community_id": out.get("community_id"),
            "community_confirmed": out.get("community_confirmed"),
            "address": out.get("address"),
            "expiration_date": out.get("expiration_date"),
        },
        message,
        history,
    )
    for key in (
        "community_name", "community_id", "community_confirmed", "address",
    ):
        if single.get(key) is not None:
            out[key] = single[key]

    items = out.get("items")
    if not isinstance(items, list) or not items:
        items = []
        for d in drafts:
            item = {
                "title": d.get("title"),
                "qty": d.get("qty") or 1,
                "unit": d.get("unit") or "items",
            }
            if d.get("expiry"):
                item["expiration_date"] = d["expiry"]
            if d.get("photo_url"):
                item["images"] = [d["photo_url"]]
            if d.get("allergens"):
                item["allergens"] = list(d["allergens"])
            if d.get("dietary_tags"):
                item["dietary_tags"] = list(d["dietary_tags"])
            items.append(item)
        out["items"] = items
    else:
        # Merge draft photos into model-supplied items by title order.
        by_title = {
            str(d.get("title") or "").lower(): d for d in drafts
        }
        used_photos: set[str] = set()
        for item in items:
            if not isinstance(item, dict):
                continue
            title_key = str(item.get("title") or "").lower()
            draft = by_title.get(title_key)
            imgs = item.get("images") if isinstance(item.get("images"), list) else []
            cleaned = []
            for u in imgs:
                norm = normalize_public_image_url(str(u)) or str(u).strip()
                if norm:
                    cleaned.append(norm)
                    used_photos.add(norm)
            if not cleaned and draft and draft.get("photo_url"):
                cleaned = [draft["photo_url"]]
                used_photos.add(draft["photo_url"])
            if cleaned:
                item["images"] = cleaned
            if draft and draft.get("expiry") and not (
                item.get("expiration_date") or item.get("expiry_date")
            ):
                item["expiration_date"] = draft["expiry"]
        out["items"] = items

    # Batch-wide expiry from the thread applies to every item still missing one.
    thread_exp = _best_user_expiry_from_thread(message, history)
    if thread_exp:
        for item in out.get("items") or []:
            if not isinstance(item, dict):
                continue
            if not (item.get("expiration_date") or item.get("expiry_date")):
                item["expiration_date"] = thread_exp
                item["expiry_date"] = thread_exp

    return out


def posting_batch_tool_block_reason(
    message: str,
    history: list | None,
    fn_args: dict | None = None,
    user_id: str = "",
) -> str | None:
    """Block post_food_listings when the multi-share queue is incomplete."""
    args = fn_args or {}
    uid = str(user_id or args.get("user_id") or "").strip()
    drafts = get_share_drafts(uid) if uid else []
    items = args.get("items") if isinstance(args.get("items"), list) else []

    if len(drafts) < 2 and len(items) < 2:
        return (
            "post_food_listings is for 2+ items. For a single listing use "
            "post_food_listing instead."
        )

    state = posting_flow_state(message, history)
    community_confirmed = bool(args.get("community_confirmed")) or state["community_confirmed"]
    if not community_confirmed:
        return (
            "Confirm which community/school this batch goes under, then call "
            "post_food_listings with community_name and community_confirmed=true."
        )

    thread_exp = _best_user_expiry_from_thread(message, history)

    # Prefer explicit items[] gaps when provided; else draft queue.
    if items:
        gaps = []
        for i, item in enumerate(items, start=1):
            if not isinstance(item, dict):
                gaps.append(f"item {i}: invalid")
                continue
            miss = []
            if not item.get("title"):
                miss.append("title")
            if item.get("qty") is None and item.get("quantity") is None:
                miss.append("qty")
            has_exp = bool(
                item.get("expiration_date")
                or item.get("expiry_date")
                or thread_exp
            )
            if not has_exp:
                miss.append("expiry")
            imgs = item.get("images") if isinstance(item.get("images"), list) else []
            if not imgs:
                # Allow decline only when drafts say so for that title.
                title = str(item.get("title") or "").lower()
                declined = any(
                    str(d.get("title") or "").lower() == title and d.get("photo_declined")
                    for d in drafts
                )
                if not declined and not state.get("photo_declined"):
                    miss.append("photo")
            if miss:
                gaps.append(f"{item.get('title') or i}: {', '.join(miss)}")
        if gaps:
            return (
                "Batch incomplete — still need: " + "; ".join(gaps) + ". "
                "Ask for the next missing field, then retry post_food_listings."
            )
    else:
        missing = share_drafts_missing(drafts)
        if missing:
            bits = [
                f"{m.get('title')}: {', '.join(m.get('missing') or [])}"
                for m in missing
            ]
            return (
                "Batch incomplete — still need: " + "; ".join(bits) + ". "
                "Ask for the next missing field (one at a time), then retry."
            )

    return _post_confirm_needed_reason(message, history)


def enrich_post_food_listing_args(
    args: dict,
    message: str,
    history: list | None,
) -> dict:
    """Fill community_confirmed and community_name from thread context."""
    out = dict(args or {})
    state = posting_flow_state(message, history)
    desc = str(out.get("description") or "")
    if not out.get("community_name"):
        m = re.search(r"Community:\s*([^\n\.,]+)", desc, re.IGNORECASE)
        if m:
            out["community_name"] = m.group(1).strip()
    out = _resolve_community_from_thread(history, message, out)
    if state["community_confirmed"] or (
        _is_affirmative_post_confirm(message)
        and _assistant_last_asked_kind(history) in {"community", "post_confirm"}
    ):
        out["community_confirmed"] = True
    elif _extract_community_name_from_text(message or ""):
        # Donor named a specific community this turn — treat as confirmed.
        out["community_confirmed"] = True

    # Photo: ONLY attach URLs from the CURRENT posting flow. The model
    # often replays images[] from a prior listing in full chat context —
    # never trust model-passed images/image_url without scoped validation.
    out.pop("image_url", None)
    if state["photo_declined"]:
        out.pop("images", None)
    else:
        photo_url = _extract_photo_url_for_current_posting(history, message)
        if photo_url:
            norm = normalize_public_image_url(photo_url) or photo_url
            out["images"] = [norm]
        else:
            out.pop("images", None)

    user_exp = _best_user_expiry_from_thread(message, history)
    model_exp = out.get("expiration_date") or out.get("expiry_date")
    # Always prefer the donor's spoken/typed date — the model inventing
    # a past year (e.g. 2024 for "July 24th") was trapping share flows.
    exp = user_exp or model_exp
    if exp:
        out["expiration_date"] = exp
        out["expiry_date"] = exp
    # Allergens + dietary tags — donor may have mentioned them in prose
    # ('contains peanuts', 'it's vegan') without the model routing them
    # into the structured args. Advisory only — never overwrites what the
    # model already set. See backend/ai/allergens.py.
    try:
        from backend.ai.allergens import enrich_post_listing_allergen_args
        out = enrich_post_listing_allergen_args(out, message, history)
    except Exception:  # pragma: no cover — allergen layer is advisory
        pass
    return out


def enrich_attach_photos_args(
    args: dict,
    message: str,
    history: list | None,
    user_id: str,
) -> dict:
    """Fill listing_id / images[] from chat when the model omits them."""
    out = dict(args or {})
    uid = str(user_id or "").strip()

    images: list[str] = []
    for raw in out.get("images") or []:
        if not raw:
            continue
        norm = normalize_public_image_url(str(raw)) or str(raw).strip()
        if norm:
            images.append(norm)
    if not images:
        # Prefer every image: URL in the CURRENT message (multi-photo sends),
        # then fall back to the most recent URL in history.
        from_msg = _extract_all_photo_urls_from_history([], message)
        if from_msg:
            images.extend(from_msg)
        else:
            url = _extract_photo_url_from_history(history, message)
            if url:
                images.append(url)

    if images:
        out["images"] = images

    if not out.get("listing_id") and uid:
        intent = donor_photo_add_intent(message, history, uid)
        if intent and intent.get("listing_id"):
            out["listing_id"] = intent["listing_id"]
        else:
            recent = get_last_write_action(uid)
            if isinstance(recent, dict) and recent.get("listing_id"):
                out["listing_id"] = recent["listing_id"]

    return out


def posting_tool_block_reason(
    message: str,
    history: list | None,
    fn_args: dict | None = None,
) -> str | None:
    """Return a block message if post_food_listing is premature."""
    if not is_posting_flow(message, history):
        return None
    state = posting_flow_state(message, history)
    last_asked = _assistant_last_asked_kind(history)
    args = fn_args or {}
    ready = _posting_ready_to_execute(message, history)

    community_confirmed = bool(args.get("community_confirmed")) or state["community_confirmed"]
    if not community_confirmed:
        return (
            "Ask which community/school this listing goes under and get explicit "
            "confirmation ('yes, that one') before posting. Pass community_name "
            "and community_confirmed=true only after they confirm."
        )

    has_expiry = bool(
        args.get("expiration_date")
        or args.get("expiry_date")
        or state["expiry_provided"]
        or _best_user_expiry_from_thread(message, history)
    )
    if not has_expiry:
        return (
            "Ask when the food expires or its best-by date before posting. "
            "Map their answer to expiration_date (YYYY-MM-DD). Do not guess silently."
        )

    # After "Shall I post? / yes", post immediately — but still require the
    # photo step to have happened at least once (ask OR upload OR decline).
    if ready:
        if not state["photo_asked"] and not state["has_photo"] and not state["photo_declined"]:
            return (
                "Ask for a photo once before calling post_food_listing "
                "(the donor may decline)."
            )
        # Re-asking photo after a Ready-to-post yes is what trapped the
        # tomatoes/carrots share — only keep waiting if no summary was offered yet.
        if state["awaiting_photo"] and not state["post_summary_offered"]:
            if last_asked == "photo" and _is_short_affirmative(message):
                return (
                    "The donor said yes/ok but no photo URL is in the chat yet. "
                    "Ask them to upload/attach the photo in chat, or say 'skip photo' "
                    "to continue without one. Do NOT call post_food_listing yet."
                )
            return (
                "Still waiting for a photo upload (image: … URL in chat) or an "
                "explicit 'no photo' / 'skip photo' before posting."
            )
        return None

    if not state["photo_asked"] and not state["has_photo"]:
        return (
            "Ask for a photo once before calling post_food_listing "
            "(the donor may decline)."
        )

    if state["awaiting_photo"]:
        if last_asked == "photo" and _is_short_affirmative(message):
            return (
                "The donor said yes/ok but no photo URL is in the chat yet. "
                "Ask them to upload/attach the photo in chat, or say 'skip photo' "
                "to continue without one. Do NOT call post_food_listing yet."
            )
        if not state["has_photo"] and not state["photo_declined"]:
            return (
                "Still waiting for a photo upload (image: … URL in chat) or an "
                "explicit 'no photo' / 'skip photo' before posting."
            )

    return _post_confirm_needed_reason(message, history)


def build_posting_step_reminder(
    message: str,
    history: list | None,
    lang: str = "en",
) -> str | None:
    """Contextual posting nudge — not a numbered script."""
    if not is_posting_flow(message, history):
        return None

    state = posting_flow_state(message, history)
    last_asked = _assistant_last_asked_kind(history)
    parsed_exp = _best_user_expiry_from_thread(message, history)
    ready = _posting_ready_to_execute(message, history)

    if lang == "es":
        if not state["community_confirmed"]:
            return (
                "Sugerencia: pregunta bajo qué escuela o comunidad va el "
                "listado y espera un 'sí' claro antes de seguir. Frase "
                "libre, no un guion."
            )
        if not state["expiry_provided"]:
            if not state["expiry_asked"]:
                return (
                    "Sugerencia: incluye una pregunta sobre vencimiento / "
                    "fecha límite en tu próxima respuesta. Pásalo como "
                    "expiration_date en YYYY-MM-DD."
                )
            return (
                "Sugerencia: todavía no dieron la fecha — espera y "
                "mapéala a expiration_date (YYYY-MM-DD)."
            )
        if state["expiry_provided"] and last_asked == "expiry":
            exp_hint = (
                f" Usa expiration_date={parsed_exp} — ya la dieron en el chat."
                if parsed_exp else " Usa la fecha que ya dieron."
            )
            return (
                "Sugerencia: el donante ya dio la fecha de vencimiento."
                f"{exp_hint} No la vuelvas a pedir — sigue con foto o resumen."
            )
        if ready and (
            state["photo_asked"] or state["has_photo"] or state["photo_declined"]
        ):
            exp_hint = (
                f" Usa expiration_date={parsed_exp} exactamente."
                if parsed_exp else ""
            )
            return (
                "Confirmaron — llama post_food_listing (o post_food_listings "
                f"si hay 2+ borradores) AHORA.{exp_hint} No vuelvas a pedir "
                "foto, fecha, comunidad ni confirmación."
            )
        if state["awaiting_photo"] and last_asked == "photo" and _is_short_affirmative(message):
            return (
                "Sugerencia: dijeron sí pero aún no hay foto adjunta. "
                "No publiques. Pide que suban la foto o pregúntales si "
                "prefieren seguir sin ella."
            )
        if state["awaiting_photo"]:
            return (
                "Sugerencia: espera a que suban la foto o digan 'sin foto' "
                "antes de resumir o publicar."
            )
        if not state["photo_asked"]:
            return (
                "Sugerencia: pregunta por foto una vez (pueden decir que "
                "no), luego un resumen breve y '¿listo para publicar?'."
            )
        if not state["post_summary_offered"]:
            return (
                "Sugerencia: da UN resumen corto y pregunta "
                "'¿Listo para publicar?' UNA vez. Tras su sí, llama al "
                "tool de inmediato — no pidas confirmar otra vez."
            )
        if last_asked == "post_confirm" and _is_affirmative_post_confirm(message):
            return (
                "Confirmaron — llama post_food_listing (o post_food_listings "
                "si hay 2+ borradores) AHORA. No vuelvas a pedir confirmación."
            )
        return (
            "Sugerencia: conversacional — una pregunta por turno. Si ya "
            "preguntaste '¿listo para publicar?', espera el sí y publica."
        )

    if not state["community_confirmed"]:
        return (
            "Nudge: ask which school or community this goes under, and "
            "wait for a clear yes before moving on. Phrase it however "
            "sounds natural — this is not a fixed script."
        )
    if not state["expiry_provided"]:
        if not state["expiry_asked"]:
            return (
                "Nudge: work an expiry / best-by question into your next "
                "reply. Pass expiration_date as YYYY-MM-DD when posting."
            )
        return (
            "Nudge: they haven't given the expiry yet — wait for it and "
            "map it to expiration_date (YYYY-MM-DD)."
        )
    if state["expiry_provided"] and last_asked == "expiry":
        exp_hint = (
            f" Use expiration_date={parsed_exp} — already provided in chat."
            if parsed_exp else " Map the date they already gave."
        )
        return (
            "Nudge: the donor already gave a best-by / expiry date."
            f"{exp_hint} Do NOT ask again — move on to photo or post summary."
        )
    if ready and (
        state["photo_asked"] or state["has_photo"] or state["photo_declined"]
    ):
        exp_hint = (
            f" Use expiration_date={parsed_exp} exactly — do not invent another year."
            if parsed_exp else ""
        )
        return (
            "They confirmed — call post_food_listing now "
            "(or post_food_listings if 2+ share drafts are queued)."
            f"{exp_hint} Do NOT re-ask for photos, expiry, community, or "
            "another confirmation."
        )
    if state["awaiting_photo"] and last_asked == "photo" and _is_short_affirmative(message):
        return (
            "Nudge: they said 'yes/ok' but no photo is attached yet. "
            "Don't post. Warmly ask them to upload it, or offer to "
            "continue without one."
        )
    if state["awaiting_photo"]:
        return (
            "Nudge: waiting on either a photo upload or an explicit "
            "'no photo' before summarizing / posting."
        )
    if not state["photo_asked"]:
        return (
            "Nudge: ask about a photo once (declining is fine), then give "
            "ONE short summary and check 'Ready to post?'."
        )
    if not state["post_summary_offered"]:
        return (
            "Nudge: give ONE short summary and ask 'Ready to post?' once. "
            "After they say yes, call the post tool immediately — do NOT "
            "ask them to confirm again."
        )
    if last_asked == "post_confirm" and _is_affirmative_post_confirm(message):
        return (
            "They confirmed — call post_food_listing now "
            "(or post_food_listings if 2+ share drafts are queued). "
            "Do NOT re-ask for confirmation."
        )
    return (
        "Nudge: keep it conversational — one question per turn. If you "
        "already asked 'Ready to post?', wait for yes and post — don't "
        "repeat the same confirmation."
    )


def _is_affirmative_post_confirm(message: str) -> bool:
    t = (message or "").strip().lower()
    if not t:
        return False
    keys = (
        "yes", "yep", "yeah", "yup", "post it", "post them", "post these",
        "post now", "publish now", "go ahead", "confirm", "publish",
        "use that", "that one",
        "sounds good", "looks good", "looks right", "do it", "please do",
        "sí", "si ", "publicalo", "publícalo", "dale", "adelante",
        "yes, confirm", "yes confirm", "yes, post", "yes post",
    )
    return any(k in t for k in keys)


def _posting_ready_to_execute(message: str, history: list | None) -> bool:
    """True when the donor already greenlit posting this turn."""
    last = _assistant_last_asked_kind(history)
    state = posting_flow_state(message, history)
    affirmative = (
        _is_affirmative_post_confirm(message)
        or _is_short_affirmative(message)
    )
    if not affirmative:
        return False
    if last == "post_confirm":
        return True
    if state.get("post_summary_offered"):
        return True
    t = (message or "").lower()
    # Explicit publish language even if the assistant phrased the ask oddly.
    return any(k in t for k in (
        "post it", "post them", "post these", "publish it",
        "yes, post", "yes post", "go ahead and post", "yes, confirm",
    ))


def _post_confirm_needed_reason(message: str, history: list | None) -> str | None:
    """Ask for exactly one Ready-to-post confirm — never a second one."""
    if _posting_ready_to_execute(message, history):
        return None
    last = _assistant_last_asked_kind(history)
    state = posting_flow_state(message, history)
    if last == "post_confirm" or state.get("post_summary_offered"):
        if _is_affirmative_post_confirm(message) or _is_short_affirmative(message):
            return None
        return (
            "They have already seen a post summary. Wait for a clear yes / "
            "'post it' — then call the post tool immediately. Do NOT restate "
            "the same confirmation question."
        )
    return (
        "Give ONE short summary of the ready listing(s) and ask "
        "'Ready to post these?' — then wait. After they say yes, call the "
        "post tool immediately. Do NOT ask them to confirm twice."
    )


def _posting_checklist(message: str, history: list | None, lang: str) -> str:
    """Legacy checklist — prefer build_posting_step_reminder for live turns."""
    if needs_assistance_mode_choice(message, history):
        if lang == "es":
            return (
                "FLUJO ACTIVO — COMPARTIR (elegir modo primero):\n"
                "Pregunta si quieres que Nouri lo publique TODO en el chat, o te "
                "guíe paso a paso en Share Food. NO llames post_food_listing aún."
            )
        return (
            "ACTIVE FLOW — SHARE FOOD (choose mode first):\n"
            "Ask whether they want Nouri to handle the whole post in chat, or "
            "guide them step by step on Share Food. Do NOT call "
            "post_food_listing yet."
        )
    mode = resolve_assistance_mode(message, history)
    if mode == "guided":
        if lang == "es":
            return (
                "FLUJO ACTIVO — COMPARTIR (modo guiado):\n"
                "Abre Share Food con navigate_ui (target=create) y explica los "
                "pasos. No publiques en el chat a menos que lo pidan."
            )
        return (
            "ACTIVE FLOW — SHARE FOOD (guided):\n"
            "Open Share Food via navigate_ui (target=create) and coach the steps. "
            "Do not post in chat unless they ask you to take over."
        )
    contextual = build_posting_step_reminder(message, history, lang=lang)
    if contextual:
        return contextual
    state = posting_flow_state(message, history)
    if lang == "es":
        return "Flujo de publicación activo — una pregunta por turno."
    return "Active posting flow — one question per turn."


def _claim_checklist(lang: str) -> str:
    if lang == "es":
        return (
            "Estás ayudando a reclamar comida — habla con calidez, no como formulario.\n"
            "• Pueden reclamar VARIOS ítems a la vez (#1 y #3, ambos, '2 naranjas y 3 panes').\n"
            "• Si eligen 2+: usa la cola multi-reclamo, pregunta cantidades una por una, "
            "resume y pregunta '¿Listo para reclamar estos?', luego claim_listings.\n"
            "• Si eligen uno solo: pregunta cuántos, luego claim_listing.\n"
            "• Si falla: explica el error; no vuelvas a buscar sin que lo pidan."
        )
    return (
        "You're helping them claim food — warm and conversational, not a form.\n"
        "• They can claim MULTIPLE items at once (#1 and #3, both, "
        "'2 oranges and 3 bread'). Emphasize that when showing results.\n"
        "• If they pick 2+: keep the multi-claim queue, ask missing qty one "
        "at a time, then ONE summary + 'Ready to claim these?' and call "
        "claim_listings with items[]. Never claim only the first.\n"
        "• If they pick a single listing: ask how many, then claim_listing.\n"
        "• If it fails: explain the error clearly — don't re-search unless they ask."
    )


def _user_picked_listing_in_history(history: list | None) -> bool:
    """True if a recent user turn looks like a numbered / claim pick."""
    if not history:
        return False
    for msg in reversed(history[-8:]):
        if msg.get("role") != "user":
            continue
        text = msg.get("message") or ""
        if _looks_like_listing_pick(text):
            return True
        if any(k in text.lower() for k in _CLAIM_TRIGGERS):
            return True
    return False


def _assistant_awaiting_quantity(history: list | None) -> bool:
    """True only when the assistant asked a claim-intake quantity question.

    Requires search/listing context so a mistaken qty ask cannot lock the
    conversation when no food options were ever shown.
    """
    if not history:
        return False
    if not (_recent_search_context(history) or _user_picked_listing_in_history(history)):
        return False
    for msg in reversed(history[-4:]):
        if msg.get("role") == "assistant":
            text = (msg.get("message") or "").lower()
            # Help / menu questions often contain "how many would you like to
            # try" — those are not claim quantity prompts.
            if any(k in text for k in (
                "try first", "would you like to try", "can you do",
                "how does this work", "what can i help",
            )):
                return False
            # Availability answers ("how many are left?") are user-side;
            # never treat the assistant's claim qty ask as that.
            return any(k in text for k in _CLAIM_QTY_ASK_MARKERS)
    return False


def _quantity_step_complete(history: list | None, message: str) -> bool:
    """True after the user answered a how-many question."""
    if not _assistant_awaiting_quantity(history):
        return False
    t = (message or "").strip().lower()
    if re.fullmatch(r"\d{1,3}", t):
        return True
    if t in ("all", "all of them", "the whole thing", "everything", "todo", "todos"):
        return True
    if re.search(r"\b\d+\b", t) and not _looks_like_multi_option_pick(message):
        return True
    return False


def _user_just_picked_listing(message: str, history: list | None) -> bool:
    """True when the user selects one listing from search results this turn.

    Returns False when the user already gave a quantity in the same message
    ("claim 2 oranges") so the how-many block doesn't misfire.
    """
    if _looks_like_multi_option_pick(message):
        return False
    if not _recent_search_context(history):
        return False
    if _assistant_awaiting_quantity(history):
        return False
    if _quantity_step_complete(history, message):
        return False

    # Message already contains a claim intent WITH a quantity → no "how many" needed.
    intent = _extract_claim_intent(message)
    if intent.get("quantity") is not None:
        return False

    t = (message or "").strip().lower()
    if _looks_like_listing_pick(message):
        return True
    if any(k in t for k in _CLAIM_TRIGGERS):
        return True
    words = _tokenize_words(message)
    if len(words) <= 2 and any(w in _FOOD_WORDS for w in words):
        return True
    return False


def build_claim_quantity_reminder(
    message: str,
    history: list | None,
    lang: str = "en",
) -> str | None:
    """After a listing pick, require a how-many question before claim_listing.

    The exact phrasing is adapted to the food's *real-world* form: bulk
    foods (beans, rice) get 'a bag / a few pounds', canned goods get
    'how many cans', countable produce gets 'how many'. Falls back to
    the generic prompt when we can't infer a food kind.
    """
    flow = detect_conversation_flow(message, history)
    if flow != "claiming":
        return None
    if not _user_just_picked_listing(message, history):
        return None

    try:
        from backend.ai.world_model import detect_food_kind  # local import; no hard dep
        entry = detect_food_kind(message)
        if not entry and history:
            for msg in reversed(history[-8:]):
                if msg.get("role") != "user":
                    continue
                entry = detect_food_kind(msg.get("message") or "")
                if entry:
                    break
    except Exception:  # pragma: no cover — defensive
        entry = None

    if entry:
        if lang == "es":
            return (
                f"El usuario eligió un listado de '{entry['food']}' "
                f"(tipo {entry['kind']}). Pregunta con unidades reales: "
                f"{entry['es_question']} No llames claim_listing todavía."
            )
        return (
            f"They picked a listing for '{entry['food']}' "
            f"({entry['kind']} item). Ask in real-world units: "
            f"{entry['en_question']} Do not call claim_listing yet."
        )

    if lang == "es":
        return (
            "El usuario eligió un listado. Pregunta SOLO: '¿Cuántos quieres?' "
            "Cita cuántos hay disponibles. No llames claim_listing todavía."
        )
    return (
        "They picked a listing. Ask ONLY one warm question: how many they want. "
        "Mention what's available. Do not call claim_listing yet."
    )


def _finding_checklist(message: str, history: list | None, lang: str) -> str:
    # Prefer assistance-mode fork over auto-search on a fresh find.
    if needs_assistance_mode_choice(message, history):
        if lang == "es":
            return (
                "FLUJO ACTIVO — BUSCAR (elegir modo primero):\n"
                "Pregunta si quieres que Nouri lo haga TODO en el chat, o te "
                "guíe paso a paso en Find Food. NO llames search_food_near_user aún."
            )
        return (
            "ACTIVE FLOW — FIND FOOD (choose mode first):\n"
            "Ask whether they want Nouri to handle everything in chat, or "
            "guide them step by step on Find Food. Do NOT call "
            "search_food_near_user yet."
        )

    mode = resolve_assistance_mode(message, history)
    if mode == "guided":
        if lang == "es":
            return (
                "FLUJO ACTIVO — BUSCAR (modo guiado):\n"
                "Abre Find Food con navigate_ui (target=list) y explica los "
                "pasos. No busques ni reclames en el chat a menos que lo pidan."
            )
        return (
            "ACTIVE FLOW — FIND FOOD (guided):\n"
            "Open Find Food via navigate_ui (target=list) and coach the steps. "
            "Do not search/claim in chat unless they ask you to take over."
        )

    blob_l = _history_blob(history, message, 8).lower()
    searched = any(k in blob_l for k in (
        "found ", "near you", "here's what's", "opciones", "cerca de ti",
    ))
    clear_stuck = _user_clears_claim_flow(message) or _user_wants_fresh_search(message)
    if lang == "es":
        if not searched or _is_distress(message) or clear_stuck:
            return (
                "FLUJO ACTIVO — BUSCAR COMIDA:\n"
                "Reconoce con calidez, llama search_food_near_user EN ESTE turno. "
                "NO digas que hay un reclamo en progreso — el usuario está buscando "
                "comida (o negó un reclamo fantasma). "
                "NO repitas la lista en texto — las tarjetas abajo muestran las "
                "opciones. UNA frase + 'Elige un número abajo'."
            )
        return (
            "FLUJO ACTIVO — ELEGIR COMIDA:\n"
            "El usuario elige de la lista. UNA pregunta: confirmar cuál listing (#). "
            "Después de elegir, pregunta cuántos quieren de ESE listing antes de "
            "claim_listing. Nunca sumes cantidades de listings con el mismo nombre."
        )
    if not searched or _is_distress(message) or clear_stuck:
        return (
            "ACTIVE FLOW — FIND FOOD:\n"
            "Acknowledge warmly, call search_food_near_user THIS turn. "
            "If they named MULTIPLE foods (e.g. 'pawpaw and carrots'), pass "
            "title_query with ALL of them comma-separated so none get dropped. "
            "Do NOT say a claim is in progress — the user is looking for food "
            "(or just denied a phantom claim). "
            "In your reply name each matched food with quantity + pickup address "
            "from the tool/cards. Do NOT invent missing foods. "
            "ONE warm sentence (or two if multi-match) + 'Pick a number below'."
        )
    return (
        "ACTIVE FLOW — PICK FOOD:\n"
        "User is choosing from search results. ONE question: confirm which "
        "listing (#). After they pick, ask how many they want from THAT listing "
        "before claim_listing. Never sum quantities across listings with the same title."
    )


def _request_checklist(message: str, history: list | None, lang: str) -> str:
    if needs_assistance_mode_choice(message, history):
        if lang == "es":
            return (
                "FLUJO ACTIVO — SOLICITAR (elegir modo primero):\n"
                "Pregunta si quieres que Nouri publique la solicitud TODO en el chat, "
                "o te guíe paso a paso en Request Food. NO llames post_food_request aún."
            )
        return (
            "ACTIVE FLOW — REQUEST FOOD (choose mode first):\n"
            "Ask whether they want Nouri to post the request in chat, or "
            "guide them step by step on Request Food. Do NOT call "
            "post_food_request yet."
        )
    mode = resolve_assistance_mode(message, history)
    if mode == "guided":
        if lang == "es":
            return (
                "FLUJO ACTIVO — SOLICITAR (modo guiado):\n"
                "Abre Request Food con navigate_ui (target=request) y explica los "
                "pasos. No publiques en el chat a menos que lo pidan."
            )
        return (
            "ACTIVE FLOW — REQUEST FOOD (guided):\n"
            "Open Request Food via navigate_ui (target=request) and coach the steps. "
            "Do not post in chat unless they ask you to take over."
        )
    if lang == "es":
        return (
            "FLUJO ACTIVO — SOLICITUD EXPLÍCITA:\n"
            "Pregunta solo lo que falte (qué necesita, cantidad, comunidad) y "
            "llama post_food_request. Si solo buscan comida disponible, usa "
            "search_food_near_user en su lugar."
        )
    return (
        "ACTIVE FLOW — EXPLICIT REQUEST:\n"
        "Ask only what's missing (what they need, quantity, community) then "
        "call post_food_request. If they're just looking for available food, "
        "use search_food_near_user instead."
    )


def natural_rhythm_prompt(lang: str = "en") -> str:
    """Universal conversational rhythm — safe to inject on any multi-turn chat."""
    return _natural_rhythm(lang)


def build_turn_reminder(
    message: str,
    history: list | None,
    lang: str = "en",
    user_id: str = "",
) -> tuple[Optional[str], FlowKind]:
    """Build per-turn natural-flow injection and return (prompt, flow_kind)."""
    flow = detect_conversation_flow(message, history)
    if flow == "idle":
        return None, flow

    parts = [_natural_rhythm(lang)]
    if flow == "posting":
        parts.append(_posting_checklist(message, history, lang))
    elif flow == "claiming":
        parts.append(_claim_checklist(lang))
    elif flow == "finding":
        parts.append(_finding_checklist(message, history, lang))
        avail = build_availability_answer_reminder(
            message, history, lang=lang, user_id=user_id,
        )
        if avail:
            parts.append(avail)
    elif flow == "requesting":
        parts.append(_request_checklist(message, history, lang))

    return "\n\n".join(parts), flow


def build_fresh_search_after_claim_reminder(
    message: str,
    history: list | None,
    lang: str = "en",
) -> str | None:
    """After a completed claim, nudge a fresh search when user wants more food."""
    if not is_finding_flow(message, history):
        return None
    last = _last_assistant_text(history)
    if not last or not any(k in last for k in _CLAIM_SUCCESS_MARKERS):
        return None
    if lang == "es":
        return (
            "RECLAMO ANTERIOR COMPLETADO: el usuario quiere más comida. "
            "Llama search_food_near_user EN ESTE turno. No digas que hay un "
            "reclamo en progreso ni pidas confirmar el anterior."
        )
    return (
        "PRIOR CLAIM COMPLETE: the user wants available food now. "
        "Call search_food_near_user THIS turn. Do NOT say a claim is in "
        "progress or ask them to finish the previous one."
    )


def build_last_search_snapshot_reminder(
    user_id: str,
    lang: str = "en",
) -> str | None:
    """Inject the last search results so the model can see listing qty/titles."""
    listings = get_last_search_listings(user_id)
    if not listings:
        return None
    lines: list[str] = []
    for row in listings[:12]:
        idx = row.get("display_index") or "?"
        title = row.get("title") or "Unknown"
        qty = row.get("quantity")
        unit = (row.get("unit") or "").strip()
        lid = row.get("id") or ""
        addr = (row.get("address") or "").strip()
        community = (row.get("community_name") or "").strip()
        if qty is not None:
            qty_str = f"{qty} {unit}".strip()
        else:
            qty_str = "quantity unknown"
        place = addr or community or "address unknown"
        if community and addr and community.lower() not in addr.lower():
            place = f"{addr} ({community})"
        elif community and not addr:
            place = community
        lines.append(
            f"  #{idx}: {title} — {qty_str} available — pickup: {place} "
            f"(listing_id={lid})"
        )
    if lang == "es":
        header = (
            "LISTADOS VISIBLES (última búsqueda — el usuario los ve como tarjetas):\n"
            "Usa estos números, cantidades y direcciones para responder. "
            "Si el usuario pidió varias comidas, nombra CADA una que aparezca aquí."
        )
    else:
        header = (
            "VISIBLE LISTINGS (last search — user sees these as cards below):\n"
            "Use these numbers, quantities, and pickup addresses when answering. "
            "If the user asked for multiple foods, name EACH one that appears here — "
            "never say a food is missing when it is listed below. "
            "If a claim completed since this search, run search_food_near_user again "
            "before quoting quantities."
        )
    return header + "\n" + "\n".join(lines)


def build_availability_answer_reminder(
    message: str,
    history: list | None,
    lang: str = "en",
    user_id: str = "",
) -> str | None:
    """When user asks how much/many is left, answer from search cache — don't claim."""
    if not _user_asking_availability(message):
        return None
    listings = get_last_search_listings(user_id) if user_id else []
    hint = _mentioned_food_hint_from_message(message)
    if hint and listings:
        matches = [
            row for row in listings
            if hint in str(row.get("title") or "").lower()
            or hint in {
                w for w in re.findall(r"[a-z']+", str(row.get("title") or "").lower())
            }
        ]
        if matches:
            row = matches[0]
            qty = row.get("quantity")
            unit = (row.get("unit") or "").strip()
            title = row.get("title") or hint
            idx = row.get("display_index") or "?"
            qty_str = f"{qty} {unit}".strip() if qty is not None else "an unknown amount"
            if lang == "es":
                return (
                    f"PREGUNTA DE DISPONIBILIDAD: responde SOLO con el número — "
                    f"#{idx} {title} tiene {qty_str} disponible. "
                    "NO llames claim_listing. NO pidas disculpas por confusión."
                )
            return (
                f"AVAILABILITY QUESTION: answer with the number ONLY — "
                f"#{idx} {title} has {qty_str} available. "
                "Do NOT call claim_listing. Do NOT apologize for confusion."
            )
    if lang == "es":
        return (
            "PREGUNTA DE DISPONIBILIDAD: lee las cantidades de los listados "
            "visibles arriba y responde con el número exacto. NO reclames nada "
            "en este turno. Si acabas de reclamar algo o las cantidades pueden "
            "haber cambiado, llama search_food_near_user de nuevo primero."
        )
    return (
        "AVAILABILITY QUESTION: read quantities from the visible listings above "
        "and answer with the exact number. Do NOT claim anything this turn. "
        "If a claim just completed or quantities may have changed, call "
        "search_food_near_user again first for live numbers."
    )


# Back-compat alias used by tests
def posting_flow_reminder(
    message: str, history: list | None, lang: str = "en",
) -> str | None:
    prompt, flow = build_turn_reminder(message, history, lang)
    return prompt if flow == "posting" else None


# ---------------------------------------------------------------------------
# Typo / unclear-input detection — ask user to confirm before acting
# ---------------------------------------------------------------------------

_KNOWN_TYPOS: dict[str, str] = {
    "iam": "I am", "im": "I'm", "ive": "I've", "idk": "I don't know",
    "bred": "bread", "brad": "bread", "appels": "apples", "aplles": "apples",
    "banans": "bananas", "bananss": "bananas", "doughter": "daughter",
    "desparate": "desperate", "desparat": "desperate", "alergin": "allergic",
    "alergic": "allergic", "vigan": "vegan", "veagn": "vegan", "hambre": "hungry",
    "hungy": "hungry", "starvingg": "starving", "comunity": "community",
    "communtiy": "community", "adress": "address", "addres": "address",
    "pickup": "pickup", "picup": "pickup", "loav": "loaf", "loafs": "loaves",
    "clame": "claim", "clam": "claim", "reclamar": "claim", "pubish": "publish",
    "postt": "post", "shre": "share", "donte": "donate",
}

_FOOD_WORDS: frozenset[str] = frozenset({
    "bread", "apple", "apples", "banana", "bananas", "milk", "eggs", "rice",
    "pasta", "soup", "salad", "vegetables", "produce", "chicken", "beef",
    "fish", "cheese", "yogurt", "cereal", "beans", "tomatoes", "tomato",
    "potatoes", "potato", "onions", "onion", "carrots", "carrot",
    "lettuce", "kale", "berries", "fruit", "snacks",
    "loaf", "loaves", "tray", "trays", "box", "boxes", "bag", "bags",
    "basket", "baskets", "sack", "sacks",
    "orange", "oranges", "milk", "butter", "cream", "juice", "water",
    "spinach", "broccoli", "cabbage", "corn", "peas", "lentils", "oats",
    "flour", "sugar", "honey", "jam", "nuts", "almonds", "peanut", "peanuts",
    # Tropical / less-common produce — users ask by name; must not be dropped
    # when paired with a lexicon food (e.g. "pawpaw and carrots").
    "pawpaw", "pawpaws", "papaya", "papayas", "mango", "mangoes", "mangos",
    "avocado", "avocados", "cucumber", "cucumbers", "pepper", "peppers",
    "celery", "zucchini", "squash", "pumpkin", "garlic", "ginger",
})

# Stopwords when extracting free-form food pairs ("want X and Y").
_FOOD_EXTRACT_STOP: frozenset[str] = frozenset({
    "i", "a", "an", "the", "and", "or", "to", "for", "of", "in", "on", "at",
    "my", "me", "near", "you", "your", "some", "any", "want", "need", "like",
    "find", "looking", "search", "get", "grab", "take", "claim", "please",
    "both", "also", "just", "food", "something", "things", "items", "extra",
    "available", "address", "right", "now", "today", "nearby", "around",
    "here", "there", "this", "that", "with", "without", "from", "into",
})


def _mentioned_foods_from_message(message: str) -> list[str]:
    """All distinct foods the user asked for (supports 'pawpaw and carrots')."""
    t = (message or "").strip().lower()
    if not t:
        return []
    found: list[str] = []
    seen: set[str] = set()

    def _add(token: str) -> None:
        w = (token or "").strip().lower()
        if not w or w in _FOOD_EXTRACT_STOP or len(w) < 3:
            return
        # Prefer singular-ish key for carrots/carrot
        key = w
        if key not in seen:
            seen.add(key)
            found.append(key)

    for w in re.findall(r"[a-zA-Z']+", t):
        if w in _FOOD_WORDS:
            _add(w)

    # Free-form "X and Y" / "X, Y" pairs so unknown fruit names still count.
    for m in re.finditer(
        r"\b([a-z']{3,})\s*(?:,|&|and|/)\s*([a-z']{3,})\b",
        t,
    ):
        _add(m.group(1))
        _add(m.group(2))

    # "looking for X" / "want some X" single trailing nouns already covered
    # by lexicon; keep order stable.
    return found


def _mentioned_food_hint_from_message(message: str) -> Optional[str]:
    """Best-guess single food noun (first of any multi-food ask)."""
    intent = _extract_claim_intent(message)
    if intent.get("title_hint"):
        return intent["title_hint"]
    foods = _mentioned_foods_from_message(message)
    return foods[0] if foods else None


def enrich_search_food_args(
    args: dict,
    message: str,
    history: list | None = None,
) -> dict:
    """Ensure multi-food asks become an OR title_query, not a single token.

    Bug: 'I want pawpaw and carrots' + model title_query='pawpaw' dropped
    carrot listings from the tool payload even when they existed nearby.
    """
    out = dict(args or {})
    foods = _mentioned_foods_from_message(message or "")
    raw_tq = out.get("title_query") or out.get("title")
    if isinstance(raw_tq, str):
        raw_tq = raw_tq.strip() or None
    else:
        raw_tq = None

    if len(foods) >= 2:
        # Always OR across every food the user named this turn.
        out["title_query"] = ", ".join(foods)
        out["_multi_food_search"] = True
        out["_requested_foods"] = foods
    elif len(foods) == 1 and not raw_tq:
        out["title_query"] = foods[0]
        out["_requested_foods"] = foods
    elif raw_tq and foods:
        # Merge model hint with any extras from the message.
        from backend.tools import split_title_query_hints
        hints = list(dict.fromkeys(
            split_title_query_hints(raw_tq) + foods
        ))
        if len(hints) >= 2:
            out["title_query"] = ", ".join(hints)
            out["_multi_food_search"] = True
            out["_requested_foods"] = hints
    return out

# Common words that must never be flagged as garbled (e.g. "hungry" ends in -ngry).
_SAFE_WORDS: frozenset[str] = frozenset({
    "hungry", "food", "need", "some", "near", "help", "share", "find", "want",
    "have", "extra", "family", "please", "thanks", "hello", "today", "tomorrow",
    "pickup", "delivery", "community", "school", "address", "photo", "claim",
    "bread", "apples", "bananas", "hungry", "starving", "daughter", "desperate",
})


def _tokenize_words(message: str) -> list[str]:
    return re.findall(r"[a-zA-Z#']+", (message or "").lower())


def _is_garbled_token(word: str) -> bool:
    w = re.sub(r"[^a-z]", "", word.lower())
    if len(w) < 4 or w in _SAFE_WORDS:
        return False
    if re.search(r"(.)\1{2,}", w):
        return True
    # Treat y as vowel — avoids false positives on hungry, berry, etc.
    if re.search(r"[^aeiouy]{4,}", w):
        return True
    return False


def _fuzzy_food_typo(word: str) -> str | None:
    w = re.sub(r"[^a-z]", "", word.lower())
    if len(w) < 4 or w in _FOOD_WORDS or w in _KNOWN_TYPOS:
        return None
    matches = difflib.get_close_matches(w, sorted(_FOOD_WORDS), n=1, cutoff=0.78)
    if matches and matches[0] != w:
        return matches[0]
    return None


def assess_input_clarity(message: str, history: list | None = None) -> dict:
    """Return clarity signals for typo / misread confirmation."""
    text = (message or "").strip()
    t_lower = text.lower()
    flow = detect_conversation_flow(message, history)
    in_flow = flow != "idle"

    if not text or len(text) > 280:
        return {"unclear": False, "typo_hits": [], "flow": flow}

    if t_lower in _CLEAR_SHORT_REPLIES or re.fullmatch(r"#?\d{1,2}", t_lower):
        return {"unclear": False, "typo_hits": [], "flow": flow}

    typo_hits: list[dict] = []
    for word in _tokenize_words(text):
        clean = re.sub(r"[^a-z]", "", word.lower())
        if not clean:
            continue
        if clean in _KNOWN_TYPOS:
            typo_hits.append({"token": word, "guess": _KNOWN_TYPOS[clean]})
            continue
        guess = _fuzzy_food_typo(word)
        if guess:
            typo_hits.append({"token": word, "guess": guess})
            continue
        if _is_garbled_token(word):
            typo_hits.append({"token": word, "guess": None})

    # Only unclear when we have a concrete typo guess OR truly garbled unknown token
    actionable = [h for h in typo_hits if h.get("guess") or (
        h.get("guess") is None
        and re.sub(r"[^a-z]", "", h["token"].lower()) not in _SAFE_WORDS
    )]
    unclear = bool(actionable) or (
        in_flow and len(text.split()) == 1 and _is_garbled_token(text)
    )
    return {"unclear": unclear, "typo_hits": actionable, "flow": flow}


def build_typo_confirm_reminder(
    message: str,
    history: list | None,
    lang: str = "en",
) -> str | None:
    """Per-turn injection when input may be mistyped — confirm before acting."""
    assessment = assess_input_clarity(message, history)
    if not assessment["unclear"]:
        return None

    hits = assessment["typo_hits"]
    guesses = [f"'{h['token']}' → '{h['guess']}'" for h in hits if h.get("guess")]
    guess_line = ", ".join(guesses[:3]) if guesses else ""
    is_distress = _is_distress(message) or assessment.get("flow") == "finding"

    if lang == "es":
        base = (
            "POSIBLE ERROR DE ESCRITURA (este turno):\n"
        )
        if is_distress:
            base += (
                "Confirma el typo en UNA frase breve al inicio ('¿Quisiste decir …?'), "
                "pero si expresan hambre real, llama search_food_near_user EN ESTE turno "
                "igual — no los hagas esperar.\n"
            )
        else:
            base += (
                "NO publiques, reclames ni cambies datos hasta confirmar.\n"
            )
        base += (
            "Pregunta con calidez: '¿Quisiste decir …?' Cita sus palabras y tu "
            "mejor interpretación."
        )
        if guess_line:
            base += f"\nPosibles correcciones: {guess_line}."
        return base

    base = "POSSIBLE MISSPELLING / UNCLEAR INPUT (this turn):\n"
    if is_distress:
        base += (
            "Open with ONE brief spelling check ('Just to make sure — did you mean …?') "
            "if you see a typo, but if they express real hunger still call "
            "search_food_near_user THIS turn — do not delay help.\n"
        )
    else:
        base += (
            "Do NOT call write tools (post, claim, update) until they confirm.\n"
            "Ask ONE warm confirmation: 'Just to make sure I caught that — did you mean …?'\n"
        )
    base += (
        "Quote their words and your best guess. If still unsure, ask them "
        "to rephrase briefly."
    )
    if guess_line:
        base += f"\nLikely fixes: {guess_line}."
    return base


def build_ambiguous_pick_reminder(
    message: str,
    history: list | None,
    lang: str = "en",
    user_id: str = "",
) -> str | None:
    """When user picks multiple listings at once, queue them for multi-claim."""
    if not _looks_like_multi_option_pick(message) and "both" not in (message or "").lower():
        return None
    if not (_assistant_expects_flow_reply(history) or _recent_search_context(history)):
        return None
    if user_id:
        drafts = sync_claim_drafts(str(user_id), message, history)
        if len(drafts) >= 2:
            return build_claim_drafts_reminder(str(user_id), message, history, lang=lang)
    if lang == "es":
        return (
            "SELECCIÓN MÚLTIPLE (este turno):\n"
            "El usuario eligió más de una opción. Trata cada una como un "
            "borrador de reclamo: pregunta cantidades que falten UNA por "
            "turno, luego llama claim_listings."
        )
    return (
        "MULTI-PICK (this turn):\n"
        "The user referenced multiple options. Queue each as a claim draft, "
        "confirm briefly if needed, ask any missing quantities ONE at a time, "
        "then call claim_listings."
    )


# ---------------------------------------------------------------------------
# Last search cache + claim_listing id resolution (display # → UUID)
# ---------------------------------------------------------------------------

_last_search_by_user: dict[str, list[dict]] = {}
_last_donor_listings_by_user: dict[str, list[dict]] = {}
# Listing UUIDs from the most recent CSV / bulk create (chat confirm UI or
# post_food_listings). Used when the donor says "delete the bulk listings".
_last_bulk_posted_by_user: dict[str, list[str]] = {}
_last_write_action_by_user: dict[str, dict] = {}


def set_last_search_listings(user_id: str, listings: list[dict]) -> None:
    uid = str(user_id or "")
    _last_search_by_user[uid] = list(listings or [])
    # Fresh search results invalidate an unfinished multi-claim queue —
    # otherwise leftover drafts force claim_listings forever.
    _claim_drafts_by_user.pop(uid, None)


def get_last_search_listings(user_id: str) -> list[dict]:
    return _last_search_by_user.get(str(user_id), [])


def clear_last_search_listings(user_id: str) -> None:
    """Drop stale search cache (phantom claim / fresh-find pivot)."""
    _last_search_by_user.pop(str(user_id or ""), None)


def update_last_search_listing_after_claim(
    user_id: str,
    listing_id: str,
    remaining: Optional[float] = None,
    *,
    fully_claimed: bool = False,
) -> None:
    """Keep the search cache in sync after a claim so qty answers stay accurate."""
    uid = str(user_id or "")
    lid = str(listing_id or "")
    if not uid or not lid:
        return
    rows = list(_last_search_by_user.get(uid) or [])
    if not rows:
        return
    updated: list[dict] = []
    for row in rows:
        if str(row.get("id") or "") != lid:
            updated.append(row)
            continue
        if fully_claimed or (remaining is not None and remaining <= 0):
            continue
        copy = dict(row)
        if remaining is not None:
            copy["quantity"] = remaining
        updated.append(copy)
    for i, row in enumerate(updated, start=1):
        row["display_index"] = i
    _last_search_by_user[uid] = updated


def clear_last_search_listings(user_id: str) -> None:
    _last_search_by_user.pop(str(user_id or ""), None)


def set_last_donor_listings(user_id: str, listings: list[dict]) -> None:
    rows = []
    for i, row in enumerate(listings or [], start=1):
        copy = dict(row)
        copy.setdefault("display_index", i)
        rows.append(copy)
    _last_donor_listings_by_user[str(user_id)] = rows


def get_last_donor_listings(user_id: str) -> list[dict]:
    return _last_donor_listings_by_user.get(str(user_id), [])


def set_last_bulk_posted_ids(user_id: str, listing_ids: list) -> None:
    """Remember UUIDs created by the latest bulk/CSV import for this user."""
    cleaned = [
        str(x).strip() for x in (listing_ids or [])
        if x is not None and str(x).strip()
    ]
    if cleaned:
        _last_bulk_posted_by_user[str(user_id)] = cleaned


def get_last_bulk_posted_ids(user_id: str) -> list[str]:
    return list(_last_bulk_posted_by_user.get(str(user_id), []))


def clear_last_bulk_posted_ids(user_id: str) -> None:
    _last_bulk_posted_by_user.pop(str(user_id), None)


# ---------------------------------------------------------------------------
# Repeat-last-action — "and to this too" / "same for #2"
# ---------------------------------------------------------------------------

REPEATABLE_WRITE_TOOLS: frozenset[str] = frozenset({
    "update_food_listing",
    "update_listing",
    "edit_listing",
    "deactivate_listing",
    "delete_listing",
    "claim_listing",
    "claim_food",
    "attach_photos_to_listing",
})

AUTO_REPEAT_TOOLS: frozenset[str] = frozenset({
    "update_food_listing",
    "update_listing",
    "edit_listing",
    "deactivate_listing",
    "claim_listing",
    "claim_food",
    "attach_photos_to_listing",
})

_REPEAT_FOLLOWUP_KEYS = (
    "and to this too", "and this too", "this one too", "that one too",
    "and that too", "do the same", "same for", "same thing", "apply to",
    "also for", "also to", "for this one too", "for that one too",
    "and for ", "y tambien", "y también", "tambien para", "también para",
    "lo mismo para", "igual para", "haz lo mismo", "same community",
    "same change", "do that too", "that too",
)

_REPEAT_FOLLOWUP_RE = re.compile(
    r"(?:"
    r"and\s+(?:to\s+)?(?:this|that)(?:\s+one)?\s+too|"
    r"(?:this|that)\s+one\s+too|"
    r"same\s+(?:for|thing|change|community)|"
    r"do\s+(?:the\s+)?same|"
    r"also\s+(?:for|to|apply)|"
    r"apply\s+(?:that|it|this)\s+to|"
    r"and\s+(?:for\s+)?#?\d{1,2}|"
    r"y\s+tambi[eé]n|tambi[eé]n\s+(?:para|a)|"
    r"lo\s+mismo\s+para|igual\s+para"
    r")",
    re.I,
)


def set_last_write_action(
    user_id: str,
    tool: str,
    args: dict,
    result: dict | None = None,
) -> None:
    """Remember the last successful write so 'and this too' can replay it."""
    if tool not in REPEATABLE_WRITE_TOOLS:
        return
    template = {
        k: v for k, v in (args or {}).items()
        if k not in {"user_id", "confirmed", "_resolve_error", "_bulk_delete_count"}
        and v is not None
    }
    template.pop("listing_id", None)
    template.pop("listing_ids", None)
    template.pop("title_lookup", None)
    listing_id = None
    if isinstance(result, dict):
        listing_id = result.get("listing_id")
    listing_id = listing_id or (args or {}).get("listing_id")
    _last_write_action_by_user[str(user_id)] = {
        "tool": tool,
        "args": template,
        "listing_id": str(listing_id) if listing_id else None,
    }


def get_last_write_action(user_id: str) -> dict | None:
    return _last_write_action_by_user.get(str(user_id))


def _recent_write_in_history(history: list | None) -> bool:
    if not history:
        return False
    write_words = (
        "updated", "posted", "deleted", "claimed", "removed", "changed",
        "actualizado", "publicado", "eliminado", "reclamado", "cambiado",
    )
    for msg in reversed(history[-6:]):
        if msg.get("role") != "assistant":
            continue
        text = (msg.get("message") or "").lower()
        if any(w in text for w in write_words):
            return True
    return False


def is_repeat_followup(message: str, history: list | None = None) -> bool:
    """True when the user wants the same action applied to another target."""
    t = (message or "").strip().lower()
    if not t:
        return False
    if any(k in t for k in _REPEAT_FOLLOWUP_KEYS):
        return True
    if _REPEAT_FOLLOWUP_RE.search(t):
        return True
    if re.search(r"\b(?:and|also)\s+.+\s+too\b", t):
        return True
    if re.search(r"\b\w+\s+one\s+too\b", t):
        return True
    if len(t.split()) <= 5 and _recent_write_in_history(history):
        if re.search(r"#?\d{1,2}", t) or any(w in t for w in ("this", "that", "too", "also", "same")):
            return True
    return False


def _resolve_repeat_target_listing(
    message: str,
    history: list | None,
    user_id: str,
    exclude_listing_id: str | None = None,
) -> Optional[str]:
    """Pick a listing id for 'and this too' — must differ from exclude."""
    exclude = str(exclude_listing_id or "").strip()

    picked = _resolve_update_listing_from_message(message, history, user_id)
    if picked and picked != exclude:
        return picked

    current = (message or "").strip().lower()
    for msg in reversed(history or []):
        if msg.get("role") != "user":
            continue
        text = (msg.get("message") or "").strip()
        if text.lower() == current:
            continue
        picked = _resolve_update_listing_from_message(text, history, user_id)
        if picked and picked != exclude:
            return picked
        if text:
            break

    blob = _history_blob(history, message, limit=6).lower()
    for row in get_last_donor_listings(user_id):
        lid = str(row.get("id") or "")
        if not lid or lid == exclude:
            continue
        title = str(row.get("title") or "").lower()
        if title and len(title) >= 3 and title in blob:
            return lid

    for row in get_last_search_listings(user_id):
        lid = str(row.get("id") or "")
        if not lid or lid == exclude:
            continue
        title = str(row.get("title") or "").lower()
        if title and len(title) >= 3 and title in blob:
            return lid

    return None


def enrich_repeat_write_action(
    tool_name: str,
    args: dict,
    message: str,
    history: list | None,
    user_id: str,
) -> dict:
    """Replay the last write action's fields onto a new target listing."""
    if tool_name not in REPEATABLE_WRITE_TOOLS:
        return dict(args or {})
    if not is_repeat_followup(message, history):
        return dict(args or {})

    last = get_last_write_action(user_id)
    if not last:
        return dict(args or {})

    canonical = {
        "update_listing": "update_food_listing",
        "edit_listing": "update_food_listing",
        "claim_food": "claim_listing",
    }
    last_tool = canonical.get(last.get("tool"), last.get("tool"))
    this_tool = canonical.get(tool_name, tool_name)
    if last_tool != this_tool:
        return dict(args or {})

    out = dict(args or {})
    for key, val in (last.get("args") or {}).items():
        if val is not None and out.get(key) is None:
            out[key] = val

    exclude = last.get("listing_id")
    if this_tool in {"update_food_listing", "deactivate_listing", "delete_listing"}:
        if not out.get("listing_id"):
            target = _resolve_repeat_target_listing(
                message, history, user_id, exclude_listing_id=exclude,
            )
            if target:
                out["listing_id"] = target
        elif str(out.get("listing_id")) == str(exclude):
            target = _resolve_repeat_target_listing(
                message, history, user_id, exclude_listing_id=exclude,
            )
            if target:
                out["listing_id"] = target

    if this_tool in {"claim_listing", "claim_food"} and not out.get("listing_id"):
        target = _resolve_repeat_target_listing(
            message, history, user_id, exclude_listing_id=exclude,
        )
        if target:
            out["listing_id"] = target

    return out


def build_repeat_action_reminder(
    message: str,
    history: list | None,
    user_id: str,
    lang: str = "en",
) -> str | None:
    """Nudge the model to call a write tool, not text-only success."""
    if not is_repeat_followup(message, history):
        return None
    last = get_last_write_action(user_id)
    if not last:
        return None

    fields = ", ".join(sorted((last.get("args") or {}).keys())[:6]) or "same fields"
    if lang == "es":
        return (
            "REPETIR ACCIÓN (este turno — CRÍTICO):\n"
            "El usuario quiere la MISMA acción en OTRO listado/objetivo. "
            f"Última acción: {last.get('tool')} ({fields}). "
            "Llama esa herramienta ESTE turno con un listing_id DIFERENTE. "
            "NO digas que ya está hecho sin un resultado de herramienta exitoso."
        )
    return (
        "REPEAT ACTION (this turn — CRITICAL):\n"
        "The user wants the SAME change on a DIFFERENT listing/target. "
        f"Last action: {last.get('tool')} ({fields}). "
        "Call that tool THIS turn with a different listing_id. "
        "Do NOT say it is done without a successful tool result."
    )


def resolve_listing_id_from_search(
    raw_id,
    user_id: str,
) -> tuple[Optional[str], Optional[str]]:
    """Map display index (1-N) or UUID string to a listing id."""
    listings = get_last_search_listings(user_id)
    if raw_id is None:
        return None, "missing listing_id"
    s = str(raw_id).strip()
    if re.match(r"^[0-9a-f-]{36}$", s, re.I):
        return s, None
    try:
        idx = int(s)
    except (TypeError, ValueError):
        return None, (
            f"Invalid listing_id {raw_id!r}. Use the list number 1–{len(listings)} "
            "from the search cards, or the food name."
        )
    if idx < 1 or idx > len(listings):
        return None, (
            f"List number {idx} is out of range (1–{len(listings)}). "
            "Run search_food_near_user again."
        )
    resolved = listings[idx - 1].get("id")
    if not resolved:
        return None, "Could not resolve listing from search index."
    return str(resolved), None


def resolve_donor_listing_id(
    raw_id,
    user_id: str,
) -> tuple[Optional[str], Optional[str]]:
    """Map display index, full UUID, or truncated UUID to a donor listing id."""
    listings = get_last_donor_listings(user_id)
    if raw_id is None:
        return None, "missing listing_id"
    s = str(raw_id).strip()
    if re.match(r"^[0-9a-f-]{36}$", s, re.I):
        return s, None
    # Display index from get_user_listings (1–N). Accept up to 3 digits so
    # donors with large batches (CSV imports) can say "#47".
    if re.fullmatch(r"#?\d{1,3}", s):
        idx = int(s.lstrip("#"))
        if 1 <= idx <= len(listings):
            lid = listings[idx - 1].get("id")
            if lid:
                return str(lid), None
        return None, (
            f"List number {idx} is out of range (1–{len(listings)}). "
            "Call get_user_listings again."
        )
    if re.match(r"^[0-9a-f-]{8,}$", s, re.I):
        prefix = s.lower()
        matches = [
            str(row["id"])
            for row in listings
            if str(row.get("id") or "").lower().startswith(prefix)
        ]
        if len(matches) == 1:
            return matches[0], None
        if len(matches) > 1:
            return None, (
                "That listing id is ambiguous — ask which number from their list "
                "(1, 2, 3…) and retry with that number or the full id."
            )
    return None, (
        f"Invalid listing_id {raw_id!r}. Use the list number 1–{len(listings)} "
        "from get_user_listings, or the food title."
    )


_EDIT_LISTING_TRIGGERS = (
    "edit listing", "edit my listing", "update listing", "update my listing",
    "change listing", "change my listing", "rename", "change to", "change it to",
    "make it", "set quantity", "increase quantity", "decrease quantity",
    "editar", "actualizar", "cambiar", "renombrar",
)

_RENAME_TO_RE = re.compile(
    r"(?:change|rename|update|edit|switch|make)\s+(?:it|this|the listing)?\s*"
    r"(?:to|as)\s+['\"]?([a-z0-9][a-z0-9\s\-]{1,40})['\"]?",
    re.I,
)
_COMMUNITY_IN_DESC_RE = re.compile(r"community\s*:\s*([^.;,\n]+)", re.I)
_EXPIRY_IN_DESC_RE = re.compile(
    r"(?:expiry|expiration|best\s*by|expires?)\s*:\s*(\d{4}-\d{2}-\d{2})",
    re.I,
)
_EXPIRY_IN_MSG_RE = re.compile(
    r"(?:expiry|expiration|best\s*by|expires?(?:\s+on)?)\s*(?:to|is|=|:)?\s*"
    r"(\d{4}-\d{2}-\d{2}|\d{1,2}[/-]\d{1,2}[/-]\d{2,4})",
    re.I,
)


def _donor_listing_row(user_id: str, listing_id: str) -> Optional[dict]:
    lid = str(listing_id or "").strip()
    if not lid:
        return None
    for row in get_last_donor_listings(user_id):
        if str(row.get("id") or "") == lid:
            return row
    return None


def _looks_like_listing_edit(message: str) -> bool:
    t = (message or "").lower()
    return any(k in t for k in _EDIT_LISTING_TRIGGERS)


def _extract_update_quantity(message: str) -> Optional[float]:
    t = (message or "").strip().lower()
    if not t:
        return None
    m = re.search(
        r"(?:quantity|qty|amount|servings?|portions?)\s*(?:to|is|=|:)?\s*(\d{1,4}(?:\.\d+)?)",
        t,
    )
    if m:
        return float(m.group(1))
    m = re.search(
        r"(?:change|set|update|make)\s+(?:the\s+)?(?:quantity|qty|amount|servings?)\s+"
        r"(?:to|as)\s+(\d{1,4}(?:\.\d+)?)",
        t,
    )
    if m:
        return float(m.group(1))
    if _looks_like_listing_edit(t):
        m = re.search(r"\b(\d{1,4}(?:\.\d+)?)\b", t)
        if m and not re.search(r"\b#?\d{1,2}\b", t):
            return float(m.group(1))
    return None


def _extract_rename_title(message: str) -> Optional[str]:
    t = (message or "").strip()
    if not t:
        return None
    m = _RENAME_TO_RE.search(t)
    if m:
        candidate = m.group(1).strip(" .,!?:;\"'")
        if candidate and len(candidate) >= 2:
            return candidate[:200]
    return None


def _resolve_update_listing_from_message(
    message: str,
    history: list | None,
    user_id: str,
) -> Optional[str]:
    """Pick donor listing id from '#2', display index, title, or a food-noun.

    Robust to partial titles: 'update oranges add a photo' resolves to a
    'Fresh Oranges' listing via token overlap once the exact-title match
    misses.
    """
    blob = _history_blob(history, message, limit=12)
    text = (message or "").strip()
    listings = get_last_donor_listings(user_id)
    if not listings:
        return None

    m = re.search(r"(?:listing\s*)?#(\d{1,2})\b", text, re.I)
    if not m:
        m = re.search(r"\b(?:edit|update|change|delete|remove|deactivate)\s+#?(\d{1,2})\b", text, re.I)
    if m:
        idx = int(m.group(1))
        if 1 <= idx <= len(listings):
            lid = listings[idx - 1].get("id")
            if lid:
                return str(lid)

    if re.fullmatch(r"#?\d{1,2}", text.strip()):
        resolved, err = resolve_donor_listing_id(text.strip(), user_id)
        if resolved and not err:
            return resolved

    lower_blob = blob.lower()
    for row in listings:
        title = str(row.get("title") or "").strip()
        if title and len(title) >= 3 and title.lower() in lower_blob:
            lid = row.get("id")
            if lid:
                return str(lid)

    # Token-overlap fallback: 'update oranges add a photo' finds Fresh Oranges.
    blob_tokens = set(re.findall(r"[a-z']+", lower_blob))
    # Discard common connector words so the overlap is meaningful.
    stop = {
        "add", "a", "an", "the", "to", "my", "our", "photo", "picture", "image",
        "new", "update", "edit", "change", "please", "delete", "remove", "of",
        "for", "and", "with", "put", "attach", "upload",
    }
    blob_food_tokens = blob_tokens - stop
    if blob_food_tokens:
        best_id: Optional[str] = None
        best_score = 0.0
        for row in listings:
            title = str(row.get("title") or "").strip().lower()
            if not title:
                continue
            title_tokens = set(re.findall(r"[a-z']+", title))
            if not title_tokens:
                continue
            overlap = len(title_tokens & blob_food_tokens)
            if overlap == 0:
                continue
            score = overlap / max(len(title_tokens), 1)
            if score > best_score:
                best_score = score
                lid = row.get("id")
                if lid:
                    best_id = str(lid)
        if best_id and best_score >= 0.4:
            return best_id
    return None


def _unwrap_listing_metadata_from_args(args: dict) -> dict:
    """Move Community:/Expiry: blobs out of description into real tool fields."""
    out = dict(args or {})
    desc = str(out.get("description") or "").strip()
    if desc:
        comm_m = _COMMUNITY_IN_DESC_RE.search(desc)
        if comm_m and not out.get("community_name") and not out.get("community_id"):
            out["community_name"] = comm_m.group(1).strip()
        exp_m = _EXPIRY_IN_DESC_RE.search(desc)
        if exp_m and not out.get("expiry_date"):
            out["expiry_date"] = exp_m.group(1).strip()

        cleaned = desc
        cleaned = _COMMUNITY_IN_DESC_RE.sub("", cleaned)
        cleaned = _EXPIRY_IN_DESC_RE.sub("", cleaned)
        cleaned = re.sub(r"\s*[.;,\-–—]+\s*", " ", cleaned).strip(" .,;:-")
        if not cleaned or len(cleaned) < 3:
            out.pop("description", None)
        elif cleaned != desc:
            out["description"] = cleaned

    return out


def _extract_update_fields_from_message(message: str) -> dict:
    """Pull structured edit values from natural language."""
    out: dict = {}
    text = (message or "").strip()
    if not text:
        return out

    comm_m = _COMMUNITY_IN_MSG_RE.search(text)
    if comm_m:
        out["community_name"] = comm_m.group(1).strip(" .,;")

    exp_m = _EXPIRY_IN_MSG_RE.search(text)
    if exp_m:
        raw = exp_m.group(1).strip()
        if re.fullmatch(r"\d{4}-\d{2}-\d{2}", raw):
            out["expiry_date"] = raw
        else:
            from backend.tools import _normalize_expiry_date
            resolved = _normalize_expiry_date(raw)
            if resolved:
                out["expiry_date"] = resolved

    return out


_PHOTO_ADD_INTENT_PATTERNS = (
    r"\badd(?:ing|s)?\s+(?:a|an|another|one\s+more|new)?\s*photo\b",
    r"\badd(?:ing|s)?\s+(?:a|an|another|one\s+more|new)?\s*picture\b",
    r"\badd(?:ing|s)?\s+(?:a|an|another|one\s+more|new)?\s*image\b",
    r"\battach(?:ing|es)?\s+(?:a|an|another|new)?\s*(?:photo|picture|image)\b",
    r"\bupload(?:ing|s)?\s+(?:a|an|another|new)?\s*(?:photo|picture|image)\b",
    r"\bput\s+(?:a|an|another|new)?\s*(?:photo|picture|image)\b",
    r"\bnew\s+(?:photo|picture|image)\b",
    r"\bmore\s+(?:photos|pictures|images)\b",
    r"\bagregar\s+(?:una?|otra|nueva)?\s*(?:foto|imagen)\b",
    r"\badjuntar\s+(?:una?|otra|nueva)?\s*(?:foto|imagen)\b",
    r"\bsubir\s+(?:una?|otra|nueva)?\s*(?:foto|imagen)\b",
    r"\bponer\s+(?:una?|otra|nueva)?\s*(?:foto|imagen)\b",
    r"\bnueva\s+(?:foto|imagen)\b",
)

_PHOTO_ADD_INTENT_RE = re.compile("|".join(_PHOTO_ADD_INTENT_PATTERNS), re.IGNORECASE)


def _mentions_photo_add(text: str) -> bool:
    return bool(_PHOTO_ADD_INTENT_RE.search(text or ""))


def _resolve_donor_listing_by_food_token(
    message: str,
    history: list | None,
    user_id: str,
) -> Optional[str]:
    """Fuzzy match donor listings by any food-noun overlap with the message.

    Complements `_resolve_update_listing_from_message` (which needs the full
    title to appear in the blob) for cases like 'update oranges add a photo'
    where the donor referenced the food by a single word.
    """
    uid = str(user_id or "").strip()
    if not uid:
        return None
    listings = get_last_donor_listings(uid)
    if not listings:
        return None
    blob = _history_blob(history, message, limit=8).lower()
    if not blob:
        return None
    blob_tokens = set(re.findall(r"[a-z']+", blob))
    best_id: Optional[str] = None
    best_score = 0.0
    for row in listings:
        title = str(row.get("title") or "").strip().lower()
        if not title:
            continue
        title_tokens = set(re.findall(r"[a-z']+", title))
        if not title_tokens:
            continue
        overlap = len(title_tokens & blob_tokens)
        if overlap == 0:
            continue
        score = overlap / max(len(title_tokens), 1)
        # Also bump when the whole title matches literally.
        if title in blob:
            score = max(score, 1.0)
        if score > best_score:
            best_score = score
            lid = row.get("id")
            if lid:
                best_id = str(lid)
    if best_id and best_score >= 0.4:
        return best_id
    return None


def donor_photo_add_intent(
    message: str,
    history: list | None,
    user_id: str,
) -> Optional[dict]:
    """Detect 'update <listing> add a photo' style requests.

    Returns a dict with `listing_id` (best-resolved), `has_photo_url` (bool),
    and `photo_url` (str | None). Returns None when the message is not
    actually a photo-add intent for one of the user's own listings.
    """
    text = (message or "").strip()
    if not text or not _mentions_photo_add(text):
        return None

    uid = str(user_id or "").strip()
    listing_id: Optional[str] = None
    if uid:
        listing_id = _resolve_update_listing_from_message(message, history, uid)
        if not listing_id:
            listing_id = _resolve_donor_listing_by_food_token(
                message, history, uid,
            )
        if not listing_id:
            # Fall back to the last write action (most recent posted listing).
            recent = get_last_write_action(uid)
            if isinstance(recent, dict):
                cand = recent.get("listing_id") or recent.get("args", {}).get("listing_id")
                if cand:
                    listing_id = str(cand)
        if not listing_id:
            # Final fallback: if the donor only has one listing, use it.
            listings = get_last_donor_listings(uid)
            if len(listings) == 1:
                only = listings[0].get("id")
                if only:
                    listing_id = str(only)

    photo_url = _extract_photo_url_from_history(history, message)
    return {
        "listing_id": listing_id,
        "photo_url": photo_url,
        "has_photo_url": bool(photo_url),
    }


def update_photo_intent_block_reason(
    tool_name: str,
    args: dict | None,
    message: str,
    history: list | None,
    user_id: str,
) -> str | None:
    """Redirect update_food_listing → attach_photos_to_listing on photo intent.

    The update tool has a legacy single `image_url` field but the AI should
    prefer `attach_photos_to_listing` so we preserve any existing images.
    Also handles the case where the user says 'add a photo' but hasn't
    actually attached one yet — the model must ask, not fabricate.
    """
    if tool_name not in {"update_food_listing", "update_listing", "edit_listing"}:
        return None
    intent = donor_photo_add_intent(message, history, user_id)
    if not intent:
        return None
    args = args or {}
    if not intent.get("has_photo_url") and not args.get("image_url"):
        target = intent.get("listing_id") or "the listing"
        return (
            "The donor asked to add a photo but no image URL is in the chat "
            f"yet. Ask them to upload the photo now (it will appear as an "
            f"'image: /uploads/…' line), then call attach_photos_to_listing "
            f"with listing_id={target} and the new URL. Do NOT call "
            "update_food_listing for a photo add."
        )
    # Photo is available → route to attach_photos_to_listing.
    target = intent.get("listing_id") or "the listing"
    url = intent.get("photo_url") or args.get("image_url") or "the uploaded URL"
    return (
        "For adding photos to an existing listing, call "
        f"attach_photos_to_listing with listing_id={target} and images=[{url!r}] "
        "instead of update_food_listing. That keeps existing photos "
        "and de-dups new ones."
    )


_EDIT_INTENT_VERBS = (
    "edit", "update", "change", "rename", "fix", "correct", "modify",
    "set the", "make it", "adjust",
    "editar", "actualizar", "cambiar", "corregir", "modificar",
)


def update_new_share_block_reason(
    tool_name: str,
    args: dict | None,
    message: str,
    history: list | None,
    user_id: str,
) -> str | None:
    """Block update_food_listing when the donor is sharing a NEW item.

    Symptom this prevents: the model calls update_food_listing for a fresh
    'I want to share <new food>' turn, the enrich layer resolves listing_id to
    a recent listing via title/token overlap, and the existing listing gets
    OVERWRITTEN — so the original disappears and the new food "replaces" it.
    A brand-new food must go through post_food_listing (a new row).
    """
    if tool_name not in {"update_food_listing", "update_listing", "edit_listing"}:
        return None

    if not _is_fresh_share_intent(message):
        return None

    text = (message or "").lower()

    # Respect explicit edit intent — '#2', 'edit the apples', etc. are real edits.
    if re.search(r"#\d{1,2}\b", text):
        return None
    if any(v in text for v in _EDIT_INTENT_VERBS):
        return None

    # Adding a photo to an existing listing is handled elsewhere.
    if donor_photo_add_intent(message, history, user_id):
        return None

    return (
        "This turn is the donor sharing a NEW food item, not editing an "
        "existing one. Do NOT call update_food_listing — that would overwrite "
        "a previous listing and make it disappear. Call post_food_listing "
        "(or post_food_listings for 2+ items) to create a brand-new listing."
    )


def _normalize_update_food_listing_args(
    args: dict,
    message: str,
    user_id: str,
) -> dict:
    """Fix common model mistakes: title_lookup vs new title, stale title field."""
    out = dict(args or {})
    out = _unwrap_listing_metadata_from_args(out)
    for key, val in _extract_update_fields_from_message(message).items():
        out.setdefault(key, val)
    uid = str(user_id or "").strip()
    if not uid:
        return out

    if not out.get("listing_id"):
        picked = _resolve_update_listing_from_message(message, None, uid)
        if picked:
            out["listing_id"] = picked

    listing_id = str(out.get("listing_id") or "").strip()
    row = _donor_listing_row(uid, listing_id) if listing_id else None
    current_title = str((row or {}).get("title") or "").strip()
    title_lookup = str(out.get("title_lookup") or "").strip()
    new_title = str(out.get("title") or "").strip()

    rename_from_msg = _extract_rename_title(message)
    if rename_from_msg:
        out["title"] = rename_from_msg
        new_title = rename_from_msg

    if listing_id and title_lookup:
        tl = title_lookup.lower()
        cur = current_title.lower()
        if cur and tl != cur and tl not in cur:
            if not new_title or new_title.lower() == cur:
                out["title"] = title_lookup
                new_title = title_lookup
        out.pop("title_lookup", None)
    elif listing_id:
        out.pop("title_lookup", None)

    if listing_id and new_title and current_title:
        if new_title.lower() == current_title.lower():
            out.pop("title", None)

    if out.get("quantity") is None:
        qty = _extract_update_quantity(message)
        if qty is not None and qty > 0:
            out["quantity"] = qty

    return out


def _wants_delete_duplicates(message: str, history: list | None) -> bool:
    blob = _history_blob(history, message, limit=12).lower()
    keys = (
        "delete all duplicate", "delete the duplicate", "remove duplicate",
        "remove all duplicate", "delete duplicates", "remove duplicates",
        "eliminar duplicados", "borrar duplicados", "elimina duplicados",
        "borra duplicados", "quitar duplicados",
    )
    if any(k in blob for k in keys):
        return True
    if re.search(r"\b\d{1,3}\s+duplicate", blob):
        return True
    # "delete them all" only means duplicate-cleanup when duplicates were
    # mentioned — otherwise it is handled by delete_all (bulk wipe).
    return "duplicate" in blob and any(
        k in blob for k in (
            "delete all", "remove all", "delete them", "remove them",
            "delete them all", "delete all of them", "remove them all",
            "yes delete", "confirm delete", "yes, confirm", "eliminar todo",
            "borrar todo", "sí, confirmar", "si confirmar",
        )
    )


def _wants_delete_all_listings(message: str, history: list | None) -> bool:
    """True when the donor wants to wipe many / all / the last bulk batch."""
    if _wants_delete_duplicates(message, history):
        return False
    blob = _history_blob(history, message, limit=12).lower()
    keys = (
        "delete the bulk", "delete bulk listing", "delete bulk listings",
        "remove the bulk", "remove bulk listing", "remove bulk listings",
        "delete all my listing", "delete all listings", "delete all my food",
        "remove all my listing", "remove all listings", "remove all my food",
        "delete everything i posted", "delete everything i just",
        "delete everything i shared", "clear all my listing",
        "wipe my listing", "delete the csv", "delete csv listing",
        "undo the import", "undo the bulk", "delete those listings",
        "delete these listings", "remove those listings", "remove these listings",
        "delete them all", "delete all of them", "remove them all",
        "eliminar todas", "borrar todas", "elimina todas las publicaciones",
        "borrar el lote", "eliminar el lote",
    )
    if any(k in blob for k in keys):
        return True
    # Recent CSV / bulk confirm context + a broad delete ask.
    bulk_ctx = any(
        k in blob for k in (
            "csv", "spreadsheet", "bulk listing", "bulk import",
            "imported", "created ", "posted ", "listings from",
        )
    )
    if bulk_ctx and any(
        k in blob for k in (
            "delete all", "remove all", "delete them", "remove them",
            "yes delete", "confirm delete", "yes, confirm",
        )
    ):
        return True
    return False


def _resolve_listing_ids_list(raw_ids, user_id: str) -> tuple[list[str], Optional[str]]:
    """Map a mixed list of UUIDs / display indices to real listing UUIDs."""
    if not raw_ids:
        return [], None
    resolved: list[str] = []
    seen: set[str] = set()
    for raw in raw_ids:
        if raw is None:
            continue
        lid, err = resolve_donor_listing_id(raw, user_id)
        if not lid:
            # Already a full UUID even if not in the short cache — keep it.
            s = str(raw).strip()
            if re.match(r"^[0-9a-f-]{36}$", s, re.I):
                lid = s
            else:
                return [], err or f"Could not resolve listing_id {raw!r}."
        if lid not in seen:
            seen.add(lid)
            resolved.append(lid)
    return resolved, None


def enrich_donor_listing_tool_args(
    tool_name: str,
    args: dict,
    message: str,
    history: list | None,
    user_id: str,
) -> dict:
    """Resolve listing_id for delete / deactivate / update donor tools."""
    out = enrich_repeat_write_action(tool_name, args, message, history, user_id)
    uid = str(user_id or out.get("user_id") or "").strip()
    if not uid:
        return out

    raw_lid = out.get("listing_id")
    title = out.get("title")

    # Resolve any model-supplied listing_ids (often display indices like "1")
    # BEFORE branching into delete_all / delete_duplicates.
    if tool_name == "delete_listing" and out.get("listing_ids"):
        resolved_ids, resolve_err = _resolve_listing_ids_list(
            out.get("listing_ids"), uid,
        )
        if resolve_err:
            out["_resolve_error"] = resolve_err
            out.pop("listing_ids", None)
        else:
            out["listing_ids"] = resolved_ids
            out["_bulk_delete_count"] = len(resolved_ids)
            out.pop("listing_id", None)

    # Wipe last bulk batch or all active listings (CSV / "delete them all").
    if (
        tool_name == "delete_listing"
        and not out.get("listing_ids")
        and (
            out.get("delete_all")
            or _wants_delete_all_listings(message, history)
        )
    ):
        out["delete_all"] = True
        out.pop("listing_id", None)
        out.pop("delete_duplicates", None)
        bulk_ids = get_last_bulk_posted_ids(uid)
        if bulk_ids:
            out["listing_ids"] = list(bulk_ids)
            out["_bulk_delete_count"] = len(bulk_ids)
            out["_delete_scope"] = "last_bulk"
        else:
            donor_rows = get_last_donor_listings(uid)
            all_ids = [
                str(r["id"]) for r in donor_rows
                if r.get("id")
            ]
            if all_ids:
                out["listing_ids"] = all_ids
                out["_bulk_delete_count"] = len(all_ids)
                out["_delete_scope"] = "all_active"
            else:
                # Tool will fetch from Supabase; keep delete_all so confirm
                # summary + executor know the intent without inventing ids.
                out["_bulk_delete_count"] = out.get("_bulk_delete_count") or 0
                out["_delete_scope"] = "all_active"

    # Bulk duplicate cleanup (keeps one copy per title).
    elif tool_name == "delete_listing" and not out.get("listing_ids") and (
        out.get("delete_duplicates")
        or _wants_delete_duplicates(message, history)
    ):
        out["delete_duplicates"] = True
        out.pop("listing_id", None)
        from backend.tools import duplicate_listing_ids_to_remove

        donor_rows = get_last_donor_listings(uid)
        filter_title = out.get("title")
        remove_ids, meta = duplicate_listing_ids_to_remove(
            donor_rows, title=filter_title,
        )
        if remove_ids:
            out["listing_ids"] = remove_ids
            out["_bulk_delete_count"] = meta.get("to_delete", len(remove_ids))
        elif not out.get("_resolve_error"):
            out["_resolve_error"] = (
                "No duplicate listings found to delete. Call get_user_listings first."
            )
    elif raw_lid is not None and str(raw_lid).strip():
        resolved, err = resolve_donor_listing_id(raw_lid, uid)
        if resolved:
            out["listing_id"] = resolved
        elif err and not title:
            out["_resolve_error"] = err

    if tool_name != "delete_listing" or not out.get("listing_ids"):
        if not out.get("listing_id") and not title and not out.get("listing_ids"):
            blob = _history_blob(history, message, limit=10).lower()
            for row in get_last_donor_listings(uid):
                t = str(row.get("title") or "").lower()
                if t and len(t) >= 3 and t in blob:
                    out["listing_id"] = str(row["id"])
                    if tool_name not in {"update_food_listing", "update_listing", "edit_listing"}:
                        out.setdefault("title", row.get("title"))
                    break

    if tool_name in {"update_food_listing", "update_listing", "edit_listing"}:
        out = _normalize_update_food_listing_args(out, message, uid)
        if not out.get("listing_id"):
            picked = _resolve_update_listing_from_message(message, history, uid)
            if picked:
                out["listing_id"] = picked

    if tool_name == "delete_listing":
        if _is_affirmative_post_confirm(message) or any(
            k in (message or "").lower()
            for k in ("delete it", "remove it", "yes delete", "erase it", "elimínalo")
        ):
            out["confirmed"] = True

    return out


def _is_claim_all_quantity_reply(message: str) -> bool:
    """True when the user answered a how-many ask with 'all' / 'everything'."""
    t = (message or "").strip().lower()
    if not t:
        return False
    if t in (
        "all", "all of them", "all of it", "the whole thing", "everything",
        "todo", "todos", "toda", "todas", "completo", "completa",
    ):
        return True
    return any(p in t for p in (
        "all of them", "all of it", "take all", "claim all", "everything left",
        "the whole thing", "toda la", "todos los",
    ))


def _extract_quantity_from_message(message: str) -> Optional[int]:
    t = (message or "").strip().lower()
    if not t:
        return None
    if re.fullmatch(r"\d{1,3}", t):
        return int(t)
    m = re.search(r"\b(\d{1,3})\b", t)
    if m and not _looks_like_multi_option_pick(message):
        return int(m.group(1))
    return None


def _available_qty_for_listing(user_id: str, listing_id: str | None) -> Optional[int]:
    """Look up available quantity from the last search cache for a listing."""
    if not listing_id:
        return None
    for row in get_last_search_listings(user_id) or []:
        if str(row.get("id") or "") != str(listing_id):
            continue
        try:
            q = float(row.get("quantity") or 0)
        except (TypeError, ValueError):
            return None
        if q >= 1:
            return int(q)
        return None
    return None


# Words the user glues onto a food noun that we should ignore when
# matching listings (`2 loaves of bread` → match on "bread").
_QTY_UNIT_WORDS: frozenset[str] = frozenset({
    "loaf", "loaves", "tray", "trays", "box", "boxes", "bag", "bags",
    "basket", "baskets", "sack", "sacks",
    "bunch", "bunches", "piece", "pieces", "pack", "packs", "packet",
    "packets", "carton", "cartons", "can", "cans", "jar", "jars",
    "container", "containers", "bottle", "bottles", "pound", "pounds",
    "lb", "lbs", "kg", "kilo", "kilos", "gram", "grams",
    "cup", "cups", "unit", "units", "portion", "portions", "serving",
    "servings", "slice", "slices", "of", "the",
})

_CLAIM_INTENT_RE = re.compile(
    r"^\s*(?:i(?:'|)?\s*(?:ll|will)\s*take|i\s*want|i\s*need|i\s*would\s*like|"
    r"claim|reserve|grab|take|reclamar|reservar|quiero|"
    r"pedir|tomo|lo\s*tomo)\b",
    re.IGNORECASE,
)


def _extract_claim_intent(message: str) -> dict:
    """Parse quantity and food hint from an initial claim message.

    Handles patterns like:
      - "claim 2 oranges"          → {qty: 2, title_hint: "oranges"}
      - "I'll take 3 loaves of bread" → {qty: 3, title_hint: "bread"}
      - "reserve the apples"       → {title_hint: "apples"}
      - "2 oranges please"         → {qty: 2, title_hint: "oranges"}
      - "1 and 2"                  → {} (multi-pick, handled elsewhere)
    """
    out: dict = {}
    text = (message or "").strip()
    if not text or _looks_like_multi_option_pick(text):
        return out
    if _looks_like_food_quantity_spec(text):
        # Multi-food orders belong to the batch-order path.
        nums = re.findall(r"\d+", text)
        if len(nums) >= 2:
            return out

    t_lower = text.lower()
    has_claim_verb = bool(_CLAIM_INTENT_RE.search(text)) or any(
        k in t_lower for k in _CLAIM_TRIGGERS
    )

    m = re.search(
        r"\b(\d{1,3})\s+((?:[a-zA-Z][a-zA-Z']*\s*){1,5})",
        text,
    )
    if m:
        try:
            qty = int(m.group(1))
        except (TypeError, ValueError):
            qty = None
        raw_words = re.findall(r"[a-zA-Z']+", m.group(2).lower())
        food_words = [w for w in raw_words if w not in _QTY_UNIT_WORDS]
        food_hit = next((w for w in food_words if w in _FOOD_WORDS), None)
        if qty is not None and 0 < qty <= 300 and food_hit:
            out["quantity"] = qty
            out["title_hint"] = food_hit
            return out
        if qty is not None and 0 < qty <= 300 and has_claim_verb and food_words:
            out["quantity"] = qty
            out["title_hint"] = food_words[-1]
            return out

    if has_claim_verb:
        qty = _extract_quantity_from_message(text)
        if qty is not None:
            out["quantity"] = qty
        food_words = [
            w for w in re.findall(r"[a-zA-Z']+", t_lower)
            if w in _FOOD_WORDS
        ]
        if food_words:
            out["title_hint"] = food_words[-1]

    return out


def _resolve_listing_id_by_title_hint(
    title_hint: str,
    user_id: str,
) -> Optional[str]:
    """Match a food word against titles in the last search cache.

    Uses substring + fuzzy match so 'oranges' finds 'Fresh Oranges' or
    'Orange bag'. Returns the listing id when a confident match exists.
    """
    hint = (title_hint or "").strip().lower()
    if not hint:
        return None
    listings = get_last_search_listings(user_id)
    if not listings:
        return None

    best_id: Optional[str] = None
    best_score = 0.0
    for row in listings:
        title = str(row.get("title") or "").strip().lower()
        if not title:
            continue
        title_tokens = set(re.findall(r"[a-z']+", title))
        if hint in title_tokens or hint in title:
            score = 0.95
        else:
            score = difflib.SequenceMatcher(None, hint, title).ratio()
            for tok in title_tokens:
                score = max(score, difflib.SequenceMatcher(None, hint, tok).ratio())
        if score > best_score:
            best_score = score
            lid = row.get("id")
            if lid:
                best_id = str(lid)
    if best_id and best_score >= 0.72:
        return best_id
    return None


def _last_search_food_titles(user_id: str) -> list[str]:
    """Titles from the last search cache (used for pivot detection)."""
    return [
        str(row.get("title") or "").strip().lower()
        for row in get_last_search_listings(user_id)
        if row.get("title")
    ]


def _user_pivoted_claim_target(
    message: str,
    history: list | None,
    user_id: str = "",
) -> bool:
    """Detect when the user switches to a different listing mid-claim.

    Triggers on either an explicit pivot phrase ('actually', 'instead',
    'wait, I want ...') OR a different index / food than what was already
    picked in this thread. Lets the search / claim flow reset gracefully
    instead of forcing the user through the previous claim.
    """
    t = (message or "").strip().lower()
    if not t:
        return False

    pivot_phrases = (
        "actually", "instead", "wait", "on second thought", "change my mind",
        "changed my mind", "nope", "never mind", "nevermind", "cancel that",
        "hold on", "scratch that", "un momento", "espera", "mejor",
        "en realidad", "cambié de opinión", "cambio de opinion",
    )
    if any(p in t for p in pivot_phrases):
        return True

    intent = _extract_claim_intent(message)
    new_title = intent.get("title_hint")
    if not new_title and _looks_like_listing_pick(message):
        # numeric pick — see if it's different from what was picked before
        nums = re.findall(r"\d+", t)
        current_idx = None
        if nums:
            try:
                current_idx = int(nums[0])
            except (TypeError, ValueError):
                current_idx = None
        if current_idx is not None and history:
            for msg in reversed(history[-6:]):
                if msg.get("role") != "user":
                    continue
                prev = (msg.get("message") or "").strip().lower()
                prev_nums = re.findall(r"\d+", prev)
                if prev_nums:
                    try:
                        prev_idx = int(prev_nums[0])
                    except (TypeError, ValueError):
                        prev_idx = None
                    if prev_idx is not None and prev_idx != current_idx:
                        return True
                    break

    if new_title and history:
        # If the previous user turn mentioned a different food word, pivot.
        for msg in reversed(history[-6:]):
            if msg.get("role") != "user":
                continue
            prev_hint = _mentioned_food_hint_from_message(
                msg.get("message") or "",
            )
            if prev_hint and prev_hint != new_title:
                return True
            break

    return False


def build_claim_execute_reminder(
    message: str,
    history: list | None,
    lang: str = "en",
) -> str | None:
    """After quantity is known, nudge the model to claim immediately."""
    if detect_conversation_flow(message, history) != "claiming":
        return None
    if not _quantity_step_complete(history, message):
        return None
    if lang == "es":
        return (
            "RECLAMAR AHORA (este turno):\n"
            "Ya tienen listing y cantidad. Llama claim_listing en este turno "
            "con el listing que eligieron y la cantidad. Luego confirma con "
            "calidez (dirección de recogida si la tienes). No pidas más confirmación."
        )
    return (
        "CLAIM NOW (this turn):\n"
        "They picked a listing and gave a quantity. Call claim_listing this turn "
        "with that listing and quantity, then reply warmly with pickup details. "
        "Do not ask another confirmation question first."
    )


def _last_listing_pick_from_history(
    history: list | None,
    user_id: str,
) -> Optional[str]:
    """Find the most recent single listing pick in chat history."""
    listings = get_last_search_listings(user_id)
    if not listings or not history:
        return None
    for msg in reversed(history):
        if msg.get("role") != "user":
            continue
        text = (msg.get("message") or "").strip()
        if not text or _looks_like_multi_option_pick(text):
            continue
        if not (_looks_like_listing_pick(text) or any(
            k in text.lower() for k in _CLAIM_TRIGGERS
        )):
            continue
        raw = text.lstrip("#").strip()
        if re.fullmatch(r"\d{1,2}", raw):
            resolved, err = resolve_listing_id_from_search(int(raw), user_id)
            if resolved and not err:
                return resolved
        for idx, row in enumerate(listings, start=1):
            title = str(row.get("title") or "").lower()
            if title and title in text.lower():
                lid = row.get("id")
                if lid:
                    return str(lid)
    return None


# ---------------------------------------------------------------------------
# Multi-listing claim drafts (queue of items + per-item qty)
# ---------------------------------------------------------------------------

_claim_drafts_by_user: dict[str, list[dict]] = {}


def get_claim_drafts(user_id: str) -> list[dict]:
    return list(_claim_drafts_by_user.get(str(user_id or ""), []) or [])


def set_claim_drafts(user_id: str, drafts: list[dict] | None) -> None:
    uid = str(user_id or "").strip()
    if not uid:
        return
    if not drafts:
        _claim_drafts_by_user.pop(uid, None)
        return
    _claim_drafts_by_user[uid] = [dict(d) for d in drafts]


def clear_claim_drafts(user_id: str) -> None:
    _claim_drafts_by_user.pop(str(user_id or ""), None)


def remove_claimed_from_drafts(user_id: str, claimed_listing_ids: list | None) -> None:
    """Drop successfully claimed items; keep failed drafts for retry."""
    uid = str(user_id or "").strip()
    if not uid:
        return
    lids = {
        str(x).strip().lower()
        for x in (claimed_listing_ids or [])
        if x is not None and str(x).strip()
    }
    if not lids:
        return
    drafts = get_claim_drafts(uid)
    if not drafts:
        return
    kept = [
        d for d in drafts
        if str(d.get("listing_id") or "").strip().lower() not in lids
    ]
    if len(kept) < 2:
        clear_claim_drafts(uid)
    else:
        set_claim_drafts(uid, kept)


def _parse_claim_index_picks(message: str, user_id: str) -> list[dict]:
    """Parse '#1 and #3' / '1 and 2' / 'both' into claim draft stubs."""
    t = (message or "").strip().lower()
    listings = get_last_search_listings(user_id)
    if not listings:
        return []

    indices: list[int] = []
    if t in ("both", "all", "both of them", "all of them"):
        indices = list(range(1, min(len(listings), 2) + 1))
        if t.startswith("all") and len(listings) > 2:
            indices = list(range(1, len(listings) + 1))
    else:
        # Prefer #N tokens; fall back to small integers when multi-pick.
        hash_nums = [int(n) for n in re.findall(r"#(\d{1,2})", t)]
        if hash_nums:
            indices = hash_nums
        elif _looks_like_multi_option_pick(message):
            indices = [int(n) for n in re.findall(r"\d+", t) if 1 <= int(n) <= 15]

    out: list[dict] = []
    seen: set[str] = set()
    for idx in indices:
        if idx < 1 or idx > len(listings):
            continue
        row = listings[idx - 1]
        lid = str(row.get("id") or "")
        if not lid or lid in seen:
            continue
        seen.add(lid)
        out.append({
            "listing_id": lid,
            "display_index": idx,
            "title": str(row.get("title") or f"#{idx}"),
            "qty": None,
            "unit": row.get("unit"),
        })
    return out


def _parse_claim_food_items(message: str, user_id: str) -> list[dict]:
    """Parse '2 oranges and 3 bread' / 'the apples and bananas' against search."""
    items = _parse_share_items_from_text(message or "")
    # Bare dual food titles without quantities.
    if len(items) < 2:
        foods = [
            w for w in re.findall(r"[a-zA-Z']+", (message or "").lower())
            if w in _FOOD_WORDS and w not in _QTY_UNIT_WORDS
        ]
        uniq: list[str] = []
        for f in foods:
            if f not in uniq:
                uniq.append(f)
        if len(uniq) >= 2:
            items = [{"title": f, "qty": None, "unit": "items"} for f in uniq[:6]]

    out: list[dict] = []
    seen: set[str] = set()
    for item in items:
        title = str(item.get("title") or "").strip()
        if not title:
            continue
        lid = _resolve_listing_id_by_title_hint(title, user_id)
        key = lid or title.lower()
        if key in seen:
            continue
        seen.add(key)
        display_index = None
        if lid:
            for i, row in enumerate(get_last_search_listings(user_id), start=1):
                if str(row.get("id") or "") == lid:
                    display_index = i
                    title = str(row.get("title") or title)
                    break
        qty = item.get("qty")
        try:
            qty_val = float(qty) if qty is not None else None
        except (TypeError, ValueError):
            qty_val = None
        # _parse_share_items always sets qty=1.0 default for bare foods —
        # treat that as missing when the message had no digit for that food.
        if qty_val is not None and qty_val == 1.0:
            # Keep 1 only if message explicitly has "1 <food>" or "a/an <food>".
            tl = title.lower()
            msg_l = (message or "").lower()
            explicit = bool(re.search(rf"\b1\s+(?:[a-z]+\s+)*(?:of\s+)?{re.escape(tl)}\b", msg_l))
            if not explicit and not re.search(
                rf"\b(?:a|an)\s+(?:[a-z]+\s+)*(?:of\s+)?{re.escape(tl)}\b", msg_l,
            ):
                # For share-style "2 oranges and 3 bread", qty is real.
                if not re.search(rf"\b\d+\s+(?:[a-z]+\s+)*(?:of\s+)?{re.escape(tl)}\b", msg_l):
                    qty_val = None
        out.append({
            "listing_id": lid,
            "display_index": display_index,
            "title": title,
            "qty": qty_val,
            "unit": item.get("unit") or "items",
        })
    return out


def upsert_claim_drafts_from_message(
    user_id: str,
    message: str,
    history: list | None = None,
) -> list[dict]:
    """Merge newly mentioned claim targets into the user's draft queue."""
    uid = str(user_id or "").strip()
    if not uid:
        return []

    parsed = _parse_claim_index_picks(message, uid)
    if len(parsed) < 2:
        food_parsed = _parse_claim_food_items(message, uid)
        if len(food_parsed) >= 2:
            parsed = food_parsed
        elif len(parsed) == 0 and len(food_parsed) == 1:
            # Don't start a multi-queue from a single item.
            parsed = []

    existing = get_claim_drafts(uid)
    by_key: dict[str, dict] = {}
    for d in existing:
        key = str(d.get("listing_id") or d.get("title") or "").lower()
        if key:
            by_key[key] = dict(d)

    for item in parsed:
        key = str(item.get("listing_id") or item.get("title") or "").lower()
        if not key:
            continue
        if key in by_key:
            cur = by_key[key]
            if item.get("listing_id") and not cur.get("listing_id"):
                cur["listing_id"] = item["listing_id"]
            if item.get("display_index") and not cur.get("display_index"):
                cur["display_index"] = item["display_index"]
            if item.get("qty") is not None and (
                cur.get("qty") is None or float(cur.get("qty") or 0) <= 0
            ):
                cur["qty"] = item["qty"]
            if item.get("title"):
                cur["title"] = item["title"]
        else:
            by_key[key] = {
                "id": f"c{len(by_key) + 1}",
                "listing_id": item.get("listing_id"),
                "display_index": item.get("display_index"),
                "title": item.get("title"),
                "qty": item.get("qty"),
                "unit": item.get("unit"),
            }

    # Short qty reply while a draft is missing qty and assistant asked how many.
    msg_stripped = (message or "").strip()
    if existing and re.fullmatch(r"\d{1,3}", msg_stripped):
        qty = _extract_quantity_from_message(message)
        if qty is not None:
            for d in by_key.values():
                if d.get("qty") is None or float(d.get("qty") or 0) <= 0:
                    # Prefer draft mentioned in last assistant turn.
                    last_a = ""
                    for msg in reversed(history or []):
                        if msg.get("role") == "assistant":
                            last_a = (msg.get("message") or "").lower()
                            break
                    title = str(d.get("title") or "").lower()
                    if title and title in last_a:
                        d["qty"] = float(qty)
                        break
            else:
                for d in by_key.values():
                    if d.get("qty") is None or float(d.get("qty") or 0) <= 0:
                        d["qty"] = float(qty)
                        break

    # "2 each" / "2 of each" → same qty for every draft still missing qty.
    each_m = re.fullmatch(
        r"(\d{1,3})\s*(?:each|of each|apiece|for each|para cada uno)?",
        msg_stripped.lower(),
    )
    if existing and each_m and (
        "each" in msg_stripped.lower()
        or "apiece" in msg_stripped.lower()
        or "para cada" in msg_stripped.lower()
    ):
        try:
            each_qty = float(each_m.group(1))
        except (TypeError, ValueError):
            each_qty = None
        if each_qty and each_qty > 0:
            for d in by_key.values():
                if d.get("qty") is None or float(d.get("qty") or 0) <= 0:
                    d["qty"] = each_qty

    # "all of them" after a multi how-many ask → fill missing drafts from cache.
    if existing and _is_claim_all_quantity_reply(message):
        for d in by_key.values():
            if d.get("qty") is not None and float(d.get("qty") or 0) > 0:
                continue
            avail = _available_qty_for_listing(uid, d.get("listing_id"))
            d["qty"] = float(avail) if avail else "all"

    # Resolve missing listing_ids from search cache.
    for d in by_key.values():
        if d.get("listing_id"):
            continue
        title = str(d.get("title") or "")
        if title:
            lid = _resolve_listing_id_by_title_hint(title, uid)
            if lid:
                d["listing_id"] = lid
                for i, row in enumerate(get_last_search_listings(uid), start=1):
                    if str(row.get("id") or "") == lid:
                        d["display_index"] = i
                        d["title"] = str(row.get("title") or title)
                        break

    order_keys = [
        str(d.get("listing_id") or d.get("title") or "").lower()
        for d in existing
    ]
    for item in parsed:
        k = str(item.get("listing_id") or item.get("title") or "").lower()
        if k and k not in order_keys:
            order_keys.append(k)
    for k in by_key:
        if k not in order_keys:
            order_keys.append(k)
    ordered = [by_key[k] for k in order_keys if k in by_key]
    for i, d in enumerate(ordered, start=1):
        d["id"] = f"c{i}"
    set_claim_drafts(uid, ordered)
    return ordered


def sync_claim_drafts(
    user_id: str,
    message: str,
    history: list | None = None,
) -> list[dict]:
    uid = str(user_id or "").strip()
    if not uid:
        return []
    return upsert_claim_drafts_from_message(uid, message, history)


def claim_drafts_missing(drafts: list[dict] | None) -> list[dict]:
    missing: list[dict] = []
    for d in drafts or []:
        gaps: list[str] = []
        if not d.get("listing_id"):
            gaps.append("listing")
        qty = d.get("qty")
        qty_ok = (
            (isinstance(qty, str) and qty.strip().lower() in {
                "all", "everything", "todo", "todos",
            })
            or (
                qty is not None
                and not isinstance(qty, str)
                and float(qty or 0) > 0
            )
        )
        if not qty_ok:
            gaps.append("qty")
        if gaps:
            missing.append({
                "id": d.get("id"),
                "title": d.get("title"),
                "display_index": d.get("display_index"),
                "missing": gaps,
            })
    return missing


def claim_drafts_ready(drafts: list[dict] | None) -> bool:
    if not drafts or len(drafts) < 2:
        return False
    return len(claim_drafts_missing(drafts)) == 0


def build_claim_drafts_reminder(
    user_id: str,
    message: str = "",
    history: list | None = None,
    lang: str = "en",
) -> str | None:
    drafts = get_claim_drafts(str(user_id or ""))
    if len(drafts) < 2:
        return None
    missing = claim_drafts_missing(drafts)
    lines = []
    for d in drafts:
        idx = d.get("display_index")
        label = f"#{idx} " if idx else ""
        qty = d.get("qty")
        qty_s = f"qty={qty}" if qty is not None else "qty=?"
        lid = "listing=ok" if d.get("listing_id") else "listing=?"
        lines.append(f"- {label}{d.get('title')}: {qty_s}, {lid}")
    body = "\n".join(lines)
    if lang == "es":
        tip = (
            "COLA DE RECLAMOS MÚLTIPLES (2+). Pregunta UN campo faltante "
            "por turno (cantidad por ítem). Cuando todo esté listo, da UN "
            "resumen corto y pregunta '¿Listo para reclamar estos?'; tras "
            "el sí, llama claim_listings con items[]. No reclames solo el primero."
        )
    else:
        tip = (
            "MULTI-CLAIM DRAFT QUEUE (2+ listings). Ask ONE missing field "
            "per turn (usually qty for the next unfinished item). When all "
            "drafts have listing_id + qty, give ONE short summary and ask "
            "'Ready to claim these?' — after they say yes, call "
            "claim_listings with items[]. Do NOT claim only the first item "
            "with claim_listing. Emphasize they can claim several at once."
        )
    if missing:
        gap = " Still missing: " + "; ".join(
            f"{m.get('title') or m.get('display_index')}→{','.join(m.get('missing') or [])}"
            for m in missing
        )
    else:
        if _claiming_ready_to_execute(message, history):
            gap = (
                " All drafts ready and user confirmed — call claim_listings "
                "NOW with items[] for every draft."
            )
        else:
            gap = (
                " All drafts ready — ONE short summary + ask "
                "'Ready to claim these?' once, then wait for yes before "
                "claim_listings."
            )
    return f"{tip}\nDrafts:\n{body}.{gap}"


def _is_affirmative_claim_confirm(message: str) -> bool:
    t = (message or "").strip().lower()
    if not t:
        return False
    keys = (
        "yes", "yep", "yeah", "yup", "claim it", "claim them", "claim these",
        "claim both", "claim all", "claim now", "go ahead", "confirm",
        "do it", "please do", "sounds good", "looks good",
        "sí", "si ", "reclama", "reclámalos", "reclamarlos", "dale", "adelante",
        "yes, claim", "yes claim",
    )
    return any(k in t for k in keys)


def _claiming_ready_to_execute(message: str, history: list | None) -> bool:
    """True when the recipient greenlit the multi-claim this turn."""
    last = _assistant_last_asked_kind(history)
    affirmative = (
        _is_affirmative_claim_confirm(message)
        or _is_short_affirmative(message)
    )
    if not affirmative:
        # Explicit multi-claim language with amounts already in the message.
        t = (message or "").lower()
        if any(k in t for k in (
            "claim these", "claim both", "claim all", "claim them now",
            "yes, claim", "reclama estos", "reclamar ambos",
        )):
            return True
        return False
    if last == "claim_confirm":
        return True
    t = (message or "").lower()
    return any(k in t for k in (
        "claim it", "claim them", "claim these", "claim both", "claim all",
        "yes, claim", "yes claim", "go ahead and claim",
    ))


def _claim_confirm_needed_reason(message: str, history: list | None) -> str | None:
    """Ask for exactly one Ready-to-claim confirm when drafts are complete."""
    if _claiming_ready_to_execute(message, history):
        return None
    last = _assistant_last_asked_kind(history)
    if last == "claim_confirm":
        if _is_affirmative_claim_confirm(message) or _is_short_affirmative(message):
            return None
        return (
            "You already asked 'Ready to claim these?' — wait for their yes "
            "(or a quantity change). Do NOT call claim_listings yet."
        )
    return (
        "All multi-claim drafts are ready. Give ONE short summary of what "
        "they'll get (titles + quantities) and ask 'Ready to claim these?' "
        "— then wait. After they say yes, call claim_listings with items[]."
    )


def enrich_claim_listings_args(
    args: dict,
    message: str,
    history: list | None,
    user_id: str,
) -> dict:
    """Fill claim_listings items[] from the claim-draft queue."""
    out = dict(args or {})
    uid = str(user_id or "").strip()
    drafts = sync_claim_drafts(uid, message, history) if uid else get_claim_drafts(uid)

    items = out.get("items")
    if not isinstance(items, list) or not items:
        items = []
        for d in drafts:
            if not d.get("listing_id"):
                continue
            item = {"listing_id": d["listing_id"]}
            raw_qty = d.get("qty")
            if raw_qty is not None:
                if isinstance(raw_qty, str) and raw_qty.strip().lower() in {
                    "all", "everything", "todo", "todos",
                }:
                    avail = _available_qty_for_listing(uid, d.get("listing_id"))
                    item["quantity"] = avail if avail is not None else "all"
                else:
                    try:
                        item["quantity"] = int(float(raw_qty))
                    except (TypeError, ValueError):
                        item["quantity"] = raw_qty
            if d.get("title"):
                item["title"] = d["title"]
            items.append(item)
        out["items"] = items
    else:
        by_lid = {
            str(d.get("listing_id") or ""): d for d in drafts if d.get("listing_id")
        }
        for item in items:
            if not isinstance(item, dict):
                continue
            lid = str(item.get("listing_id") or "").strip()
            if lid and not re.match(r"^[0-9a-f-]{36}$", lid, re.I):
                resolved, err = resolve_listing_id_from_search(lid, uid)
                if resolved:
                    item["listing_id"] = resolved
                    lid = resolved
            draft = by_lid.get(lid)
            if draft and item.get("quantity") is None and draft.get("qty") is not None:
                raw_qty = draft["qty"]
                if isinstance(raw_qty, str) and raw_qty.strip().lower() in {
                    "all", "everything", "todo", "todos",
                }:
                    avail = _available_qty_for_listing(uid, lid)
                    item["quantity"] = avail if avail is not None else "all"
                else:
                    try:
                        item["quantity"] = int(float(raw_qty))
                    except (TypeError, ValueError):
                        item["quantity"] = raw_qty
        out["items"] = items
    return out


def claiming_batch_tool_block_reason(
    message: str,
    history: list | None,
    fn_args: dict | None = None,
    user_id: str = "",
) -> str | None:
    """Block claim_listings when the multi-claim queue is incomplete."""
    args = fn_args or {}
    uid = str(user_id or args.get("user_id") or "").strip()
    drafts = get_claim_drafts(uid) if uid else []
    items = args.get("items") if isinstance(args.get("items"), list) else []

    if len(drafts) < 2 and len(items) < 2:
        return (
            "claim_listings is for 2+ listings. For a single listing use "
            "claim_listing instead."
        )

    if items:
        gaps = []
        for i, item in enumerate(items, start=1):
            if not isinstance(item, dict):
                gaps.append(f"item {i}: invalid")
                continue
            miss = []
            if not item.get("listing_id"):
                miss.append("listing_id")
            raw_q = item.get("quantity")
            if raw_q is None:
                raw_q = item.get("qty")
            qty_ok = False
            if isinstance(raw_q, str) and raw_q.strip().lower() in {
                "all", "everything", "todo", "todos",
            }:
                qty_ok = True
            elif raw_q is not None:
                try:
                    qty_ok = float(raw_q) > 0
                except (TypeError, ValueError):
                    qty_ok = False
            if not qty_ok:
                miss.append("qty")
            if miss:
                gaps.append(f"{item.get('title') or i}: {', '.join(miss)}")
        if gaps:
            return (
                "Batch claim incomplete — still need: " + "; ".join(gaps) + ". "
                "Ask for the next missing quantity (one at a time), then retry "
                "claim_listings."
            )
    else:
        missing = claim_drafts_missing(drafts)
        if missing:
            bits = [
                f"{m.get('title') or m.get('display_index')}: "
                f"{', '.join(m.get('missing') or [])}"
                for m in missing
            ]
            return (
                "Batch claim incomplete — still need: " + "; ".join(bits) + ". "
                "Ask ONE missing field per turn, then retry claim_listings."
            )

    # Drafts/items complete → one Ready-to-claim confirm (mirrors share flow).
    items_complete = (
        isinstance(items, list)
        and len(items) >= 2
        and all(
            isinstance(it, dict)
            and it.get("listing_id")
            and _claim_item_qty_ok(it)
            for it in items
        )
    )
    if claim_drafts_ready(drafts) or items_complete:
        return _claim_confirm_needed_reason(message, history)

    return None


def _claim_item_qty_ok(item: dict) -> bool:
    raw_q = item.get("quantity")
    if raw_q is None:
        raw_q = item.get("qty")
    if isinstance(raw_q, str) and raw_q.strip().lower() in {
        "all", "everything", "todo", "todos",
    }:
        return True
    if raw_q is None:
        return False
    try:
        return float(raw_q) > 0
    except (TypeError, ValueError):
        return False


def enrich_claim_listing_args(
    args: dict,
    message: str,
    history: list | None,
    user_id: str,
) -> dict:
    """Resolve display index → UUID and attach quantity when inferable.

    Supports one-shot claim messages ("claim 2 oranges") by parsing the
    intent up front and reconciling with the last search cache before
    falling back to earlier picks in history.
    """
    out = enrich_repeat_write_action("claim_listing", args, message, history, user_id)
    uid = str(user_id or out.get("user_id") or "")

    intent = _extract_claim_intent(message)

    resolved, err = resolve_listing_id_from_search(out.get("listing_id"), uid)
    if resolved:
        out["listing_id"] = resolved
        out["_resolved_from_index"] = str(args.get("listing_id")) != resolved
    if err:
        out["_resolve_error"] = err

    if (not out.get("listing_id") or out.get("_resolve_error")) and intent.get("title_hint"):
        picked = _resolve_listing_id_by_title_hint(intent["title_hint"], uid)
        if picked:
            out["listing_id"] = picked
            out.pop("_resolve_error", None)
            out["_resolved_from_title"] = True
        elif get_last_search_listings(uid):
            out["_no_matching_listing_food"] = intent["title_hint"]

    if not out.get("listing_id") or out.get("_resolve_error"):
        if not out.get("_no_matching_listing_food"):
            from_history = _last_listing_pick_from_history(history, uid)
            if from_history:
                out["listing_id"] = from_history
                out.pop("_resolve_error", None)
                out["_resolved_from_history"] = True

    if out.get("quantity") is None and intent.get("quantity") is not None:
        out["quantity"] = intent["quantity"]

    if out.get("quantity") is None:
        if _quantity_step_complete(history, message) or _assistant_awaiting_quantity(history):
            if _is_claim_all_quantity_reply(message):
                # Pass through so _normalize_claim_quantity takes full available.
                # Never force 1 — that made "All of them" claim a single unit.
                avail = _available_qty_for_listing(uid, out.get("listing_id"))
                out["quantity"] = avail if avail is not None else "all"
            else:
                qty = _extract_quantity_from_message(message)
                if qty is not None:
                    out["quantity"] = qty
    if out.get("quantity") is None and _quantity_step_complete(history, message):
        # Last-resort default only when they answered vaguely without all/digit.
        if not _is_claim_all_quantity_reply(message):
            out["quantity"] = 1
    return out


def claiming_tool_block_reason(
    message: str,
    history: list | None,
    fn_args: dict | None = None,
    user_id: str = "",
) -> str | None:
    """Block premature claim_listing before quantity/listing is verified.

    Priorities (checked in order):
      0. User is asking availability — answer qty, don't claim.
      1. User asked for a food that isn't in the last search results —
         tell the model to search that specific food instead of pretending
         to claim something we haven't verified exists.
      2. No listing_id could be resolved at all — tell the model to search.
      3. User picked a listing but hasn't said how many yet — ask quantity.
    """
    if _user_asking_availability(message):
        return (
            "The user is asking how much/many is available — answer with "
            "the quantity from the visible listings. Do NOT call "
            "claim_listing this turn."
        )

    args = fn_args or {}
    uid = str(user_id or args.get("user_id") or "")

    no_match_food = args.get("_no_matching_listing_food")
    if no_match_food:
        return (
            f"You don't have a listing for '{no_match_food}' in the current "
            "search results — do NOT ask 'how many'. Call search_food_near_user "
            f"with title_query='{no_match_food}' to see if it's available, then let "
            "the user pick from the fresh results."
        )

    intent = _extract_claim_intent(message)
    hint = intent.get("title_hint") or _mentioned_food_hint_from_message(message)
    if hint and uid and get_last_search_listings(uid):
        titles = _last_search_food_titles(uid)
        if titles and not any(hint in t for t in titles):
            # Only fire when the model actually tried to claim without a
            # verified listing_id; otherwise pass-through and let the model
            # ask a clarifying question or search.
            if not args.get("listing_id"):
                return (
                    f"You don't have a listing for '{hint}' in the current "
                    "search results. Do NOT invent one — call "
                    f"search_food_near_user with title_query='{hint}' first."
                )

    if not args.get("listing_id") and not _last_listing_pick_from_history(history, uid):
        # No listing anywhere — don't ask quantity in the void.
        if _user_just_picked_listing(message, history) is False and hint:
            return (
                f"No listing yet for '{hint}'. Run search_food_near_user "
                "(or ask which numbered option they meant) before claiming."
            )

    if not _user_just_picked_listing(message, history):
        return None
    return (
        "Ask how many they want from that listing before calling claim_listing."
    )


_CLAIM_DISTRACTOR_TOOLS = frozenset({
    "search_food_near_user",
    "get_active_communities",
    "get_profile_gaps",
})


def _user_wants_fresh_search(message: str) -> bool:
    t = (message or "").lower()
    return any(k in t for k in (
        "search again", "other options", "something else", "different listing",
        "show me more", "find food", "what else", "another option", "other food",
        "available food", "what's available", "whats available", "show available",
        "any food", "new food", "more food", "food near", "near me", "nearby",
        "want some food", "want food", "need food", "some food",
        "something easy", "easy to prepare", "start over", "start again",
        "buscar otra", "otra opción", "algo más", "buscar de nuevo",
        "buscar comida", "busco comida", "quiero comida", "algo fácil",
    )) or _user_clears_claim_flow(message)


def claiming_distractor_tool_block_reason(
    tool_name: str,
    message: str,
    history: list | None,
    user_id: str = "",
) -> str | None:
    """Stop search/community/profile tools from hijacking an in-progress claim.

    Yields to the search tool when the user pivots to a new food/listing —
    otherwise Nouri keeps saying 'claim in progress' when the user just
    wanted to switch targets.
    """
    if tool_name not in _CLAIM_DISTRACTOR_TOOLS:
        return None
    if is_finding_flow(message, history) or _user_wants_fresh_search(message):
        return None
    if detect_conversation_flow(message, history) != "claiming":
        return None
    if _user_pivoted_claim_target(message, history, str(user_id or "")):
        return None
    if _quantity_step_complete(history, message):
        return (
            f"Do not call {tool_name} — the user gave a quantity. "
            "Call claim_listing now with their listing and quantity."
        )
    if _user_just_picked_listing(message, history):
        return (
            f"Do not call {tool_name} — the user just picked a listing. "
            "Ask how many they want first."
        )
    if _assistant_awaiting_quantity(history):
        return (
            f"Do not call {tool_name} — waiting for the user's quantity answer."
        )
    return (
        f"Do not call {tool_name} during an active claim. "
        "Finish claim_listing or ask one clarifying question."
    )


def _user_wants_different_community(message: str) -> bool:
    t = (message or "").lower()
    return any(k in t for k in (
        "different community", "different school", "other community",
        "another school", "not that one", "change community",
        "otra comunidad", "otra escuela", "cambiar comunidad",
    ))


def _posting_community_already_shown(history: list | None) -> bool:
    blob_l = _history_blob(history, "", limit=14).lower()
    return any(p in blob_l for p in (
        "alameda unified", "which community", "which school", "list under",
        "school district", "go under", "active communit", "comunidad",
        "escuela", "different one", "list this under",
    ))


def posting_distractor_tool_block_reason(
    tool_name: str,
    message: str,
    history: list | None,
) -> str | None:
    """Stop repeated get_active_communities calls from hijacking share flow."""
    if tool_name != "get_active_communities":
        return None
    if not is_posting_flow(message, history):
        return None
    if _user_wants_different_community(message):
        return None
    if not _posting_community_already_shown(history):
        return None
    return (
        "Do not call get_active_communities again — you already showed communities. "
        "Ask the donor to confirm the school/community (yes or the name), then call "
        "post_food_listing (or post_food_listings for 2+ items) with community_name "
        "and community_confirmed=true."
    )


def build_food_order_spec_reminder(
    message: str,
    history: list | None,
    lang: str = "en",
    user_id: str = "",
) -> str | None:
    """When user lists foods + amounts, queue multi-claim drafts."""
    if not _looks_like_food_quantity_spec(message):
        return None
    if not _recent_search_context(history):
        return None
    if user_id:
        drafts = sync_claim_drafts(str(user_id), message, history)
        if len(drafts) >= 2:
            return build_claim_drafts_reminder(str(user_id), message, history, lang=lang)
    if lang == "es":
        return (
            "PEDIDO CON CANTIDADES (este turno):\n"
            "El usuario pidió varias comidas con cantidades. Mantén una cola "
            "de reclamos; resuelve cada alimento al listing del último search. "
            "Si falta qty o match, pregunta UNA cosa; luego claim_listings."
        )
    return (
        "FOOD + QUANTITY ORDER (this turn):\n"
        "The user named multiple foods with amounts. Keep a claim draft "
        "queue and match each food to a listing from the last search. "
        "Ask ONE clarifying question if a match or qty is missing, then "
        "call claim_listings for all ready items."
    )
