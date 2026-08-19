/**
 * useFormVoiceGuide
 *
 * AI voice assistant for forms:
 * - Speaks a welcome message when the form opens
 * - Speaks field-specific hints when the user focuses a field
 *
 * Audio uses the backend AI TTS endpoint (OpenAI voice).
 */
import { useState, useEffect, useRef, useCallback } from 'react'
import { textToSpeech, playAudioBlob } from '../utils/openaiVoice'

const DEFAULT_WELCOME =
  "Welcome! I'll guide you step by step. Click or tap any field whenever you need help."

export default function useFormVoiceGuide({
  hints = {},
  welcomeMessage = DEFAULT_WELCOME,
  lang = 'en',
}) {
  const [isMuted, setIsMuted] = useState(false)
  const [isSpeaking, setIsSpeaking] = useState(false)
  const [isDismissed, setIsDismissed] = useState(false)
  const stopRef = useRef(null)
  const welcomedRef = useRef(false)

  const speakText = useCallback(async (text) => {
    if (!text) return
    if (stopRef.current) { stopRef.current(); stopRef.current = null }

    try {
      const blob = await textToSpeech(text, { lang })
      const { stop } = playAudioBlob(
        blob,
        () => setIsSpeaking(true),
        () => { setIsSpeaking(false); stopRef.current = null },
      )
      stopRef.current = stop
    } catch {
      const synth = typeof window !== 'undefined' ? window.speechSynthesis : null
      if (!synth) return
      synth.cancel()
      const utt = new SpeechSynthesisUtterance(text)
      utt.lang = lang === 'es' ? 'es-ES' : 'en-US'
      utt.rate = 0.95
      utt.onstart = () => setIsSpeaking(true)
      utt.onend = () => setIsSpeaking(false)
      utt.onerror = () => setIsSpeaking(false)
      synth.speak(utt)
    }
  }, [lang])

  // Welcome the user once when the form opens
  useEffect(() => {
    if (welcomedRef.current || isDismissed || isMuted) return
    welcomedRef.current = true
    const timer = setTimeout(() => speakText(welcomeMessage), 400)
    return () => clearTimeout(timer)
  }, [isDismissed, isMuted, welcomeMessage, speakText])

  useEffect(() => {
    return () => { if (stopRef.current) stopRef.current() }
  }, [])

  const speakWelcome = useCallback(() => {
    if (isMuted || isDismissed) return
    speakText(welcomeMessage)
  }, [isMuted, isDismissed, welcomeMessage, speakText])

  const speakField = useCallback((fieldName) => {
    if (isMuted || isDismissed) return
    const hint = hints[fieldName]
    if (hint) speakText(hint)
  }, [isMuted, isDismissed, speakText, hints])

  const toggleMute = useCallback(() => {
    setIsMuted((m) => {
      if (!m && stopRef.current) { stopRef.current(); stopRef.current = null }
      return !m
    })
  }, [])

  const dismiss = useCallback(() => {
    if (stopRef.current) { stopRef.current(); stopRef.current = null }
    setIsDismissed(true)
  }, [])

  return {
    welcomeMessage,
    isMuted,
    isSpeaking,
    isDismissed,
    toggleMute,
    speakWelcome,
    dismiss,
    speakField,
  }
}

// ---------------------------------------------------------------------------
// Per-form welcome messages
// ---------------------------------------------------------------------------

export const SHARE_FOOD_WELCOME =
  "Welcome! I'll guide you step by step through sharing your food. Click or tap any field whenever you need help."

export const REQUEST_FOOD_WELCOME =
  "Welcome! I'll guide you step by step through your food request. Click or tap any field whenever you need help."

export const CLAIM_FOOD_WELCOME =
  "Welcome! I'll guide you step by step through confirming your claim. Click or tap any field whenever you need help."

// ---------------------------------------------------------------------------
// Per-field focus hints — spoken when the user clicks/tabs into a field
// ---------------------------------------------------------------------------

export const SHARE_FOOD_HINTS = {
  donor_name:       'Enter your full name, or the name of your organization if you\'re donating on behalf of one.',
  donor_type:       'Choose Individual or Family if you\'re donating personally, or Organization if you represent a business or group.',
  donor_zip:        'Enter the ZIP code for your pickup location.',
  donor_city:       'Enter the city where the food can be picked up.',
  donor_state:      'Select the state where pickup will happen.',
  school_district:  'Choose the community or school this donation belongs to.',
  donor_email:      'Enter your email address so recipients can contact you if needed.',
  donor_phone:      'Optional — add a phone number if you\'d like to be reachable by phone.',
  full_address:     'Enter the complete street address for pickup. We\'ll pin it on the map automatically.',
  donor_occupation: 'Optional — your occupation or role, for example Teacher or Chef.',
  title:            'Give the food a short, clear name. For example: Apples, Rice, or Homemade Bread.',
  category:         'Pick the category that best fits the food — such as Fresh Produce, Dairy, or Bakery.',
  description:      'Describe the food in a few sentences — its condition, source, and any details recipients should know.',
  quantity:         'Enter how much food you have, then choose a unit like pounds, kilograms, or count.',
  unit:             'Choose the unit for the quantity — pounds, kilograms, ounces, or servings.',
  expiry_date:      'Enter the expiration or best-before date so recipients know how fresh the food is.',
  pickup_by:        'Optional — set a specific date and time by which the food must be picked up.',
  dietary_tags:     'Check any labels that apply to this food, such as Vegetarian, Vegan, or Gluten-Free.',
  allergens:        'Check all allergens present so recipients with dietary restrictions can stay safe.',
  ingredients:      'Optional — list the main ingredients, especially if this is a prepared or packaged food.',
  image:            'Upload a real photo of the food. Clear, well-lit photos help recipients decide faster.',
}

export const REQUEST_FOOD_HINTS = {
  title:           'Describe the food you need — for example Rice, Baby Formula, or Fresh Vegetables.',
  category:        'Select the category that best matches the food you\'re looking for.',
  quantity:        'Enter how much you need and choose a unit like items, pounds, or bags.',
  unit:            'Choose the unit for your quantity.',
  needed_by:       'Optional — if you need the food by a specific date, enter it here.',
  school_district: 'Choose your school or community so the right donors can see your request.',
  description:     'Optional — add details like household size, why you need it, or preferred pickup area.',
  dietary_notes:   'Optional — list any dietary needs, such as gluten-free or nut allergy.',
  requester_name:  'Enter your name so donors know who the request is from.',
  requester_email: 'Enter your email address so donors or admins can reach you.',
  requester_phone: 'Optional — add a phone number if you prefer to be contacted by phone.',
  full_address:    'Optional — enter your neighborhood or address to help donors near you.',
}

export const CLAIM_FOOD_HINTS = {
  claimQty: 'Use the plus and minus buttons to choose how many portions you\'d like to claim, then press Confirm Claim.',
}
