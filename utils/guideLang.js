/** @typedef {'en' | 'es' | 'fr' | 'vi' | 'zh'} GuideLang */

/** @type {Record<GuideLang, string>} BCP-47 tags for Web Speech / TTS hints */
export const GUIDE_TTS_LANG = {
  en: 'en-US',
  es: 'es-ES',
  fr: 'fr-FR',
  vi: 'vi-VN',
  zh: 'zh-CN',
}

/**
 * Normalize a language code to a supported guide language.
 * @param {string|null|undefined} code
 * @returns {GuideLang}
 */
export function normalizeGuideLang(code) {
  const raw = String(code || 'en').toLowerCase().trim()
  if (raw.startsWith('es')) return 'es'
  if (raw.startsWith('fr')) return 'fr'
  if (raw.startsWith('vi')) return 'vi'
  if (raw.startsWith('zh')) return 'zh'
  return 'en'
}

/**
 * Resolve guide language: explicit override → accessibility setting → default.
 * @param {string|null|undefined} override
 * @param {string|null|undefined} settingsLang
 * @param {GuideLang} [fallback='en']
 */
export function resolveGuideLang(override, settingsLang, fallback = 'en') {
  if (override) return normalizeGuideLang(override)
  if (settingsLang) return normalizeGuideLang(settingsLang)
  return normalizeGuideLang(fallback)
}

/** @param {GuideLang} lang */
export function ttsLangTag(lang) {
  return GUIDE_TTS_LANG[normalizeGuideLang(lang)] || GUIDE_TTS_LANG.en
}
