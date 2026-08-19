/**
 * FormVoiceGuide — floating AI assistant banner on forms.
 * Shows welcome text, then the active field hint when a field is focused.
 */
import React from 'react'
import PropTypes from 'prop-types'

export default function FormVoiceGuide({ guide, className = '' }) {
  const {
    welcomeMessage,
    activeHint,
    isMuted,
    isSpeaking,
    isDismissed,
    toggleMute,
    speakWelcome,
    dismiss,
  } = guide

  if (isDismissed) return null

  const showingField = Boolean(activeHint?.text)

  return (
    <div
      className={`relative flex items-start gap-3 rounded-xl border border-[#2CABE3]/40 bg-[#2CABE3]/10 px-4 py-3 shadow-sm ${className}`}
      role="status"
      aria-live="polite"
      aria-atomic="true"
    >
      <div className="flex-shrink-0 mt-0.5">
        <div
          className={`w-9 h-9 rounded-full flex items-center justify-center transition-all duration-300 ${
            isSpeaking
              ? 'bg-[#2CABE3] shadow-lg shadow-[#2CABE3]/40'
              : 'bg-[#2CABE3]/15'
          }`}
        >
          {isSpeaking ? (
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
          {showingField ? (activeHint.label || 'Field help') : 'AI guide'}
        </p>
        <p className="text-sm text-gray-800 leading-snug">
          {showingField ? activeHint.text : welcomeMessage}
        </p>
        {!showingField && (
          <p className="text-xs text-gray-500 mt-1.5">
            Click or tap any field for step-by-step help.
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
  )
}

FormVoiceGuide.propTypes = {
  guide: PropTypes.shape({
    welcomeMessage: PropTypes.string,
    activeHint: PropTypes.shape({
      fieldName: PropTypes.string,
      label: PropTypes.string,
      text: PropTypes.string,
    }),
    isMuted: PropTypes.bool,
    isSpeaking: PropTypes.bool,
    isDismissed: PropTypes.bool,
    toggleMute: PropTypes.func,
    speakWelcome: PropTypes.func,
    dismiss: PropTypes.func,
  }).isRequired,
  className: PropTypes.string,
}
