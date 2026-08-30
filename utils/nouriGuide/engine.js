/**
 * Nouri Guide Engine — single conductor for accessibility + AI guidance.
 * Merges: voice TTS queue, step state, DOM field focus, persistence.
 */
import { textToSpeech, playAudioBlob } from '../openaiVoice'
import { guideFormField, clearAllFormFieldGuides, reapplyPendingGuideField } from '../formFieldGuide'
import { NOURI_GOALS, getStepMeta, goalKeyFromFormId, getStepIndexForField } from './registry'
import { parseGuidedStepHeader, simplifyGuideText, inferGuidedFieldFromText } from './parseGuidedMessage'
import { trackFieldFocus, notifyFieldChanged, reportFieldError, resetStuckTracking } from './stuckDetection'
import { normalizeGuideLang, ttsLangTag } from '../guideLang'

function defaultGuideLang(lang) {
  return normalizeGuideLang(lang || a11yPrefs.preferredLanguage || 'en')
}

export const NOURI_GUIDE_STORAGE_KEY = 'nouri.guide.v2'
export const NOURI_GUIDE_EVENT = 'nouri:guide-update'

/** Warm browser voices so the first form utterance isn't delayed. */
function warmSpeechVoices() {
  if (typeof window === 'undefined' || !window.speechSynthesis) return
  try {
    window.speechSynthesis.getVoices()
    window.speechSynthesis.addEventListener?.('voiceschanged', () => {
      window.speechSynthesis.getVoices()
    }, { once: true })
  } catch { /* noop */ }
}
warmSpeechVoices()

/**
 * Pick a matching local voice (instant) for form guidance.
 * @param {SpeechSynthesis} synth
 * @param {string} langTag
 */
function pickLocalVoice(synth, langTag) {
  try {
    const voices = synth.getVoices() || []
    if (!voices.length) return null
    const primary = String(langTag || 'en-US').toLowerCase()
    const base = primary.split('-')[0]
    return (
      voices.find((v) => (v.lang || '').toLowerCase() === primary)
      || voices.find((v) => (v.lang || '').toLowerCase().startsWith(base))
      || null
    )
  } catch {
    return null
  }
}

/**
 * Instant local TTS — used for form field guidance (no network wait).
 * @param {string} caption
 * @param {string} guideLang
 * @param {number} generation
 */
function speakWithBrowserTTS(caption, guideLang, generation) {
  const synth = typeof window !== 'undefined' ? window.speechSynthesis : null
  if (!synth) return false

  let started = false
  const start = () => {
    if (started || generation !== speakGeneration) return
    started = true
    try { synth.cancel() } catch { /* noop */ }
    const utt = new SpeechSynthesisUtterance(caption)
    utt.lang = ttsLangTag(guideLang)
    utt.rate = 1.05
    const voice = pickLocalVoice(synth, utt.lang)
    if (voice) utt.voice = voice
    utt.onstart = () => {
      if (generation !== speakGeneration) return
      state.isSpeaking = true
      notify()
    }
    utt.onend = () => {
      if (generation !== speakGeneration) return
      state.isSpeaking = false
      activeStop = null
      notify()
    }
    utt.onerror = () => {
      if (generation !== speakGeneration) return
      state.isSpeaking = false
      activeStop = null
      notify()
    }
    activeStop = () => {
      try { synth.cancel() } catch { /* noop */ }
    }
    // Chrome often needs a tick after cancel() before speak() starts.
    setTimeout(() => {
      if (generation !== speakGeneration) return
      try { synth.speak(utt) } catch { /* noop */ }
    }, 0)
  }

  // Voices may still be loading on first visit.
  if (!(synth.getVoices() || []).length) {
    const onVoices = () => {
      synth.removeEventListener?.('voiceschanged', onVoices)
      start()
    }
    synth.addEventListener?.('voiceschanged', onVoices)
    // Fallback if voiceschanged never fires.
    setTimeout(start, 60)
  } else {
    start()
  }
  return true
}

/** @typedef {'form'|'chat'|'system'} GuideSource */

/**
 * @typedef {Object} NouriGuideState
 * @property {GuideSource} source
 * @property {string|null} goalKey
 * @property {string|null} formId
 * @property {number} stepIndex
 * @property {number} stepTotal
 * @property {string} section
 * @property {string} label
 * @property {string} fieldName
 * @property {string} text
 * @property {string} caption
 * @property {boolean} isSpeaking
 * @property {boolean} isMuted
 * @property {boolean} isDismissed
 * @property {boolean} hasResume
 * @property {number} updatedAt
 */

/** @type {NouriGuideState} */
const EMPTY_STATE = {
  source: 'system',
  goalKey: null,
  formId: null,
  stepIndex: 0,
  stepTotal: 0,
  section: '',
  label: '',
  fieldName: '',
  text: '',
  caption: '',
  isSpeaking: false,
  isMuted: false,
  isDismissed: false,
  hasResume: false,
  updatedAt: 0,
}

let state = { ...EMPTY_STATE }
let speakGeneration = 0
let activeStop = null
/** @type {Set<(s: NouriGuideState) => void>} */
const listeners = new Set()

/** @type {{ preferTextOverVoice: boolean, formVoiceGuideEnabled: boolean, simpleLanguage: boolean, alwaysShowCaptions: boolean, preferredLanguage: string }} */
let a11yPrefs = {
  preferTextOverVoice: false,
  formVoiceGuideEnabled: false,
  simpleLanguage: false,
  alwaysShowCaptions: true,
  preferredLanguage: 'en',
}

/** Form TTS is opt-in — off unless the user enables it in Accessibility settings. */
function shouldSpeakFormVoice() {
  return (
    a11yPrefs.formVoiceGuideEnabled
    && !a11yPrefs.preferTextOverVoice
    && !state.isMuted
    && !state.isDismissed
  )
}

function allowGuideSpeech(speak, { force = false } = {}) {
  if (!speak && !force) return false
  if (state.isDismissed || state.isMuted || a11yPrefs.preferTextOverVoice) return false
  if (state.source === 'form' && !shouldSpeakFormVoice()) return false
  return true
}

function notify() {
  const snapshot = { ...state }
  listeners.forEach((fn) => {
    try { fn(snapshot) } catch { /* noop */ }
  })
  if (typeof window !== 'undefined') {
    try {
      window.sessionStorage.setItem(NOURI_GUIDE_STORAGE_KEY, JSON.stringify(snapshot))
    } catch { /* quota */ }
    window.dispatchEvent(new CustomEvent(NOURI_GUIDE_EVENT, { detail: snapshot }))
  }
}

export function subscribeNouriGuide(listener) {
  listeners.add(listener)
  listener({ ...state })
  return () => listeners.delete(listener)
}

export function getNouriGuideState() {
  return { ...state }
}

export function loadPersistedGuideState() {
  if (typeof window === 'undefined') return null
  try {
    const raw = window.sessionStorage.getItem(NOURI_GUIDE_STORAGE_KEY)
    return raw ? JSON.parse(raw) : null
  } catch {
    return null
  }
}

export function setNouriA11yPrefs(prefs) {
  a11yPrefs = { ...a11yPrefs, ...prefs }
}

export function setGuideMuted(muted) {
  state.isMuted = muted
  if (muted) cancelSpeech()
  notify()
}

export function dismissGuide() {
  cancelSpeech()
  clearAllFormFieldGuides()
  resetStuckTracking()
  state = { ...EMPTY_STATE, isDismissed: true, updatedAt: Date.now() }
  notify()
  if (typeof window !== 'undefined') {
    try { window.sessionStorage.removeItem(NOURI_GUIDE_STORAGE_KEY) } catch { /* noop */ }
  }
}

export function cancelSpeech() {
  speakGeneration += 1
  if (activeStop) {
    activeStop()
    activeStop = null
  }
  if (typeof window !== 'undefined' && window.speechSynthesis) {
    window.speechSynthesis.cancel()
  }
  state.isSpeaking = false
  notify()
}

function focusFieldForStep(fieldName, dataGuideField, guideText) {
  const target = fieldName || dataGuideField
  if (!target) return
  guideFormField(target, { guideText, scroll: true })
}

/**
 * @param {Partial<NouriGuideState>} patch
 * @param {{ speak?: boolean, lang?: string, focusField?: boolean }} [options]
 */
export function updateGuide(patch, { speak = false, lang, focusField = true } = {}) {
  const guideLang = defaultGuideLang(lang)
  const prevDismissed = state.isDismissed
  state = {
    ...state,
    ...patch,
    updatedAt: Date.now(),
    hasResume: Boolean(patch.formId && patch.stepIndex != null && patch.text),
  }
  if (prevDismissed && patch.isDismissed === undefined) {
    state.isDismissed = false
  }

  if (state.caption || state.text) {
    state.caption = simplifyGuideText(state.caption || state.text, a11yPrefs.simpleLanguage)
  }

  const meta = state.goalKey ? getStepMeta(state.goalKey, state.stepIndex) : null
  const fieldName = patch.fieldName ?? meta?.fieldName ?? state.fieldName
  const dataGuideField = meta?.dataGuideField
  if (fieldName) state.fieldName = fieldName

  if (focusField && (fieldName || dataGuideField)) {
    focusFieldForStep(fieldName, dataGuideField, state.caption || state.text)
  }

  if (state.formId && (fieldName || dataGuideField)) {
    trackFieldFocus(state.formId, fieldName || dataGuideField, state.label)
  }

  notify()

  if (allowGuideSpeech(speak)) {
    speakGuideText(state.caption || state.text, { lang: guideLang })
  }
}

/**
 * @param {string} text
 * @param {{ lang?: string, force?: boolean, preferLocal?: boolean }} [options]
 */
export async function speakGuideText(text, { lang, force = false, preferLocal } = {}) {
  if (!text) return
  const guideLang = defaultGuideLang(lang)
  const caption = simplifyGuideText(text, a11yPrefs.simpleLanguage)
  state.caption = caption
  state.text = state.text || caption

  if (!allowGuideSpeech(true, { force })) {
    state.isSpeaking = false
    notify()
    return
  }

  cancelSpeech()
  const generation = speakGeneration
  // Form field guidance must start immediately — browser TTS, no /api/ai/tts wait.
  const useLocal = preferLocal === true
    || (preferLocal !== false && state.source === 'form')

  if (useLocal) {
    state.isSpeaking = true
    notify()
    if (!speakWithBrowserTTS(caption, guideLang, generation)) {
      state.isSpeaking = false
      notify()
    }
    return
  }

  try {
    const blob = await textToSpeech(caption, { lang: guideLang })
    if (generation !== speakGeneration) return

    const { stop } = playAudioBlob(
      blob,
      () => {
        state.isSpeaking = true
        notify()
      },
      () => {
        state.isSpeaking = false
        activeStop = null
        notify()
      },
    )
    activeStop = stop
  } catch {
    if (generation !== speakGeneration) return
    speakWithBrowserTTS(caption, guideLang, generation)
  }
  notify()
}

/**
 * Handle any assistant message — guided or freeform.
 * @returns {boolean} true if guided step was detected
 */
export function handleChatAssistantMessage(message, { lang = 'en', speak = false } = {}) {
  const synced = syncGuideFromChatMessage(message, { lang, speak })
  if (synced) return true

  // Keep the live form-field hint when chat is not a GUIDED step.
  if (state.source === 'form' && state.fieldName && (state.caption || state.text)) {
    return false
  }

  const body = simplifyGuideText(
    message
      .replace(/\*\*(.*?)\*\*/g, '$1')
      .replace(/[#*_~`]/g, '')
      .replace(/\n+/g, ' ')
      .replace(/\s+/g, ' ')
      .trim(),
    a11yPrefs.simpleLanguage,
  )

  updateGuide({
    source: 'chat',
    goalKey: null,
    formId: state.formId,
    label: 'Nouri',
    text: body,
    caption: body,
  }, { speak, lang, focusField: false })

  return false
}

/**
 * Sync guide from chat assistant message (guided mode header).
 */
export function syncGuideFromChatMessage(message, { lang = 'en', speak = false } = {}) {
  let parsed = parseGuidedStepHeader(message)
  // Model often drops the GUIDED header — still try to point at the right field.
  if (!parsed?.goalKey) {
    const inferred = inferGuidedFieldFromText(message, state.goalKey)
    if (!inferred) return false
    parsed = inferred
  }

  const goal = NOURI_GOALS[parsed.goalKey]
  const meta = getStepMeta(parsed.goalKey, parsed.stepIndex)
  const bodyText = message.split('\n').slice(1).join('\n').trim() || message
  const fieldName = parsed.fieldName || meta?.fieldName || ''

  updateGuide({
    source: 'chat',
    goalKey: parsed.goalKey,
    formId: goal?.formId || null,
    stepIndex: parsed.stepIndex,
    stepTotal: parsed.stepTotal || goal?.steps.length || 0,
    section: parsed.section || meta?.section || '',
    label: meta?.label || parsed.section || 'Nouri',
    fieldName,
    text: bodyText,
    caption: bodyText,
  }, { speak, lang, focusField: Boolean(fieldName) })

  return true
}

/**
 * Form field focus — unified with chat step state.
 * @param {{ formId: string, fieldName: string, label?: string, text: string, hints?: Record<string, unknown> }} params
 * @param {{ lang?: string }} [options]
 */
export function syncGuideFromFormField(
  { formId, fieldName, label, text, hints = {} },
  { lang = 'en' } = {},
) {
  if (state.isDismissed) return

  const goalKey = goalKeyFromFormId(formId)
  const mappedIndex = goalKey ? getStepIndexForField(goalKey, fieldName) : -1
  const hintKeys = Object.keys(hints)
  const hintIndex = hintKeys.indexOf(fieldName)
  const stepIndex = mappedIndex >= 0
    ? mappedIndex
    : (hintIndex >= 0 ? hintIndex : state.stepIndex)
  const stepTotal = NOURI_GOALS[goalKey]?.steps?.length || hintKeys.length || state.stepTotal

  updateGuide({
    source: 'form',
    goalKey,
    formId,
    stepIndex,
    stepTotal,
    section: '',
    label: label || fieldName,
    fieldName,
    text,
    caption: text,
  }, { speak: true, lang, focusField: true })
}

/**
 * Welcome on form open — respects resume if same formId.
 * @param {{ formId: string, welcomeMessage: string, hints?: Record<string, unknown> }} params
 * @param {{ lang?: string }} [options]
 */
export function startFormGuide({ formId, welcomeMessage, hints = {} }, { lang = 'en' } = {}) {
  if (state.isDismissed) return

  const persisted = loadPersistedGuideState()
  if (
    persisted
    && persisted.formId === formId
    && persisted.source === 'chat'
    && persisted.text
    && Date.now() - persisted.updatedAt < 30 * 60 * 1000
  ) {
    updateGuide({
      ...persisted,
      source: 'form',
      hasResume: true,
      isDismissed: false,
    }, { speak: false, lang, focusField: true })
    // Form just mounted — re-apply highlight for the chat-guided field.
    setTimeout(() => reapplyPendingGuideField(), 50)
    return
  }

  const goalKey = goalKeyFromFormId(formId)
  const hintKeys = Object.keys(hints)
  updateGuide({
    source: 'form',
    goalKey,
    formId,
    stepIndex: 0,
    stepTotal: hintKeys.length,
    section: 'Welcome',
    label: 'AI guide',
    fieldName: '',
    text: welcomeMessage,
    caption: welcomeMessage,
    hasResume: false,
  }, { speak: true, lang, focusField: false })

  // If chat already asked for a field before the form existed, highlight now.
  setTimeout(() => reapplyPendingGuideField(), 80)
}

export function resumeGuide({ lang = 'en' } = {}) {
  if (!state.text && !state.caption) return
  updateGuide({ hasResume: false }, { speak: true, lang, focusField: true })
}

export function replayGuide({ lang = 'en' } = {}) {
  // Replay form captions with local TTS; chat steps keep neural TTS when source is chat.
  speakGuideText(state.caption || state.text, {
    lang,
    force: true,
    preferLocal: state.source === 'form',
  })
}

export { reportFieldError, notifyFieldChanged, resetStuckTracking } from './stuckDetection'

// Legacy re-exports for gradual migration
export const subscribeAiVoice = (fn) => subscribeNouriGuide((s) => fn({
  captionText: s.caption,
  isSpeaking: s.isSpeaking,
}))
export const getAiVoiceState = () => {
  const s = getNouriGuideState()
  return { captionText: s.caption, isSpeaking: s.isSpeaking }
}
export const setAiCaption = (text) => updateGuide({ caption: text, text }, { speak: false })
export const cancelAllSpeech = cancelSpeech
export const speakWithAiVoice = (text, opts = {}) => speakGuideText(text, opts)
export const registerExternalSpeechStop = (stop) => { activeStop = stop }
export const clearAiCaption = () => updateGuide({ caption: '', text: '' }, { speak: false })

export const publishGuideState = (partial) => updateGuide(partial, { speak: false })
export const readGuideState = loadPersistedGuideState
export const clearGuideState = () => {
  cancelSpeech()
  clearAllFormFieldGuides()
  resetStuckTracking()
  state = { ...EMPTY_STATE, updatedAt: Date.now() }
  notify()
  if (typeof window !== 'undefined') {
    try { window.sessionStorage.removeItem(NOURI_GUIDE_STORAGE_KEY) } catch { /* noop */ }
  }
}
export const GUIDE_UPDATE_EVENT = NOURI_GUIDE_EVENT
