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


_CLAIM_CONFIRM_RESPONSE_CUES = (
    "ready to claim",
    "claim these",
    "claim both",
    "claim all of these",
    "shall i claim",
    "want me to claim",
    "listo para reclamar",
    "reclamar estos",
    "reclamo estos",
)

_CLAIM_QTY_MULTI_CUES = (
    "how many of the",
    "how many for each",
    "quantity for each",
    "cuántos de",
    "cuantos de",
    "para cada",
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

    if any(c in text for c in _CLAIM_CONFIRM_RESPONSE_CUES):
        if es:
            return [
                {"label": "Sí, reclamar todos", "message": "Sí, reclama todos"},
                {"label": "Cambiar cantidades", "message": "Quiero cambiar las cantidades"},
            ]
        return [
            {"label": "Yes, claim these", "message": "Yes, claim these"},
            {"label": "Change amounts", "message": "I want to change the amounts"},
        ]

    if any(c in text for c in _CLAIM_QTY_MULTI_CUES) or (
        "how many" in text and any(k in text for k in ("and", "both", "each", "first", "second"))
    ):
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


_COMMUNITY_CUES = (
    "community", "school", "district", "neighborhood", "comunidad",
    "escuela", "distrito",
)

_COMMUNITY_PROMPT_KEYS = (
    "which community", "what community", "community is this", "community should",
    "post to", "share with", "listed under", "list this under", "list under",
    "for which community", "profile community", "your community",
    "confirm the community", "is this for", "different community",
    "profile is set", "profile is connected", "post it there",
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
    "different community", "use a different community", "another community",
    "other community", "otra comunidad", "usar otra comunidad",
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
    full = (text or "").lower()
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
        r"post (?:it )?(?:to|under)|profile is(?:\s+set to|\s+linked to|\s+connected to)?)\s+"
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
        if len(chips) >= _MAX_CHIPS:
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
            for row in communities[:5]:
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
) -> List[Chip]:
    """Build up to six tappable chips for the chat UI."""
    out: List[Chip] = []
    seen: set[str] = set()

    def add(chip: Chip) -> None:
        label = _chip_label(chip)
        if not label or label in seen or len(out) >= _MAX_CHIPS:
            return
        seen.add(label)
        out.append(chip)

    # Lazy import: live quick-reply heuristics live in backend.ai.ai_engine.
    # Importing at module load would create a cycle with ConversationEngine.
    from backend.ai.ai_engine import generate_quick_replies

    next_step = compute_next_step(tool_results, language)
    if next_step:
        # Normalize to FE shape: SuggestedActionButton uses message/prompt.
        add({
            "label": next_step.get("label") or "",
            "message": next_step.get("prompt") or next_step.get("message") or next_step.get("label") or "",
            "kind": "next_step",
        })

    search_chips = _chips_from_search_results(tool_results, language)
    for chip in search_chips:
        add(chip)

    multi_claim_chips = _chips_for_multi_claim_flow(response_text or "", language)
    for chip in multi_claim_chips:
        add(chip)

    list_pick_chips = _chips_for_community_list_pick(
        response_text or "",
        language,
        last_user_message=last_user_message,
        user_context=user_context,
        tool_results=tool_results,
    )
    if list_pick_chips:
        for chip in list_pick_chips:
            add(chip)
    else:
        community_chips = _chips_for_community_selection(
            response_text or "",
            language,
            user_context=user_context,
            tool_results=tool_results,
        )
        if community_chips:
            for chip in community_chips:
                add(chip)
        elif not search_chips:
            # Skip bare 1/2/3 quick-replies when Claim #N chips already match
            # the search results — avoids duplicate / less specific chips.
            for chip in generate_quick_replies(
                response_text or "",
                language,
                user_message=last_user_message or "",
                communities=(user_context or {}).get("active_communities") or None,
                suggested_community=(user_context or {}).get("suggested_community"),
            ):
                add(chip)

    for item in pending_suggestions or []:
        if isinstance(item, str):
            add(item)
        elif isinstance(item, dict):
            if item.get("kind") == "next_step":
                continue
            normalized = _normalize_proactive(item)
            if normalized:
                add(normalized)

    # Only fall back to generic lazy chips when nothing contextual was found.
    # Padding to min_chips mixed "Find food" with "Claim #1" / yes-no replies.
    if len(out) == 0:
        for chip in get_lazy_default_chips(language, detected_intent, guide_mode):
            add(chip)
            if len(out) >= _MAX_CHIPS:
                break

    return out[:_MAX_CHIPS]
