/**
 * FormVoiceGuide — AI assistant banner + inline chat on forms.
 */
import React, { useState, useRef, useCallback } from 'react'
import PropTypes from 'prop-types'
import VoiceInput from '../assistant/VoiceInput'

export default function FormVoiceGuide({ guide, className = '' }) {
  const {
    welcomeMessage,
    activeHint,
    isMuted,
    isSpeaking,
    isDismissed,
    isChatLoading,
    chatMessages,
    chatError,
    canChat,
    toggleMute,
    speakWelcome,
    dismiss,
    askQuestion,
  } = guide

  const [input, setInput] = useState('')
  const [chatOpen, setChatOpen] = useState(false)
  const inputRef = useRef(null)
  const chatEndRef = useRef(null)

  const showingField = Boolean(activeHint?.text) && !chatOpen

  const handleSend = useCallback(() => {
    const text = input.trim()
    if (!text || isChatLoading) return
    setChatOpen(true)
    setInput('')
    askQuestion(text)
  }, [input, isChatLoading, askQuestion])

  const handleVoiceTranscript = useCallback((text) => {
    const trimmed = String(text || '').trim()
    if (!trimmed) return
    setChatOpen(true)
    setInput('')
    askQuestion(trimmed)
  }, [askQuestion])

  React.useEffect(() => {
    if (chatOpen && chatEndRef.current) {
      chatEndRef.current.scrollIntoView({ behavior: 'smooth', block: 'nearest' })
    }
  }, [chatMessages, chatOpen, isChatLoading])

  if (isDismissed) return null

  return (
    <div className={`rounded-xl border border-[#2CABE3]/40 bg-[#2CABE3]/10 shadow-sm overflow-hidden ${className}`}>
      {/* Status banner */}
      <div className="relative flex items-start gap-3 px-4 py-3">
        <div className="flex-shrink-0 mt-0.5">
          <div
            className={`w-9 h-9 rounded-full flex items-center justify-center transition-all duration-300 ${
              isSpeaking || isChatLoading
                ? 'bg-[#2CABE3] shadow-lg shadow-[#2CABE3]/40'
                : 'bg-[#2CABE3]/15'
            }`}
          >
            {isSpeaking || isChatLoading ? (
              <span className="flex items-end gap-0.5 h-4">
                {[1, 2, 3].map((i) => (
                  <span
                    key={i}
                    className="w-1 bg-white rounded-full animate-bounce"
                    style={{ height: `${8 + i * 4}px`, animationDelay: `${i * 0.12}s` }}
                  />
                ))}
              </span>
            ) : (
              <i className="fas fa-robot text-[#2CABE3] text-sm" aria-hidden="true" />
            )}
          </div>
        </div>

        <div className="flex-1 min-w-0">
          <p className="text-xs font-semibold text-[#2CABE3] mb-0.5 uppercase tracking-wide">
            {showingField ? (activeHint.label || 'Field help') : 'Nouri — form guide'}
          </p>
          <p className="text-sm text-gray-800 leading-snug">
            {showingField ? activeHint.text : welcomeMessage}
          </p>
          {!showingField && !chatOpen && (
            <p className="text-xs text-gray-500 mt-1.5">
              Click any field for help, or ask me a question below.
            </p>
          )}
        </div>

        <div className="flex items-center gap-1 flex-shrink-0">
          <button
            type="button"
            onClick={speakWelcome}
            title="Replay welcome"
            aria-label="Replay welcome message"
            className="w-7 h-7 rounded-full flex items-center justify-center text-[#2CABE3] hover:bg-[#2CABE3]/15 transition-colors"
          >
            <i className="fas fa-redo text-xs" aria-hidden="true" />
          </button>
          <button
            type="button"
            onClick={toggleMute}
            title={isMuted ? 'Unmute voice guide' : 'Mute voice guide'}
            aria-label={isMuted ? 'Unmute voice guide' : 'Mute voice guide'}
            className={`w-7 h-7 rounded-full flex items-center justify-center transition-colors ${
              isMuted
                ? 'bg-rose-100 text-rose-600 hover:bg-rose-200'
                : 'text-gray-500 hover:bg-gray-100'
            }`}
          >
            <i className={`fas ${isMuted ? 'fa-volume-xmark' : 'fa-volume-high'} text-xs`} aria-hidden="true" />
          </button>
          <button
            type="button"
            onClick={dismiss}
            title="Dismiss guide"
            aria-label="Dismiss voice guide"
            className="w-7 h-7 rounded-full flex items-center justify-center text-gray-400 hover:bg-gray-100 transition-colors"
          >
            <i className="fas fa-xmark text-xs" aria-hidden="true" />
          </button>
        </div>
      </div>

      {/* Chat thread */}
      {chatOpen && chatMessages.length > 0 && (
        <div className="border-t border-[#2CABE3]/20 bg-white/60 px-4 py-3 max-h-48 overflow-y-auto space-y-2">
          {chatMessages.map((msg) => (
            <div
              key={msg.id}
              className={`text-sm leading-snug rounded-lg px-3 py-2 ${
                msg.role === 'user'
                  ? 'bg-[#2CABE3]/15 text-gray-800 ml-6'
                  : 'bg-white border border-gray-200 text-gray-800 mr-6'
              }`}
            >
              {msg.message}
            </div>
          ))}
          {isChatLoading && (
            <p className="text-xs text-gray-500 italic px-1">Nouri is thinking…</p>
          )}
          <div ref={chatEndRef} />
        </div>
      )}

      {/* Ask Nouri input */}
      <div className="border-t border-[#2CABE3]/20 bg-white/80 px-3 py-2.5">
        {chatError && (
          <p className="text-xs text-red-600 mb-2 px-1" role="alert">{chatError}</p>
        )}
        {!canChat && (
          <p className="text-xs text-amber-700 mb-2 px-1">
            Sign in to ask Nouri questions while you fill out the form.
          </p>
        )}
        <div className="flex items-center gap-2">
          <VoiceInput
            onTranscript={handleVoiceTranscript}
            disabled={!canChat || isChatLoading}
            language="en"
          />
          <input
            ref={inputRef}
            type="text"
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === 'Enter' && !e.shiftKey) {
                e.preventDefault()
                handleSend()
              }
            }}
            onFocus={() => setChatOpen(true)}
            disabled={!canChat || isChatLoading}
            placeholder={canChat ? 'Ask Nouri anything about this form…' : 'Sign in to chat'}
            className="flex-1 min-w-0 text-sm px-3 py-2 rounded-lg border border-gray-300 focus:outline-none focus:ring-2 focus:ring-[#2CABE3]/50 disabled:bg-gray-100 disabled:cursor-not-allowed"
            aria-label="Ask Nouri a question about this form"
          />
          <button
            type="button"
            onClick={handleSend}
            disabled={!canChat || isChatLoading || !input.trim()}
            className="flex-shrink-0 w-9 h-9 rounded-lg bg-[#2CABE3] text-white flex items-center justify-center hover:opacity-90 disabled:opacity-40 disabled:cursor-not-allowed transition-opacity"
            aria-label="Send question"
          >
            <i className="fas fa-paper-plane text-xs" aria-hidden="true" />
          </button>
        </div>
      </div>
    </div>
  )
}

FormVoiceGuide.propTypes = {
  guide: PropTypes.shape({
    welcomeMessage: PropTypes.string,
    activeHint: PropTypes.object,
    isMuted: PropTypes.bool,
    isSpeaking: PropTypes.bool,
    isDismissed: PropTypes.bool,
    isChatLoading: PropTypes.bool,
    chatMessages: PropTypes.array,
    chatError: PropTypes.string,
    canChat: PropTypes.bool,
    toggleMute: PropTypes.func,
    speakWelcome: PropTypes.func,
    dismiss: PropTypes.func,
    askQuestion: PropTypes.func,
  }).isRequired,
  className: PropTypes.string,
}
