/**
 * Global caption bar for AI speech (chat + forms).
 */
import React, { useEffect, useState } from 'react'
import { useAccessibility } from '../../utils/AccessibilityContext'
import { subscribeAiVoice } from '../../utils/aiVoiceService'

export default function AICaptionBar() {
  const { settings } = useAccessibility()
  const [caption, setCaption] = useState('')
  const [speaking, setSpeaking] = useState(false)

  useEffect(() => {
    return subscribeAiVoice(({ captionText, isSpeaking }) => {
      setCaption(captionText || '')
      setSpeaking(isSpeaking)
    })
  }, [])

  if (!settings.alwaysShowCaptions || !caption) return null

  return (
    <div
      className="nouri-ai-caption-bar"
      role="status"
      aria-live="polite"
      aria-atomic="true"
      aria-label={speaking ? 'AI is speaking' : 'AI caption'}
    >
      <span className="sr-only">{speaking ? 'Speaking: ' : 'Caption: '}</span>
      {caption}
    </div>
  )
}
