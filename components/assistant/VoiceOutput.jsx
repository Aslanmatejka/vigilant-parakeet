import React, { useState, useEffect, useCallback, useRef } from 'react'

const synth = typeof window !== 'undefined' ? window.speechSynthesis : null

/**
 * VoiceOutput — reads AI responses aloud via browser SpeechSynthesis and
 * exposes a small toolbar (play/stop + mute auto-read).
 *
 * UI/UX revision goals:
 *  • The two icons in the previous version were near-identical "speaker + X"
 *    glyphs. The new version uses a distinct play/stop pair and a unique
 *    bell-style mute glyph so the buttons are scannable at a glance.
 *  • While speaking, the play button morphs into a stop button + a tiny
 *    3-bar equalizer animation — much clearer than a hue change alone.
 *  • Focus rings, larger hit targets (still small enough for an inline
 *    chat toolbar), and clearer aria-labels.
 *  • Mute state has a persistent visual when active (rose tint + filled
 *    icon) so it's never ambiguous whether auto-read is off.
 *  • Unsupported environments render a tiny "no audio available" indicator
 *    rather than nothing — discoverable, but unobtrusive.
 *
 * Props (unchanged):
 *   text                          — text to speak
 *   language                      — 'en' | 'es'
 *   autoSpeak                     — auto-speak each new `text` (default false)
 *   onSpeakingChange(isSpeaking)  — callback on speaking state changes
 */
function VoiceOutput({ text, language = 'en', autoSpeak = false, onSpeakingChange }) {
  const [isSpeaking, setIsSpeaking] = useState(false)
  const [isMuted, setIsMuted] = useState(false)
  const [supported, setSupported] = useState(false)
  const utteranceRef = useRef(null)
  const prevTextRef = useRef('')
  // Chromium fires `voiceschanged` once voices are ready; the first
  // synchronous `getVoices()` after page load often returns []. Cache the
  // latest list so `speak()` can pick the right voice immediately.
  const voicesRef = useRef([])

  useEffect(() => {
    setSupported(!!synth)
    if (!synth) return undefined

    const refreshVoices = () => { voicesRef.current = synth.getVoices() || [] }
    refreshVoices()
    synth.addEventListener?.('voiceschanged', refreshVoices)

    return () => {
      synth.removeEventListener?.('voiceschanged', refreshVoices)
      // Null out callbacks before cancel so a queued onend/onerror from this
      // utterance doesn't fire setState on an unmounted component.
      if (utteranceRef.current) {
        utteranceRef.current.onstart = null
        utteranceRef.current.onend = null
        utteranceRef.current.onerror = null
      }
      synth.cancel()
    }
  }, [])

  // Auto-speak when new text arrives
  useEffect(() => {
    if (!autoSpeak || isMuted || !text || text === prevTextRef.current) return
    prevTextRef.current = text
    speak(text)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [text, autoSpeak, isMuted])

  const speak = useCallback((textToSpeak) => {
    if (!synth || !textToSpeak) return
    synth.cancel()

    // Clean text for speech (remove markdown, excessive punctuation)
    const cleanText = textToSpeak
      .replace(/\*\*(.*?)\*\*/g, '$1')
      .replace(/[#*_~`]/g, '')
      .replace(/\n+/g, '. ')
      .replace(/\s+/g, ' ')
      .trim()

    if (!cleanText) return

    const utterance = new SpeechSynthesisUtterance(cleanText)
    utterance.lang = language === 'es' ? 'es-ES' : 'en-US'
    utterance.rate = 0.95
    utterance.pitch = 1.0

    // Prefer the cached voice list; fall back to a fresh getVoices() in case
    // voices loaded between renders without firing `voiceschanged`.
    const voices = voicesRef.current.length ? voicesRef.current : (synth.getVoices() || [])
    const langCode = language === 'es' ? 'es' : 'en'
    const preferredVoice = voices.find(v =>
      v.lang.startsWith(langCode) && (v.name.includes('Google') || v.name.includes('Samantha') || v.name.includes('Microsoft'))
    ) || voices.find(v => v.lang.startsWith(langCode))

    if (preferredVoice) utterance.voice = preferredVoice

    utterance.onstart = () => { setIsSpeaking(true); onSpeakingChange?.(true) }
    utterance.onend   = () => { setIsSpeaking(false); onSpeakingChange?.(false) }
    utterance.onerror = () => { setIsSpeaking(false); onSpeakingChange?.(false) }

    utteranceRef.current = utterance
    synth.speak(utterance)
  }, [language, onSpeakingChange])

  const stop = useCallback(() => {
    if (synth) {
      synth.cancel()
      setIsSpeaking(false)
      onSpeakingChange?.(false)
    }
  }, [onSpeakingChange])

  const toggleMute = useCallback(() => {
    if (isSpeaking) stop()
    setIsMuted(prev => !prev)
  }, [isSpeaking, stop])

  const handleSpeak = useCallback(() => {
    if (isSpeaking) stop()
    else speak(text)
  }, [isSpeaking, text, speak, stop])

  if (!supported) {
    // Tiny static hint so the toolbar's alignment stays consistent and
    // users notice their browser doesn't support audio playback.
    return (
      <span
        className="inline-flex items-center justify-center h-7 w-7 rounded-md text-slate-300 cursor-not-allowed"
        title="Voice output isn't supported in this browser"
        aria-label="Voice output not supported"
      >
        <svg xmlns="http://www.w3.org/2000/svg" className="h-3.5 w-3.5" viewBox="0 0 20 20" fill="currentColor" aria-hidden="true">
          <path fillRule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zM8.707 7.293a1 1 0 00-1.414 1.414L8.586 10l-1.293 1.293a1 1 0 101.414 1.414L10 11.414l1.293 1.293a1 1 0 001.414-1.414L11.414 10l1.293-1.293a1 1 0 00-1.414-1.414L10 8.586 8.707 7.293z" clipRule="evenodd" />
        </svg>
      </span>
    )
  }

  const disabledSpeak = !text

  return (
    <div className="inline-flex items-center gap-0.5" role="toolbar" aria-label="Voice output controls">
      {/* ─── Play / Stop ─── */}
      <button
        type="button"
        onClick={handleSpeak}
        disabled={disabledSpeak}
        className={`relative inline-flex items-center justify-center h-7 w-7 rounded-md transition-colors focus:outline-none focus-visible:ring-2 focus-visible:ring-emerald-300 ${
          disabledSpeak
            ? 'text-slate-300 cursor-not-allowed'
            : isSpeaking
              ? 'text-emerald-600 bg-emerald-50 hover:bg-emerald-100'
              : 'text-slate-400 hover:text-emerald-600 hover:bg-emerald-50'
        }`}
        title={isSpeaking ? (language === 'es' ? 'Detener lectura' : 'Stop reading') : (language === 'es' ? 'Leer en voz alta' : 'Read aloud')}
        aria-label={isSpeaking ? (language === 'es' ? 'Detener lectura' : 'Stop reading') : (language === 'es' ? 'Leer mensaje en voz alta' : 'Read message aloud')}
        aria-pressed={isSpeaking}
      >
        {isSpeaking ? (
          // Stop square + tiny equalizer overlay so it's unmistakable.
          <span className="relative inline-flex items-center justify-center">
            <svg xmlns="http://www.w3.org/2000/svg" className="h-3.5 w-3.5" viewBox="0 0 20 20" fill="currentColor" aria-hidden="true">
              <rect x="5" y="5" width="10" height="10" rx="1.5" />
            </svg>
            <span className="absolute -top-1.5 -right-2 flex items-end gap-[1.5px] h-2.5" aria-hidden="true">
              {[0, 1, 2].map((i) => (
                <span
                  key={i}
                  className="w-[2px] rounded-full bg-emerald-500 animate-voice-bar"
                  style={{ animationDelay: `${i * 0.12}s`, height: '100%' }}
                />
              ))}
            </span>
          </span>
        ) : (
          // Play triangle inside a speaker — distinct from the stop variant.
          <svg xmlns="http://www.w3.org/2000/svg" className="h-3.5 w-3.5" viewBox="0 0 20 20" fill="currentColor" aria-hidden="true">
            <path fillRule="evenodd" d="M9.383 3.076A1 1 0 0110 4v12a1 1 0 01-1.707.707L4.586 13H2a1 1 0 01-1-1V8a1 1 0 011-1h2.586l3.707-3.707a1 1 0 011.09-.217zM14.657 2.929a1 1 0 011.414 0A9.972 9.972 0 0119 10a9.972 9.972 0 01-2.929 7.071 1 1 0 01-1.414-1.414A7.971 7.971 0 0017 10c0-2.21-.894-4.208-2.343-5.657a1 1 0 010-1.414zm-2.829 2.828a1 1 0 011.415 0A5.983 5.983 0 0115 10a5.984 5.984 0 01-1.757 4.243 1 1 0 01-1.415-1.415A3.984 3.984 0 0013 10a3.983 3.983 0 00-1.172-2.828 1 1 0 010-1.415z" clipRule="evenodd" />
          </svg>
        )}
      </button>

      {/* ─── Mute toggle — visually distinct: bell-with-slash icon, persistent rose state when muted ─── */}
      <button
        type="button"
        onClick={toggleMute}
        className={`inline-flex items-center justify-center h-7 w-7 rounded-md transition-colors focus:outline-none focus-visible:ring-2 focus-visible:ring-rose-300 ${
          isMuted
            ? 'text-rose-500 bg-rose-50 hover:bg-rose-100'
            : 'text-slate-300 hover:text-slate-600 hover:bg-slate-100'
        }`}
        title={isMuted ? (language === 'es' ? 'Activar lectura automática' : 'Unmute auto-read') : (language === 'es' ? 'Silenciar lectura automática' : 'Mute auto-read')}
        aria-label={isMuted ? (language === 'es' ? 'Activar salida de voz' : 'Unmute voice output') : (language === 'es' ? 'Silenciar salida de voz' : 'Mute voice output')}
        aria-pressed={isMuted}
      >
        {isMuted ? (
          // Bell-with-slash — communicates "notifications/sounds off" cleanly.
          <svg xmlns="http://www.w3.org/2000/svg" className="h-3.5 w-3.5" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true">
            <path d="M3.293 2.293a1 1 0 011.414 0l18 18a1 1 0 01-1.414 1.414l-2.012-2.012A2 2 0 0118 20H6a2 2 0 01-1.414-3.414L6 15.172V11c0-1.07.21-2.09.59-3.013L3.293 3.707a1 1 0 010-1.414z"/>
            <path d="M10 22a2 2 0 104 0h-4zM18 8.586l-9.6-9.6A6 6 0 0118 11v-2.414z" opacity=".25"/>
          </svg>
        ) : (
          // Open bell — auto-read is on.
          <svg xmlns="http://www.w3.org/2000/svg" className="h-3.5 w-3.5" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true">
            <path d="M12 2a6 6 0 00-6 6v3.586l-1.707 1.707A1 1 0 005 15h14a1 1 0 00.707-1.707L18 11.586V8a6 6 0 00-6-6zM10 19a2 2 0 104 0h-4z"/>
          </svg>
        )}
      </button>
    </div>
  )
}

export default VoiceOutput
