/**
 * useFormVoiceGuide
 *
 * Drives a step-by-step spoken guide on any form.
 *
 * Usage:
 *   const guide = useFormVoiceGuide({ steps, formData })
 *
 * Each step has:
 *   id          – matches the key in formData (or an array of keys for multi-field steps)
 *   instruction – what to say/show when this step becomes active
 *   isFilled    – (formData) => boolean — returns true once the user has entered the data
 *
 * The hook returns:
 *   currentStep      – { id, instruction, index, total }
 *   isComplete       – all steps filled
 *   isMuted          – voice is muted
 *   isSpeaking       – currently reading aloud
 *   toggleMute       – fn
 *   speak            – fn(text?) – re-read current step or a custom message
 *   dismiss          – fn – hide the guide for the rest of the session
 *   isDismissed      – bool
 */
import { useState, useEffect, useRef, useCallback } from 'react'

const synth = typeof window !== 'undefined' ? window.speechSynthesis : null

function getBestVoice(lang = 'en') {
  if (!synth) return null
  const voices = synth.getVoices()
  const tag = lang === 'es' ? 'es' : 'en'
  return (
    voices.find((v) => v.lang.startsWith(tag) && v.localService) ||
    voices.find((v) => v.lang.startsWith(tag)) ||
    voices[0] ||
    null
  )
}

export default function useFormVoiceGuide({ steps = [], formData = {}, lang = 'en' }) {
  const [stepIndex, setStepIndex] = useState(0)
  const [isMuted, setIsMuted] = useState(false)
  const [isSpeaking, setIsSpeaking] = useState(false)
  const [isDismissed, setIsDismissed] = useState(false)
  const utteranceRef = useRef(null)
  const spokenStepRef = useRef(-1)   // track which step index was last spoken
  const voicesReady = useRef(false)

  // Load voices (Chromium fires voiceschanged once async)
  useEffect(() => {
    if (!synth) return
    const onVoices = () => { voicesReady.current = true }
    synth.addEventListener('voiceschanged', onVoices)
    if (synth.getVoices().length > 0) voicesReady.current = true
    return () => synth.removeEventListener('voiceschanged', onVoices)
  }, [])

  // Determine which step is active: the first unfilled step
  const activeIndex = steps.findIndex((s) => !s.isFilled(formData))
  const effectiveIndex = activeIndex === -1 ? steps.length : activeIndex
  const isComplete = effectiveIndex >= steps.length
  const currentStep = isComplete
    ? null
    : { ...steps[effectiveIndex], index: effectiveIndex, total: steps.length }

  // Advance the tracked step and speak when it changes
  useEffect(() => {
    if (isDismissed || isMuted || !synth) return
    if (isComplete) return
    if (effectiveIndex === spokenStepRef.current) return

    spokenStepRef.current = effectiveIndex
    setStepIndex(effectiveIndex)

    // Small delay so the user has a moment to absorb the previous response
    const timer = setTimeout(() => {
      speakText(steps[effectiveIndex]?.instruction || '')
    }, 600)
    return () => clearTimeout(timer)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [effectiveIndex, isDismissed, isMuted, isComplete])

  const speakText = useCallback((text) => {
    if (!synth || !text) return
    synth.cancel()
    const utt = new SpeechSynthesisUtterance(text)
    utt.voice = getBestVoice(lang)
    utt.rate = 0.95
    utt.pitch = 1.05
    utt.onstart = () => setIsSpeaking(true)
    utt.onend = () => setIsSpeaking(false)
    utt.onerror = () => setIsSpeaking(false)
    utteranceRef.current = utt
    synth.speak(utt)
  }, [lang])

  const speak = useCallback((text) => {
    const msg = text || currentStep?.instruction || ''
    if (msg) speakText(msg)
  }, [currentStep, speakText])

  const toggleMute = useCallback(() => {
    setIsMuted((m) => {
      if (!m && synth) synth.cancel()
      return !m
    })
  }, [])

  const dismiss = useCallback(() => {
    if (synth) synth.cancel()
    setIsDismissed(true)
  }, [])

  return {
    currentStep,
    isComplete,
    isMuted,
    isSpeaking,
    isDismissed,
    toggleMute,
    speak,
    dismiss,
  }
}

// ---------------------------------------------------------------------------
// Step definitions for each form
// ---------------------------------------------------------------------------

/** Share Food (FoodForm) — ordered required fields */
export const SHARE_FOOD_STEPS = [
  {
    id: 'donor_name',
    instruction: 'Let\'s get started! First, enter your name or organization name in the Donor Information section.',
    isFilled: (f) => Boolean(String(f.donor_name || '').trim()),
  },
  {
    id: 'donor_type',
    instruction: 'Great! Now select your donor type — Individual or Organization.',
    isFilled: (f) => Boolean(f.donor_type),
  },
  {
    id: 'full_address',
    instruction: 'Enter the full pickup address so people can find your food on the map.',
    isFilled: (f) => Boolean(String(f.full_address || '').trim()),
  },
  {
    id: 'title',
    instruction: 'What food are you donating? Enter a short, clear name for the item.',
    isFilled: (f) => Boolean(String(f.title || '').trim()),
  },
  {
    id: 'category',
    instruction: 'Select a category for the food — for example, Fresh Produce, Dairy, or Bakery.',
    isFilled: (f) => Boolean(f.category),
  },
  {
    id: 'quantity',
    instruction: 'How much do you have? Enter the quantity and choose a unit like pounds or kilograms.',
    isFilled: (f) => Boolean(f.quantity) && Number(f.quantity) > 0,
  },
  {
    id: 'expiry_date',
    instruction: 'Enter the expiration or best-before date so recipients know how fresh the food is.',
    isFilled: (f) => f.category === 'produce' || Boolean(f.expiry_date),
  },
  {
    id: 'image',
    instruction: 'Almost done! Upload a real photo of the food — no stock images. Then hit Submit.',
    isFilled: (f) => Boolean(f.image) || Boolean(f.image_url),
  },
]

/** Request Food (RequestFoodForm) */
export const REQUEST_FOOD_STEPS = [
  {
    id: 'title',
    instruction: 'Tell the community what food you need. Enter the name or type of food.',
    isFilled: (f) => Boolean(String(f.title || '').trim()),
  },
  {
    id: 'category',
    instruction: 'Select a category that best describes the food you\'re looking for.',
    isFilled: (f) => Boolean(f.category),
  },
  {
    id: 'quantity',
    instruction: 'How much do you need? Enter the quantity and pick a unit.',
    isFilled: (f) => Boolean(f.quantity) && Number(f.quantity) > 0,
  },
  {
    id: 'school_district',
    instruction: 'Choose your school or community so donors near you can see your request.',
    isFilled: (f) => Boolean(String(f.school_district || '').trim()),
  },
  {
    id: 'requester_name',
    instruction: 'Enter your name so donors know who the request is from.',
    isFilled: (f) => Boolean(String(f.requester_name || '').trim()),
  },
  {
    id: 'requester_email',
    instruction: 'Last step — enter your email address, then submit your request.',
    isFilled: (f) => Boolean(String(f.requester_email || '').trim()),
  },
]

/** Claim Food (ClaimFoodForm) — only one interactive step */
export const CLAIM_FOOD_STEPS = [
  {
    id: 'claimQty',
    instruction: 'Use the plus and minus buttons to choose how many portions you need, then press Confirm Claim.',
    isFilled: (f) => Boolean(f.hasConfirmed),  // completes once user confirms
  },
]
