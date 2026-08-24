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
  if (guidedTutorial) {
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
  if (isForkAsk && !/(say done|let me know when|when you see|i see the form|next step together)/.test(text)) {
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
  const handsOnStep = /(what food|how much do you have|how many .+ sharing|best by|stay fresh|expir|allerg|short description|describe the food|one sentence about|\bdescription\b|listing description|people should know|ready to post|post this under|which community|upload .+ photo|add a photo|attach a photo)/.test(text)
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

  // Always run conflict filter — injects goal-aware open chips on forks
  // even when the backend returned food examples or nothing.
  const filtered = filterChipsAgainstResponse(responseText, normalized)
  const text = String(responseText || '').toLowerCase().replace(/[-_/]+/g, ' ').replace(/\s+/g, ' ')
  const onlyBareQty = filtered.length > 0
    && filtered.every((c) => /^(1|2|3|5|10)$/.test(chipLabel(c)))
  const qtyOnlyAsk = (
    /(how many|how much|cuántos|cuántas|cuánto)/.test(text)
    && !/(what food|what would you like to share|what are you sharing|best by|allerg|community|photo|ready to post|post this under|school)/.test(text)
  )
  const expiryChip = /^(tomorrow|in 2 days|in 3 days|in a month|other date|mañana|en 2 d[ií]as|en 3 d[ií]as|en un mes|otra fecha|good for 24)/i
  const onlyExpiry = filtered.length > 0
    && filtered.every((c) => expiryChip.test(chipLabel(c)))
  const allergenAsk = /(allerg|alérgen|alergia|dietary restriction|shellfish|frutos secos)/.test(text)
  const postConfirmAsk = /(ready to post|ready to publish|shall i post|should i post|want me to post|post these|sound good to post|looks? right|does this look|go ahead and share)/.test(text)
  const expiryAsk = (
    /(best by|best-by|good until|good for|use by|expir|when does it expire|how long is it good|stay fresh|fecha de venc|best before)/.test(text)
    && !allergenAsk
    && !postConfirmAsk
    && !/(got it|noted|i'?ll use|listed as|confirmed).{0,40}(best by|good until|tomorrow)/.test(text)
  )
  const descriptionAsk = /(short description|add a description|describe the food|describe it|description for recipients|listing description|one[- ]sentence|one sentence about|tell me a bit about|tell me more about|how would you describe|people should know|should know about|note for recipients|condition or packaging|how is it packaged|what'?s included|short blurb|sentence about the food|put as the description|descripci[oó]n|\bdescription\b)/.test(text)
  const descriptionChip = /^(still sealed|homemade|assorted leftovers|sigue sellado|casero|sobras variadas)/i
  const onlyDescription = filtered.length > 0
    && filtered.every((c) => descriptionChip.test(chipLabel(c)))
  // Stale qty/expiry chips on the wrong turn (common mid hands-on) → prefer infer.
  // Keep backend description chips whenever the reply is clearly a description ask
  // (including bare "Description?" / "Listing description?").
  const staleForTurn = (
    (onlyBareQty && !qtyOnlyAsk)
    || (onlyExpiry && !expiryAsk)
    || (onlyExpiry && postConfirmAsk)
    || (onlyDescription && !descriptionAsk)
    || (onlyExpiry && descriptionAsk)
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
