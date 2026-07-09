"""Conversation tone presets for Nouri AI chat."""
from __future__ import annotations

CONVERSATION_TONE_KEY = "conversation_tone"
DEFAULT_TONE = "warm"

VALID_TONES = frozenset({"warm", "professional", "casual", "empathetic"})

TONE_TEMPERATURE: dict[str, float] = {
    "warm": 0.7,
    "professional": 0.35,
    "casual": 0.85,
    "empathetic": 0.65,
}

_TONE_PROMPTS_EN: dict[str, str] = {
    "warm": (
        "ACTIVE CONVERSATION TONE: warm (default neighbor voice).\n"
        "MUST: encouraging, concise (1–3 short sentences), simple words, light contractions.\n"
        "Example opener: \"Happy to help — here's what I found near you.\"\n"
        "MUST NOT: stiff corporate language or cold bullet-only replies."
    ),
    "professional": (
        "ACTIVE CONVERSATION TONE: professional.\n"
        "MUST: complete sentences, formal polite address, clear structure, no slang, no emoji.\n"
        "Example opener: \"Certainly. DoGoods connects donors with recipients in your area.\"\n"
        "MUST NOT: contractions (don't, I'm, here's), exclamation marks, casual slang, "
        "or neighborly chitchat."
    ),
    "casual": (
        "ACTIVE CONVERSATION TONE: casual.\n"
        "MUST: relaxed texting style, contractions, plain words, friendly and brief.\n"
        "Example opener: \"Sure thing — here's what's nearby.\"\n"
        "MUST NOT: formal corporate phrasing, stiff titles, or essay-length replies."
    ),
    "empathetic": (
        "ACTIVE CONVERSATION TONE: empathetic.\n"
        "MUST: start with brief validation of feelings before facts or actions.\n"
        "Example opener: \"That sounds really hard — let me find food near you right now.\"\n"
        "MUST NOT: jump straight to lists/tools without acknowledging the person first."
    ),
}

_TONE_PROMPTS_ES: dict[str, str] = {
    "warm": (
        "TONO ACTIVO: cálido (vecino servicial).\n"
        "DEBES: alentador, breve, lenguaje sencillo.\n"
        "Ejemplo: \"Con gusto — esto hay cerca de ti.\"\n"
        "NO: lenguaje corporativo frío."
    ),
    "professional": (
        "TONO ACTIVO: profesional.\n"
        "DEBES: oraciones completas, cortesía formal, sin jerga ni emoji.\n"
        "Ejemplo: \"Por supuesto. DoGoods conecta donantes con quienes necesitan comida.\"\n"
        "NO: contracciones informales ni tono de chat casual."
    ),
    "casual": (
        "TONO ACTIVO: informal.\n"
        "DEBES: estilo relajado, contracciones, amigable y breve.\n"
        "Ejemplo: \"Claro — mira lo que hay cerca.\"\n"
        "NO: frases formales o respuestas largas tipo ensayo."
    ),
    "empathetic": (
        "TONO ACTIVO: empático.\n"
        "DEBES: validar sentimientos en una frase antes de actuar.\n"
        "Ejemplo: \"Suena difícil — busco comida cerca de ti ahora mismo.\"\n"
        "NO: ir directo a listas sin reconocer a la persona."
    ),
}

TONE_LABELS_EN: dict[str, str] = {
    "warm": "Warm",
    "professional": "Professional",
    "casual": "Casual",
    "empathetic": "Empathetic",
}

TONE_LABELS_ES: dict[str, str] = {
    "warm": "Cálido",
    "professional": "Profesional",
    "casual": "Informal",
    "empathetic": "Empático",
}


def normalize_tone(value: str | None) -> str:
    """Return a valid tone id, falling back to default."""
    if not value:
        return DEFAULT_TONE
    key = str(value).strip().lower()
    return key if key in VALID_TONES else DEFAULT_TONE


def tone_temperature(tone: str) -> float:
    """Sampling temperature tuned per tone."""
    return TONE_TEMPERATURE.get(normalize_tone(tone), 0.7)


def tone_system_prompt(tone: str, lang: str = "en") -> str:
    """Build the per-turn tone instruction for the model."""
    t = normalize_tone(tone)
    prompts = _TONE_PROMPTS_ES if lang == "es" else _TONE_PROMPTS_EN
    base = prompts[t]
    if lang == "es":
        override = (
            "PRIORIDAD MÁXIMA: Este tono anula instrucciones genéricas de estilo "
            "'cálido/conversacional' en el contexto. Tu respuesta visible DEBE "
            "sonar claramente distinta al tono cálido predeterminado."
        )
    else:
        override = (
            "MAXIMUM PRIORITY: This tone OVERRIDES generic 'warm/conversational' "
            "style instructions elsewhere. Your visible reply MUST sound clearly "
            "different from the default warm neighbor voice."
        )
    return f"{base}\n{override}"


def tone_reminder(tone: str, lang: str = "en") -> str:
    """Short reminder re-appended before tool follow-up summarization."""
    t = normalize_tone(tone)
    if lang == "es":
        labels = TONE_LABELS_ES
        return f"Recordatorio: responde al usuario en tono {labels[t]} — mantén ese registro."
    labels = TONE_LABELS_EN
    return f"Reminder: reply to the user in {labels[t]} tone — stay in that register."
