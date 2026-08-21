/** @typedef {'en' | 'es' | 'fr' | 'vi' | 'zh'} PreferredLanguage */

/**
 * @typedef {Object} AccessibilitySettings
 * @property {boolean} largeText
 * @property {boolean} highContrast
 * @property {boolean} reduceMotion
 * @property {boolean} alwaysShowCaptions
 * @property {boolean} preferTextOverVoice
 * @property {boolean} simpleLanguage
 * @property {boolean} easyMode
 * @property {boolean} listFirstFind
 * @property {PreferredLanguage} preferredLanguage
 * @property {boolean} screenReaderOptimized
 * @property {boolean} smsGuideEnabled
 */

/** @type {PreferredLanguage[]} */
export const SUPPORTED_GUIDE_LANGUAGES = ['en', 'es', 'fr', 'vi', 'zh']

/** @type {Record<PreferredLanguage, string>} */
export const GUIDE_LANGUAGE_LABELS = {
  en: 'English',
  es: 'Español',
  fr: 'Français',
  vi: 'Tiếng Việt',
  zh: '中文',
}

export const A11Y_STORAGE_KEY = 'nouri.accessibility.v1'

/** @type {AccessibilitySettings} */
export const DEFAULT_A11Y_SETTINGS = {
  largeText: false,
  highContrast: false,
  reduceMotion: false,
  alwaysShowCaptions: true,
  preferTextOverVoice: false,
  simpleLanguage: false,
  easyMode: false,
  listFirstFind: true,
  preferredLanguage: 'en',
  screenReaderOptimized: false,
  smsGuideEnabled: false,
}

/**
 * Normalize persisted settings (local or server).
 * @param {Partial<AccessibilitySettings>|null|undefined} raw
 * @returns {AccessibilitySettings}
 */
export function mergeAccessibilitySettings(raw) {
  const merged = { ...DEFAULT_A11Y_SETTINGS, ...(raw || {}) }
  if (!SUPPORTED_GUIDE_LANGUAGES.includes(merged.preferredLanguage)) {
    merged.preferredLanguage = 'en'
  }
  return merged
}

/** @param {AccessibilitySettings} settings */
export function buildAccessibilityProfilePayload(settings) {
  return {
    largeText: !!settings.largeText,
    highContrast: !!settings.highContrast,
    reduceMotion: !!settings.reduceMotion,
    alwaysShowCaptions: !!settings.alwaysShowCaptions,
    preferTextOverVoice: !!settings.preferTextOverVoice,
    simpleLanguage: !!settings.simpleLanguage,
    easyMode: !!settings.easyMode,
    listFirstFind: !!settings.listFirstFind,
    preferredLanguage: settings.preferredLanguage || 'en',
    screenReaderOptimized: !!settings.screenReaderOptimized,
    smsGuideEnabled: !!settings.smsGuideEnabled,
  }
}

/** @returns {AccessibilitySettings} */
export function loadAccessibilitySettings() {
  if (typeof window === 'undefined') return { ...DEFAULT_A11Y_SETTINGS }
  try {
    const raw = window.localStorage.getItem(A11Y_STORAGE_KEY)
    if (!raw) return { ...DEFAULT_A11Y_SETTINGS }
    const parsed = JSON.parse(raw)
    return mergeAccessibilitySettings(parsed)
  } catch {
    return { ...DEFAULT_A11Y_SETTINGS }
  }
}

/** @param {AccessibilitySettings} settings */
export function saveAccessibilitySettings(settings) {
  if (typeof window === 'undefined') return
  window.localStorage.setItem(A11Y_STORAGE_KEY, JSON.stringify(settings))
}

/** @param {AccessibilitySettings} settings */
export function applyAccessibilityClasses(settings) {
  if (typeof document === 'undefined') return
  const root = document.documentElement
  root.classList.toggle('a11y-large-text', settings.largeText)
  root.classList.toggle('a11y-high-contrast', settings.highContrast)
  root.classList.toggle('a11y-reduce-motion', settings.reduceMotion)
  root.classList.toggle('a11y-simple-language', settings.simpleLanguage)
  root.classList.toggle('a11y-easy-mode', settings.easyMode)
  root.classList.toggle('a11y-list-first-find', settings.listFirstFind)
  root.classList.toggle('a11y-screen-reader', settings.screenReaderOptimized)
  root.setAttribute('lang', settings.preferredLanguage || 'en')
}
