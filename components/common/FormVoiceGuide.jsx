/**
 * FormVoiceGuide
 *
 * Floating guided-assistant banner shown on forms.
 * Speaks the current step instruction aloud and shows progress dots.
 *
 * Props:
 *   guide  — return value of useFormVoiceGuide()
 *   className — optional extra Tailwind classes on the wrapper
 */
import React from 'react'
import PropTypes from 'prop-types'

export default function FormVoiceGuide({ guide, className = '' }) {
  const {
    currentStep,
    isComplete,
    isMuted,
    isSpeaking,
    isDismissed,
    toggleMute,
    speak,
    dismiss,
  } = guide

  if (isDismissed) return null

  return (
    <div
      className={`relative flex items-start gap-3 rounded-xl border border-[#2CABE3]/40 bg-[#2CABE3]/8 px-4 py-3 shadow-sm ${className}`}
      role="status"
      aria-live="polite"
      aria-atomic="true"
    >
      {/* Avatar / speaking indicator */}
      <div className="flex-shrink-0 mt-0.5">
        <div
          className={`w-9 h-9 rounded-full flex items-center justify-center transition-all duration-300 ${
            isSpeaking
              ? 'bg-[#2CABE3] shadow-lg shadow-[#2CABE3]/40'
              : 'bg-[#2CABE3]/15'
          }`}
        >
          {isSpeaking ? (
            /* Animated equalizer bars */
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

      {/* Text content */}
      <div className="flex-1 min-w-0">
        {isComplete ? (
          <p className="text-sm font-semibold text-emerald-700">
            <i className="fas fa-check-circle mr-1.5" aria-hidden="true" />
            All fields filled — review your details and hit Submit!
          </p>
        ) : (
          <>
            {/* Step label */}
            <p className="text-xs font-semibold text-[#2CABE3] mb-0.5 uppercase tracking-wide">
              Step {(currentStep?.index ?? 0) + 1} of {currentStep?.total ?? 1}
            </p>
            {/* Instruction */}
            <p className="text-sm text-gray-800 leading-snug">{currentStep?.instruction}</p>

            {/* Progress dots */}
            <div className="flex gap-1 mt-2" aria-hidden="true">
              {Array.from({ length: currentStep?.total ?? 1 }).map((_, i) => (
                <span
                  key={i}
                  className={`h-1.5 rounded-full transition-all duration-300 ${
                    i < (currentStep?.index ?? 0)
                      ? 'w-3 bg-emerald-400'
                      : i === (currentStep?.index ?? 0)
                      ? 'w-5 bg-[#2CABE3]'
                      : 'w-1.5 bg-gray-300'
                  }`}
                />
              ))}
            </div>
          </>
        )}
      </div>

      {/* Controls */}
      <div className="flex items-center gap-1 flex-shrink-0">
        {/* Re-speak button */}
        {!isComplete && (
          <button
            type="button"
            onClick={() => speak()}
            title="Repeat instruction"
            aria-label="Repeat voice instruction"
            className="w-7 h-7 rounded-full flex items-center justify-center text-[#2CABE3] hover:bg-[#2CABE3]/15 transition-colors"
          >
            <i className="fas fa-redo text-xs" aria-hidden="true" />
          </button>
        )}

        {/* Mute toggle */}
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

        {/* Dismiss */}
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
    currentStep: PropTypes.object,
    isComplete: PropTypes.bool,
    isMuted: PropTypes.bool,
    isSpeaking: PropTypes.bool,
    isDismissed: PropTypes.bool,
    toggleMute: PropTypes.func,
    speak: PropTypes.func,
    dismiss: PropTypes.func,
  }).isRequired,
  className: PropTypes.string,
}
