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

function chipLabel(chip) {
  if (chip == null) return ''
  if (typeof chip === 'string') return chip
  if (typeof chip === 'object') {
    return String(chip.label || chip.message || chip.prompt || chip.text || '')
  }
  return String(chip)
}

/**
 * Input-rail chips. Contextual bubble suggestions own the turn — the rail
 * stays empty when the backend returns any, to avoid duplicates / mismatched
 * "Find food" starters under a claim-qty question. Lazy defaults are only for
 * true idle mid-conversation (no backend chips).
 */
export function resolveInputChips(suggestions, language = 'en', role = null, { allowLazy = true } = {}) {
  if (Array.isArray(suggestions) && suggestions.length > 0) {
    // Bubble already shows these — do not mirror them on the input rail.
    return []
  }
  if (!allowLazy) return []
  return getLazyPreChips(language, role)
}

export { chipLabel }
