import { inferChipsFromResponse } from './inferSuggestionChips.js'

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

const KNOWN_TURN_FAMILIES = new Set([
  'fork', 'guided', 'post', 'photo', 'description', 'community',
  'allergen', 'expiry', 'food_qty', 'food', 'qty', 'address',
])

function backendChipFamily(chips) {
  if (!chips || !chips.length) return 'none'
  const labels = chips.map((c) => chipLabel(c).toLowerCase())
  if (labels.every((l) => /^(1|2|3|5|10)$/.test(l))) return 'qty'
  if (labels.every((l) => /^(tomorrow|in 2 days|in 3 days|in a month|mañana|en 2|en 3|en un mes)/i.test(l))) return 'expiry'
  if (labels.every((l) => /^(still sealed|homemade|assorted leftovers|sigue sellado|casero|sobras)/i.test(l))) return 'description'
  if (labels.some((l) => /^(attach a photo|adjuntar foto|i'll add a photo)/i.test(l)) && labels.length <= 2) return 'photo'
  if (labels.some((l) => /^(yes, post it|sí, publícalo|wait, edit)/i.test(l))) return 'post'
  if (labels.some((l) => /^(no allergens|sin alérgenos|just gluten|dairy|nuts|lácteos|frutos)/i.test(l))) return 'allergen'
  if (labels.some((l) => /^(do it for me|hazlo por|guide me|guíame|open the form|open find)/i.test(l))) return 'fork'
  if (labels.some((l) => /^(done|what's next|need help|listo|siguiente|necesito ayuda|i see the form|ya veo)/i.test(l))) return 'guided'
  if (labels.some((l) => /^(5 apples|2 loaves|vegetables —|eggs —|5 manzanas|2 panes)/i.test(l))) return 'food_qty'
  if (labels.some((l) => /^(bread|fruit|vegetables|prepared meal|pan|frutas|comida preparada)$/i.test(l))) return 'food'
  if (labels.some((l) => /different community|otra comunidad|use my profile community/i.test(l))) return 'community'
  if (labels.some((l) => /address|dirección|use that one|usa esa/i.test(l))) return 'address'
  return 'other'
}

function turnFamilyFromText(responseText) {
  const text = String(responseText || '').toLowerCase().replace(/[-_/]+/g, ' ').replace(/\s+/g, ' ')
  if (/(do it for me|handle everything).{0,80}(guide me|paso a paso|open the form)/.test(text)
    || /(how would you like|like to proceed).{0,40}(shar|donat)/.test(text)) return 'fork'
  if (/ready to post|shall i post|sound good to post|looks? right|does this look|go ahead and share/.test(text)
    && !/your community|list under|linked to|profile address/.test(text)) return 'post'
  if (/short description|add a description|describe the food|describe it|describing the|describing this|one short sentence|sentence describing|\bdescription\b|people should know|how is it packaged|how it'?s packed|how it is packed|how fresh|give me one short|short description of|in the carton|still in the carton|write one short sentence/.test(text)
      && !/i'?ll put|into the description/.test(text)) return 'description'
  if (/photo|picture|foto/.test(text) && /attach|upload|required|please/.test(text)
    && !/short description|add a description|describe the food|with photo|ready to post/.test(text)) return 'photo'
  if (/which community|list under|your community|linked to|use that one|for the community/.test(text)
    && !/ready to post|looks? right/.test(text)) return 'community'
  if (/profile address|what address|where should|does that look good|pickup address/.test(text)
    && !/ready to post|community/.test(text)) return 'address'
  if (/allerg|contain nuts|dietary restriction/.test(text) && !/ready to post|looks? right/.test(text)) return 'allergen'
  if (/when does it expire|best by|good until|how long is it good|stay fresh/.test(text)
    && !/allerg|short description|describe/.test(text)) return 'expiry'
  if (/(what food|tell me what you have).{0,40}(how much|how many)|food and how much|food name and/.test(text)) return 'food_qty'
  if (/what food|what would you like to share|what are you sharing|tell me the food/.test(text)) return 'food'
  if (/how many|how much|cuántos|cuántas/.test(text) && !/what food|description/.test(text)) return 'qty'
  return 'other'
}

/**
 * Index of the live unanswered assistant turn, or -1.
 * Chips belong only to that message: after the user replies, on error, or
 * while waiting, return -1 so previous chips are not re-shown.
 */
export function liveAssistantIndex(messages) {
  if (!Array.isArray(messages) || messages.length === 0) return -1
  const newest = messages[messages.length - 1]
  if (newest?.role === 'assistant' && newest?.isError) return -1

  let lastUserIdx = -1
  let lastOkAssistantIdx = -1
  for (let i = messages.length - 1; i >= 0; i--) {
    const m = messages[i]
    if (lastUserIdx < 0 && m.role === 'user') lastUserIdx = i
    if (
      lastOkAssistantIdx < 0
      && m.role === 'assistant'
      && !m.isError
      && m.id !== 'welcome'
    ) {
      lastOkAssistantIdx = i
    }
  }
  if (lastOkAssistantIdx < 0) return -1
  if (lastUserIdx >= 0 && lastOkAssistantIdx < lastUserIdx) return -1
  if (messages[lastOkAssistantIdx]?.requiresConfirmation) return -1
  return lastOkAssistantIdx
}

/**
 * Drop chips that clearly conflict with the assistant's latest reply.
 * Empty is better than Yes/No under a photo or food question.
 * When the reply is an assistance fork, force goal-aware open chips
 * (Share → Open the form; Find → Open Find Food; Request → Open Request Food).
 */
export function filterChipsAgainstResponse(responseText, chips) {
  if (!Array.isArray(chips) || chips.length === 0) {
    chips = []
  }
  const text = String(responseText || '').toLowerCase().replace(/[-_/]+/g, ' ').replace(/\s+/g, ' ')
  const rawChips = chips
  const rawFamily = backendChipFamily(rawChips)

  // Active guided tutorial — never re-show Open / Do it for me / Guide me.
  const guidedTutorial = (
    /^guided\b|^guiado\b/.test(String(responseText || '').trim().toLowerCase())
    || (/guided —|guided -|guiado —|guiado -/.test(text))
    || (
      /(open the share|open share food|open the find|open find food|open the request|tap share food|tap find food|look at the top|main menu|top menu|please open the)/.test(text)
      && /(say done|let me know when|when you see|next step|see the form|together)/.test(text)
    )
    || /(baby step|look at the blue|look at the green|tap the box|type your name)/.test(text)
  )
  if (guidedTutorial && (rawChips.length === 0 || rawFamily === 'guided' || rawFamily === 'none')) {
    const es = /[¿áéíóúñ]|listo|siguiente|ayuda/.test(String(responseText || '').toLowerCase())
    const openStep = /(open the share|open share|open the find|open find|open the request|tap share|tap find|main menu|top menu|see the form)/.test(text)
    const base = es
      ? [
          { label: 'Listo', message: 'listo' },
          { label: 'Siguiente', message: 'siguiente' },
          { label: '¿Ayuda?', message: 'Necesito ayuda con este paso' },
        ]
      : [
          { label: 'Done', message: 'done' },
          { label: "What's next?", message: "what's next" },
          { label: 'Need help', message: 'I need help with this step' },
        ]
    if (openStep) {
      const see = es
        ? { label: 'Ya veo el formulario', message: 'listo — ya veo el formulario' }
        : { label: 'I see the form', message: 'done — I see the form' }
      return [see, ...base]
    }
    return base
  }

  // Real mode-choice ask only — not a hands-on ack like "I'll handle everything…".
  const isForkAsk = (
    (
      (/do it for me|handle everything|handle the whole|hazlo por|here in chat/.test(text)
        && /guide me|walk you through|paso a paso|gu[ií]ame|open the form|open find food|open request food/.test(text))
      || (/would you like me to handle|would you rather|how would you like|like to proceed/.test(text)
        && /shar|donat|find food|request|search|nearby|posting/.test(text))
    )
    && /(or |want me|would you|prefer|options|three)/.test(text)
  )
  // Don't treat "please open Share Food… say done" as a fresh fork ask.
  // Don't replace food/expiry/description chips the backend already sent.
  if (
    isForkAsk
    && !/(say done|let me know when|when you see|i see the form|next step together)/.test(text)
    && (rawChips.length === 0 || rawFamily === 'fork' || rawFamily === 'none')
  ) {
    const es = /[¿áéíóúñ]|hazlo|gu[ií]ame|abrir el formulario|abrir buscar|abrir solicitar/.test(String(responseText || '').toLowerCase())
    const ctx = text
    let path = typeof window !== 'undefined' ? String(window.location?.pathname || '') : ''
    const pagePath = path.toLowerCase()

    let goal = 'share'
    if (/(find food|buscar comida|search nearby|near you|handle the search)/.test(ctx)
      && !/(share food|compartir|donate|posting)/.test(ctx)) {
      goal = 'find'
    } else if (/(request food|solicitar)/.test(ctx)
      && !/(share food|compartir|donate|posting)/.test(ctx)) {
      goal = 'request'
    } else if (/\/find|near-me/.test(pagePath) && !/\/share|\/request/.test(pagePath)) {
      goal = 'find'
    } else if (/\/request/.test(pagePath)) {
      goal = 'request'
    } else if (/\/share/.test(pagePath)) {
      goal = 'share'
    }

    let openChip
    if (goal === 'find') {
      const nav = pagePath.includes('near-me') ? '/near-me' : '/find'
      openChip = es
        ? { label: 'Abrir Buscar comida', message: 'Abrir Buscar comida', action: 'navigate', path: nav, href: nav }
        : { label: 'Open Find Food', message: 'Open Find Food', action: 'navigate', path: nav, href: nav }
    } else if (goal === 'request') {
      openChip = es
        ? { label: 'Abrir Solicitar comida', message: 'Abrir Solicitar comida', action: 'navigate', path: '/request', href: '/request' }
        : { label: 'Open Request Food', message: 'Open Request Food', action: 'navigate', path: '/request', href: '/request' }
    } else {
      openChip = es
        ? { label: 'Abrir el formulario', message: 'Abrir el formulario', action: 'navigate', path: '/share', href: '/share' }
        : { label: 'Open the form', message: 'Open the form', action: 'navigate', path: '/share', href: '/share' }
    }

    const modeChips = es
      ? [
          { label: 'Hazlo por mí', message: 'Hazlo por mí' },
          { label: 'Guíame paso a paso', message: 'Guíame paso a paso' },
        ]
      : [
          { label: 'Do it for me', message: 'Do it for me' },
          { label: 'Guide me step by step', message: 'Guide me step by step' },
        ]
    return [openChip, ...modeChips]
  }

  if (!rawChips.length) return []

  const drop = new Set()
  const photoAsk = /(photo|picture|foto|imagen)/.test(text)
    && /(upload|attach|required|please|add a|add one|sube|adjunt)/.test(text)
  if (photoAsk) {
    ;['yes', 'no', 'later', 'sí', 'si', 'más tarde', 'skip', 'skip photo', 'no photo'].forEach((x) => drop.add(x))
  }
  if (/(which community|which school|list under|listed under|post (this |it )?under|go under|school district|your community|comunidad|escuela)/.test(text)) {
    ;['yes, post it', 'sí, publícalo', 'wait, edit it', 'yes', 'no', 'later'].forEach((x) => drop.add(x))
  }
  if (/^guided\b|guided —|guided -|guiado —|guiado -/i.test(String(responseText || '').trim())) {
    ;['yes', 'no', 'later', 'yes, post it', 'find food near me', 'i want to share food'].forEach((x) => drop.add(x))
  }
  if (/(ready to claim|claim these|shall i claim|claim this listing)/.test(text)) {
    ;['yes', 'no', 'later', 'yes, post it'].forEach((x) => drop.add(x))
  }

  // Hands-on share/find step — never keep mode-fork chips (Open form / Do it / Guide).
  const handsOnStep = /(what food|how much|how many|best by|stay fresh|expir|allerg|short description|describe the food|one sentence about|\bdescription\b|listing description|people should know|ready to post|post this under|which community|upload .+ photo|add a photo|attach a photo)/.test(text)
  const forkChip = /^(open the form|open find food|open request food|abrir el formulario|abrir buscar|abrir solicitar|do it for me|hazlo por m[ií]|guide me|gu[ií]ame)/i

  // Combined food+qty ask — bare 1/3/5/10 is wrong; drop so infer can refill.
  const foodAsk = /(what food|what would you like to share|what are you sharing|what do you have|qué comida)/.test(text)
  const qtyAsk = /(how much|how many|cuántos|cuántas|cuánto)/.test(text)
  const combinedFoodQty = foodAsk && qtyAsk
  const allergenAsk = /(allerg|alérgen|alergia|dietary restriction)/.test(text)
  const expiryChipLabel = /^(tomorrow|in 2 days|in 3 days|other date|mañana|en 2 d[ií]as|en 3 d[ií]as|otra fecha|good for 24)/i

  // Never keep food-example chips under a mode / confirm ask.
  const foodExamples = new Set([
    '5 apples', 'bread and eggs', 'vegetables — 2 boxes', 'use my saved address',
    '5 manzanas', 'pan y huevos', 'verduras — 2 cajas', 'usa mi dirección guardada',
    '2 loaves of bread', 'vegetables — 1 box', 'eggs — 1 dozen',
    '2 panes', 'verduras — 1 caja', 'huevos — 1 docena',
    'bread', 'fruit', 'vegetables', 'prepared meal',
    'pan', 'frutas', 'verduras', 'comida preparada',
  ])

  return rawChips
    .filter((c) => {
      const label = chipLabel(c).toLowerCase()
      if (drop.has(label)) return false
      if (handsOnStep && forkChip.test(label)) return false
      if (combinedFoodQty && /^(1|2|3|5|10)$/.test(label)) return false
      if (allergenAsk && expiryChipLabel.test(label)) return false
      if (foodExamples.has(label) && /(chat|guide|step|form|page)/.test(text) && !combinedFoodQty) return false
      return true
    })
    .slice(0, 40)
}

/**
 * Input-rail chips (prechips above the composer).
 * Prefer backend contextual suggestions for the latest turn; fall back to
 * role-aware starters only when idle / no backend chips.
 */
export function resolveInputChips(suggestions, language = 'en', role = null, { allowLazy = true, responseText = '' } = {}) {
  const normalized = (Array.isArray(suggestions) ? suggestions : [])
    .map((chip) => {
      if (chip == null) return null
      if (typeof chip === 'string') {
        const t = chip.trim()
        return t ? { label: t, message: t } : null
      }
      if (typeof chip === 'object') {
        const label = String(chip.label || chip.message || chip.prompt || chip.text || '').trim()
        const message = String(chip.message || chip.prompt || chip.label || chip.text || label).trim()
        if (!label) return null
        const item = { label: label.slice(0, 60), message: message || label }
        if (chip.action) item.action = chip.action
        if (chip.path) item.path = chip.path
        if (chip.href) item.href = chip.href
        if (chip.target) item.target = chip.target
        return item
      }
      return null
    })
    .filter(Boolean)

  // Filter may drop conflicts; it must not replace a known backend family
  // with fork/guided chips (see filterChipsAgainstResponse).
  const filtered = filterChipsAgainstResponse(responseText, normalized)

  const turnFamily = turnFamilyFromText(responseText)
  const backendFamily = backendChipFamily(filtered)
  const onlyBareQty = filtered.length > 0
    && filtered.every((c) => /^(1|2|3|5|10)$/.test(chipLabel(c)))
  const qtyOnlyAsk = turnFamily === 'qty'
  const expiryChip = /^(tomorrow|in 2 days|in 3 days|in a month|other date|mañana|en 2 d[ií]as|en 3 d[ií]as|en un mes|otra fecha|good for 24)/i
  const onlyExpiry = filtered.length > 0
    && filtered.every((c) => expiryChip.test(chipLabel(c)))
  const expiryAsk = turnFamily === 'expiry'
  const descriptionAsk = turnFamily === 'description'
  const descriptionChip = /^(still sealed|homemade|assorted leftovers|sigue sellado|casero|sobras variadas)/i
  const onlyDescription = filtered.length > 0
    && filtered.every((c) => descriptionChip.test(chipLabel(c)))

  const familyMismatch = (
    filtered.length > 0
    && KNOWN_TURN_FAMILIES.has(turnFamily)
    && backendFamily !== 'none'
    && backendFamily !== turnFamily
  )

  const staleForTurn = (
    (onlyBareQty && !qtyOnlyAsk)
    || (onlyExpiry && !expiryAsk)
    || (onlyDescription && !descriptionAsk)
    || (onlyExpiry && descriptionAsk)
    || familyMismatch
  )
  if (filtered.length > 0 && !staleForTurn) {
    return filtered.slice(0, 40)
  }

  // Safety net: infer chips from the reply text when the backend sent none
  // or sent chips that conflict with the current question.
  if (responseText) {
    const inferred = inferChipsFromResponse(responseText, language)
    if (inferred.length > 0) return inferred.slice(0, 40)
  }

  if (!allowLazy) return []
  return getLazyPreChips(language, role).map((t) => ({ label: t, message: t }))
}

export { chipLabel }
