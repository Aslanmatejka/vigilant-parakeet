import { useState, useEffect, useCallback, useRef } from 'react'
import { useAuthContext } from '../AuthContext.jsx'
import { useNouriGuide } from '../NouriGuideContext.jsx'
import { buildAccessibilityProfilePayload } from '../accessibilityProfileService.js'
import { getNouriGuideState, clearGuideState } from '../nouriGuide/engine.js'
import { recordGuideFailure, recordGuideSuccess, clearGuideFailures } from '../nouriGuide/humanHandoff.js'
import {
  pickInitialChatLanguage,
  chatErrorMessage,
  getToneLabels,
  CHAT_UI_LANGUAGES,
  isValidChatLanguage,
  t as chatT,
} from '../chatI18n.js'
import aiChatService from '../services/aiChatService.js'
import normalizeToolResults from '../services/normalizeToolResults.js'

function normalizeAssistantAction(action) {
  if (!action || typeof action !== 'object') return action || null
  if (action.action === 'navigate') return action
  if (action.href) {
    return { action: 'navigate', target: action.href, label: action.label || 'Go' }
  }
  return action
}

// Pick the best initial UI language (see utils/chatI18n.js).
function pickInitialLanguage(user, preferredLanguage) {
  return pickInitialChatLanguage(user, preferredLanguage)
}

export const AI_TONE_OPTIONS = ['warm', 'professional', 'casual', 'empathetic']
const DEFAULT_TONE = 'warm'

export const AI_TONE_LABELS = {
  en: getToneLabels('en'),
  es: getToneLabels('es'),
  fr: getToneLabels('fr'),
  vi: getToneLabels('vi'),
  zh: getToneLabels('zh'),
}

export { CHAT_UI_LANGUAGES }

function pickInitialTone() {
  try {
    if (typeof sessionStorage !== 'undefined') {
      const cached = sessionStorage.getItem('dg.ai.tone')
      if (cached && AI_TONE_OPTIONS.includes(cached)) return cached
    }
  } catch { /* private mode */ }
  return DEFAULT_TONE
}

function pageKeyFromPath(pathname) {
  const p = String(pathname || '/').replace(/\/+$/, '') || '/'
  if (p === '/') return 'home'
  if (p.startsWith('/admin')) return 'admin'
  if (p.startsWith('/community/')) return 'community'
  if (p.startsWith('/blog')) return 'blog'
  const exact = {
    '/share': 'share',
    '/find': 'find',
    '/near-me': 'near-me',
    '/request': 'request',
    '/claim': 'claim',
    '/profile': 'profile',
    '/settings': 'settings',
    '/receipts': 'receipts',
    '/dashboard': 'dashboard',
    '/listings': 'listings',
    '/community-requests': 'community-requests',
    '/login': 'login',
    '/signup': 'signup',
    '/donations': 'donations',
    '/notifications': 'notifications',
    '/recipes': 'recipes',
    '/contact': 'contact',
    '/how-it-works': 'how-it-works',
    '/sponsors': 'sponsors',
    '/donate': 'donate',
    '/faqs': 'faqs',
    '/news': 'news',
    '/featured': 'featured',
  }
  if (exact[p]) return exact[p]
  return p.replace(/^\//, '').split('/')[0] || 'unknown'
}

function snapshotGuideState() {
  const g = getNouriGuideState() || {}
  let path = ''
  let search = ''
  let hash = ''
  try {
    if (typeof window !== 'undefined') {
      path = window.location.pathname || ''
      search = window.location.search || ''
      hash = window.location.hash || ''
    }
  } catch { /* SSR / private */ }
  const pageKey = pageKeyFromPath(path)
  return {
    formId: g.formId || null,
    goalKey: g.goalKey || null,
    stepIndex: g.stepIndex ?? 0,
    stepTotal: g.stepTotal ?? 0,
    fieldName: g.fieldName || '',
    label: g.label || '',
    section: g.section || '',
    source: g.source || 'system',
    path,
    search,
    hash,
    pageKey,
  }
}

export function useAIChat() {
  const { user, isAuthenticated, initialized } = useAuthContext()
  const { settings: a11ySettings } = useNouriGuide()
  const [messages, setMessages] = useState([])
  const [isLoading, setIsLoading] = useState(false)
  const [error, setError] = useState(null)
  const [language, setLanguage] = useState(() => pickInitialLanguage(null, 'en'))
  const [tone, setToneState] = useState(pickInitialTone)
  // Mirror the active language into sessionStorage so a page refresh
  // mid-conversation doesn't snap a Spanish user back to English.
  useEffect(() => {
    try {
      if (typeof sessionStorage !== 'undefined') {
        sessionStorage.setItem('dg.ai.lang', language)
      }
    } catch { /* noop */ }
  }, [language])
  useEffect(() => {
    try {
      if (typeof sessionStorage !== 'undefined') {
        sessionStorage.setItem('dg.ai.tone', tone)
      }
    } catch { /* noop */ }
  }, [tone])
  const [historyLoaded, setHistoryLoaded] = useState(false)
  // Monotonic counter so a slow earlier request can't append after a
  // newer, faster one finished. Prevents out-of-order assistant bubbles
  // when the user double-sends or retries quickly.
  const reqSeqRef = useRef(0)
  const isLoadingRef = useRef(false)

  // When the active user changes (logout → login as a different account,
  // or guest → authenticated), we MUST forget the previous chat so the
  // new session starts clean and re-fetches the right history.
  useEffect(() => {
    reqSeqRef.current += 1
    setHistoryLoaded(false)
    // Adopt the freshly-logged-in user's preferred language if they
    // have one set. Falls back to current state (which already honored
    // navigator.language at mount). Never auto-flips an EN session to
    // ES once the user has chosen a language explicitly via the toggle.
    const preferred = pickInitialLanguage(user, a11ySettings?.preferredLanguage)
    setLanguage((prev) => (preferred !== 'en' ? preferred : prev))
    setMessages([])
    setToneState(pickInitialTone())
    setError(null)
  }, [user?.id, isAuthenticated, a11ySettings?.preferredLanguage])

  // Load conversation history from backend when user logs in.
  // Gate on `initialized` so we don't fire this authenticated call during the
  // cold-load window where isAuthenticated is true (restored from localStorage)
  // but the Supabase session token isn't ready yet — that race returned 401s.
  useEffect(() => {
    if (!initialized || !isAuthenticated || !user?.id || historyLoaded) return

    let cancelled = false
    const loadHistory = async () => {
      try {
        const history = await aiChatService.getHistory(user.id, 50)
        if (cancelled) return
        if (!history?.length) {
          setHistoryLoaded(true)
          return
        }

        const formatted = history
          .filter(msg => {
            // Drop internal silent assistant turns (metadata flag preferred;
            // legacy rows used a "[Action completed]" prefix). Keep them
            // out of the UI but the backend still uses them as context.
            if ((msg.metadata && (msg.metadata.silent_trigger || msg.metadata.silent)) === true) return false
            if (msg.role !== 'user') return true
            const text = String(msg.message || '').trimStart()
            return !text.startsWith('[Action completed]')
                && !text.startsWith('[Acción completada]')
                && !text.startsWith('[Accion completada]')
          })
          .map(msg => {
            // Only treat a real UUID as the backend row id; otherwise we
            // emit a synthetic local key for React and leave
            // conversationId null so feedback writes are skipped instead
            // of being orphaned against a fake "hist-..." id.
            const isUuid = typeof msg.id === 'string' && /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i.test(msg.id)
            return {
              id: isUuid ? msg.id : `hist-${msg.created_at}-${msg.role}`,
              role: msg.role,
              conversationId: isUuid ? msg.id : null,
              message: msg.message,
              metadata: msg.metadata,
              toolResults: Array.isArray(msg.metadata?.actions)
                ? normalizeToolResults(msg.metadata.actions)
                : [],
              suggestions: Array.isArray(msg.metadata?.suggestions)
                ? msg.metadata.suggestions
                : [],
              requiresConfirmation: !!msg.metadata?.requires_confirmation,
              pendingAction: msg.metadata?.pending_action || null,
              fromHistory: true,
              timestamp: msg.created_at,
            }
          })

        // Preserve the current language for the welcome bubble so a
        // Spanish session doesn't get an English "Hi! I'm Nouri..."
        // wedged in at the top after history loads.
        setMessages(formatted)
        setHistoryLoaded(true)
      } catch (err) {
        console.error('Failed to load AI history:', err)
        if (!cancelled) setHistoryLoaded(true)
      }
    }

    loadHistory()
    return () => { cancelled = true }
  }, [initialized, isAuthenticated, user?.id, historyLoaded, language])

  // Load saved conversation tone from backend when user logs in.
  useEffect(() => {
    if (!initialized || !isAuthenticated || !user?.id) return
    let cancelled = false
    aiChatService.getTone(user.id).then((saved) => {
      if (!cancelled && saved && AI_TONE_OPTIONS.includes(saved)) {
        setToneState(saved)
      }
    }).catch(() => {})
    return () => { cancelled = true }
  }, [initialized, isAuthenticated, user?.id])

  const setTone = useCallback(async (nextTone) => {
    const normalized = AI_TONE_OPTIONS.includes(nextTone) ? nextTone : DEFAULT_TONE
    setToneState(normalized)
    if (user?.id && isAuthenticated) {
      try {
        await aiChatService.setTone(user.id, normalized)
      } catch (err) {
        console.warn('Failed to save AI tone preference:', err)
      }
    }
  }, [user?.id, isAuthenticated])

  /**
   * Translate a typed backend error code into a friendly bubble message.
   * Falls back to a generic line for unknown codes so the user is never
   * stuck staring at a raw `error_code` like "model_unavailable".
   */
  const friendlyErrorMessage = useCallback((code, lang = language) => {
    const profileLang = (user?.language || '').toString().toLowerCase()
    const resolved = lang || (profileLang.startsWith('es') ? 'es' : language)
    return chatErrorMessage(code || 'internal', resolved)
  }, [language, user?.language])

  const renderSignInRequired = useCallback(() => {
    setMessages(prev => [...prev, {
      id: `assistant-signin-${Date.now()}`,
      role: 'assistant',
      message: chatT(language, 'signInRequired'),
      isError: false,
      timestamp: new Date().toISOString(),
    }])
  }, [language])

  /**
   * Core send-and-render pipeline shared by `sendMessage`, `retryMessage`,
   * and `regenerateLast`. Centralized so all three pathways apply the same
   * ordering guard, typed-error handling, language switch, and bubble shape.
   *
   * `userMessage` is the bubble already in state (or about to be) representing
   * the user turn. If passed, we don't re-add it.
   */
  const runChatTurn = useCallback(async (text, { userMessage = null, replaceErrorId = null } = {}) => {
    if (!text?.trim()) return
    const seq = ++reqSeqRef.current
    isLoadingRef.current = true
    setIsLoading(true)
    setError(null)

    // If we're re-running after a failure, remove the failed bubble so the
    // chat doesn't accumulate stale errors when a retry succeeds.
    if (replaceErrorId) {
      setMessages(prev => prev.filter(m => m.id !== replaceErrorId))
    }

    // If caller didn't provide a userMessage (i.e. plain sendMessage), add one.
    if (!userMessage) {
      const userMsg = {
        id: `user-${Date.now()}`,
        role: 'user',
        message: text.trim(),
        timestamp: new Date().toISOString(),
      }
      setMessages(prev => [...prev, userMsg])
    }

    try {
      const accessibilityProfile = buildAccessibilityProfilePayload(a11ySettings)
      const result = await aiChatService.sendMessage(text.trim(), {
        userId: user.id,
        tone,
        accessibilityProfile,
        guideState: snapshotGuideState(),
      })

      // Drop the response if a newer request was started while this one
      // was in flight — prevents out-of-order assistant bubbles.
      if (seq !== reqSeqRef.current) return

      // Update language from backend detection
      if (result.lang && result.lang !== language) {
        setLanguage(result.lang)
      }
      if (result.tone && AI_TONE_OPTIONS.includes(result.tone) && result.tone !== tone) {
        setToneState(result.tone)
      }

      // Typed backend error — render an error bubble carrying the retry
      // metadata so the panel can show a Retry button + diagnostic chip.
      if (result.error) {
        recordGuideFailure(result.error.code || 'chat_error')
        const err = result.error
        const errorBubble = {
          id: `error-${Date.now()}`,
          role: 'assistant',
          message: friendlyErrorMessage(err.code, result.lang || language),
          isError: true,
          errorCode: err.code,
          errorRetryable: !!err.retryable,
          errorRetryAfter: err.retryAfter ?? null,
          requestId: err.requestId || result.requestId || null,
          // Stash the originating user text so the Retry button can re-send
          // even after the user has typed other things in the meantime.
          retryText: text.trim(),
          timestamp: new Date().toISOString(),
        }
        setMessages(prev => [...prev, errorBubble])
        setError(err.message)
        return
      }

      const assistantMsg = {
        id: `assistant-${Date.now()}`,
        role: 'assistant',
        message: result.response,
        audioUrl: result.audioUrl,
        conversationId: result.conversationId,
        toolResults: result.toolResults || [],
        suggestions: result.suggestions || [],
        action: normalizeAssistantAction(result.action),
        requiresConfirmation: !!result.requiresConfirmation,
        pendingAction: result.pendingAction || null,
        degraded: !!result.degraded,
        source: result.source || null,
        requestId: result.requestId || null,
        timestamp: new Date().toISOString(),
      }

      setMessages(prev => [...prev, assistantMsg])
      recordGuideSuccess()
    } catch (err) {
      if (seq !== reqSeqRef.current) return
      recordGuideFailure(err?.message || 'network_error')
      const isNetwork = !err?.status
        || err.status === 0
        || /fetch|network|ECONNREFUSED|Failed to fetch/i.test(String(err?.message || ''))
      const errorCode = isNetwork ? 'network' : 'internal'
      const errorBubble = {
        id: `error-${Date.now()}`,
        role: 'assistant',
        message: friendlyErrorMessage(errorCode, language),
        isError: true,
        errorCode,
        errorRetryable: true,
        retryText: text.trim(),
        timestamp: new Date().toISOString(),
      }
      setMessages(prev => [...prev, errorBubble])
      setError(err.message)
    } finally {
      if (seq === reqSeqRef.current) {
        isLoadingRef.current = false
        setIsLoading(false)
      }
    }
  }, [language, tone, user?.id, friendlyErrorMessage, a11ySettings])

  const sendMessage = useCallback(async (text) => {
    if (!text?.trim() || isLoadingRef.current) return
    if (!isAuthenticated || !user?.id) {
      // Add the user bubble so the conversation reads naturally, then the
      // assistant explains why we can't respond. Avoids hitting /api/ai/chat
      // with a nil UUID that the backend will 401.
      setMessages(prev => [...prev, {
        id: `user-${Date.now()}`,
        role: 'user',
        message: text.trim(),
        timestamp: new Date().toISOString(),
      }])
      renderSignInRequired()
      return
    }
    await runChatTurn(text)
  }, [runChatTurn, isAuthenticated, user?.id, renderSignInRequired])

  /**
   * Retry a failed assistant turn. Resends the original user text (stashed
   * on the error bubble as `retryText`) and removes the failed bubble so
   * the chat ends up clean if the retry succeeds.
   */
  const retryMessage = useCallback(async (errorMessageId) => {
    if (isLoading) return
    const target = messages.find(m => m.id === errorMessageId)
    if (!target || !target.isError || !target.retryText) return
    await runChatTurn(target.retryText, { replaceErrorId: errorMessageId })
  }, [isLoading, messages, runChatTurn])

  /**
   * Regenerate the most recent assistant response: re-runs the previous
   * user message to get a fresh answer. Doesn't add a duplicate user
   * bubble — we reuse the existing one.
   */
  const regenerateLast = useCallback(async () => {
    if (isLoading) return
    // Find the most recent user message that has an assistant response after it.
    let lastUserIdx = -1
    for (let i = messages.length - 1; i >= 0; i--) {
      if (messages[i].role === 'user') { lastUserIdx = i; break }
    }
    if (lastUserIdx === -1) return
    const lastUser = messages[lastUserIdx]
    // Drop everything after the user message so we don't end up with two
    // assistant answers competing for screen space.
    setMessages(prev => prev.slice(0, lastUserIdx + 1))
    await runChatTurn(lastUser.message, { userMessage: lastUser })
  }, [isLoading, messages, runChatTurn])

  const sendVoice = useCallback(async (audioBlob) => {
    if (isLoadingRef.current || !audioBlob) return
    if (!isAuthenticated || !user?.id) {
      renderSignInRequired()
      return
    }

    const seq = ++reqSeqRef.current
    isLoadingRef.current = true
    setIsLoading(true)
    setError(null)

    try {
      const accessibilityProfile = buildAccessibilityProfilePayload(a11ySettings)
      const result = await aiChatService.sendVoice(audioBlob, {
        userId: user.id,
        includeAudio: true,
        tone,
        accessibilityProfile,
        guideState: snapshotGuideState(),
      })

      if (seq !== reqSeqRef.current) return

      if (result.lang && result.lang !== language) {
        setLanguage(result.lang)
      }
      if (result.tone && AI_TONE_OPTIONS.includes(result.tone) && result.tone !== tone) {
        setToneState(result.tone)
      }

      if (result.transcript) {
        setMessages(prev => [...prev, {
          id: `user-${Date.now()}`,
          role: 'user',
          message: result.transcript,
          source: 'voice',
          timestamp: new Date().toISOString(),
        }])
      }

      const assistantMsg = {
        id: `assistant-${Date.now()}`,
        role: 'assistant',
        message: result.response,
        audioUrl: result.audioUrl,
        conversationId: result.conversationId,
        toolResults: result.toolResults || [],
        suggestions: result.suggestions || [],
        action: normalizeAssistantAction(result.action),
        requiresConfirmation: !!result.requiresConfirmation,
        pendingAction: result.pendingAction || null,
        source: 'voice',
        degraded: !!result.degraded,
        requestId: result.requestId || null,
        timestamp: new Date().toISOString(),
      }

      setMessages(prev => [...prev, assistantMsg])
    } catch (err) {
      if (seq !== reqSeqRef.current) return
      const aiErr = err.aiError
      // "invalid_input" from the voice endpoint means Whisper heard noise /
      // couldn't make out speech. That's a normal hiccup, not a failure — show
      // a calm, dismissible nudge (not a red error bubble) so a hands-free
      // session can simply stand down and try again.
      const unintelligible = aiErr?.code === 'invalid_input'
      const errorMsg = {
        id: `error-${Date.now()}`,
        role: 'assistant',
        message: unintelligible
          ? (language === 'es'
            ? 'No te escuché con claridad. Intenta hablar de nuevo o escribe tu mensaje.'
            : "I didn't quite catch that. Please try speaking again or type your message.")
          : aiErr
          ? friendlyErrorMessage(aiErr.code, language)
          : (language === 'es'
            ? 'No pude procesar tu audio. Por favor usa el campo de texto.'
            : "I couldn't process your voice message. Please try typing instead."),
        isError: !unintelligible,
        errorCode: aiErr?.code || 'internal',
        errorRetryable: unintelligible ? true : (aiErr?.retryable ?? true),
        errorRetryAfter: aiErr?.retryAfter ?? null,
        requestId: err.requestId || aiErr?.requestId || null,
        retryText: null,
        source: 'voice',
        timestamp: new Date().toISOString(),
      }

      setMessages(prev => [...prev, errorMsg])
      // Don't latch a global error state for benign "didn't hear you" cases.
      if (!unintelligible) setError(err.message)
    } finally {
      if (seq === reqSeqRef.current) {
        isLoadingRef.current = false
        setIsLoading(false)
      }
    }
  }, [language, tone, user?.id, friendlyErrorMessage, isAuthenticated, renderSignInRequired])

  const clearHistory = useCallback(async () => {
    // Drop any in-flight turn so a slow response can't repopulate the thread.
    reqSeqRef.current += 1
    isLoadingRef.current = false
    setIsLoading(false)

    let ok = true
    try {
      if (isAuthenticated && user?.id) {
        await aiChatService.clearHistory(user.id)
      }
    } catch (err) {
      console.error('Failed to clear AI history:', err)
      setError(err.message || 'Failed to clear conversation')
      ok = false
    }

    // Always wipe the visible thread + local caches so Clear feels immediate
    // even if the network delete fails.
    setMessages([])
    if (ok) setError(null)
    setHistoryLoaded(true)
    try { clearGuideState() } catch { /* noop */ }
    try { clearGuideFailures() } catch { /* noop */ }
    return ok
  }, [isAuthenticated, user?.id])

  const submitFeedback = useCallback(async (messageId, rating) => {
    if (!isAuthenticated || !user?.id) return
    const msg = messages.find(m => m.id === messageId)
    const convId = msg?.conversationId
    if (!convId) return
    try {
      await aiChatService.submitFeedback(convId, user.id, rating)
    } catch (err) {
      console.error('Failed to submit feedback:', err)
    }
  }, [isAuthenticated, user?.id, messages])

  /**
   * Append a synthetic message (user or assistant) directly into the
   * local conversation without hitting the backend. Used for client-side
   * flows like file uploads (photo / CSV → bulk-listings) where the chat
   * UI narrates the action locally.
   */
  const appendLocalMessage = useCallback((msg) => {
    if (!msg || !msg.role || !msg.message) return null
    const id = msg.id || `${msg.role}-local-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`
    const enriched = {
      id,
      timestamp: new Date().toISOString(),
      ...msg,
    }
    setMessages(prev => [...prev, enriched])
    return id
  }, [])

  /**
   * Send a context message to the AI backend without showing a user bubble.
   * The AI's response IS shown as a normal assistant message.
   * Used after events like bulk listing creation so Nouri can react naturally.
   */
  const sendSilentMessage = useCallback(async (text) => {
    if (!text?.trim()) return
    // Silent prompts are a no-op for guests — there's no user bubble to
    // explain why, and showing a sign-in nudge in response to a backend
    // event would be confusing. Just bail.
    if (!isAuthenticated || !user?.id) return
    // Intentionally NOT setting isLoading — silent prompts run in the
    // background and must not block the user from typing/sending real
    // messages. The assistant reply still appears as a normal bubble.
    try {
      const accessibilityProfile = buildAccessibilityProfilePayload(a11ySettings)
      const result = await aiChatService.sendMessage(text.trim(), {
        userId: user.id,
        silent: true,
        accessibilityProfile,
        guideState: snapshotGuideState(),
      })
      if (result.lang && result.lang !== language) setLanguage(result.lang)
      if (result.error) {
        console.warn('sendSilentMessage backend error:', result.error.code)
        return
      }
      if (!result.response) return
      const assistantMsg = {
        id: `assistant-${Date.now()}`,
        role: 'assistant',
        message: result.response,
        toolResults: result.toolResults || [],
        suggestions: result.suggestions || [],
        action: normalizeAssistantAction(result.action),
        degraded: !!result.degraded,
        timestamp: new Date().toISOString(),
      }
      setMessages(prev => [...prev, assistantMsg])
    } catch (err) {
      // Don't surface to the user, but log for debug visibility so
      // failed bulk-upload reactions don't disappear silently in dev.
      console.warn('sendSilentMessage failed:', err)
    }
  }, [language, user?.id, isAuthenticated, a11ySettings])

  const confirmPendingAction = useCallback(async (confirmed = true) => {
    if (!isAuthenticated || !user?.id || isLoadingRef.current) return
    const seq = ++reqSeqRef.current
    isLoadingRef.current = true
    setIsLoading(true)
    setError(null)
    try {
      const result = await aiChatService.confirmAction(user.id, confirmed)
      if (seq !== reqSeqRef.current) return
      if (result.error) {
        setError(result.error.message)
        return
      }
      if (result.lang && result.lang !== language) setLanguage(result.lang)
      const assistantMsg = {
        id: `assistant-${Date.now()}`,
        role: 'assistant',
        message: result.response,
        toolResults: result.toolResults || [],
        suggestions: result.suggestions || [],
        action: normalizeAssistantAction(result.action),
        requiresConfirmation: false,
        pendingAction: null,
        timestamp: new Date().toISOString(),
      }
      setMessages(prev => [...prev, assistantMsg])
    } catch (err) {
      if (seq !== reqSeqRef.current) return
      setError(err.message)
    } finally {
      if (seq === reqSeqRef.current) {
        isLoadingRef.current = false
        setIsLoading(false)
      }
    }
  }, [isAuthenticated, user?.id, language])

  return {
    messages,
    sendMessage,
    sendVoice,
    isLoading,
    error,
    language,
    setLanguage,
    clearHistory,
    submitFeedback,
    appendLocalMessage,
    sendSilentMessage,
    isAuthenticated,
    // New: error recovery actions
    retryMessage,
    regenerateLast,
    historyLoaded,
    tone,
    setTone,
    confirmPendingAction,
  }
}
