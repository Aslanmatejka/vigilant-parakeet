import React, { useState, useEffect, useCallback, useRef } from 'react'

const SpeechRecognition = typeof window !== 'undefined'
  ? window.SpeechRecognition || window.webkitSpeechRecognition
  : null

/**
 * VoiceInput — microphone button that converts speech to text via Web Speech API.
 *
 * UI/UX revision goals:
 *  • Active state is unmistakable — coloured pill + live equalizer + halo,
 *    not just a tiny red square that's hard to spot in chat noise.
 *  • Live audio-level meter so users can verify the mic is actually picking
 *    them up — addresses the #1 complaint with browser STT ("did it hear me?").
 *  • Idle state has a subtle hover affordance so the button reads as tappable.
 *  • Interim transcripts streamed back via `onInterimTranscript` (optional)
 *    so callers can preview-render the in-progress text.
 *  • Unsupported environments render a disabled, tooltip-ed button instead
 *    of silently disappearing — users notice a missing affordance fast.
 *
 * Props:
 *   onTranscript(text)         — fires once on final transcript
 *   onInterimTranscript(text)  — optional: streamed partial transcripts
 *   onListeningChange(bool)    — fires whenever listening state flips
 *   language                   — 'en' | 'es' (default 'en')
 *   disabled                   — disable the mic button
 *   large                      — render the 80px voice-mode variant
 */
function VoiceInput({
  onTranscript,
  onInterimTranscript,
  onListeningChange,
  language = 'en',
  disabled = false,
  large = false,
}) {
  const [isListening, setIsListening] = useState(false)
  const [supported, setSupported] = useState(false)
  const [audioLevel, setAudioLevel] = useState(0)

  const recognitionRef = useRef(null)
  const transcriptRef = useRef('')
  const audioCtxRef = useRef(null)
  const analyserRef = useRef(null)
  const streamRef = useRef(null)
  const rafRef = useRef(null)

  useEffect(() => {
    setSupported(!!SpeechRecognition)
    return () => { cleanupAudio() }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  // Cleanup helpers — keep them tight so we never leak a mic indicator.
  const cleanupAudio = useCallback(() => {
    if (rafRef.current) { cancelAnimationFrame(rafRef.current); rafRef.current = null }
    if (analyserRef.current) {
      try { analyserRef.current.disconnect() } catch (_) {}
      analyserRef.current = null
    }
    if (streamRef.current) {
      streamRef.current.getTracks().forEach((t) => t.stop())
      streamRef.current = null
    }
    if (audioCtxRef.current) {
      audioCtxRef.current.close().catch(() => {})
      audioCtxRef.current = null
    }
    setAudioLevel(0)
  }, [])

  // Set up a separate mic stream just for the level meter. The Web Speech
  // API doesn't expose audio, so we tap a parallel MediaStream solely for
  // visualization. It runs only while listening, so privacy cost is zero.
  const startAudioMeter = useCallback(async () => {
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true })
      streamRef.current = stream
      const Ctx = window.AudioContext || window.webkitAudioContext
      const audioCtx = new Ctx()
      audioCtxRef.current = audioCtx
      const source = audioCtx.createMediaStreamSource(stream)
      const analyser = audioCtx.createAnalyser()
      analyser.fftSize = 256
      analyser.smoothingTimeConstant = 0.4
      source.connect(analyser)
      analyserRef.current = analyser
      const data = new Uint8Array(analyser.frequencyBinCount)

      const tick = () => {
        if (!analyserRef.current) return
        analyser.getByteFrequencyData(data)
        let sum = 0
        for (let i = 0; i < data.length; i++) sum += data[i]
        const avg = sum / data.length
        setAudioLevel(Math.min(1, avg / 80))
        rafRef.current = requestAnimationFrame(tick)
      }
      tick()
    } catch (err) {
      // Mic level is a nice-to-have; recognition can continue without it.
      console.warn('[VoiceInput] level meter unavailable:', err?.name || err)
    }
  }, [])

  const startListening = useCallback(() => {
    if (!SpeechRecognition || disabled) return

    if (recognitionRef.current) recognitionRef.current.abort()

    const recognition = new SpeechRecognition()
    recognition.lang = language === 'es' ? 'es-ES' : 'en-US'
    // Enable interim results when the caller cares about them, otherwise stay
    // single-shot to match the previous behavior.
    recognition.interimResults = !!onInterimTranscript
    recognition.continuous = false
    recognition.maxAlternatives = 1

    transcriptRef.current = ''

    recognition.onstart = () => {
      setIsListening(true)
      onListeningChange?.(true)
      startAudioMeter()
    }

    recognition.onresult = (event) => {
      let interim = ''
      let finalText = ''
      for (let i = event.resultIndex; i < event.results.length; i++) {
        const r = event.results[i]
        const text = r[0]?.transcript || ''
        if (r.isFinal) finalText += text
        else interim += text
      }
      if (finalText) transcriptRef.current = finalText.trim()
      if (interim && onInterimTranscript) onInterimTranscript(interim.trim())
    }

    recognition.onend = () => {
      setIsListening(false)
      onListeningChange?.(false)
      cleanupAudio()
      if (transcriptRef.current && onTranscript) onTranscript(transcriptRef.current)
      recognitionRef.current = null
    }

    recognition.onerror = (event) => {
      // 'no-speech' and 'aborted' are normal — don't spam the console for those.
      if (event.error !== 'no-speech' && event.error !== 'aborted') {
        console.error('Speech recognition error:', event.error)
      }
      setIsListening(false)
      onListeningChange?.(false)
      cleanupAudio()
      recognitionRef.current = null
    }

    recognitionRef.current = recognition
    try { recognition.start() } catch (err) {
      console.warn('Speech start failed:', err)
      setIsListening(false)
      onListeningChange?.(false)
    }
  }, [language, disabled, onTranscript, onInterimTranscript, onListeningChange, startAudioMeter, cleanupAudio])

  const stopListening = useCallback(() => {
    if (recognitionRef.current) recognitionRef.current.stop()
  }, [])

  const toggleListening = useCallback(() => {
    if (isListening) stopListening()
    else startListening()
  }, [isListening, startListening, stopListening])

  // ─── Unsupported environment: render a visible disabled affordance so the
  // user knows where the missing feature would live, rather than nothing.
  if (!supported) {
    return (
      <button
        type="button"
        disabled
        className={`${large ? 'w-20 h-20 rounded-full' : 'p-2 rounded-full'} bg-slate-100 text-slate-300 cursor-not-allowed`}
        title="Voice input isn't supported in this browser. Try Chrome or Edge."
        aria-label="Voice input not supported in this browser"
      >
        <svg xmlns="http://www.w3.org/2000/svg" className={large ? 'h-8 w-8 mx-auto' : 'h-5 w-5'} viewBox="0 0 20 20" fill="currentColor" aria-hidden="true">
          <path d="M12.293 4.293a1 1 0 011.414 1.414L4.414 15H2v-2.414L11.293 4.293a1 1 0 011 0z" />
          <path fillRule="evenodd" d="M7 4a3 3 0 016 0v4a3 3 0 01-.06.602L7.358 14.184A3 3 0 017 12.93V4z" clipRule="evenodd" />
        </svg>
      </button>
    )
  }

  // ─── Large variant — used in the voice-mode overlay's bottom button row.
  if (large) {
    return (
      <div className="relative inline-flex items-center justify-center">
        {/* Live ring scales with audio level */}
        {isListening && (
          <span
            className="absolute inset-0 -m-3 rounded-full border-2 border-rose-400/40 pointer-events-none transition-transform duration-100"
            style={{ transform: `scale(${1 + audioLevel * 0.3})` }}
            aria-hidden="true"
          />
        )}
        <button
          type="button"
          onClick={toggleListening}
          disabled={disabled}
          className={`relative z-10 w-20 h-20 rounded-full transition-all duration-300 flex items-center justify-center focus:outline-none focus-visible:ring-4 focus-visible:ring-cyan-400/40 ${
            isListening
              ? 'bg-gradient-to-br from-rose-500 to-red-600 text-white shadow-lg shadow-rose-500/40'
              : disabled
                ? 'bg-slate-700/50 text-slate-500 cursor-not-allowed'
                : 'bg-gradient-to-br from-cyan-500 to-blue-600 text-white shadow-lg shadow-cyan-500/30 hover:shadow-cyan-400/50 hover:scale-105'
          }`}
          style={isListening ? { transform: `scale(${1 + audioLevel * 0.08})` } : undefined}
          title={isListening ? 'Stop listening' : 'Speak to Nouri'}
          aria-label={isListening ? 'Stop voice input' : 'Start voice input'}
          aria-pressed={isListening}
        >
          {isListening ? (
            <svg xmlns="http://www.w3.org/2000/svg" className="h-8 w-8" viewBox="0 0 20 20" fill="currentColor" aria-hidden="true">
              <rect x="5" y="5" width="10" height="10" rx="2" />
            </svg>
          ) : (
            <svg xmlns="http://www.w3.org/2000/svg" className="h-8 w-8" viewBox="0 0 20 20" fill="currentColor" aria-hidden="true">
              <path fillRule="evenodd" d="M7 4a3 3 0 016 0v4a3 3 0 11-6 0V4zm4 10.93A7.001 7.001 0 0017 8a1 1 0 10-2 0A5 5 0 015 8a1 1 0 00-2 0 7.001 7.001 0 006 6.93V17H6a1 1 0 100 2h8a1 1 0 100-2h-3v-2.07z" clipRule="evenodd" />
            </svg>
          )}
        </button>
      </div>
    )
  }

  // ─── Compact inline mic — used in the chat input bar.
  // When listening, the button morphs into a small pill containing a stop
  // square + live 3-bar audio meter, giving the user unmistakable feedback.
  if (isListening) {
    return (
      <button
        type="button"
        onClick={toggleListening}
        disabled={disabled}
        className="relative inline-flex items-center gap-1.5 pl-2 pr-2.5 h-9 rounded-full bg-gradient-to-r from-rose-500 to-red-500 text-white shadow-md shadow-rose-500/30 transition-all hover:shadow-rose-500/50 focus:outline-none focus-visible:ring-2 focus-visible:ring-rose-300"
        title={language === 'es' ? 'Toca para detener' : 'Tap to stop'}
        aria-label={language === 'es' ? 'Detener entrada de voz' : 'Stop voice input'}
        aria-pressed="true"
      >
        {/* Stop square */}
        <svg xmlns="http://www.w3.org/2000/svg" className="h-3.5 w-3.5" viewBox="0 0 20 20" fill="currentColor" aria-hidden="true">
          <rect x="5" y="5" width="10" height="10" rx="1.5" />
        </svg>
        {/* Live 3-bar meter — heights driven by audioLevel + per-bar phase. */}
        <span className="flex items-end gap-[2px] h-4" aria-hidden="true">
          {[0, 1, 2].map((i) => {
            const phase = Math.sin((Date.now() / 160) + i * 0.9) * 0.5 + 0.5
            const h = Math.max(3, (audioLevel * 14 + 2) * (0.4 + phase * 0.6))
            return (
              <span
                key={i}
                className="w-[3px] rounded-full bg-white/85 transition-[height] duration-75"
                style={{ height: `${h}px` }}
              />
            )
          })}
        </span>
      </button>
    )
  }

  return (
    <button
      type="button"
      onClick={toggleListening}
      disabled={disabled}
      className={`relative inline-flex items-center justify-center h-9 w-9 rounded-full transition-all focus:outline-none focus-visible:ring-2 focus-visible:ring-emerald-300 ${
        disabled
          ? 'text-slate-300 cursor-not-allowed'
          : 'text-slate-500 hover:text-emerald-600 hover:bg-emerald-50 active:scale-95'
      }`}
      title={language === 'es' ? 'Hablar a Nouri' : 'Speak to Nouri'}
      aria-label={language === 'es' ? 'Iniciar entrada de voz' : 'Start voice input'}
      aria-pressed="false"
    >
      <svg xmlns="http://www.w3.org/2000/svg" className="h-5 w-5" viewBox="0 0 20 20" fill="currentColor" aria-hidden="true">
        <path fillRule="evenodd" d="M7 4a3 3 0 016 0v4a3 3 0 11-6 0V4zm4 10.93A7.001 7.001 0 0017 8a1 1 0 10-2 0A5 5 0 015 8a1 1 0 00-2 0 7.001 7.001 0 006 6.93V17H6a1 1 0 100 2h8a1 1 0 100-2h-3v-2.07z" clipRule="evenodd" />
      </svg>
    </button>
  )
}

export default VoiceInput
