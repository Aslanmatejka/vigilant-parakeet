/**
 * Form voice guide — thin adapter over unified NouriGuideContext.
 */
import { useEffect, useRef, useCallback } from 'react'
import { useSearchParams } from 'react-router-dom'
import { useNouriGuide } from '../utils/NouriGuideContext'
import { resolveGuideLang } from '../utils/guideLang'
import { reapplyPendingGuideField } from '../utils/formFieldGuide'

export {
  SHARE_FOOD_WELCOME,
  REQUEST_FOOD_WELCOME,
  CLAIM_FOOD_WELCOME,
  SHARE_FOOD_HINTS,
  REQUEST_FOOD_HINTS,
  CLAIM_FOOD_HINTS,
  LOGIN_WELCOME,
  SIGNUP_WELCOME,
  FIND_FOOD_WELCOME,
  RECEIPTS_WELCOME,
  BULK_UPLOAD_WELCOME,
  LOGIN_HINTS,
  SIGNUP_HINTS,
  FIND_FOOD_HINTS,
  RECEIPTS_HINTS,
  BULK_UPLOAD_HINTS,
  FORM_GUIDE_CONFIG,
} from './formGuideHints'

const FIELD_DEBOUNCE_MS = 80

export default function useFormVoiceGuide({
  hints = {},
  welcomeMessage,
  lang = 'en',
  formId = 'form',
}) {
  const [searchParams] = useSearchParams()
  const {
    settings,
    guide,
    registerForm,
    onFieldFocus,
    toggleMute,
    dismiss,
    replay,
    reportFieldError,
    notifyFieldActivity,
  } = useNouriGuide()

  const guideLang = resolveGuideLang(
    searchParams.get('lang'),
    settings.preferredLanguage,
    lang,
  )
  const forceGuide = searchParams.get('guide') === '1'

  const welcomedRef = useRef(false)
  const fieldTimerRef = useRef(null)

  useEffect(() => {
    if (welcomedRef.current || guide.isDismissed || !welcomeMessage) return
    welcomedRef.current = true
    const delay = forceGuide ? 0 : 80
    const timer = setTimeout(() => {
      registerForm({ formId, welcomeMessage, hints }, guideLang)
    }, delay)
    return () => clearTimeout(timer)
  }, [formId, welcomeMessage, hints, guideLang, registerForm, guide.isDismissed, forceGuide])

  // SMS / shared deep links: ?guide=1&lang=es retriggers welcome immediately
  useEffect(() => {
    if (!forceGuide || guide.isDismissed || !welcomeMessage) return
    welcomedRef.current = true
    registerForm({ formId, welcomeMessage, hints }, guideLang)
  }, [forceGuide, formId, welcomeMessage, hints, guideLang, registerForm, guide.isDismissed])

  const speakField = useCallback((fieldName) => {
    if (guide.isDismissed) return
    const entry = hints[fieldName]
    if (!entry) return

    const text = typeof entry === 'string' ? entry : entry.text
    const label = typeof entry === 'string' ? null : entry.label
    if (!text) return

    notifyFieldActivity()

    if (fieldTimerRef.current) clearTimeout(fieldTimerRef.current)
    fieldTimerRef.current = setTimeout(() => {
      fieldTimerRef.current = null
      onFieldFocus({ formId, fieldName, label, text, hints }, guideLang)
    }, FIELD_DEBOUNCE_MS)
  }, [guide.isDismissed, hints, formId, guideLang, onFieldFocus, notifyFieldActivity])

  const speakWelcome = useCallback(() => {
    if (guide.isDismissed || !welcomeMessage) return
    registerForm({ formId, welcomeMessage, hints }, guideLang)
  }, [guide.isDismissed, welcomeMessage, formId, hints, guideLang, registerForm])

  const reportError = useCallback((fieldName, errorMessage) => {
    const entry = hints[fieldName]
    const label = entry && typeof entry !== 'string' ? entry.label : fieldName
    reportFieldError(formId, fieldName, errorMessage, label)
  }, [formId, hints, reportFieldError])

  useEffect(() => () => {
    if (fieldTimerRef.current) clearTimeout(fieldTimerRef.current)
  }, [])

  // When the form mounts or chat points at a field, re-try highlight
  // (chat often arrives before the form DOM exists).
  useEffect(() => {
    if (guide.isDismissed) return
    const t = setTimeout(() => reapplyPendingGuideField(), 60)
    return () => clearTimeout(t)
  }, [formId, guide.fieldName, guide.isDismissed])

  return {
    welcomeMessage,
    fieldName: guide.fieldName || '',
    activeHint: guide.fieldName
      ? { fieldName: guide.fieldName, label: guide.label, text: guide.text }
      : null,
    currentCaption: guide.caption || guide.text,
    isMuted: guide.isMuted,
    isSpeaking: guide.isSpeaking,
    isDismissed: guide.isDismissed,
    toggleMute,
    speakWelcome,
    dismiss,
    speakField,
    replay,
    reportError,
  }
}
