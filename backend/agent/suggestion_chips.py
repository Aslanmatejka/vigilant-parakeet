"""Unified suggestion chips for lazy / confused users.

Combines quick-reply heuristics, tool-context chips (claim #1), proactive
suggestions, and safe default actions so every turn returns tappable options.
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Union

from backend.ai_engine import compute_next_step

Chip = Union[str, Dict[str, Any]]

_MAX_CHIPS = 6
# Community list picks need the full catalog (NEA/ACLC, Ruby Bridges, …).
_MAX_COMMUNITY_CHIPS = 40

_MENU_CHIPS_EN = [
    "Find food near me",
    "I want to share food",
    "My pickups",
    "How does this work?",
]

_MENU_CHIPS_ES = [
    "Buscar comida cerca",
    "Quiero compartir comida",
    "Mis reservas",
    "¿Cómo funciona?",
]

_LAZY_DEFAULTS_EN = [
    "Find food near me",
    "I'm hungry — what's available?",
    "I want to share food",
    "My pickups",
    "Show my impact",
    "Help me get started",
]

_LAZY_DEFAULTS_ES = [
    "Buscar comida cerca",
    "Tengo hambre — ¿qué hay?",
    "Quiero compartir comida",
    "Mis reservas",
    "Mi impacto",
    "Ayúdame a empezar",
]

_SEARCH_TOOLS = frozenset({
    "search_food_listings",
    "search_listings",
    "search_nearby_food",
    "find_food",
})


def _normalize_chip_text(text: str) -> str:
    """Normalize hyphens/spacing so 'step-by-step' matches 'step by step'."""
    t = (text or "").lower()
    t = t.replace("–", "-").replace("—", "-")
    t = re.sub(r"[-_/]+", " ", t)
    t = re.sub(r"\s+", " ", t)
    return t.strip()


def _infer_assistance_fork_goal(
    reply: str,
    user_message: str = "",
    assistance_reminder: str = "",
    guide_state: Optional[Dict[str, Any]] = None,
) -> str:
    """Return share | find | request for assistance-fork chips."""
    rem = (assistance_reminder or "").lower()
    combined = f"{reply} {user_message} {rem}".lower()
    page_key = ""
    path = ""
    if isinstance(guide_state, dict):
        page_key = str(guide_state.get("pageKey") or "").lower()
        path = str(guide_state.get("path") or "").lower()

    # Explicit reminder / copy wins.
    if any(k in rem for k in ("share food", "to share", "compartir")):
        return "share"
    if any(k in rem for k in ("request food", "to request", "solicitar")):
        return "request"
    if any(k in rem for k in ("find food", "to find", "buscar comida", "search")):
        return "find"

    share_hit = any(k in combined for k in (
        "share food", "sharing", "donate", "donating", "posting", "compartir",
        "share food page", "/share",
    ))
    request_hit = any(k in combined for k in (
        "request food", "solicitar", "request food page", "/request",
    ))
    find_hit = any(k in combined for k in (
        "find food", "finding food", "search nearby", "near you", "find free",
        "buscar comida", "find food page", "/find", "near-me", "search for you",
        "handle the search",
    ))

    if share_hit and not request_hit:
        return "share"
    if request_hit and not share_hit:
        return "request"
    if find_hit and not share_hit and not request_hit:
        return "find"

    # Live page when the ask is ambiguous.
    if page_key == "share" or "/share" in path:
        return "share"
    if page_key == "request" or "/request" in path:
        return "request"
    if page_key in {"find", "near-me", "claim"} or "/find" in path or "/near-me" in path:
        return "find"

    return "share"


def share_assistance_fork_chips(
    response_text: str,
    language: str = "en",
    *,
    user_message: str = "",
    assistance_reminder: Optional[str] = None,
    guide_state: Optional[Dict[str, Any]] = None,
) -> List[Chip]:
    """Forced chips when Nouri asks do-it-for-me vs guide (share / find / request).

    Share: lead with **Open the form** → `/share`.
    Request: lead with **Open Request Food** → `/request`.
    Find: lead with **Open Find Food** → `/find` (never "Open the form").
    Always show the open chip so users get three options; label must match the goal.
    """
    rem = (assistance_reminder or "").strip()
    rem_l = _normalize_chip_text(rem)
    reply = _normalize_chip_text(response_text or "")
    um = _normalize_chip_text(user_message or "")

    explicit_fork = any(
        k in reply for k in (
            "do it for me", "handle everything", "handle the whole",
            "guide me step by step", "walk you through", "step by step",
            "do everything for you", "yourself on the", "on the pages",
            "on the form", "share food page", "find food page", "request food page",
            "hazlo por", "paso a paso", "yo te guio", "todo por ti", "te guio",
            "shall i handle", "prefer i handle", "or guide me",
            "or walk you", "do it myself",
            "handle it for you", "do this for you", "or would you rather",
            "open the form", "open find food", "open request food",
            "three options", "handle everything for you",
            "in chat for you", "in chat or", "here in chat",
            "handle the search", "search for you", "find it for you",
            "guide you on", "guide you through", "or guide you",
            "step by step help", "help on the share", "help on the find",
        )
    )
    share_ctx = any(k in f"{reply} {um} {rem_l}" for k in (
        "share", "sharing", "donate", "donating", "post ", "posting", "listing",
        "find food", "request food", "finding food", "requesting",
        "search nearby", "search for", "near you", "find free",
        "compartir", "donar", "publicar", "buscar comida", "solicitar",
    ))
    vague_proceed = share_ctx and any(k in reply for k in (
        "how would you like", "how do you want", "how should we",
        "how would you prefer", "prefer to proceed", "like to proceed",
        "would you like me to handle", "would you rather",
        "como quieres", "como prefieres", "de que forma",
    ))
    asking_fork = (
        rem_l.startswith(("assistance mode", "modo de ayuda"))
        or explicit_fork
        or vague_proceed
    )
    if not asking_fork:
        return []

    # Never re-offer the mode fork once the user already picked a path.
    if (
        rem_l.startswith(("guided", "guiado", "hands-on", "hands on", "modo manos"))
        or _is_guided_response(response_text or "")
        or _looks_like_guided_tutorial(response_text or "")
        or _user_chose_guided(user_message or "", assistance_reminder or "")
        or _user_chose_hands_on(user_message or "", assistance_reminder or "")
    ):
        if not rem_l.startswith(("assistance mode", "modo de ayuda")):
            return []

    es = language == "es" or "¿" in (response_text or "") or any(
        k in reply for k in ("quieres", "guio", "hazlo")
    ) or rem_l.startswith("modo de ayuda")

    goal = _infer_assistance_fork_goal(
        reply, um, rem_l, guide_state=guide_state,
    )

    path = ""
    if isinstance(guide_state, dict):
        path = str(guide_state.get("path") or "").lower()

    if goal == "share":
        nav_path, nav_target = "/share", "create"
        open_label = "Abrir el formulario" if es else "Open the form"
        open_message = open_label
    elif goal == "request":
        nav_path, nav_target = "/request", "request"
        open_label = "Abrir Solicitar comida" if es else "Open Request Food"
        open_message = open_label
    else:
        # Find Food — never label this "Open the form".
        nav_path = "/near-me" if ("near-me" in path or (isinstance(guide_state, dict) and str(guide_state.get("pageKey") or "").lower() == "near-me")) else "/find"
        nav_target = "near-me" if nav_path == "/near-me" else "list"
        open_label = "Abrir Buscar comida" if es else "Open Find Food"
        open_message = open_label

    chips: List[Chip] = [{
        "label": open_label,
        "message": open_message,
        "action": "navigate",
        "target": nav_target,
        "path": nav_path,
        "href": nav_path,
    }]

    if es:
        chips.extend([
            {"label": "Hazlo por mí", "message": "Hazlo por mí"},
            {"label": "Guíame paso a paso", "message": "Guíame paso a paso"},
        ])
    else:
        chips.extend([
            {"label": "Do it for me", "message": "Do it for me"},
            {"label": "Guide me step by step", "message": "Guide me step by step"},
        ])
    return chips


def get_menu_chips(language: str = "en") -> List[str]:
    """Chips shown after the welcome / help menu."""
    return list(_MENU_CHIPS_ES if language == "es" else _MENU_CHIPS_EN)


def get_lazy_default_chips(
    language: str = "en",
    detected_intent: Optional[str] = None,
    guide_mode: Optional[str] = None,
) -> List[str]:
    """No generic fallback chips — only contextual chips from tool results / reply text."""
    return []


def _chip_label(chip: Chip) -> str:
    if isinstance(chip, str):
        return chip.strip()
    if isinstance(chip, dict):
        return str(
            chip.get("label")
            or chip.get("message")
            or chip.get("prompt")
            or chip.get("text")
            or ""
        ).strip()
    return ""


def _normalize_proactive(item: Dict[str, Any]) -> Optional[Dict[str, str]]:
    label = (item.get("action_label") or item.get("label") or "").strip()
    message = (item.get("message") or item.get("prompt") or label).strip()
    if not label and message:
        label = message[:48]
    if not label:
        return None
    return {"label": label[:60], "message": message}


def _listings_from_tool_entry(entry: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Extract listing rows from either nested ``result`` or flat action shape.

    The live Nouri engine enriches actions with top-level ``listings`` via
    ``enrich_tool_action``; the older agent path nests them under ``result``.
    """
    raw = entry.get("result")
    result = raw if isinstance(raw, dict) else {}
    listings = (
        result.get("results")
        or result.get("listings")
        or entry.get("listings")
        or entry.get("results")
        or []
    )
    if not isinstance(listings, list):
        return []
    return [row for row in listings if isinstance(row, dict)]


def _chips_from_search_results(
    tool_results: Optional[List[Dict[str, Any]]],
    language: str,
) -> List[Chip]:
    """Numbered claim chips after a search tool returns listings.

    When 2+ results are shown, lead with multi-claim chips so recipients
    discover they can grab several items in one go.
    """
    es = language == "es"
    for entry in reversed(tool_results or []):
        if not isinstance(entry, dict) or not entry.get("ok"):
            continue
        tool = str(entry.get("tool") or "").lower()
        if tool not in _SEARCH_TOOLS and "search" not in tool:
            continue
        # Don't offer Claim #N on donor listing lookups.
        if tool in {"get_user_listings", "get_my_listings", "list_my_listings"}:
            continue
        listings = _listings_from_tool_entry(entry)
        if not listings:
            continue

        chips: List[Chip] = []
        n = len(listings)

        # Emphasize multi-claim first when there are 2+ options.
        if n >= 2:
            if es:
                chips.append({
                    "label": "Reclamar #1 y #2",
                    "message": "Quiero reclamar el #1 y el #2",
                })
                if n >= 3:
                    chips.append({
                        "label": "Reclamar los 3 primeros",
                        "message": "Quiero reclamar el #1, #2 y #3",
                    })
                else:
                    chips.append({
                        "label": "Reclamar ambos",
                        "message": "Quiero reclamar ambos",
                    })
            else:
                chips.append({
                    "label": "Claim #1 & #2",
                    "message": "I'd like to claim #1 and #2",
                })
                if n >= 3:
                    chips.append({
                        "label": "Claim first 3",
                        "message": "I'd like to claim #1, #2, and #3",
                    })
                else:
                    chips.append({
                        "label": "Claim both",
                        "message": "I'd like to claim both",
                    })

        # Individual chips (cap so multi + singles fit under _MAX_CHIPS).
        single_cap = 2 if n >= 2 else 3
        for i, listing in enumerate(listings[:single_cap], start=1):
            title = str(listing.get("title") or listing.get("name") or f"#{i}")[:28]
            if es:
                chips.append({
                    "label": f"Reclamar #{i}: {title}",
                    "message": f"Reclamar el #{i}",
                })
            else:
                chips.append({
                    "label": f"Claim #{i}: {title}",
                    "message": f"Claim #{i}",
                })
        if n > 3:
            chips.append("Show more options" if not es else "Ver más opciones")
        return chips
    return []


# Multi-item claim confirmation only (plural / batch language).
_CLAIM_CONFIRM_MULTI_CUES = (
    "ready to claim",
    "claim these",
    "claim both",
    "claim all of these",
    "claim all",
    "listo para reclamar",
    "reclamar estos",
    "reclamo estos",
    "reclamar ambos",
    "reclamar todos",
)

# Single listing claim confirmation.
_CLAIM_CONFIRM_SINGLE_CUES = (
    "shall i claim",
    "want me to claim",
    "claim this listing",
    "claim it for you",
    "claim this for you",
    "claim that listing",
    "reclamar este",
    "reclamarlo",
    "quieres que lo reclame",
    "quieres que reclame",
)

# Back-compat alias used by filters.
_CLAIM_CONFIRM_RESPONSE_CUES = _CLAIM_CONFIRM_MULTI_CUES + _CLAIM_CONFIRM_SINGLE_CUES

# Multi-item qty only — "how many of the bread" is a SINGLE listing ask.
_CLAIM_QTY_MULTI_CUES = (
    "how many for each",
    "quantity for each",
    "how many of each",
    "cuántos de cada",
    "cuantos de cada",
    "para cada uno",
    "para cada",
    "2 each",
    "de cada uno",
)


def _chips_for_multi_claim_flow(
    response_text: str,
    language: str,
) -> List[Chip]:
    """Chips while Nouri is collecting multi-claim qty or confirmation."""
    text = (response_text or "").lower()
    if not text:
        return []
    es = language == "es"

    if any(c in text for c in _CLAIM_CONFIRM_MULTI_CUES):
        if es:
            return [
                {"label": "Sí, reclamar todos", "message": "Sí, reclama todos"},
                {"label": "Cambiar cantidades", "message": "Quiero cambiar las cantidades"},
                {"label": "Cancelar", "message": "Cancelar"},
            ]
        return [
            {"label": "Yes, claim these", "message": "Yes, claim these"},
            {"label": "Change amounts", "message": "I want to change the amounts"},
            {"label": "Cancel", "message": "Cancel"},
        ]

    if any(c in text for c in _CLAIM_CONFIRM_SINGLE_CUES):
        if es:
            return [
                {"label": "Sí, reclámalo", "message": "Sí, reclámalo"},
                {"label": "No, gracias", "message": "No, gracias"},
                {"label": "Cancelar", "message": "Cancelar"},
            ]
        return [
            {"label": "Yes, claim it", "message": "Yes, claim it"},
            {"label": "No thanks", "message": "No thanks"},
            {"label": "Cancel", "message": "Cancel"},
        ]

    multi_qty = any(c in text for c in _CLAIM_QTY_MULTI_CUES) or (
        "how many" in text
        and any(k in text for k in (" each", "both", " and ", "first", "second", "para cada"))
        and any(k in text for k in ("claim", "reclamar", "of the", "de los", "de las", "items"))
    )
    if multi_qty and any(k in text for k in ("and", "both", "each", "cada", "first", "second", "#")):
        if es:
            return [
                {"label": "2 de cada uno", "message": "2 de cada uno"},
                {"label": "Todo de cada uno", "message": "Todo de cada uno"},
                {"label": "1 de cada uno", "message": "1 de cada uno"},
            ]
        return [
            {"label": "2 each", "message": "2 each"},
            {"label": "All of each", "message": "all of them"},
            {"label": "1 each", "message": "1 each"},
        ]
    return []


_GUIDED_MARKERS = ("guided —", "guided -", "guiado —", "guiado -", "guided — step", "guiado — paso")


def _is_guided_response(text: str) -> bool:
    t = (text or "").lower()
    return any(m in t for m in _GUIDED_MARKERS) or t.lstrip().startswith(("guided", "guiado"))


def _looks_like_guided_tutorial(text: str) -> bool:
    """True when the model dropped the GUIDED header but is still coaching."""
    if _is_guided_response(text):
        return True
    t = _normalize_chip_text(text)
    open_ask = any(k in t for k in (
        "open the share food", "open share food", "open the find food",
        "open find food", "open the request food", "open request food",
        "tap share food", "tap find food", "tap request food",
        "click share food", "click find food", "click request food",
        "please open the", "look at the top", "top of the screen",
        "top menu", "main menu", "tapping share food", "tapping find food",
        "abre compartir", "abre buscar", "abre solicitar",
        "mira arriba", "pulsa compartir", "pulsa buscar", "pulsa solicitar",
        "menu principal", "menú de arriba",
    ))
    wait_done = any(k in t for k in (
        "say done", "let me know when", "when you see", "next step",
        "see the form", "see find food", "together",
        "di listo", "avisame cuando", "avísame cuando", "cuando veas",
        "siguiente paso", "ves el formulario",
    ))
    baby_step = any(k in t for k in (
        "baby step", "look at the blue", "look at the green",
        "tap the box", "type your name", "scroll down to",
        "caja azul", "caja verde", "escribe tu nombre",
    ))
    return (open_ask and wait_done) or baby_step


def _user_chose_guided(user_message: str = "", assistance_reminder: str = "") -> bool:
    rem = _normalize_chip_text(assistance_reminder)
    um = _normalize_chip_text(user_message)
    if rem.startswith(("guided", "guiado")):
        return True
    return any(k in um for k in (
        "guide me", "step by step", "walk me through", "show me the steps",
        "guíame", "guiame", "paso a paso", "enseñame", "ensename",
    ))


def _user_chose_hands_on(user_message: str = "", assistance_reminder: str = "") -> bool:
    rem = _normalize_chip_text(assistance_reminder)
    um = _normalize_chip_text(user_message)
    if rem.startswith(("hands-on", "hands on", "modo manos")):
        return True
    return any(k in um for k in (
        "do it for me", "handle everything", "handle it for me", "do everything for me",
        "hazlo por mí", "hazlo por mi", "hazlo todo", "tú hazlo", "tu hazlo",
    ))


def _chips_for_guided_response(
    response_text: str,
    language: str,
    *,
    force: bool = False,
) -> List[Chip]:
    """Tappable replies that match a GUIDED UI-coaching turn."""
    if not force and not _looks_like_guided_tutorial(response_text):
        return []
    text = response_text or ""
    low = text.lower()
    es = language == "es"

    chips: List[Chip] = []

    # Field-specific options from the guided body.
    if any(k in low for k in ("donor type", "tipo de donante")):
        if es:
            chips.extend([
                {"label": "Individual / Familia", "message": "Individual/Familia"},
                {"label": "Organización", "message": "Organización"},
            ])
        else:
            chips.extend([
                {"label": "Individual / Family", "message": "Individual/Family"},
                {"label": "Organization", "message": "Organization"},
            ])
    elif any(k in low for k in ("allerg", "dietary", "dietética", "dietetica", "restricciones")):
        if es:
            chips.extend(["Ninguna", "Vegetariano", "Sin frutos secos"])
        else:
            chips.extend(["None", "Vegetarian", "Nut-free"])
    elif any(k in low for k in ("photo", "picture", "foto", "imagen")):
        if es:
            chips.extend([
                {"label": "Adjuntar foto", "message": "Adjuntaré una foto"},
            ])
        else:
            chips.extend([
                {"label": "I'll add a photo", "message": "I'll add a photo"},
            ])
    elif any(k in low for k in ("claim", "reclamar", "+ / −", "+/−", "portion")):
        if es:
            chips.extend(["1", "2", "3", "Listo"])
        else:
            chips.extend(["1", "2", "3", "Done"])
    elif any(k in low for k in (
        "what kind of food", "qué tipo de comida", "que tipo de comida",
        "looking for", "buscas", "what food", "qué alimento",
    )):
        if es:
            chips.extend(["Pan", "Frutas", "Verduras", "Comida preparada"])
        else:
            chips.extend(["Bread", "Fruit", "Vegetables", "Prepared meal"])
    elif any(k in low for k in (
        "open the share", "open share", "open the find", "open find",
        "open the request", "open request", "tap share food", "tap find food",
        "see the form", "main menu", "top menu",
        "abre compartir", "abre buscar", "ves el formulario",
    )):
        if es:
            chips.extend([
                {"label": "Ya veo el formulario", "message": "listo — ya veo el formulario"},
            ])
        else:
            chips.extend([
                {"label": "I see the form", "message": "done — I see the form"},
            ])

    # Always offer advance / help for guided coaching.
    if es:
        chips.extend([
            {"label": "Listo", "message": "listo"},
            {"label": "Siguiente", "message": "siguiente"},
            {"label": "¿Ayuda?", "message": "Necesito ayuda con este paso"},
        ])
    else:
        chips.extend([
            {"label": "Done", "message": "done"},
            {"label": "What's next?", "message": "what's next"},
            {"label": "Need help", "message": "I need help with this step"},
        ])

    # Deduplicate while preserving order.
    out: List[Chip] = []
    seen: set[str] = set()
    for chip in chips:
        label = _chip_label(chip)
        key = label.lower()
        if not label or key in seen:
            continue
        seen.add(key)
        out.append(chip)
    return out[:_MAX_CHIPS]


def _filter_chips_to_match_response(
    response_text: str,
    chips: List[Chip],
    language: str,
) -> List[Chip]:
    """Drop chips that clearly conflict with what the assistant just asked."""
    if not chips:
        return chips
    text = (response_text or "").lower()
    if not text:
        return chips

    drop_labels: set[str] = set()
    es = language == "es"

    # Claim confirm → never show generic Yes/No/Later or post chips.
    if any(c in text for c in _CLAIM_CONFIRM_RESPONSE_CUES):
        drop_labels.update({
            "yes", "no", "later", "sí", "si", "más tarde", "mas tarde",
            "yes, post it", "sí, publícalo", "si, publicalo", "wait, edit it",
        })

    # Community ask → never show post-it chips.
    if _is_community_selection_turn(response_text or ""):
        drop_labels.update({
            "yes, post it", "sí, publícalo", "si, publicalo",
            "wait, edit it", "espera, edítalo", "cancel", "cancelar",
            "yes", "no", "later",
        })

    # Guided coaching → drop unrelated menu / claim / post starters.
    if _is_guided_response(response_text or ""):
        drop_labels.update({
            "find food near me", "buscar comida cerca",
            "i want to share food", "quiero compartir comida",
            "yes, post it", "sí, publícalo",
            "claim #1", "reclamar #1",
            "yes", "no", "later", "sí", "más tarde",
        })

    # Photo required → never skip / bare yes-no.
    if any(k in text for k in ("photo", "picture", "foto", "imagen")) and any(
        k in text for k in ("upload", "attach", "required", "please", "add a", "add one", "sube", "adjunt")
    ):
        drop_labels.update({
            "skip", "skip photo", "no photo", "sin foto", "later", "más tarde",
            "yes", "no", "sí",
        })

    # Assistance fork → only mode chips.
    if any(k in text for k in (
        "do it for me", "guide me step by step", "walk you through",
        "handle everything", "do everything for you",
        "hazlo por mí", "hazlo por mi", "paso a paso", "yo te guío", "yo te guio",
    )):
        keep = {
            "do it for me", "guide me step by step", "open the form",
            "open find food", "open request food",
            "hazlo por mí", "hazlo por mi", "guíame paso a paso", "guiame paso a paso",
            "abrir el formulario", "abrir buscar comida", "abrir solicitar comida",
        }
        filtered = []
        for chip in chips:
            label = _chip_label(chip).lower()
            if (
                label in keep
                or "do it" in label
                or "guide me" in label
                or "open the form" in label
                or "open find food" in label
                or "open request food" in label
                or "abrir el formulario" in label
                or "abrir buscar" in label
                or "abrir solicitar" in label
                or "hazlo" in label
                or "guía" in label
                or "guia" in label
            ):
                filtered.append(chip)
        if filtered:
            return filtered[:_MAX_CHIPS]

    out: List[Chip] = []
    for chip in chips:
        label = _chip_label(chip)
        if label.lower() in drop_labels:
            continue
        # Prefix drops for Claim # when not a search turn
        out.append(chip)
    return out[:_MAX_CHIPS]


_COMMUNITY_CUES = (
    "community", "school", "district", "neighborhood", "warehouse",
    "elementary", "unified", "academy",
    "comunidad", "escuela", "distrito",
)

_COMMUNITY_PROMPT_KEYS = (
    "which community", "what community", "community is this", "community should",
    "list under", "list this under", "listed under",
    "post to", "share with", "for which community", "profile community", "your community",
    "confirm the community", "is this for", "different community",
    "profile is set", "profile is connected", "profile is linked",
    "linked to", "use that one", "post it there", "post this to",
    "qué comunidad", "que comunidad", "cuál comunidad", "cual comunidad",
    "para qué comunidad", "a qué comunidad", "tu comunidad",
    "comunidad de tu perfil", "bajo qué comunidad", "otra comunidad",
)

_COMMUNITY_NAME_EXCLUDE = frozenset({
    "Should", "Which", "What", "Community", "School", "District",
    "Post", "Share", "List", "Under", "Profile", "Your", "Quick",
    "The", "This", "That", "When", "Where", "How", "Would", "Could",
    "Thanks", "Thank", "Perfect", "Great", "Nice", "Got", "Please",
    "Just", "Here", "Before", "After", "Pickup",
    "Qué", "Cuál", "Para", "Tu", "Comunidad", "Escuela", "Gracias",
})

_STREET_SUFFIXES = frozenset({
    "st", "street", "ave", "avenue", "rd", "road", "blvd", "dr",
    "drive", "ln", "lane", "way", "ct", "court", "ca",
})

_COMMUNITY_NAME_MARKERS = (
    "linked to", "connected to", "set to", "listed under", "list under",
    "list this under", "post to", "post under", "for ",
    "vinculado a", "conectado a", "bajo ",
)

_COMMUNITY_SUFFIXES = (
    "unified", "usd", "school", "district", "elementary", "high",
    "academy", "college", "hub", "center", "group", "tech", "warehouse",
)

_DIFFERENT_COMMUNITY_USER_CUES = (
    "different one", "another one", "other one",
    "different community", "use a different community", "another community",
    "other community", "different school", "another school",
    "otra comunidad", "usar otra comunidad", "otra escuela",
)

_OPEN_COMMUNITY_PICK_KEYS = (
    "tell me the name", "name of the school", "name of the group",
    "which community should", "what community", "pick a community",
    "choose a community", "select a community", "list your",
    "dime el nombre", "nombre de la escuela", "nombre del grupo",
)


def _sanitize_community_name(name: str) -> str:
    cleaned = re.sub(r"\s+", " ", (name or "").strip(" \t\n\"'""''.,—-"))
    cleaned = re.sub(
        r"^(?:linked to|connected to|set to|listed under|list under|for)\s+",
        "",
        cleaned,
        flags=re.I,
    ).strip(" .,—-")
    return cleaned


def _looks_like_community_name(name: str) -> bool:
    cleaned = _sanitize_community_name(name)
    if not cleaned or len(cleaned) < 3:
        return False
    if re.search(r"\d", cleaned):
        return False

    words = cleaned.split()
    exclude = {w.lower() for w in _COMMUNITY_NAME_EXCLUDE}
    if words and all(w.lower() in exclude for w in words):
        return False
    if len(words) == 1 and words[0] in _COMMUNITY_NAME_EXCLUDE:
        return False
    if words[-1].lower() in _STREET_SUFFIXES:
        return False
    if len(words) == 1 and len(cleaned) < 5:
        return False

    low = cleaned.lower()
    if len(words) >= 2:
        return True
    return any(suffix in low for suffix in _COMMUNITY_SUFFIXES)


def _community_relevant_segment(text: str) -> str:
    """Prefer the part of the message that mentions community selection."""
    lower = text.lower()
    start = len(text)
    for marker in _COMMUNITY_NAME_MARKERS + ("which community", "qué comunidad", "que comunidad"):
        idx = lower.find(marker)
        if idx >= 0:
            start = min(start, idx)
    if start < len(text):
        return text[start:]
    for marker in _COMMUNITY_CUES:
        idx = lower.find(marker)
        if idx >= 0:
            return text[max(0, idx - 40):]
    return text


def _is_community_selection_turn(text: str) -> bool:
    try:
        from backend.ai.conversation_flow import is_post_success_response
        if is_post_success_response(text or ""):
            return False
    except Exception:  # pragma: no cover
        pass
    full = (text or "").lower()
    # Expiry/photo questions that mention the chosen school must not steal
    # the chip rail ("I'll list under Alameda Unified. When does it expire?").
    try:
        from backend.ai.ai_engine import _is_allergen_ask, _is_expiry_ask
        from backend.ai.conversation_flow import _is_description_ask
        if (
            _is_expiry_ask(full)
            or _is_allergen_ask(full)
            or _is_description_ask(full)
        ):
            if not any(k in full for k in (
                "which community", "which school", "community should",
                "qué comunidad", "cuál escuela", "cual escuela",
            )):
                return False
    except Exception:
        pass
    if any(k in full for k in ("expire", "expiry", "best by", "good until", "use by")):
        if not any(k in full for k in (
            "which community", "which school", "community should",
        )):
            return False
    if "?" not in full and "¿" not in full:
        return False
    return (
        any(c in full for c in _COMMUNITY_CUES)
        and any(k in full for k in _COMMUNITY_PROMPT_KEYS)
    )


def _extract_community_names_from_text(text: str) -> List[str]:
    """Pull community/school names from assistant copy (community segment only)."""
    if not text:
        return []

    segment = _community_relevant_segment(text)
    names: List[str] = []
    seen: set[str] = set()

    def _keep(raw: str) -> None:
        cleaned = _sanitize_community_name(raw)
        if not _looks_like_community_name(cleaned):
            return
        key = cleaned.lower()
        if key in seen:
            return
        seen.add(key)
        names.append(cleaned)

    quote_pat = r'["\'\u201c\u201d]([^\u201c\u201d"\']{2,60})["\'\u201c\u201d]'
    for match in re.finditer(quote_pat, segment):
        _keep(match.group(1))

    for match in re.finditer(
        r"(?:linked to|connected to|set to|list(?:ed)? under|list this under|"
        r"post (?:it |this )?(?:to|under)|profile is(?:\s+set to|\s+linked to|\s+connected to)?)\s+"
        r"([A-Za-z][\w\s\-]{2,48}?)(?:[\?\.,!—\-]|$|\s+(?:should|or|and|—))",
        segment,
        re.I,
    ):
        _keep(match.group(1))

    for match in re.finditer(
        r"\b([A-Z][a-z]+(?:\s+[A-Z][a-z]+){0,3})\b",
        segment,
    ):
        _keep(match.group(1))

    return names


def should_load_active_communities(
    response_text: str,
    last_user_message: str = "",
    user_context: Optional[Dict[str, Any]] = None,
) -> bool:
    """Whether this turn needs the active-communities catalog for chips."""
    if user_context and user_context.get("active_communities"):
        return False
    return _is_community_list_pick_turn(response_text, last_user_message)


def _user_chose_different_community(last_user_message: str) -> bool:
    low = (last_user_message or "").lower()
    return any(cue in low for cue in _DIFFERENT_COMMUNITY_USER_CUES)


def _response_has_profile_community_default(response_text: str) -> bool:
    full = (response_text or "").lower()
    return any(k in full for k in (
        "linked to", "connected to", "set to", "profile is",
        "profile community", "your profile",
    ))


def _is_open_community_pick(response_text: str) -> bool:
    full = (response_text or "").lower()
    if "?" not in full and "¿" not in full:
        return False
    if not any(c in full for c in _COMMUNITY_CUES):
        return False
    if _response_has_profile_community_default(response_text):
        return False
    return any(k in full for k in _OPEN_COMMUNITY_PICK_KEYS)


def _is_community_list_pick_turn(
    response_text: str,
    last_user_message: str = "",
) -> bool:
    """User rejected profile default — show full community catalog as chips."""
    if _user_chose_different_community(last_user_message):
        return bool(
            _is_open_community_pick(response_text)
            or _is_community_selection_turn(response_text)
        )
    return _is_open_community_pick(response_text)


def _active_community_rows(
    user_context: Optional[Dict[str, Any]],
    tool_results: Optional[List[Dict[str, Any]]],
) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    seen: set[str] = set()

    def _add(row: Any) -> None:
        if not isinstance(row, dict):
            return
        name = str(row.get("name") or "").strip()
        cid = str(row.get("id") or name).strip()
        if not name or cid in seen:
            return
        seen.add(cid)
        rows.append({"id": row.get("id"), "name": name})

    ctx = user_context if isinstance(user_context, dict) else {}
    for row in ctx.get("active_communities") or []:
        _add(row)

    for entry in reversed(tool_results or []):
        if not isinstance(entry, dict):
            continue
        tool = str(entry.get("tool") or "").lower()
        raw = entry.get("result")
        result = raw if isinstance(raw, dict) else {}
        if tool == "get_active_communities" or result.get("communities"):
            for row in result.get("communities") or []:
                _add(row)

    return rows


def _profile_community_name(user_context: Optional[Dict[str, Any]]) -> str:
    ctx = user_context if isinstance(user_context, dict) else {}
    entities = ctx.get("last_intent_entities") or {}
    if isinstance(entities, dict):
        name = entities.get("community_name")
        if name:
            return str(name).strip()
    for field in ("community_name", "default_community_name", "organization"):
        val = ctx.get(field)
        if val:
            return str(val).strip()
    return ""


def _chips_for_community_list_pick(
    response_text: str,
    language: str,
    last_user_message: str = "",
    user_context: Optional[Dict[str, Any]] = None,
    tool_results: Optional[List[Dict[str, Any]]] = None,
) -> List[Chip]:
    """All active communities as chips after user picks 'Different community'."""
    if not _is_community_list_pick_turn(response_text, last_user_message):
        return []

    es = language == "es"
    exclude = _profile_community_name(user_context) if _user_chose_different_community(last_user_message) else ""
    exclude_key = exclude.lower()

    chips: List[Chip] = []
    for row in _active_community_rows(user_context, tool_results):
        name = row["name"]
        if exclude_key and name.lower() == exclude_key:
            continue
        if es:
            chips.append({"label": name, "message": f"Sí, publicar en {name}"})
        else:
            chips.append({"label": name, "message": f"Yes, list under {name}"})
        if len(chips) >= _MAX_COMMUNITY_CHIPS:
            break

    if not chips:
        return []

    return chips


def _community_names_from_context(
    user_context: Optional[Dict[str, Any]],
    tool_results: Optional[List[Dict[str, Any]]],
) -> List[str]:
    names: List[str] = []
    seen: set[str] = set()

    def _add(raw: Any) -> None:
        cleaned = _sanitize_community_name(str(raw or ""))
        if not _looks_like_community_name(cleaned):
            return
        key = cleaned.lower()
        if key in seen:
            return
        seen.add(key)
        names.append(cleaned)

    ctx = user_context if isinstance(user_context, dict) else {}
    entities = ctx.get("last_intent_entities") or {}
    if isinstance(entities, dict):
        _add(entities.get("community_name"))

    for field in ("community_name", "organization", "default_community_name"):
        _add(ctx.get(field))

    for entry in reversed(tool_results or []):
        if not isinstance(entry, dict):
            continue
        raw = entry.get("result")
        result = raw if isinstance(raw, dict) else {}
        _add(result.get("suggested_community_name"))
        communities = result.get("communities") or []
        if isinstance(communities, list):
            for row in communities:
                if isinstance(row, dict):
                    _add(row.get("name"))

    return names


def _chips_for_community_selection(
    response_text: str,
    language: str,
    user_context: Optional[Dict[str, Any]] = None,
    tool_results: Optional[List[Dict[str, Any]]] = None,
) -> List[Chip]:
    """Named community chips for donate/post community confirmation."""
    if not _is_community_selection_turn(response_text):
        return []

    es = language == "es"
    names: List[str] = []
    seen: set[str] = set()

    for source in (
        _community_names_from_context(user_context, tool_results),
        _extract_community_names_from_text(response_text),
    ):
        for name in source:
            key = name.lower()
            if key not in seen:
                seen.add(key)
                names.append(name)

    if not names:
        return []

    chips: List[Chip] = []
    for name in names[:3]:
        if es:
            chips.append({
                "label": name,
                "message": f"Sí, publicar en {name}",
            })
        else:
            chips.append({
                "label": name,
                "message": f"Yes, list under {name}",
            })

    if es:
        chips.append({
            "label": "Otra comunidad",
            "message": "Usar otra comunidad",
        })
    else:
        chips.append({
            "label": "Different community",
            "message": "Use a different community",
        })

    return chips


def is_hands_on_share_active(
    message: str = "",
    history: Optional[List[Dict[str, Any]]] = None,
    assistance_reminder: str = "",
) -> bool:
    """True when the donor is mid hands-on share (not guided form)."""
    if _user_chose_hands_on(message or "", assistance_reminder or ""):
        return True
    from backend.ai.conversation_flow import (
        _assistance_mode_from_history,
        _hands_on_assistance_goal,
        is_posting_flow,
    )
    if _assistance_mode_from_history(history) != "hands_on":
        return False
    goal = _hands_on_assistance_goal(message or "", history)
    return goal == "share" or is_posting_flow(message or "", history)


def _has_explicit_quantity_in_thread(message: str, history: Optional[list]) -> bool:
    """True when the donor already gave a numeric quantity in this share."""
    from backend.ai.conversation_flow import (
        _current_posting_boundary_index,
        _parse_share_items_from_text,
    )
    boundary = _current_posting_boundary_index(history)
    scoped = (history or [])[boundary:]
    parts = [message or ""]
    for msg in reversed(scoped):
        if msg.get("role") == "user":
            parts.append(msg.get("message") or "")
    for part in parts:
        text = (part or "").strip()
        if not text:
            continue
        if re.fullmatch(r"\d+", text):
            return True
        if _parse_share_items_from_text(text) and re.search(r"\d", text):
            return True
        if re.match(r"^\s*\d+\s+", text):
            return True
    return False


def resolve_hands_on_share_chip_step(
    message: str = "",
    history: Optional[List[Dict[str, Any]]] = None,
    *,
    assistance_reminder: str = "",
    response_text: str = "",
) -> Optional[str]:
    """Fixed step label for hands-on share chips (state-driven, not reply heuristics)."""
    if not is_hands_on_share_active(message, history, assistance_reminder):
        return None

    from backend.ai.conversation_flow import (
        _assistant_last_asked_kind,
        _is_different_community_choice,
        _share_title_qty_from_thread,
        is_post_success_response,
        posting_flow_state,
    )

    if is_post_success_response(response_text or ""):
        return "success"

    extended = list(history or [])
    if response_text:
        extended.append({"role": "assistant", "message": response_text})
    last_asked = _assistant_last_asked_kind(extended)

    if last_asked == "claim_confirm":
        return None

    # Prefer what Nouri is asking THIS turn over incomplete checklist flags.
    # Common bug: assistant says "I'll list under X. When is it best by?"
    # before the donor tapped a community chip → community_confirmed is still
    # false, but expiry chips must win.
    if response_text:
        from backend.ai.ai_engine import (
            _is_allergen_ask,
            _is_expiry_ask,
            _is_post_confirm_ask,
        )
        from backend.ai.conversation_flow import _is_description_ask

        if _is_allergen_ask(response_text) or last_asked == "allergen":
            return "allergen"
        if _is_post_confirm_ask(response_text) or last_asked == "post_confirm":
            # Ready-to-post without a photo → attach nudge, not Yes/post.
            state_early = posting_flow_state(message, history)
            reply_l = (response_text or "").lower()
            photo_evidence = bool(state_early.get("has_photo")) or any(k in reply_l for k in (
                "with photo", "with a photo", "photo attached", "photos received",
                "got your photo", "image:", "con foto", "foto adjunta",
            ))
            if not photo_evidence:
                return "photo"
            return "post_confirm"
        if _is_expiry_ask(response_text) or last_asked == "expiry":
            return "expiry"
        if _is_description_ask(response_text) or last_asked == "description":
            return "description"
        if last_asked == "photo":
            return "photo"
        photo_ask = any(k in (response_text or "").lower() for k in (
            "photo", "picture", "foto", "imagen",
        )) and any(k in (response_text or "").lower() for k in (
            "attach", "upload", "add a", "required", "please", "snap", "sube",
        ))
        if photo_ask and not _is_post_confirm_ask(response_text):
            return "photo"
        if last_asked == "community":
            return "community"

    title, _, _ = _share_title_qty_from_thread(history, message)
    if not title:
        return "food_qty"
    if not _has_explicit_quantity_in_thread(message, history):
        return "qty"

    if _is_different_community_choice(message) or _user_chose_different_community(message):
        return "community_pick"

    state = posting_flow_state(message, history)
    if not state.get("community_confirmed"):
        return "community"
    if not state.get("expiry_provided"):
        return "expiry"
    if not state.get("description_provided"):
        return "description"
    if not state.get("has_photo"):
        return "photo"
    if state.get("post_summary_offered") or last_asked == "post_confirm":
        return "post_confirm"
    return "post_confirm"


def _hands_on_chip(label: str, message: str, step: str) -> Chip:
    return {
        "label": label,
        "message": message,
        "kind": "hands_on_step",
        "step": step,
    }


def build_labeled_hands_on_share_chips(
    step: str,
    language: str = "en",
    *,
    user_context: Optional[Dict[str, Any]] = None,
    message: str = "",
    history: Optional[List[Dict[str, Any]]] = None,
) -> List[Chip]:
    """Fixed chip sets per hands-on share step — independent of AI wording."""
    es = language == "es"
    ctx = user_context or {}
    suggested = str(ctx.get("suggested_community") or "").strip()
    communities = list(ctx.get("active_communities") or [])

    if step == "food_qty":
        if es:
            return [
                _hands_on_chip("5 manzanas", "5 manzanas", step),
                _hands_on_chip("2 panes", "2 panes", step),
                _hands_on_chip("Verduras — 1 caja", "Verduras — 1 caja", step),
                _hands_on_chip("Huevos — 1 docena", "Huevos — 1 docena", step),
            ]
        return [
            _hands_on_chip("5 apples", "5 apples", step),
            _hands_on_chip("2 loaves of bread", "2 loaves of bread", step),
            _hands_on_chip("Vegetables — 1 box", "Vegetables — 1 box", step),
            _hands_on_chip("Eggs — 1 dozen", "Eggs — 1 dozen", step),
        ]

    if step == "qty":
        return [
            _hands_on_chip("1", "1", step),
            _hands_on_chip("3", "3", step),
            _hands_on_chip("5", "5", step),
            _hands_on_chip("10", "10", step),
        ]

    if step == "community":
        chips: List[Chip] = []
        name = suggested or (communities[0] if communities else "")
        if name:
            if es:
                chips.append(_hands_on_chip(name, f"Sí, publicar en {name}", step))
            else:
                chips.append(_hands_on_chip(name, f"Yes, list under {name}", step))
        if es:
            chips.append(_hands_on_chip("Otra comunidad", "Usar otra comunidad", step))
        else:
            chips.append(_hands_on_chip("Different community", "Use a different community", step))
        return chips[:_MAX_COMMUNITY_CHIPS]

    if step == "community_pick":
        pick_from = communities
        if suggested:
            pick_from = [c for c in communities if c.lower() != suggested.lower()] or communities
        chips = []
        for name in pick_from[:_MAX_COMMUNITY_CHIPS]:
            if es:
                chips.append(_hands_on_chip(name, f"Sí, publicar en {name}", step))
            else:
                chips.append(_hands_on_chip(name, f"Yes, list under {name}", step))
        return chips

    if step == "expiry":
        if es:
            return [
                _hands_on_chip("Mañana", "Mañana", step),
                _hands_on_chip("En 2 días", "En 2 días", step),
                _hands_on_chip("En 3 días", "En 3 días", step),
                _hands_on_chip("En un mes", "En un mes", step),
            ]
        return [
            _hands_on_chip("Tomorrow", "Tomorrow", step),
            _hands_on_chip("In 2 days", "In 2 days", step),
            _hands_on_chip("In 3 days", "In 3 days", step),
            _hands_on_chip("In a month", "In a month", step),
        ]

    if step == "description":
        if es:
            return [
                _hands_on_chip("Sigue sellado", "Sigue sellado", step),
                _hands_on_chip("Casero, refrigerado", "Casero, refrigerado", step),
                _hands_on_chip("Sobras variadas", "Sobras variadas", step),
            ]
        return [
            _hands_on_chip("Still sealed", "Still sealed", step),
            _hands_on_chip("Homemade, refrigerated", "Homemade, refrigerated", step),
            _hands_on_chip("Assorted leftovers", "Assorted leftovers", step),
        ]

    if step == "photo":
        if es:
            return [_hands_on_chip("Adjuntar foto", "Adjuntar foto", step)]
        return [_hands_on_chip("Attach a photo", "Attach a photo", step)]

    if step == "post_confirm":
        if es:
            return [
                _hands_on_chip("Sí, publícalo", "Sí, publícalo", step),
                _hands_on_chip("Espera, edítalo", "Espera, edítalo", step),
                _hands_on_chip("Cancelar", "Cancelar", step),
            ]
        return [
            _hands_on_chip("Yes, post it", "Yes, post it", step),
            _hands_on_chip("Wait, edit it", "Wait, edit it", step),
            _hands_on_chip("Cancel", "Cancel", step),
        ]

    if step == "allergen":
        if es:
            return [
                _hands_on_chip("Sin alérgenos", "Sin alérgenos", step),
                _hands_on_chip("Solo gluten", "Solo gluten", step),
                _hands_on_chip("Lácteos", "Lácteos", step),
                _hands_on_chip("Frutos secos", "Frutos secos", step),
            ]
        return [
            _hands_on_chip("No allergens", "No allergens", step),
            _hands_on_chip("Just gluten", "Just gluten", step),
            _hands_on_chip("Dairy", "Dairy", step),
            _hands_on_chip("Nuts", "Nuts", step),
        ]

    if step == "success":
        if es:
            return [
                _hands_on_chip("Compartir algo más", "Compartir algo más", step),
                _hands_on_chip("Buscar comida cerca", "Buscar comida cerca", step),
                _hands_on_chip("Eso es todo por ahora", "Eso es todo por ahora", step),
            ]
        return [
            _hands_on_chip("Share something else", "Share something else", step),
            _hands_on_chip("Find food near me", "Find food near me", step),
            _hands_on_chip("That's all for now", "That's all for now", step),
        ]

    return []


def build_turn_suggestions(
    response_text: str,
    language: str = "en",
    tool_results: Optional[List[Dict[str, Any]]] = None,
    pending_suggestions: Optional[List[Any]] = None,
    detected_intent: Optional[str] = None,
    guide_mode: Optional[str] = None,
    user_context: Optional[Dict[str, Any]] = None,
    last_user_message: str = "",
    *,
    min_chips: int = 4,
    assistance_reminder: Optional[str] = None,
    history: Optional[List[Dict[str, Any]]] = None,
) -> List[Chip]:
    """Build up to six tappable chips for the chat UI.

    Priority-ordered: first matching category wins. Mixing Yes/No with
    claim/search/fork chips is worse than returning fewer chips.
    """
    out: List[Chip] = []
    seen: set[str] = set()

    def add(chip: Chip) -> None:
        label = _chip_label(chip)
        if not label or label in seen or len(out) >= _MAX_CHIPS:
            return
        seen.add(label)
        out.append(chip)

    # Align chip language with the reply when Spanish markers are present.
    text_l = (response_text or "").lower()
    if language != "es" and (
        "¿" in (response_text or "")
        or any(k in text_l for k in (
            " qué ", " cuál ", " cómo ", "quieres que", "paso a paso",
            "hazlo por", "comida",
        ))
    ):
        language = "es"

    # Lazy import: live quick-reply heuristics live in backend.ai.ai_engine.
    from backend.ai.ai_engine import generate_quick_replies

    # 0) Active GUIDED walkthrough — never re-show Open/Do it/Guide fork.
    if (
        _user_chose_guided(last_user_message or "", assistance_reminder or "")
        or _looks_like_guided_tutorial(response_text or "")
    ):
        guided_chips = _chips_for_guided_response(
            response_text or "", language, force=True,
        )
        if guided_chips:
            return guided_chips[:_MAX_CHIPS]

    # 1) Assistance fork (reminder or reply text) — exclusive.
    fork = share_assistance_fork_chips(
        response_text or "",
        language,
        user_message=last_user_message or "",
        assistance_reminder=assistance_reminder,
        guide_state=user_context if isinstance(user_context, dict) else None,
    )
    if fork:
        return fork[:_MAX_CHIPS]

    # 1b) Hands-on share — fixed chips per flow step (not reply-text heuristics).
    if is_hands_on_share_active(
        last_user_message or "", history, assistance_reminder or "",
    ):
        step = resolve_hands_on_share_chip_step(
            last_user_message or "",
            history,
            assistance_reminder=assistance_reminder or "",
            response_text=response_text or "",
        )
        if step:
            labeled = build_labeled_hands_on_share_chips(
                step,
                language,
                user_context=user_context,
                message=last_user_message or "",
                history=history,
            )
            if labeled:
                return labeled[:_MAX_CHIPS if step != "community_pick" else _MAX_COMMUNITY_CHIPS]

    # 2) GUIDED UI coaching — exclusive.
    guided_chips = _chips_for_guided_response(response_text or "", language)
    if guided_chips:
        return _filter_chips_to_match_response(
            response_text or "", guided_chips[:_MAX_CHIPS], language,
        )

    # 3) Search / claim tool chips — exclusive when present.
    search_chips = _chips_from_search_results(tool_results, language)
    if search_chips:
        return _filter_chips_to_match_response(
            response_text or "", search_chips[:_MAX_CHIPS], language,
        )

    multi_claim_chips = _chips_for_multi_claim_flow(response_text or "", language)
    if multi_claim_chips:
        return _filter_chips_to_match_response(
            response_text or "", multi_claim_chips[:_MAX_CHIPS], language,
        )

    # 4) Community selection — exclusive.
    list_pick_chips = _chips_for_community_list_pick(
        response_text or "",
        language,
        last_user_message=last_user_message,
        user_context=user_context,
        tool_results=tool_results,
    )
    if list_pick_chips:
        return _filter_chips_to_match_response(
            response_text or "", list_pick_chips[:_MAX_COMMUNITY_CHIPS], language,
        )

    community_chips = _chips_for_community_selection(
        response_text or "",
        language,
        user_context=user_context,
        tool_results=tool_results,
    )
    if community_chips:
        return _filter_chips_to_match_response(
            response_text or "", community_chips[:_MAX_COMMUNITY_CHIPS], language,
        )

    # 5) Next-step after successful tool (claim/post) — only when no ask chips.
    next_step = compute_next_step(tool_results, language)
    if next_step:
        add({
            "label": next_step.get("label") or "",
            "message": next_step.get("prompt") or next_step.get("message") or next_step.get("label") or "",
            "kind": "next_step",
        })

    # 6) Reply-text heuristics (photo / post confirm / food / yes-no…).
    if not out:
        for chip in generate_quick_replies(
            response_text or "",
            language,
            user_message=last_user_message or "",
            communities=(user_context or {}).get("active_communities") or None,
            suggested_community=(user_context or {}).get("suggested_community"),
            assistance_reminder=assistance_reminder,
            guide_state=user_context if isinstance(user_context, dict) else None,
        ):
            add(chip)

    # 7) Pending proactive suggestions only when nothing else matched.
    if not out:
        for item in pending_suggestions or []:
            if isinstance(item, str):
                add(item)
            elif isinstance(item, dict):
                if item.get("kind") == "next_step":
                    continue
                normalized = _normalize_proactive(item)
                if normalized:
                    add(normalized)

    if len(out) == 0:
        for chip in get_lazy_default_chips(language, detected_intent, guide_mode):
            add(chip)
            if len(out) >= _MAX_CHIPS:
                break

    return _filter_chips_to_match_response(response_text or "", out[:_MAX_CHIPS], language)
