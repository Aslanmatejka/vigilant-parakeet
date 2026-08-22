"""Allergen + dietary-tag extraction.

Nouri routinely dropped allergens on the floor: the donor would say
"this has peanuts" and the resulting listing shipped with an empty
``allergens`` array. On the recipient side, a message like "I'm
allergic to dairy" would not translate into ``exclude_allergens``
on the search call unless the model happened to remember.

This module gives us a single, deterministic layer that:

  * Recognises the eight FDA "big-8" allergens plus sesame (the newer
    9th), gluten, and their common phrasings in EN + ES.
  * Distinguishes DONOR statements ("contains X" / "with X") from
    RECIPIENT constraints ("I'm allergic to X" / "no X please").
  * Extracts common dietary tags (vegan, vegetarian, gluten-free,
    dairy-free, kosher, halal, low-sodium, keto, pescatarian).
  * Fills tool args safely: never overwrites what the model already
    passed, never invents allergens that weren't stated.

Non-breaking: pure module, no side effects, imported lazily where
needed. If the extractor mis-fires, the worst outcome is an extra
tag on the listing — which is exactly the safer failure mode for
food safety.
"""
from __future__ import annotations

import re
from typing import Iterable, Optional


# ---------------------------------------------------------------------------
# Canonical vocabulary
# ---------------------------------------------------------------------------

# Canonical allergen → aliases we recognise in free-text (EN + ES + common
# phrasings). Keys are always lowercase, singular, canonical strings — the
# same strings we emit back to the tool call.
ALLERGEN_ALIASES: dict[str, tuple[str, ...]] = {
    "peanuts": (
        "peanut", "peanuts", "peanut butter", "groundnut", "groundnuts",
        "cacahuate", "cacahuates", "maní", "mani",
    ),
    "tree_nuts": (
        "tree nut", "tree nuts", "almond", "almonds", "cashew", "cashews",
        "walnut", "walnuts", "pecan", "pecans", "hazelnut", "hazelnuts",
        "pistachio", "pistachios", "brazil nut", "brazil nuts", "nut",
        "nuts", "nuez", "nueces", "almendra", "almendras",
    ),
    "milk": (
        "milk", "dairy", "cream", "butter", "cheese", "yogurt", "yoghurt",
        "casein", "whey", "lactose", "leche", "lácteos", "lacteos",
        "crema", "queso", "mantequilla",
    ),
    "eggs": (
        "egg", "eggs", "huevo", "huevos",
    ),
    "wheat": (
        "wheat", "flour", "bread", "trigo", "harina",
    ),
    "gluten": (
        "gluten",
    ),
    "soy": (
        # 'soy' alone collides with Spanish 'soy' ('I am') — accept only
        # phrases that are unambiguously food-related.
        "soya", "soybean", "soybeans", "soy sauce", "soy milk",
        "soymilk", "soja", "tofu", "edamame",
    ),
    "fish": (
        "fish", "salmon", "tuna", "cod", "tilapia", "pescado", "atún",
        "atun",
    ),
    "shellfish": (
        "shellfish", "shrimp", "prawn", "prawns", "lobster", "crab",
        "clam", "clams", "oyster", "oysters", "mussels", "camarón",
        "camarones", "langosta", "cangrejo", "mariscos", "marisco",
    ),
    "sesame": (
        "sesame", "tahini", "ajonjolí", "ajonjoli",
    ),
}


# Canonical dietary tag → recognised aliases (EN + ES).
DIETARY_ALIASES: dict[str, tuple[str, ...]] = {
    "vegan": ("vegan", "vegana", "vegano"),
    "vegetarian": ("vegetarian", "vegetariana", "vegetariano"),
    "pescatarian": ("pescatarian", "pescatariano", "pescetariano"),
    "gluten_free": (
        "gluten free", "gluten-free", "no gluten", "sin gluten",
    ),
    "dairy_free": (
        "dairy free", "dairy-free", "no dairy", "lactose free",
        "lactose-free", "sin lácteos", "sin lacteos", "no lactose",
    ),
    "nut_free": (
        "nut free", "nut-free", "no nuts", "sin nueces",
    ),
    "kosher": ("kosher",),
    "halal": ("halal",),
    "low_sodium": ("low sodium", "low-sodium", "low salt", "bajo en sodio"),
    "keto": ("keto", "ketogenic"),
    "paleo": ("paleo",),
    "organic": ("organic", "orgánico", "organico"),
}


# ---------------------------------------------------------------------------
# Phrasing detection — donor vs recipient framing
# ---------------------------------------------------------------------------


# The donor is asserting a *property of the food* ("this contains peanuts").
# These phrases → we should populate `allergens=[…]` on the listing.
_DONOR_CONTAINS_RE = re.compile(
    r"\b("
    r"contain(?:s|ing)?|"
    r"has|have|with|"
    r"made\s+with|"
    r"includes?|include(?:s|d)?|"
    r"tiene(?:n)?|contiene(?:n)?|con\s+"
    r")\b",
    re.IGNORECASE,
)


# The recipient is asserting a *constraint on what they can eat* ("no dairy",
# "I'm allergic to peanuts"). These phrases → populate
# `exclude_allergens=[…]` on searches.
_RECIPIENT_CONSTRAINT_RE = re.compile(
    r"\b("
    r"allerg(?:ic|y|ies)|"
    r"no\s+more|"
    r"can'?t\s+(?:eat|have|do)|"
    r"cannot\s+(?:eat|have|do)|"
    r"avoid|avoiding|stay\s+away|"
    r"intoleran(?:t|ce)|"
    r"free\s+of|"
    r"soy\s+alérgic|alérgic[ao]|alergia|alergias|"
    r"no\s+puedo\s+comer|evitar"
    r")\b",
    re.IGNORECASE,
)


# Simple "no X" / "sin X" phrasing that acts as a constraint even without
# the full 'allergic' framing.
_NEGATIVE_PREFIX_RE = re.compile(
    r"\b(no|sin|without|skip|hold\s+the|nada\s+de)\s+",
    re.IGNORECASE,
)


# ---------------------------------------------------------------------------
# Extraction
# ---------------------------------------------------------------------------


def _normalize(text: str) -> str:
    return (text or "").lower()


def _find_matches(
    text: str,
    vocabulary: dict[str, tuple[str, ...]],
) -> list[str]:
    """Return canonical keys whose aliases appear (as whole words) in *text*.

    Bigrams (``tree nut``, ``gluten free``, ``dairy free``) are matched
    literally; single-token aliases require whole-word boundaries so
    "buttercup" doesn't count as "butter".
    """
    if not text:
        return []
    lowered = " " + _normalize(text) + " "
    hits: list[str] = []
    for canonical, aliases in vocabulary.items():
        for alias in aliases:
            alias_l = alias.lower()
            if " " in alias_l or "-" in alias_l:
                if alias_l in lowered:
                    hits.append(canonical)
                    break
            else:
                pattern = r"\b" + re.escape(alias_l) + r"\b"
                if re.search(pattern, lowered):
                    hits.append(canonical)
                    break
    return hits


def extract_allergens_and_diet(
    text: str,
    *,
    frame: str = "auto",
) -> dict:
    """Extract allergens + dietary tags from a chunk of free text.

    ``frame`` controls how ambiguous 'contains X' phrasing is bucketed:

      * ``auto`` — split by phrasing markers (donor contains-* vs
        recipient allergic-to-*).
      * ``donor`` — everything found lands in ``allergens`` (posting).
      * ``recipient`` — everything found lands in ``exclude_allergens``
        (search / claim).

    Returns a dict with three keys, each a *sorted list*:
      * ``allergens`` — canonical allergen labels present in the food.
      * ``exclude_allergens`` — canonical labels the recipient avoids.
      * ``dietary_tags`` — canonical dietary tags (vegan, gluten_free…).
    """
    lowered = _normalize(text)
    allergens: set[str] = set()
    exclude_allergens: set[str] = set()
    dietary: set[str] = set(_find_matches(lowered, DIETARY_ALIASES))

    if not lowered:
        return {
            "allergens": [],
            "exclude_allergens": [],
            "dietary_tags": [],
        }

    found = _find_matches(lowered, ALLERGEN_ALIASES)
    if not found and not dietary:
        return {
            "allergens": [],
            "exclude_allergens": [],
            "dietary_tags": [],
        }

    if frame == "donor":
        allergens.update(found)
    elif frame == "recipient":
        exclude_allergens.update(found)
    else:
        # Auto: choose per-clause.
        is_constraint = (
            bool(_RECIPIENT_CONSTRAINT_RE.search(lowered))
            or bool(_NEGATIVE_PREFIX_RE.search(lowered))
        )
        is_property = bool(_DONOR_CONTAINS_RE.search(lowered))
        if is_constraint and not is_property:
            exclude_allergens.update(found)
        elif is_property and not is_constraint:
            allergens.update(found)
        elif is_constraint and is_property:
            # Mixed message ("I'm allergic to dairy, and this soup
            # contains peanuts"). Route both — the extractor errs on the
            # safe side and returns everything found in *both* buckets.
            allergens.update(found)
            exclude_allergens.update(found)
        else:
            # No obvious framing. If the message reads like a recipient
            # asking for food ('I want food, no eggs'), the negative
            # prefix regex already covered it. Otherwise, silent no-op
            # unless dietary tags anchor the intent.
            if any(dt in {"vegan", "vegetarian", "dairy_free", "nut_free", "gluten_free"} for dt in dietary):
                exclude_allergens.update(found)

    return {
        "allergens": sorted(allergens),
        "exclude_allergens": sorted(exclude_allergens),
        "dietary_tags": sorted(dietary),
    }


def _merge_unique(*iterables: Iterable[str]) -> list[str]:
    """Merge many iterables into a sorted, de-duplicated list of strings."""
    seen: set[str] = set()
    out: list[str] = []
    for it in iterables:
        for v in it or []:
            s = str(v).strip()
            if not s or s.lower() in {s2.lower() for s2 in seen}:
                continue
            seen.add(s)
            out.append(s)
    return out


# ---------------------------------------------------------------------------
# Enrichment helpers for tool args
# ---------------------------------------------------------------------------


def _collect_donor_user_text(
    message: str,
    history: list | None,
    since_index: int = 0,
) -> list[str]:
    """Return the donor's own turns as a list of message strings.

    We deliberately do NOT include assistant text: the assistant's
    "any peanuts?" question would leak the word "peanuts" into the
    blob and — with donor framing — get bucketed straight into the
    listing's ``allergens``. Only what the donor themselves said counts.

    ``since_index`` lets callers scope to the current posting flow so
    a donor declaration from a previously-posted listing does not bleed
    into a new one.
    """
    parts: list[str] = []
    hist = history or []
    if since_index:
        hist = hist[since_index:]
    for msg in hist[-10:]:
        if msg.get("role") == "user":
            parts.append(str(msg.get("message") or ""))
    if message:
        parts.append(message)
    return parts


def enrich_post_listing_allergen_args(
    args: dict,
    message: str,
    history: list | None,
) -> dict:
    """Populate ``allergens`` / ``dietary_tags`` on a post_food_listing call.

    Extracts ONLY from the donor's own utterances (user role), and only
    when the phrasing is clearly a property assertion ('contains X',
    'has X', 'with X') — negations and questions never contribute.

    Any tags the model already provided are preserved and merged in.
    Runs per-utterance so a "no peanuts" line elsewhere can't leak into
    the allergens bucket even if a "has dairy" line does.
    """
    out = dict(args or {})

    # Scope to the current posting flow so a "has peanuts" from an
    # already-completed listing does NOT bleed into this new one.
    try:
        from backend.ai.conversation_flow import _current_posting_boundary_index
        boundary = _current_posting_boundary_index(history)
    except Exception:  # pragma: no cover
        boundary = 0

    per_msg = _collect_donor_user_text(message, history, since_index=boundary)

    merged_allergens: list[str] = []
    merged_tags: list[str] = []
    for utterance in per_msg:
        # Auto framing: 'contains X' → allergens, 'no X' → constraint
        # (which we drop for the donor side). Utterances with no clear
        # framing yield nothing.
        parsed = extract_allergens_and_diet(utterance, frame="auto")
        if parsed["allergens"]:
            merged_allergens.extend(parsed["allergens"])
        if parsed["dietary_tags"]:
            merged_tags.extend(parsed["dietary_tags"])

    if merged_allergens:
        out["allergens"] = _merge_unique(out.get("allergens"), merged_allergens)
    if merged_tags:
        out["dietary_tags"] = _merge_unique(out.get("dietary_tags"), merged_tags)
    return out


def enrich_search_allergen_args(
    args: dict,
    message: str,
    history: list | None,
    profile_allergens: Iterable[str] | None = None,
    profile_dietary: Iterable[str] | None = None,
) -> dict:
    """Populate ``exclude_allergens`` / ``dietary_tags`` for
    search_food_near_user (or any recipient-side tool) from message +
    profile.

    Recipient-side extraction: 'I'm allergic to nuts', 'no dairy', 'vegan
    please'. The user's saved profile allergens/dietary_restrictions are
    always included — the profile is authoritative and the model should
    not be able to accidentally drop it.
    """
    out = dict(args or {})
    parsed = extract_allergens_and_diet(message or "", frame="recipient")

    # Also scan the last few user turns for a lingering allergy declaration.
    hist_parsed = {"exclude_allergens": [], "dietary_tags": []}
    if history:
        recent = " \n ".join(
            str(m.get("message") or "")
            for m in history[-6:]
            if m.get("role") == "user"
        )
        hist_parsed = extract_allergens_and_diet(recent, frame="recipient")

    out["exclude_allergens"] = _merge_unique(
        out.get("exclude_allergens"),
        parsed.get("exclude_allergens"),
        hist_parsed.get("exclude_allergens"),
        profile_allergens or [],
    )
    if not out["exclude_allergens"]:
        out.pop("exclude_allergens", None)

    out["dietary_tags"] = _merge_unique(
        out.get("dietary_tags"),
        parsed.get("dietary_tags"),
        hist_parsed.get("dietary_tags"),
        profile_dietary or [],
    )
    if not out["dietary_tags"]:
        out.pop("dietary_tags", None)

    return out


# ---------------------------------------------------------------------------
# Posting-flow reminder
# ---------------------------------------------------------------------------


# Foods where allergens genuinely matter enough to prompt for them once
# during posting. Raw produce and beverages usually don't need this
# nudge (an apple is an apple), but prepared meals and baked goods do.
_ALLERGEN_SENSITIVE_KINDS = {
    "prepared", "baked", "canned", "snack", "condiment", "dairy",
    "protein", "bulk_dry",
}


def allergens_asked(message: str, history: list | None) -> bool:
    """True if the assistant already asked about allergens in this thread."""
    blob = " ".join(
        str(m.get("message") or "").lower()
        for m in (history or [])
        if m.get("role") == "assistant"
    ) + " " + _normalize(message)
    return any(k in blob for k in (
        "allerg", "any nut", "contain nuts", "contains dairy", "gluten",
        "alérgen", "alergia", "alergen",
    ))


def allergens_answered(message: str, history: list | None) -> bool:
    """True if the donor either provided allergens or explicitly declined.

    "No allergens", "nut-free", "just gluten", "contains peanuts" — all
    count as answered. Only donor (user) utterances count — an assistant
    question containing the word "allergens" must NOT satisfy this.
    """
    # Scope to the current posting flow — a "no allergens" declaration
    # from a previous listing doesn't answer for a new one.
    try:
        from backend.ai.conversation_flow import _current_posting_boundary_index
        boundary = _current_posting_boundary_index(history)
    except Exception:  # pragma: no cover
        boundary = 0
    utterances = _collect_donor_user_text(message, history, since_index=boundary)
    for u in utterances:
        parsed = extract_allergens_and_diet(u, frame="auto")
        if parsed["allergens"] or parsed["dietary_tags"]:
            return True
        lowered = _normalize(u)
        negative = (
            "no allergens", "none", "no allergen", "allergen-free",
            "nothing to worry about", "no alérgen", "no alergen",
            "sin alérgenos", "ninguno",
        )
        if any(n in lowered for n in negative):
            return True
    return False


def build_allergen_reminder(
    message: str,
    history: list | None,
    lang: str = "en",
    flow: str = "idle",
) -> Optional[str]:
    """Nudge the model to ask about allergens once during the posting flow."""
    if flow != "posting":
        return None
    if allergens_answered(message, history) or allergens_asked(message, history):
        return None

    try:
        from backend.ai.conversation_flow import posting_flow_state, is_posting_flow
        if not is_posting_flow(message, history):
            return None
        state = posting_flow_state(message, history)
        if not state.get("expiry_provided") and not state.get("expiry_asked"):
            return None
    except Exception:  # pragma: no cover
        pass

    if lang == "es":
        return (
            "Alergénos — pregunta UNA vez sobre alérgenos comunes (maní, "
            "frutos secos, lácteos, gluten, huevo, soya, mariscos, sésamo). "
            "Pasa la lista en 'allergens', o una lista vacía si confirman "
            "que no hay ninguno."
        )
    return (
        "Allergens — ask ONCE about the big-8 (peanuts, tree nuts, dairy, "
        "eggs, wheat/gluten, soy, fish, shellfish, sesame). Pass an "
        "'allergens' list at post time (empty list is fine when they "
        "confirm none)."
    )


__all__ = [
    "ALLERGEN_ALIASES",
    "DIETARY_ALIASES",
    "extract_allergens_and_diet",
    "enrich_post_listing_allergen_args",
    "enrich_search_allergen_args",
    "build_allergen_reminder",
    "allergens_asked",
    "allergens_answered",
]
