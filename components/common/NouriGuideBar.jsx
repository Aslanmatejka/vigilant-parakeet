/**
 * Global Nouri guide bar — one UI for chat + forms + captions.
 */
import React, { useEffect, useState } from 'react'
import { useNouriGuide } from '../../utils/NouriGuideContext'
import { FORM_GUIDE_DESC_ID } from '../../utils/formFieldGuide'
import { NOURI_GOALS } from '../../utils/nouriGuide/registry'
import {
  getGuideFailureCount,
  openHumanSupport,
  shouldSuggestHumanHandoff,
} from '../../utils/nouriGuide/humanHandoff'

export default function NouriGuideBar() {
  const {
    settings,
    guide,
    toggleMute,
    dismiss,
    replay,
    resume,
  } = useNouriGuide()

  const [failureCount, setFailureCount] = useState(() => getGuideFailureCount())
  const showHandoffHint = shouldSuggestHumanHandoff()

  useEffect(() => {
    const refresh = () => setFailureCount(getGuideFailureCount())
    window.addEventListener('nouri:handoff-suggested', refresh)
    return () => window.removeEventListener('nouri:handoff-suggested', refresh)
  }, [])

  const {
    source,
    caption,
    text,
    label,
    section,
    stepIndex,
    stepTotal,
    formId,
    isSpeaking,
    isMuted,
    isDismissed,
    hasResume,
  } = guide

  const displayText = caption || text
  const showBar = !isDismissed && (
    settings.alwaysShowCaptions
    || settings.preferTextOverVoice
    || isSpeaking
    || hasResume
    || (source === 'form' && displayText)
    || (source === 'chat' && displayText)
  )

  useEffect(() => {
    if (typeof document === 'undefined') return
    document.body.classList.toggle('has-nouri-guide-bar', Boolean(showBar && displayText))
    return () => document.body.classList.remove('has-nouri-guide-bar')
  }, [showBar, displayText])

  if (!showBar || !displayText) return null

  const stepLabel = stepTotal > 0
    ? `Step ${stepIndex + 1} of ${stepTotal}`
    : null

  const goalWelcome = guide.goalKey && NOURI_GOALS[guide.goalKey]?.welcome

  return (
    <>
      <span id={FORM_GUIDE_DESC_ID} className="sr-only">
        {displayText}
      </span>

      <div
        className="nouri-ai-caption-bar nouri-guide-bar"
        role="region"
        aria-label="Nouri accessibility guide"
      >
        <div className="max-w-5xl mx-auto flex items-start gap-3">
          <div
            className={`flex-shrink-0 w-9 h-9 rounded-full flex items-center justify-center ${
              isSpeaking ? 'bg-[#2CABE3] text-white' : 'bg-white/15 text-[#2CABE3]'
            }`}
            aria-hidden="true"
          >
            <i className={`fas ${isSpeaking ? 'fa-volume-high' : 'fa-robot'}`} />
          </div>

          <div className="flex-1 min-w-0">
            <div className="flex flex-wrap items-center gap-2 text-xs uppercase tracking-wide opacity-80 mb-1">
              <span>Nouri guide</span>
              {stepLabel && <span aria-label={`${stepLabel}`}>{stepLabel}</span>}
              {section && <span>· {section}</span>}
              {label && label !== 'AI guide' && <span>· {label}</span>}
            </div>

            <p
              role="status"
              aria-live="polite"
              aria-atomic="true"
              className="text-sm leading-snug"
            >
              {displayText}
            </p>

            {hasResume && goalWelcome && (
              <p className="text-xs mt-1 opacity-80">
                Continuing where you left off in chat.
              </p>
            )}

            {settings.preferTextOverVoice && !isMuted && (
              <p className="text-xs mt-1 opacity-70">
                Text-only mode — voice is off in accessibility settings.
              </p>
            )}

            {source === 'form'
              && !settings.formVoiceGuideEnabled
              && !settings.preferTextOverVoice
              && !isMuted && (
              <p className="text-xs mt-1 opacity-70">
                Voice guide is off — enable Form voice guide in Accessibility settings.
              </p>
            )}

            {showHandoffHint && (
              <p className="text-xs mt-1 opacity-90">
                Having trouble? A team member can help.
              </p>
            )}
          </div>

          <div className="flex items-center gap-1 flex-shrink-0">
            <button
              type="button"
              onClick={() => openHumanSupport()}
              className="px-2 py-1 text-xs rounded bg-white/20 hover:bg-white/30 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-white"
              aria-label="Talk to a person for help"
              title={failureCount >= 3 ? 'Nouri suggested human help' : 'Contact support'}
            >
              <i className="fas fa-user-headset mr-1" aria-hidden="true" />
              Person
            </button>
            {hasResume && (
              <button
                type="button"
                onClick={() => resume()}
                className="px-2 py-1 text-xs rounded bg-white/20 hover:bg-white/30 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-white"
                aria-label="Continue guided step"
              >
                Continue
              </button>
            )}
            <button
              type="button"
              onClick={() => replay()}
              title="Replay"
              aria-label="Replay current guide step"
              className="w-8 h-8 rounded-full flex items-center justify-center hover:bg-white/15 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-white"
            >
              <i className="fas fa-redo text-xs" aria-hidden="true" />
            </button>
            <button
              type="button"
              onClick={toggleMute}
              title={isMuted ? 'Unmute' : 'Mute'}
              aria-label={isMuted ? 'Unmute guide voice' : 'Mute guide voice'}
              className="w-8 h-8 rounded-full flex items-center justify-center hover:bg-white/15 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-white"
            >
              <i className={`fas ${isMuted ? 'fa-volume-xmark' : 'fa-volume-high'} text-xs`} aria-hidden="true" />
            </button>
            <button
              type="button"
              onClick={dismiss}
              title="Dismiss"
              aria-label="Dismiss guide"
              className="w-8 h-8 rounded-full flex items-center justify-center hover:bg-white/15 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-white"
            >
              <i className="fas fa-xmark text-xs" aria-hidden="true" />
            </button>
          </div>
        </div>
      </div>
    </>
  )
}
