/**
 * Unified Accessibility + AI Guide context.
 * Single conductor: settings, step state, voice, captions, DOM focus.
 */
import React, {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
} from 'react'
import {
  applyAccessibilityClasses,
  DEFAULT_A11Y_SETTINGS,
  loadAccessibilitySettings,
  mergeAccessibilitySettings,
  saveAccessibilitySettings,
} from './accessibilityStorage'
import {
  loadAccessibilityProfile,
  saveAccessibilityProfile,
} from './accessibilityProfileService'
import { useAuthContext } from './AuthContext'
import {
  subscribeNouriGuide,
  setNouriA11yPrefs,
  setGuideMuted,
  dismissGuide,
  startFormGuide,
  syncGuideFromFormField,
  handleChatAssistantMessage,
  resumeGuide,
  replayGuide,
  speakGuideText,
  cancelSpeech,
  loadPersistedGuideState,
  reportFieldError,
  notifyFieldChanged,
} from './nouriGuide/engine'

const NouriGuideContext = createContext(null)

export function NouriGuideProvider({ children }) {
  const { user, isAuthenticated } = useAuthContext()
  const [settings, setSettings] = useState(() => loadAccessibilitySettings())
  const profileLoadedRef = useRef(false)
  const saveTimerRef = useRef(null)
  const [guide, setGuide] = useState(() => loadPersistedGuideState() || {
    source: 'system',
    caption: '',
    text: '',
    isSpeaking: false,
    isMuted: false,
    isDismissed: false,
    hasResume: false,
    stepIndex: 0,
    stepTotal: 0,
    section: '',
    label: '',
    fieldName: '',
    formId: null,
    goalKey: null,
  })

  useEffect(() => {
    applyAccessibilityClasses(settings)
    saveAccessibilitySettings(settings)
    setNouriA11yPrefs({
      preferTextOverVoice: settings.preferTextOverVoice,
      simpleLanguage: settings.simpleLanguage,
      alwaysShowCaptions: settings.alwaysShowCaptions,
      preferredLanguage: settings.preferredLanguage,
    })

    if (!isAuthenticated || !user?.id) return

    if (saveTimerRef.current) clearTimeout(saveTimerRef.current)
    saveTimerRef.current = setTimeout(() => {
      saveAccessibilityProfile(user.id, settings)
    }, 800)

    return () => {
      if (saveTimerRef.current) clearTimeout(saveTimerRef.current)
    }
  }, [settings, isAuthenticated, user?.id])

  // Load server profile when user signs in (merge server wins over local defaults)
  useEffect(() => {
    if (!isAuthenticated || !user?.id) {
      profileLoadedRef.current = false
      return
    }

    let cancelled = false
    ;(async () => {
      const remote = await loadAccessibilityProfile(user.id)
      if (cancelled) return
      if (remote) {
        setSettings((prev) => mergeAccessibilitySettings({ ...prev, ...remote }))
      }
      profileLoadedRef.current = true
    })()

    return () => { cancelled = true }
  }, [isAuthenticated, user?.id])

  useEffect(() => {
    const mq = window.matchMedia('(prefers-reduced-motion: reduce)')
    if (!mq.matches) return
    setSettings((prev) => (prev.reduceMotion ? prev : { ...prev, reduceMotion: true }))
  }, [])

  useEffect(() => {
    return subscribeNouriGuide(setGuide)
  }, [])

  const updateSetting = useCallback((key, value) => {
    setSettings((prev) => ({ ...prev, [key]: value }))
  }, [])

  const resetSettings = useCallback(() => {
    setSettings({ ...DEFAULT_A11Y_SETTINGS })
  }, [])

  const toggleMute = useCallback(() => {
    setGuideMuted(!guide.isMuted)
  }, [guide.isMuted])

  const dismiss = useCallback(() => {
    dismissGuide()
  }, [])

  const registerForm = useCallback((opts, lang) => {
    const resolved = lang || settings.preferredLanguage || 'en'
    startFormGuide(opts, { lang: resolved })
  }, [settings.preferredLanguage])

  const onFieldFocus = useCallback((opts, lang) => {
    const resolved = lang || settings.preferredLanguage || 'en'
    syncGuideFromFormField(opts, { lang: resolved })
  }, [settings.preferredLanguage])

  const syncFromChat = useCallback((message, { lang, speak = false } = {}) => {
    const resolved = lang || settings.preferredLanguage || 'en'
    return handleChatAssistantMessage(message, { lang: resolved, speak })
  }, [settings.preferredLanguage])

  const resume = useCallback((lang) => {
    resumeGuide({ lang: lang || settings.preferredLanguage || 'en' })
  }, [settings.preferredLanguage])

  const replay = useCallback((lang) => {
    replayGuide({ lang: lang || settings.preferredLanguage || 'en' })
  }, [settings.preferredLanguage])

  const speak = useCallback((text, lang) => {
    speakGuideText(text, { lang: lang || settings.preferredLanguage || 'en' })
  }, [settings.preferredLanguage])

  const cancelVoice = useCallback(() => {
    cancelSpeech()
  }, [])

  const reportFieldErrorFn = useCallback((formId, fieldName, errorMessage, label) => {
    reportFieldError(formId, fieldName, errorMessage, label)
  }, [])

  const notifyFieldActivity = useCallback(() => {
    notifyFieldChanged()
  }, [])

  const value = useMemo(
    () => ({
      settings,
      guide,
      updateSetting,
      resetSettings,
      toggleMute,
      dismiss,
      registerForm,
      onFieldFocus,
      syncFromChat,
      resume,
      replay,
      speak,
      cancelVoice,
      reportFieldError: reportFieldErrorFn,
      notifyFieldActivity,
    }),
    [
      settings,
      guide,
      updateSetting,
      resetSettings,
      toggleMute,
      dismiss,
      registerForm,
      onFieldFocus,
      syncFromChat,
      resume,
      replay,
      speak,
      cancelVoice,
      reportFieldErrorFn,
      notifyFieldActivity,
    ],
  )

  return (
    <NouriGuideContext.Provider value={value}>
      {children}
    </NouriGuideContext.Provider>
  )
}

export function useNouriGuide() {
  const ctx = useContext(NouriGuideContext)
  if (!ctx) {
    throw new Error('useNouriGuide must be used within NouriGuideProvider')
  }
  return ctx
}

/** @deprecated alias — same unified context */
export function useAccessibility() {
  const ctx = useContext(NouriGuideContext)
  if (!ctx) {
    return {
      settings: DEFAULT_A11Y_SETTINGS,
      updateSetting: () => {},
      resetSettings: () => {},
    }
  }
  return {
    settings: ctx.settings,
    updateSetting: ctx.updateSetting,
    resetSettings: ctx.resetSettings,
  }
}

/** Back-compat provider alias */
export const AccessibilityProvider = NouriGuideProvider
