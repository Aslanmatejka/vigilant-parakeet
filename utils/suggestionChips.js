/**
 * Canonical quick-action chips — keep in sync with backend/agent/suggestion_chips.py
 */

export const LAZY_PRE_CHIPS_EN = [
  'Find food near me',
  "I'm hungry — what's available?",
  'I want to share food',
  'My pickups',
  'Show my impact',
  'Help me get started',
]

export const LAZY_PRE_CHIPS_ES = [
  'Buscar comida cerca',
  'Tengo hambre — ¿qué hay?',
  'Quiero compartir comida',
  'Mis reservas',
  'Mi impacto',
  'Ayúdame a empezar',
]

export function getLazyPreChips(language = 'en') {
  return language === 'es' ? LAZY_PRE_CHIPS_ES : LAZY_PRE_CHIPS_EN
}

/** Chips for the input rail — backend suggestions when present, else lazy defaults. */
export function resolveInputChips(suggestions, language = 'en') {
  if (Array.isArray(suggestions) && suggestions.length > 0) {
    return suggestions
  }
  return getLazyPreChips(language)
}
