"""Real-world food knowledge (world model) for Nouri.

The rest of the code base treats every food noun as a countable atom
(``1 apple``, ``2 bananas``, ``3 beans``). That leaks into the UX:
Nouri will ask "how many beans?" as if you can share a single bean, or
"how many rice?" instead of "how many bags / pounds of rice?".

This module is a small, dependency-free ontology that captures the
*form* food usually takes when it's shared or donated:

  * ``bulk_dry`` — rice, beans, flour, sugar (measured in bags/lbs)
  * ``canned`` — canned beans, tuna, soup (counted in cans)
  * ``produce_count`` — apples, oranges (counted individually)
  * ``produce_bulk`` — potatoes, carrots (counted or by bag/lb)
  * ``baked`` — bread (loaves), muffins (pieces)
  * ``prepared`` — soup, casserole (servings / trays / containers)
  * ``dairy`` — milk (cartons / gallons), yogurt (cups)
  * ``eggs`` — eggs (dozens / cartons)
  * ``beverage`` — juice, water (bottles / cases)
  * ``protein`` — chicken, beef (lbs / packs)

Everything here is *advisory*. We only inject `world_model_reminder`
text into the prompt — no tool schemas change, no arguments get
coerced. The AI still gets to phrase the question naturally.

Non-breaking: the module is pure and side-effect free, imported lazily
where needed. Nothing else has to depend on it.
"""
from __future__ import annotations

import re
from typing import Optional


# ---------------------------------------------------------------------------
# Ontology
# ---------------------------------------------------------------------------

# Kind identifier → (natural EN unit label, natural ES unit label,
#                    example question EN, example question ES,
#                    default_unit for the tool schema).
KIND_HINTS: dict[str, dict] = {
    "bulk_dry": {
        "en_units": "bags, cans, or lbs",
        "es_units": "bolsas, latas o libras",
        "en_question": "roughly how much do you have — a bag, a few pounds, or a couple of cans?",
        "es_question": "¿más o menos cuánto tienes — una bolsa, unas libras o unas latas?",
        "default_unit": "lb",
        "notice": (
            "singleton beans/rice/flour aren't shareable — always frame quantity "
            "in bags, cans, containers, or pounds"
        ),
    },
    "canned": {
        "en_units": "cans (or a case)",
        "es_units": "latas (o una caja)",
        "en_question": "how many cans, or is it a full case?",
        "es_question": "¿cuántas latas, o es una caja completa?",
        "default_unit": "can",
        "notice": "canned goods are shared as cans or a case; never an individual item",
    },
    "produce_count": {
        "en_units": "pieces (or a bag / crate)",
        "es_units": "piezas (o una bolsa / caja)",
        "en_question": "about how many, or is it a bag or crate?",
        "es_question": "¿aproximadamente cuántas, o es una bolsa o caja?",
        "default_unit": "piece",
        "notice": "countable produce — accept a number of pieces OR a bag/crate",
    },
    "produce_bulk": {
        "en_units": "lbs, a bag, or a sack",
        "es_units": "libras, una bolsa o un saco",
        "en_question": "how much — a few pounds, a bag, or a sack?",
        "es_question": "¿cuánto — unas libras, una bolsa o un saco?",
        "default_unit": "lb",
        "notice": "root vegetables / bulk produce — quantity as weight or a bag",
    },
    "baked": {
        "en_units": "loaves, pieces, or a tray",
        "es_units": "hogazas, piezas o una bandeja",
        "en_question": "how many loaves or pieces (or a whole tray)?",
        "es_question": "¿cuántas hogazas o piezas (o una bandeja entera)?",
        "default_unit": "loaf",
        "notice": "baked goods — loaves, pieces, or a tray, never grams",
    },
    "prepared": {
        "en_units": "servings, trays, or containers",
        "es_units": "porciones, bandejas o recipientes",
        "en_question": "how many servings, or is it a tray / container?",
        "es_question": "¿cuántas porciones, o es una bandeja / recipiente?",
        "default_unit": "serving",
        "notice": "prepared meals — servings, trays, or containers",
    },
    "dairy": {
        "en_units": "cartons, gallons, or cups",
        "es_units": "cartones, galones o vasos",
        "en_question": "how many cartons or gallons?",
        "es_question": "¿cuántos cartones o galones?",
        "default_unit": "carton",
        "notice": "dairy — cartons, gallons, cups (never 'how many milks')",
    },
    "eggs": {
        "en_units": "cartons / dozens",
        "es_units": "cartones / docenas",
        "en_question": "how many dozens or cartons?",
        "es_question": "¿cuántas docenas o cartones?",
        "default_unit": "dozen",
        "notice": "eggs — dozens or cartons, not individual eggs",
    },
    "beverage": {
        "en_units": "bottles, cans, or cases",
        "es_units": "botellas, latas o cajas",
        "en_question": "how many bottles or a case?",
        "es_question": "¿cuántas botellas o una caja?",
        "default_unit": "bottle",
        "notice": "beverages — bottles, cans, or a case",
    },
    "protein": {
        "en_units": "lbs, packs, or portions",
        "es_units": "libras, paquetes o porciones",
        "en_question": "about how many pounds or packs?",
        "es_question": "¿aproximadamente cuántas libras o paquetes?",
        "default_unit": "lb",
        "notice": "meat/protein — weight or packs, never single pieces",
    },
    "condiment": {
        "en_units": "jars, bottles, or packs",
        "es_units": "frascos, botellas o paquetes",
        "en_question": "how many jars or bottles?",
        "es_question": "¿cuántos frascos o botellas?",
        "default_unit": "jar",
        "notice": "condiments — jars, bottles, or packets",
    },
    "snack": {
        "en_units": "bags, boxes, or packs",
        "es_units": "bolsas, cajas o paquetes",
        "en_question": "how many bags or boxes?",
        "es_question": "¿cuántas bolsas o cajas?",
        "default_unit": "pack",
        "notice": "snacks — bags, boxes, or packs",
    },
}


# Food noun → kind. Aliases (plural / spanish) map to the same entry.
# Keep this focused on the common shared-food vocabulary rather than a
# full dictionary — we prefer false-negatives (silent pass-through) over
# false-positives (wrong nudges).
FOOD_KIND: dict[str, str] = {
    # Bulk dry goods -------------------------------------------------------
    **{k: "bulk_dry" for k in (
        "rice", "beans", "bean", "lentils", "lentil", "chickpeas",
        "garbanzo", "garbanzos", "flour", "sugar", "salt", "oats",
        "oatmeal", "quinoa", "cornmeal", "grits", "cereal", "cereals",
        "pasta", "noodles", "macaroni", "spaghetti", "couscous",
        # Spanish
        "arroz", "frijoles", "frijol", "lentejas", "harina", "azúcar",
        "azucar", "avena", "sal",
    )},
    # Canned / jarred — ONLY naturally canned foods. Produce like tomatoes
    # belong in produce_* and promote to canned only with an explicit modifier
    # ("canned tomatoes", "cans of tomatoes"). Hard-mapping tomatoes→canned
    # made Nouri ask "how many cans?" for fresh baskets.
    **{k: "canned" for k in (
        "tuna", "sardines", "sardine", "anchovies", "salmon",
        # Spanish
        "atún", "atun", "sardinas",
    )},
    # Produce — counted individually ---------------------------------------
    **{k: "produce_count" for k in (
        "apple", "apples", "orange", "oranges", "banana", "bananas",
        "pear", "pears", "peach", "peaches", "plum", "plums",
        "lemon", "lemons", "lime", "limes", "avocado", "avocados",
        "mango", "mangoes", "mangos", "watermelon", "melon", "melons",
        "pineapple", "pineapples", "cucumber", "cucumbers",
        "pepper", "peppers", "zucchini",
        "tomato", "tomatoes",
        # Spanish
        "manzana", "manzanas", "naranja", "naranjas", "plátano",
        "plátanos", "platano", "platanos", "pera", "peras", "durazno",
        "duraznos", "limón", "limones", "aguacate", "aguacates",
        "sandía", "sandia", "piña", "pina", "pepino", "pepinos",
        "tomate", "tomates",
    )},
    # Produce — bulk / weight-based ---------------------------------------
    **{k: "produce_bulk" for k in (
        "potato", "potatoes", "onion", "onions", "carrot", "carrots",
        "kale", "lettuce", "spinach", "cabbage", "broccoli",
        "cauliflower", "beets", "turnips", "yams", "sweet potato",
        "sweet potatoes", "corn", "peas",
        # Spanish
        "papa", "papas", "patata", "patatas", "cebolla", "cebollas",
        "zanahoria", "zanahorias", "col", "coles", "acelga",
        "brócoli", "brocoli", "coliflor",
    )},
    # Baked -----------------------------------------------------------------
    **{k: "baked" for k in (
        "bread", "loaf", "loaves", "baguette", "baguettes", "roll",
        "rolls", "bagel", "bagels", "muffin", "muffins", "croissant",
        "croissants", "cookie", "cookies", "cake", "cakes", "brownie",
        "brownies", "cupcake", "cupcakes", "donut", "donuts", "pastry",
        "pastries", "pie", "pies", "biscuit", "biscuits", "tortilla",
        "tortillas",
        # Spanish
        "pan", "panes", "bollos", "bolillo", "bolillos", "galleta",
        "galletas", "pastel", "pasteles", "tortillas",
    )},
    # Prepared meals / soups -----------------------------------------------
    **{k: "prepared" for k in (
        "soup", "soups", "stew", "stews", "chili", "casserole",
        "casseroles", "lasagna", "lasagnas", "pasta salad", "quiche",
        "meal", "meals", "dinner", "dinners", "lunch", "lunches",
        "sandwich", "sandwiches", "salad", "salads", "curry",
        "rice bowl", "burrito", "burritos", "taco", "tacos", "pizza",
        "pizzas",
        # Spanish
        "sopa", "sopas", "guiso", "guisos", "ensalada", "ensaladas",
        "sandwich", "sandwiches", "arroz con", "burrito", "burritos",
    )},
    # Dairy -----------------------------------------------------------------
    **{k: "dairy" for k in (
        "milk", "cream", "half-and-half", "yogurt", "yogurts",
        "cheese", "cheeses", "butter", "cottage cheese", "sour cream",
        # Spanish
        "leche", "crema", "yogur", "yogures", "queso", "quesos",
        "mantequilla",
    )},
    # Eggs ------------------------------------------------------------------
    **{k: "eggs" for k in (
        "egg", "eggs",
        # Spanish
        "huevo", "huevos",
    )},
    # Beverages -------------------------------------------------------------
    **{k: "beverage" for k in (
        "juice", "juices", "water", "soda", "sodas", "tea", "coffee",
        "lemonade", "kombucha",
        # Spanish
        "jugo", "jugos", "agua", "refresco", "refrescos", "té", "te",
        "café", "cafe",
    )},
    # Protein / meat --------------------------------------------------------
    **{k: "protein" for k in (
        "chicken", "beef", "pork", "turkey", "lamb", "sausage",
        "sausages", "bacon", "ham", "fish", "shrimp", "meat",
        "ground beef", "hamburger", "hamburgers",
        # Spanish
        "pollo", "res", "carne", "cerdo", "puerco", "pavo", "chorizo",
        "tocino", "jamón", "jamon", "pescado", "camarones",
    )},
    # Condiments / oils / sauces -------------------------------------------
    **{k: "condiment" for k in (
        "oil", "oils", "vinegar", "sauce", "sauces", "ketchup",
        "mustard", "mayonnaise", "mayo", "jam", "jelly", "honey",
        "peanut butter", "syrup", "salsa",
        # Spanish
        "aceite", "vinagre", "salsa", "salsas", "miel", "mermelada",
    )},
    # Snacks ----------------------------------------------------------------
    **{k: "snack" for k in (
        "chips", "crackers", "cracker", "pretzels", "popcorn",
        "granola bars", "granola bar", "nuts", "almonds", "peanuts",
        "trail mix", "raisins", "dried fruit",
        # Spanish
        "papas fritas", "galletas saladas", "nueces", "cacahuates",
        "almendras", "pasas",
    )},
}


_TOKEN_RE = re.compile(r"[a-zA-ZÀ-ÿ']+")

# Words that flip a countable/bulk noun into its canned form
# ("canned beans" → canned, not bulk_dry).
# Do NOT use bare substring "can" — it false-matches "I can share…".
_CANNED_MODIFIER_RE = re.compile(
    r"\b(?:canned|cans|jarred|jars|enlatad[oa]s?)\b"
    r"|\bcan(?:s)?\s+of\b"
    r"|\ben\s+lata\b",
    re.IGNORECASE,
)

_CANNED_MODIFIERS: frozenset[str] = frozenset({
    "canned", "cans", "jarred", "jars",
    "en lata", "enlatado", "enlatada", "enlatados", "enlatadas",
    "can of", "cans of",
})

# Modifiers that lock a food into a specific unit — we honour these
# instead of the ontology default when present.
_UNIT_HINT_RE = re.compile(
    r"\b(\d+\s*)?(lb|lbs|pound|pounds|kg|kilo|kilos|gram|grams|"
    r"bag|bags|sack|sacks|box|boxes|carton|cartons|can|cans|"
    r"jar|jars|bottle|bottles|case|cases|tray|trays|pack|packs|"
    r"packet|packets|loaf|loaves|dozen|dozens|serving|servings|"
    r"container|containers|libra|libras|bolsa|bolsas|caja|cajas|"
    r"botella|botellas|frasco|frascos|paquete|paquetes|bandeja|"
    r"bandejas|hogaza|hogazas|docena|docenas|lata|latas)\b",
    re.IGNORECASE,
)


def _normalize(word: str) -> str:
    return (word or "").strip().lower()


def _iter_tokens(text: str) -> list[str]:
    return [t.lower() for t in _TOKEN_RE.findall(text or "")]


def detect_food_kind(text: str) -> Optional[dict]:
    """Return the world-model entry for the food most prominent in *text*.

    Handles:
      * bigrams (``sweet potato``, ``ground beef``, ``peanut butter``)
      * canned modifier promotion (``canned beans`` → canned, not bulk)
      * plurals via the entry itself (both ``bean`` and ``beans`` mapped)
      * silent pass-through — returns None when nothing matches.
    """
    if not text:
        return None
    lowered = " " + text.lower() + " "
    tokens = _iter_tokens(text)

    # First try 2-word phrases so 'sweet potato' beats 'potato'.
    for i in range(len(tokens) - 1):
        bigram = f"{tokens[i]} {tokens[i + 1]}"
        kind = FOOD_KIND.get(bigram)
        if kind:
            return _entry(bigram, kind, lowered)

    for tok in tokens:
        kind = FOOD_KIND.get(tok)
        if kind:
            return _entry(tok, kind, lowered)
    return None


def _entry(food: str, kind: str, lowered_message: str) -> dict:
    """Assemble the ontology entry for a detected food, honouring modifiers."""
    if kind in {"bulk_dry", "produce_bulk", "produce_count"}:
        # 'canned beans' / 'cans of tomatoes' should flip to canned.
        # Substring 'can' alone must NOT match ("I can share tomatoes").
        if _CANNED_MODIFIER_RE.search(lowered_message or ""):
            kind = "canned"
    hint = KIND_HINTS.get(kind, KIND_HINTS["bulk_dry"])
    return {
        "food": food,
        "kind": kind,
        "en_units": hint["en_units"],
        "es_units": hint["es_units"],
        "en_question": hint["en_question"],
        "es_question": hint["es_question"],
        "default_unit": hint["default_unit"],
        "notice": hint["notice"],
    }


def has_explicit_unit(text: str) -> bool:
    """True if the user already specified a real-world unit (lb, bag, can)."""
    return bool(_UNIT_HINT_RE.search(text or ""))


def is_uncountable_singleton(text: str) -> bool:
    """True when the message uses a bulk food as if it were countable
    ('1 bean', 'a rice', 'one flour'). These are almost always the AI
    mis-parsing — we want to nudge it to re-phrase.
    """
    if not text:
        return False
    entry = detect_food_kind(text)
    if not entry:
        return False
    if entry["kind"] not in {"bulk_dry", "canned", "produce_bulk", "dairy", "protein", "condiment"}:
        return False
    if has_explicit_unit(text):
        return False
    # Match patterns like 'a bean', '1 rice', 'one flour', 'a couple beans'.
    return bool(re.search(
        r"\b(a|an|one|1|2|3|4|5|6|7|8|9|10)\s+"
        + re.escape(entry["food"])
        + r"s?\b",
        text.lower(),
    ))


# ---------------------------------------------------------------------------
# Prompt reminders
# ---------------------------------------------------------------------------


def build_world_model_reminder(
    message: str,
    history: list | None = None,
    lang: str = "en",
    flow: str = "idle",
) -> Optional[str]:
    """Return an inline reminder about real-world units for the current turn.

    We only fire when a bulk/prepared food is detected AND either:
      * the user has NOT provided a unit ('I want to share beans'), or
      * the user asked a countable question that doesn't fit
        ('claim 2 rice').

    Runs for both sharing and claiming flows — the ambiguity applies to
    both sides. Idle / off-topic turns pass through silently.
    """
    if flow not in {"posting", "claiming", "requesting", "finding"}:
        return None

    text = message or ""
    entry = detect_food_kind(text)
    # produce_count items ('apples', 'oranges') are genuinely countable —
    # 'how many' is fine, no nudge needed. Same for eggs when they're
    # already qualified (dozen). We only nudge for kinds where a bare
    # 'how many <food>' is misleading.
    _AMBIGUOUS_KINDS = {
        "bulk_dry", "canned", "prepared", "dairy", "beverage",
        "protein", "condiment", "snack", "baked", "produce_bulk",
    }
    if entry and entry["kind"] not in _AMBIGUOUS_KINDS:
        return None
    if not entry:
        # Also scan the last few user messages so a bulk food declared
        # earlier still primes the nudge (e.g. 'I have beans' then 'yes').
        if history:
            for msg in reversed(history[-6:]):
                if msg.get("role") != "user":
                    continue
                cand = detect_food_kind(msg.get("message") or "")
                if cand and cand["kind"] in _AMBIGUOUS_KINDS:
                    entry = cand
                    break
    if not entry or entry["kind"] not in _AMBIGUOUS_KINDS:
        return None

    already_unit = has_explicit_unit(text) or (
        history
        and any(
            msg.get("role") == "user"
            and has_explicit_unit(msg.get("message") or "")
            for msg in history[-6:]
        )
    )
    if already_unit and not is_uncountable_singleton(text):
        return None

    food = entry["food"]
    kind = entry["kind"]
    if lang == "es":
        return (
            f"World model — '{food}' es un producto tipo '{kind}': "
            f"{entry['notice']}. NO preguntes 'cuántos {food}' como si "
            "fuera contable individualmente. Pregunta con unidades "
            f"reales: {entry['es_question']} Al llamar la herramienta, "
            f"pasa quantity + unit (por ejemplo unit='{entry['default_unit']}')."
        )
    return (
        f"World model — '{food}' is a '{kind}' item: {entry['notice']}. "
        f"Do NOT ask 'how many {food}' as if it were individually "
        f"countable. Ask in real-world units: {entry['en_question']} "
        f"When you call the tool, pass quantity AND unit "
        f"(e.g. unit='{entry['default_unit']}')."
    )


def normalize_food_quantity(
    message: str,
    args: Optional[dict] = None,
) -> dict:
    """Best-effort: fill in a sensible ``unit`` for a food-quantity args dict.

    Never overwrites an explicit unit already set by the model. Never
    changes the quantity number. Returns a shallow copy of *args* with
    ``unit`` populated when we can infer it and the food is bulk/canned.
    """
    out = dict(args or {})
    if out.get("unit"):
        return out
    entry = detect_food_kind(message)
    if not entry:
        return out
    # Only auto-fill for kinds where the default matters. For countable
    # produce ('apples'), a bare number is fine — no unit needed.
    if entry["kind"] in {"bulk_dry", "canned", "prepared", "dairy", "eggs",
                          "beverage", "protein", "condiment", "snack",
                          "produce_bulk", "baked"}:
        out["unit"] = entry["default_unit"]
    return out


__all__ = [
    "FOOD_KIND",
    "KIND_HINTS",
    "detect_food_kind",
    "has_explicit_unit",
    "is_uncountable_singleton",
    "build_world_model_reminder",
    "normalize_food_quantity",
]
