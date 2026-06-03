import { useState, useEffect, useCallback, useRef } from 'react'
import { useAuthContext } from '../AuthContext.jsx'
import aiChatService from '../services/aiChatService.js'
import normalizeToolResults from '../services/normalizeToolResults.js'

const INITIAL_MESSAGE = {
  id: 'welcome',
  role: 'assistant',
  message: "Hi! I'm Nouri, your DoGoods assistant. I can help you find food, share food, check your pickups, get recipes, set reminders, and more. How can I help you today?",
  timestamp: new Date().toISOString(),
}

const INITIAL_MESSAGE_ES = {
  id: 'welcome',
  role: 'assistant',
  message: '¡Hola! Soy Nouri, tu asistente de DoGoods. Puedo ayudarte a encontrar comida, compartir comida, verificar tus recogidas, obtener recetas, crear recordatorios y más. ¿En qué puedo ayudarte hoy?',
  timestamp: new Date().toISOString(),
}

function normalizeAssistantAction(action) {
  if (!action || typeof action !== 'object') return action || null
  if (action.action === 'navigate') return action
  if (action.href) {
    return { action: 'navigate', target: action.href, label: action.label || 'Go' }
  }
  return action
}

// Pick the best initial UI language:
//   1) sessionStorage cache from a prior turn this session.
//   2) explicit user.language profile preference, if Spanish.
//   3) navigator.language starting with 'es'.
//   4) default English.
function pickInitialLanguage(user) {
  try {
    if (typeof sessionStorage !== 'undefined') {
      const cached = sessionStorage.getItem('dg.ai.lang')
      if (cached === 'es' || cached === 'en') return cached
    }
  } catch { /* private mode */ }
  const pref = (user?.language || '').toString().toLowerCase()
  if (pref.startsWith('es')) return 'es'
  if (typeof navigator !== 'undefined') {
    const nav = (navigator.language || (navigator.languages && navigator.languages[0]) || '').toLowerCase()
    if (nav.startsWith('es')) return 'es'
  }
  return 'en'
}

export function useAIChat() {
  const { user, isAuthenticated } = useAuthContext()
  const [messages, setMessages] = useState([INITIAL_MESSAGE])
  const [isLoading, setIsLoading] = useState(false)
  const [error, setError] = useState(null)
  const [language, setLanguage] = useState(() => pickInitialLanguage(null))
  // Mirror the active language into sessionStorage so a page refresh
  // mid-conversation doesn't snap a Spanish user back to English.
  useEffect(() => {
    try {
      if (typeof sessionStorage !== 'undefined') {
        sessionStorage.setItem('dg.ai.lang', language)
      }
    } catch { /* noop */ }
  }, [language])
  const [historyLoaded, setHistoryLoaded] = useState(false)
  // Monotonic counter so a slow earlier request can't append after a
  // newer, faster one finished. Prevents out-of-order assistant bubbles
  // when the user double-sends or retries quickly.
  const reqSeqRef = useRef(0)

  // When the active user changes (logout → login as a different account,
  // or guest → authenticated), we MUST forget the previous chat so the
  // new session starts clean and re-fetches the right history.
  useEffect(() => {
    setHistoryLoaded(false)
    // Adopt the freshly-logged-in user's preferred language if they
    // have one set. Falls back to current state (which already honored
    // navigator.language at mount). Never auto-flips an EN session to
    // ES once the user has chosen a language explicitly via the toggle.
    const preferred = pickInitialLanguage(user)
    setLanguage((prev) => (preferred !== 'en' ? preferred : prev))
    setMessages([preferred === 'es' ? INITIAL_MESSAGE_ES : INITIAL_MESSAGE])
    setError(null)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [user?.id, isAuthenticated])

  // Load conversation history from backend when user logs in
  useEffect(() => {
    if (!isAuthenticated || !user?.id || historyLoaded) return

    let cancelled = false
    const loadHistory = async () => {
      try {
        const history = await aiChatService.getHistory(user.id, 50)
        if (cancelled || !history?.length) return

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
              fromHistory: true,
              timestamp: msg.created_at,
            }
          })

        // Preserve the current language for the welcome bubble so a
        // Spanish session doesn't get an English "Hi! I'm Nouri..."
        // wedged in at the top after history loads.
        const welcome = language === 'es' ? INITIAL_MESSAGE_ES : INITIAL_MESSAGE
        setMessages([welcome, ...formatted])
        setHistoryLoaded(true)
      } catch (err) {
        console.error('Failed to load AI history:', err)
      }
    }

    loadHistory()
    return () => { cancelled = true }
  }, [isAuthenticated, user?.id, historyLoaded, language])

  /**
   * Translate a typed backend error code into a friendly bubble message.
   * Falls back to a generic line for unknown codes so the user is never
   * stuck staring at a raw `error_code` like "model_unavailable".
   */
  const friendlyErrorMessage = useCallback((code, lang = language) => {
    // Fall back to the user's profile preference if the sticky lang
    // hasn't resolved yet (e.g. the very first turn errored before the
    // backend could echo a `lang` field). Without this, a Spanish-only
    // user can see their first error in English.
    const profileLang = (user?.language || '').toString().toLowerCase().startsWith('es') ? 'es' : null
    const isEs = (lang || profileLang || 'en') === 'es'
    switch (code) {
      case 'timeout':
        return isEs
          ? 'Mi respuesta tardó demasiado. Intenta de nuevo en un momento.'
          : 'My response took too long. Please try again in a moment.'
      case 'rate_limit':
        return isEs
          ? 'Estoy recibiendo muchas solicitudes ahora mismo. Intenta de nuevo en unos segundos.'
          : "I'm getting a lot of requests right now. Please try again in a few seconds."
      case 'model_unavailable':
        return isEs
          ? 'Mi modelo de IA no está disponible temporalmente. Vuelve a intentarlo.'
          : 'My AI model is temporarily unavailable. Please try again.'
      case 'circuit_open':
        return isEs
          ? 'Estoy recuperándome de un problema. Intenta de nuevo en unos segundos.'
          : "I'm recovering from a hiccup. Please try again in a few seconds."
      case 'auth':
        return isEs
          ? 'Hay un problema con mi autenticación. Contacta a soporte si esto continúa.'
          : "There's an authentication issue. Please contact support if this keeps happening."
      case 'invalid_input':
        return isEs
          ? 'No pude procesar esa solicitud. Intenta reformularla.'
          : "I couldn't process that request. Please try rephrasing it."
      default:
        return isEs
          ? 'Estoy teniendo un pequeño problema. ¿Puedes intentar de nuevo?'
          : "I'm having a little trouble right now. Please try again."
    }
  }, [language, user?.language])

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
      const result = await aiChatService.sendMessage(text.trim(), {
        userId: user?.id || '00000000-0000-0000-0000-000000000000',
      })

      // Drop the response if a newer request was started while this one
      // was in flight — prevents out-of-order assistant bubbles.
      if (seq !== reqSeqRef.current) return

      // Update language from backend detection
      if (result.lang && result.lang !== language) {
        setLanguage(result.lang)
      }

      // Typed backend error — render an error bubble carrying the retry
      // metadata so the panel can show a Retry button + diagnostic chip.
      if (result.error) {
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
        degraded: !!result.degraded,
        source: result.source || null,
        requestId: result.requestId || null,
        timestamp: new Date().toISOString(),
      }

      setMessages(prev => [...prev, assistantMsg])
    } catch (err) {
      if (seq !== reqSeqRef.current) return
      // Unexpected exception (shouldn't happen now that the service catches
      // structured errors, but defensive coding for the chat surface).
      const errorBubble = {
        id: `error-${Date.now()}`,
        role: 'assistant',
        message: friendlyErrorMessage('internal'),
        isError: true,
        errorCode: 'internal',
        errorRetryable: true,
        retryText: text.trim(),
        timestamp: new Date().toISOString(),
      }
      setMessages(prev => [...prev, errorBubble])
      setError(err.message)
    } finally {
      if (seq === reqSeqRef.current) setIsLoading(false)
    }
  }, [language, user?.id, friendlyErrorMessage])

  const sendMessage = useCallback(async (text) => {
    if (!text?.trim() || isLoading) return
    await runChatTurn(text)
  }, [isLoading, runChatTurn])

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
    if (isLoading || !audioBlob) return

    const seq = ++reqSeqRef.current
    setIsLoading(true)
    setError(null)

    try {
      const result = await aiChatService.sendVoice(audioBlob, {
        userId: user?.id || '00000000-0000-0000-0000-000000000000',
        includeAudio: true,
      })

      if (seq !== reqSeqRef.current) return

      if (result.lang && result.lang !== language) {
        setLanguage(result.lang)
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
        source: 'voice',
        degraded: !!result.degraded,
        requestId: result.requestId || null,
        timestamp: new Date().toISOString(),
      }

      setMessages(prev => [...prev, assistantMsg])
    } catch (err) {
      if (seq !== reqSeqRef.current) return
      const aiErr = err.aiError
      const errorMsg = {
        id: `error-${Date.now()}`,
        role: 'assistant',
        message: aiErr
          ? friendlyErrorMessage(aiErr.code, language)
          : (language === 'es'
            ? 'No pude procesar tu audio. Por favor usa el campo de texto.'
            : "I couldn't process your voice message. Please try typing instead."),
        isError: true,
        errorCode: aiErr?.code || 'internal',
        errorRetryable: aiErr?.retryable ?? true,
        errorRetryAfter: aiErr?.retryAfter ?? null,
        requestId: err.requestId || aiErr?.requestId || null,
        retryText: null,
        source: 'voice',
        timestamp: new Date().toISOString(),
      }

      setMessages(prev => [...prev, errorMsg])
      setError(err.message)
    } finally {
      if (seq === reqSeqRef.current) setIsLoading(false)
    }
  }, [isLoading, language, user?.id, friendlyErrorMessage])

  const clearHistory = useCallback(async () => {
    try {
      if (isAuthenticated && user?.id) {
        await aiChatService.clearHistory(user.id)
      }
      const welcome = language === 'es' ? INITIAL_MESSAGE_ES : INITIAL_MESSAGE
      setMessages([welcome])
      setHistoryLoaded(false)
      setError(null)
    } catch (err) {
      console.error('Failed to clear AI history:', err)
    }
  }, [isAuthenticated, user?.id, language])

  const submitFeedback = useCallback(async (messageId, rating) => {
    if (!isAuthenticated || !user?.id) return
    // Find the message to get real conversation UUID from backend
    const msg = messages.find(m => m.id === messageId)
    const convId = msg?.conversationId || messageId
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
    // Intentionally NOT setting isLoading — silent prompts run in the
    // background and must not block the user from typing/sending real
    // messages. The assistant reply still appears as a normal bubble.
    try {
      const result = await aiChatService.sendMessage(text.trim(), {
        userId: user?.id || '00000000-0000-0000-0000-000000000000',
        silent: true,
      })
      if (result.lang && result.lang !== language) setLanguage(result.lang)
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
  }, [language, user?.id])

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
  }
}
