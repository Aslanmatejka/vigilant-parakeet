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

const DONOR_ONLY_EN = new Set(['I want to share food'])
const DONOR_ONLY_ES = new Set(['Quiero compartir comida'])
const RECIPIENT_ONLY_EN = new Set([
  'Find food near me',
  "I'm hungry — what's available?",
  'My pickups',
])
const RECIPIENT_ONLY_ES = new Set([
  'Buscar comida cerca',
  'Tengo hambre — ¿qué hay?',
  'Mis reservas',
])

const DONOR_CHIPS_EN = [
  'I want to share food',
  'Show my listings',
  'Show my impact',
  'Help me get started',
]
const DONOR_CHIPS_ES = [
  'Quiero compartir comida',
  'Mis publicaciones',
  'Mi impacto',
  'Ayúdame a empezar',
]
const RECIPIENT_CHIPS_EN = [
  'Find food near me',
  "I'm hungry — what's available?",
  'My pickups',
  'Show my impact',
  'Help me get started',
]
const RECIPIENT_CHIPS_ES = [
  'Buscar comida cerca',
  'Tengo hambre — ¿qué hay?',
  'Mis reservas',
  'Mi impacto',
  'Ayúdame a empezar',
]

export function getLazyPreChips(language = 'en', role = null) {
  const r = String(role || '').toLowerCase()
  if (language === 'es') {
    if (r === 'donor') return DONOR_CHIPS_ES
    if (r === 'recipient') return RECIPIENT_CHIPS_ES
    return LAZY_PRE_CHIPS_ES
  }
  if (r === 'donor') return DONOR_CHIPS_EN
  if (r === 'recipient') return RECIPIENT_CHIPS_EN
  return LAZY_PRE_CHIPS_EN
}

/** Chips for the input rail — backend suggestions when present, else lazy defaults. */
export function resolveInputChips(suggestions, language = 'en', role = null) {
  if (Array.isArray(suggestions) && suggestions.length > 0) {
    const r = String(role || '').toLowerCase()
    if (r === 'donor') {
      const block = language === 'es' ? RECIPIENT_ONLY_ES : RECIPIENT_ONLY_EN
      const filtered = suggestions.filter((s) => !block.has(String(s)))
      return filtered.length ? filtered : getLazyPreChips(language, role)
    }
    if (r === 'recipient') {
      const block = language === 'es' ? DONOR_ONLY_ES : DONOR_ONLY_EN
      const filtered = suggestions.filter((s) => !block.has(String(s)))
      return filtered.length ? filtered : getLazyPreChips(language, role)
    }
    return suggestions
  }
  return getLazyPreChips(language, role)
}
