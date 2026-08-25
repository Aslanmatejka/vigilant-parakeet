"""Classify Do-it-for-me / share assistant turns for suggestion chips.

One class per turn. Prefer empty chips over wrong chips.
"""
from __future__ import annotations

from typing import Optional


CHIP_TURN_CLASSES = (
    "fork",
    "guided",
    "post_confirm",
    "photo",
    "description",
    "community",
    "allergen",
    "expiry",
    "food_qty",
    "food",
    "qty",
    "address",
    "success",
    "edit",
    "none",
)

# Classified turns must not fall through to legacy heuristics.
CLASSIFIED_EXCLUSIVE = frozenset({
    "fork", "guided", "post_confirm", "photo", "description", "community",
    "allergen", "expiry", "food_qty", "food", "qty", "address", "success", "edit",
})

# Share questions whose chips must beat leftover search/claim tool chips.
SHARE_ASK_CLASSES = frozenset({
    "post_confirm", "photo", "description", "community", "allergen",
    "expiry", "food_qty", "food", "qty", "address",
})


def _norm(text: str) -> str:
    return (text or "").lower()


PHOTO_EVIDENCE_CUES = (
    "photos received", "got your photo", "got the photo", "got a photo",
    "got the picture", "got your picture", "got a picture",
    "thanks for the photo", "thanks for the picture", "photo, thanks",
    "picture, thanks", "with your photos", "with photo", "with a photo",
    "has a photo", "photo attached", "already have a photo", "image:",
    "foto adjunta", "fotos recibidas", "con tus fotos", "con foto",
    "tengo la foto", "gracias por la foto",
)


def _is_address_turn(t: str) -> bool:
    has_addr = any(c in t for c in (
        "address", "street", " st ", " st.", " ave", "avenue", " rd", " road",
        "profile address", "what address", "which address",
        "pickup address", "dirección", "direccion", "calle", "main st",
    ))
    if not has_addr:
        return False
    if any(k in t for k in (
        "community", "school", "comunidad", "escuela", "list under", "warehouse",
        "ready to post", "shall i post", "with photo",
    )):
        return False
    return True


def _is_community_turn(t: str) -> bool:
    keys = (
        "list under", "list this under", "which community", "which school",
        "school should", "community should", "go under",
        "post under", "post this under", "post this to", "post it to",
        "should this go under", "should it go under", "under which",
        "for the community", "community for",
        "your community", "use that one", "linked to", "profile is linked",
        "profile is connected", "profile is set",
        "comunidad", "escuela", "listar bajo", "bajo qué", "bajo que",
        "publicar bajo", "en qué comunidad", "en que comunidad", "bajo cuál",
    )
    if not ("?" in t or "¿" in t):
        # Allow imperative community confirms with ?
        if not any(k in t for k in ("list under", "linked to", "use that one")):
            return False
    if not any(k in t for k in keys) and "listed under" not in t:
        return False
    # School mentioned while asking expiry/allergen/description → not community
    if any(k in t for k in (
        "when does it expire", "best by", "good until", "expiry date",
        "any allergen", "allergens", "allergen",
        "short description", "add a description", "describe the food",
        "attach a photo", "upload a photo", "need a photo",
    )):
        return False
    # Recap confirms that mention a school are post_confirm, not community.
    if any(k in t for k in (
        "ready to post", "ready to publish", "shall i post", "should i post",
        "look right", "looks right", "does this look", "sound good to post",
        "go ahead and share",
    )) and not any(k in t for k in (
        "your community", "which community", "which school", "list under",
        "list this under", "for the community", "linked to", "use that one",
        "community should", "post this to", "post it to", "post this under",
        "post under", "comunidad", "escuela",
    )):
        return False
    return True


def _is_photo_ask(t: str) -> bool:
    """True for a real photo request — not a description ask that mentions photo later."""
    from backend.ai.conversation_flow import _is_description_ask

    if _is_description_ask(t) and any(k in t for k in (
        "short description", "add a description", "description for",
        "describe the food", "describe it", "one sentence", "one-sentence",
        "still sealed", "people should know",
    )):
        # Description is primary; photo is next-step narration.
        if any(k in t for k in (
            "after that", "then i'll", "then i will", "afterwards",
            "next i'll", "next i will", "before the photo", "before we do the photo",
        )):
            return False
        # "Please add a short description … I'll need a photo" → description
        if "description" in t or "describe" in t:
            return False

    has_photo = any(k in t for k in ("photo", "picture", "foto", "imagen"))
    if not has_photo:
        return False
    ask = any(k in t for k in (
        "required", "please", "need", "upload", "attach", "add a", "add one",
        "before posting", "before we post", "mandar", "sube", "subir",
        "photo of", "picture of", "snap", "send a photo", "send a picture",
        "send one", "so we can post", "para publicar",
        "without a photo", "without photo", "skip the photo",
    ))
    if not ask:
        return False
    # Post-confirm / summary phrasing
    if any(k in t for k in PHOTO_EVIDENCE_CUES) or any(k in t for k in (
        "look right", "looks right", "does this look",
        "ready to post", "shall i post", "want me to post",
        "listo para publicar", "lo publico", "lo publicamos", "publicarlo",
    )):
        return False
    return True


def _is_post_confirm_turn(t: str) -> bool:
    if _is_address_turn(t):
        return False
    if _is_community_turn(t):
        # "Want me to post this to your community" is community, not post confirm
        if any(k in t for k in (
            "your community", "list under", "linked to", "use that one",
            "for the community", "which community", "which school",
        )) and not any(k in t for k in (
            "ready to post", "look right", "looks right", "does this look",
            "sound good to post", "with photo",
        )):
            return False

    if any(k in t for k in (
        "ready to post", "ready to publish",
        "sound good to post", "sounds good to post",
        "go ahead and share", "shall i go ahead", "should i go ahead",
        "confirm and post", "before i post",
        "listo para publicar", "¿lo publico", "¿lo publicamos",
    )):
        return True
    if any(k in t for k in (
        "look right", "looks right", "does this look", "does that look",
    )) and not _is_address_turn(t):
        return True
    if any(k in t for k in (
        "shall i post", "should i post", "want me to post",
        "good to post", "good to publish",
    )):
        # Community: "Should I post this under Alameda?" without ready/look right
        if any(k in t for k in (" under ", "list under", "your community", "linked to")):
            if not any(k in t for k in (
                "ready to post", "with photo", "look right", "looks right",
                "sound good", "good until", "expires",
            )):
                return False
        return True
    if any(k in t for k in ("look good", "looks good", "sound good", "sounds good")):
        if _is_address_turn(t):
            return False
        return any(k in t for k in ("post", "publish", "listing", "share"))
    return False


def _is_real_fork_ask(
    t: str,
    *,
    user_message: str = "",
    assistance_reminder: str = "",
) -> bool:
    """True only for a genuine do-it-for-me vs guide mode choice."""
    rem = (assistance_reminder or "").strip().lower()
    um = (user_message or "").strip().lower()
    combined = f"{t} {um} {rem}"

    if rem.startswith(("hands-on", "hands on", "modo manos", "guided", "guiado")):
        return False
    if rem.startswith(("assistance mode", "modo de ayuda")):
        return True

    # Already chose hands-on this session turn
    if any(k in um for k in (
        "do it for me", "hazlo por", "handle everything", "handle it for me",
    )):
        return False

    hands = any(k in t for k in (
        "do it for me", "handle everything", "handle the whole",
        "handle the search", "handle search", "want me to handle",
        "me to handle", "shall i handle", "prefer i handle",
        "handle it for you", "handle it in", "handle it,",
        "do this for you", "do everything for you", "fill everything",
        "hazlo por", "here in chat", "in chat for you", "aquí en el chat",
        "aqui en el chat", "lo haga", "todo por ti", "por ti aquí", "por ti aqui",
        "would you like me to handle",
    ))
    guide = any(k in t for k in (
        "guide me", "walk you through", "step by step", "paso a paso",
        "guíame", "guiame", "te guío", "te guio", "yo te guio",
        "open the form", "open find food", "open request food",
        "on the share food page", "on the find food page",
        "on the request food page", "or guide you", "or walk you",
        "prefer i walk", "the form yourself", "yourself?",
    ))
    if hands and guide:
        return True

    vague = any(k in t for k in (
        "how would you like", "how do you want", "how should we",
        "how would you prefer", "prefer to proceed", "like to proceed",
        "would you rather",
        "como quieres", "como prefieres", "de que forma",
    ))
    share_ctx = any(k in combined for k in (
        "share", "sharing", "donate", "donating", "posting", "listing",
        "find food", "request food", "compartir", "donar", "publicar",
    ))
    return bool(vague and share_ctx)


def classify_share_chip_turn(
    text: str,
    *,
    user_message: str = "",
    assistance_reminder: Optional[str] = None,
) -> str:
    """Return the chip turn class for this assistant reply."""
    raw = text or ""
    t = _norm(raw)
    if not t:
        return "none"

    rem = assistance_reminder or ""

    # Guided tutorial
    if (
        t.lstrip().startswith(("guided", "guiado"))
        or "guided —" in t
        or "guided -" in t
        or "guiado —" in t
        or "guiado -" in t
    ):
        return "guided"

    try:
        from backend.agent.suggestion_chips import _looks_like_guided_tutorial
        if _looks_like_guided_tutorial(raw):
            return "guided"
    except Exception:
        pass

    if _is_real_fork_ask(t, user_message=user_message, assistance_reminder=rem):
        return "fork"

    try:
        from backend.ai.conversation_flow import is_post_success_response
        if is_post_success_response(raw):
            return "success"
    except Exception:
        pass
    if any(k in t for k in (
        "are shared", "is shared", "posted!", "posted your", "listing is live",
        "successfully posted", "anything else you want to share",
        "share another", "you're all set", "awaiting admin approval",
    )):
        return "success"

    if any(k in t for k in (
        "what should i change", "what would you like to change",
        "what do you want to change", "what needs to change",
        "qué debo cambiar", "que debo cambiar",
        "qué quieres cambiar", "que quieres cambiar",
    )):
        return "edit"

    if _is_post_confirm_turn(t):
        return "post_confirm"

    if _is_photo_ask(t):
        return "photo"

    try:
        from backend.ai.conversation_flow import _is_description_ask
        if _is_description_ask(t):
            return "description"
    except Exception:
        pass

    if _is_community_turn(t):
        return "community"

    if _is_address_turn(t) and any(k in t for k in (
        "profile address", "use your address", "what address", "which address",
        "does that look good", "does this look good", "look good to you",
        "look right", "right address", "correct address", "that address",
        "where should", "pickup address", "dirección",
    )):
        return "address"

    # Import allergen/expiry helpers without circular import at module load
    try:
        from backend.ai import ai_engine as _ae
        if _ae._is_allergen_ask(t):
            return "allergen"
        if _ae._is_expiry_ask(t):
            return "expiry"
        if _ae._is_combined_food_qty_ask(t):
            return "food_qty"
    except Exception:
        # Fallback inline heuristics if ai_engine not ready
        if any(k in t for k in ("allerg", "alérgen", "contain nuts", "any allergens")):
            return "allergen"
        if any(k in t for k in ("when does it expire", "best by", "good until", "expir")):
            return "expiry"
        if ("what food" in t or "tell me what you have" in t) and (
            "how much" in t or "how many" in t
        ):
            return "food_qty"

    if any(k in t for k in (
        "how many", "how much", "cuántos", "cuántas", "qué unidad", "que unidad",
    )) and not any(k in t for k in (
        "what food", "what would you like to share", "tell me what you have",
    )):
        return "qty"

    if any(k in t for k in (
        "what food", "what would you like to share", "what would you like to donate",
        "what are you sharing", "what are you donating", "what is it", "what's the food",
        "what do you have", "tell me what you have", "what kind of food",
        "food name", "tell me the food",
        "qué comida", "que comida", "qué quieres compartir", "qué tienes",
    )):
        return "food"

    return "none"


def chips_for_turn_class(
    turn: str,
    *,
    lang: str = "en",
    text: str = "",
    suggested_community: Optional[str] = None,
    communities: Optional[list] = None,
) -> list[str]:
    """Return chip labels for a classified turn (EN/ES)."""
    es = lang == "es"
    communities = communities or []

    if turn == "post_confirm":
        t = _norm(text)
        photo_evidence = any(k in t for k in PHOTO_EVIDENCE_CUES) or "http" in t
        photo_nudge = (
            not photo_evidence
            and any(k in t for k in (
                "ready to post", "ready to publish",
                "shall i post", "should i post", "want me to post",
            ))
            and not any(k in t for k in (
                "look right", "looks right", "does this look", "does that look",
                "sound good", "sounds good", "go ahead and share",
            ))
        )
        if photo_nudge:
            return ["Adjuntar foto"] if es else ["Attach a photo"]
        if es:
            return ["Sí, publícalo", "Espera, edítalo", "Cancelar"]
        return ["Yes, post it", "Wait, edit it", "Cancel"]

    if turn == "photo":
        return ["Adjuntar foto"] if es else ["Attach a photo"]

    if turn == "description":
        if es:
            return ["Sigue sellado", "Casero, refrigerado", "Sobras variadas"]
        return ["Still sealed", "Homemade, refrigerated", "Assorted leftovers"]

    if turn == "allergen":
        if es:
            return ["Sin alérgenos", "Solo gluten", "Lácteos", "Frutos secos"]
        return ["No allergens", "Just gluten", "Dairy", "Nuts"]

    if turn == "expiry":
        if es:
            return ["Mañana", "En 2 días", "En 3 días", "En un mes"]
        return ["Tomorrow", "In 2 days", "In 3 days", "In a month"]

    if turn == "food_qty":
        if es:
            return ["5 manzanas", "2 panes", "Verduras — 1 caja", "Huevos — 1 docena"]
        return ["5 apples", "2 loaves of bread", "Vegetables — 1 box", "Eggs — 1 dozen"]

    if turn == "food":
        if es:
            return ["Pan", "Frutas", "Verduras", "Comida preparada"]
        return ["Bread", "Fruit", "Vegetables", "Prepared meal"]

    if turn == "qty":
        return ["1", "3", "5", "10"]

    if turn == "address":
        if es:
            return ["Sí, usa esa", "Es otra dirección", "No tengo una guardada"]
        return ["Yes, use that one", "Use a different address", "I don't have one saved"]

    if turn == "success":
        if es:
            return ["Compartir otra cosa", "Buscar comida", "Eso es todo"]
        return ["Share something else", "Find food near me", "That's all for now"]

    if turn == "edit":
        if es:
            return ["La cantidad", "La dirección", "Otro alimento", "La comunidad"]
        return ["The quantity", "The address", "Different food", "The community"]

    if turn == "community":
        pick = None
        t = _norm(text)
        if suggested_community and suggested_community.lower() in t:
            pick = suggested_community
        else:
            try:
                from backend.agent.suggestion_chips import _extract_community_names_from_text
                named = [
                    n for n in _extract_community_names_from_text(text)
                    if n.lower() not in {"school district", "community", "your community"}
                ]
                if named:
                    pick = named[0]
            except Exception:
                pass
            if not pick and suggested_community:
                # Prefer name in reply over stale suggested
                import re
                m = re.search(
                    r"(?:linked to|connected to|use|under|to|—|-)\s*"
                    r"([A-Z][A-Za-z0-9 &.'/-]{2,48}?)(?:\s+for\s+the\s+community)?(?:\s*\?|\s*$|[.!,])",
                    (text or "").strip(),
                )
                if m:
                    name = m.group(1).strip(" —-?")
                    if len(name) >= 3 and name.lower() not in {"the", "this", "that", "your"}:
                        pick = name
                if not pick:
                    pick = suggested_community
        if pick:
            return [pick[:48], "Otra comunidad" if es else "Different community"]
        if communities:
            return list(communities[:4])
        if es:
            return ["Usar la de mi perfil", "Otra comunidad"]
        return ["Use my profile community", "Different community"]

    return []
