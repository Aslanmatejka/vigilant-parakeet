/**
 * useFormVoiceGuide
 *
 * AI voice assistant for forms:
 * - Speaks a welcome message when the form opens
 * - Speaks field-specific hints when the user focuses a field
 * - Inline chat so users can ask Nouri questions while filling the form
 */
import { useState, useEffect, useRef, useCallback } from 'react'
import { textToSpeech, playAudioBlob } from '../utils/openaiVoice'
import aiChatService from '../utils/services/aiChatService'
import { useAuthContext } from '../utils/AuthContext'

const DEFAULT_WELCOME =
  "Welcome! I'll guide you step by step. Click or tap any field whenever you need help."

const FIELD_DEBOUNCE_MS = 350

export const FORM_NAMES = {
  share: 'Share Food',
  request: 'Request Food',
  claim: 'Claim Food',
}

const DONOR_FIELDS = new Set([
  'donor_name', 'donor_type', 'donor_zip', 'donor_city', 'donor_state',
  'school_district', 'donor_email', 'donor_phone', 'full_address', 'donor_occupation',
])

const REQUEST_CONTACT_FIELDS = new Set([
  'requester_name', 'requester_email', 'requester_phone', 'full_address',
])

function sectionHint(formName, fieldName) {
  if (!fieldName) return ''
  if (formName === FORM_NAMES.share) {
    if (DONOR_FIELDS.has(fieldName)) {
      return 'That field is in the DONOR INFORMATION section (top of the form).'
    }
    return 'That field is in the FOOD LISTING section (below donor information).'
  }
  if (formName === FORM_NAMES.request) {
    if (REQUEST_CONTACT_FIELDS.has(fieldName)) {
      return 'That field is in the contact information section.'
    }
    return 'That field is in the food request details section.'
  }
  if (formName === FORM_NAMES.claim) {
    return 'That field is on the claim confirmation form.'
  }
  return ''
}

function buildFormChatPayload(userText, { formName, activeHint }) {
  const fieldLine = activeHint?.label
    ? `They are focused on the "${activeHint.label}" field.`
    : 'No field is currently focused.'

  const sectionLine = sectionHint(formName, activeHint?.fieldName)

  const separationRule = formName === FORM_NAMES.share
    ? 'Keep donor information separate from food listing details — never mix the two.\n'
    : ''

  return `[FORM ASSISTANT — ${formName}]
The user is actively filling out this form in the browser. ${fieldLine} ${sectionLine}
Help them complete THIS form only. ${separationRule}Do NOT call navigate_ui or send them to other pages unless they explicitly ask to leave.
Answer briefly (2–4 sentences) unless they need more detail.

User question: ${userText.trim()}`
}

export default function useFormVoiceGuide({
  hints = {},
  welcomeMessage = DEFAULT_WELCOME,
  formName = 'Form',
  lang = 'en',
}) {
  const { user, isAuthenticated } = useAuthContext()
  const [isMuted, setIsMuted] = useState(false)
  const [isSpeaking, setIsSpeaking] = useState(false)
  const [isDismissed, setIsDismissed] = useState(false)
  const [activeHint, setActiveHint] = useState(null)
  const [chatMessages, setChatMessages] = useState([])
  const [isChatLoading, setIsChatLoading] = useState(false)
  const [chatError, setChatError] = useState(null)

  const stopRef = useRef(null)
  const welcomedRef = useRef(false)
  const speakIdRef = useRef(0)
  const fieldTimerRef = useRef(null)
  const chatSeqRef = useRef(0)
  const chatBusyRef = useRef(false)
  const activeHintRef = useRef(null)

  useEffect(() => { activeHintRef.current = activeHint }, [activeHint])

  const cancelSpeech = useCallback(() => {
    speakIdRef.current += 1
    if (stopRef.current) {
      stopRef.current()
      stopRef.current = null
    }
    const synth = typeof window !== 'undefined' ? window.speechSynthesis : null
    if (synth) synth.cancel()
    setIsSpeaking(false)
  }, [])

  const speakText = useCallback(async (text, { force = false } = {}) => {
    if (!text || (isMuted && !force)) return

    cancelSpeech()
    const id = speakIdRef.current

    try {
      const blob = await textToSpeech(text, { lang })
      if (id !== speakIdRef.current) return

      const { stop } = playAudioBlob(
        blob,
        () => setIsSpeaking(true),
        () => { setIsSpeaking(false); stopRef.current = null },
      )
      stopRef.current = stop
    } catch {
      if (id !== speakIdRef.current) return
      const synth = typeof window !== 'undefined' ? window.speechSynthesis : null
      if (!synth) return
      const utt = new SpeechSynthesisUtterance(text)
      utt.lang = lang === 'es' ? 'es-ES' : 'en-US'
      utt.rate = 0.95
      utt.onstart = () => setIsSpeaking(true)
      utt.onend = () => setIsSpeaking(false)
      utt.onerror = () => setIsSpeaking(false)
      synth.speak(utt)
    }
  }, [lang, cancelSpeech, isMuted])

  useEffect(() => {
    if (welcomedRef.current || isDismissed || isMuted) return
    welcomedRef.current = true
    const timer = setTimeout(() => {
      setActiveHint(null)
      speakText(welcomeMessage)
    }, 500)
    return () => clearTimeout(timer)
  }, [isDismissed, isMuted, welcomeMessage, speakText])

  useEffect(() => {
    return () => {
      if (fieldTimerRef.current) clearTimeout(fieldTimerRef.current)
      cancelSpeech()
    }
  }, [cancelSpeech])

  const speakWelcome = useCallback(() => {
    if (isMuted || isDismissed) return
    if (fieldTimerRef.current) clearTimeout(fieldTimerRef.current)
    setActiveHint(null)
    speakText(welcomeMessage)
  }, [isMuted, isDismissed, welcomeMessage, speakText])

  const speakField = useCallback((fieldName) => {
    if (isMuted || isDismissed || chatBusyRef.current || isChatLoading) return
    const entry = hints[fieldName]
    if (!entry) return

    const text = typeof entry === 'string' ? entry : entry.text
    const label = typeof entry === 'string' ? null : entry.label
    if (!text) return

    if (fieldTimerRef.current) clearTimeout(fieldTimerRef.current)

    fieldTimerRef.current = setTimeout(() => {
      fieldTimerRef.current = null
      if (chatBusyRef.current) return
      cancelSpeech()
      setActiveHint({ fieldName, label, text })
      speakText(text)
    }, FIELD_DEBOUNCE_MS)
  }, [isMuted, isDismissed, isChatLoading, speakText, hints, cancelSpeech])

  const askQuestion = useCallback(async (rawText) => {
    const text = String(rawText || '').trim()
    if (!text || isChatLoading) return

    if (!isAuthenticated || !user?.id) {
      setChatError('Sign in to ask Nouri questions while filling out the form.')
      return
    }

    setChatError(null)
    chatBusyRef.current = true
    if (fieldTimerRef.current) clearTimeout(fieldTimerRef.current)
    cancelSpeech()

    const userMsg = {
      id: `form-user-${Date.now()}`,
      role: 'user',
      message: text,
    }
    setChatMessages((prev) => [...prev, userMsg])
    setIsChatLoading(true)

    const seq = ++chatSeqRef.current

    try {
      const payload = buildFormChatPayload(text, {
        formName,
        activeHint: activeHintRef.current,
      })
      const result = await aiChatService.sendMessage(payload, { userId: user.id })

      if (seq !== chatSeqRef.current) return

      if (result.error) {
        setChatError(result.error.message || 'Could not reach Nouri. Try again.')
        return
      }

      const reply = String(result.response || '').trim()
      if (!reply) {
        setChatError('No response from Nouri. Try again.')
        return
      }

      setChatMessages((prev) => [...prev, {
        id: `form-ai-${Date.now()}`,
        role: 'assistant',
        message: reply,
      }])
      setActiveHint(null)
      speakText(reply)
    } catch {
      if (seq !== chatSeqRef.current) return
      setChatError('Could not reach Nouri. Check your connection and try again.')
    } finally {
      if (seq === chatSeqRef.current) {
        setIsChatLoading(false)
        chatBusyRef.current = false
      }
    }
  }, [isChatLoading, isAuthenticated, user?.id, formName, cancelSpeech, speakText])

  const toggleMute = useCallback(() => {
    setIsMuted((m) => {
      if (!m) {
        if (fieldTimerRef.current) clearTimeout(fieldTimerRef.current)
        cancelSpeech()
      }
      return !m
    })
  }, [cancelSpeech])

  const dismiss = useCallback(() => {
    if (fieldTimerRef.current) clearTimeout(fieldTimerRef.current)
    chatSeqRef.current += 1
    chatBusyRef.current = false
    setIsChatLoading(false)
    cancelSpeech()
    setIsDismissed(true)
  }, [cancelSpeech])

  return {
    welcomeMessage,
    formName,
    activeHint,
    isMuted,
    isSpeaking,
    isDismissed,
    isChatLoading,
    chatMessages,
    chatError,
    canChat: isAuthenticated && !!user?.id,
    toggleMute,
    speakWelcome,
    dismiss,
    speakField,
    askQuestion,
  }
}

// ---------------------------------------------------------------------------
// Per-form welcome messages
// ---------------------------------------------------------------------------

export const SHARE_FOOD_WELCOME =
  "Welcome! This form has two sections: donor information at the top, and food listing details below. Click any field for help, or ask me a question anytime."

export const REQUEST_FOOD_WELCOME =
  "Welcome! I'll guide you through your food request. Click any field for help, or ask me a question anytime."

export const CLAIM_FOOD_WELCOME =
  "Welcome! I'll guide you through confirming your claim. Click any field for help, or ask me a question anytime."

// ---------------------------------------------------------------------------
// Per-field focus hints
// ---------------------------------------------------------------------------

export const SHARE_FOOD_HINTS = {
  donor_name: {
    label: 'Name / Organization',
    text: 'Donor information. Enter your full name, or your organization name if you are donating on behalf of a group.',
  },
  donor_type: {
    label: 'Donor Type',
    text: 'Donor information. Choose Individual or Family for personal donations, or Organization for a business or group.',
  },
  donor_zip: {
    label: 'ZIP Code',
    text: 'Donor information. Enter the ZIP code for the pickup area.',
  },
  donor_city: {
    label: 'City',
    text: 'Donor information. Enter the city where recipients will pick up the food.',
  },
  donor_state: {
    label: 'State',
    text: 'Donor information. Select the state for the pickup location.',
  },
  school_district: {
    label: 'Community',
    text: 'Donor information. Choose the community or school this donation belongs to.',
  },
  donor_email: {
    label: 'Email',
    text: 'Donor information. Enter your email so recipients can reach you if needed.',
  },
  donor_phone: {
    label: 'Phone',
    text: 'Donor information. Optional — add a phone number if you want to be reachable by phone.',
  },
  full_address: {
    label: 'Pickup Address',
    text: 'Donor information. Enter the full street address where food will be picked up. We will locate it on the map.',
  },
  donor_occupation: {
    label: 'Occupation / Role',
    text: 'Donor information. Optional — your occupation or role, such as Teacher or Chef.',
  },
  title: {
    label: 'Food Name',
    text: 'Food listing. What are you donating? Enter a short name, like Apples, Rice, or Homemade Bread.',
  },
  category: {
    label: 'Category',
    text: 'Food listing. Select the food category, such as Fresh Produce, Dairy, or Bakery.',
  },
  description: {
    label: 'Description',
    text: 'Food listing. Describe the food — its condition, source, and anything recipients should know.',
  },
  quantity: {
    label: 'Quantity',
    text: 'Food listing. Enter how much food you have.',
  },
  unit: {
    label: 'Unit',
    text: 'Food listing. Choose the unit for the quantity, such as pounds, kilograms, or count.',
  },
  expiry_date: {
    label: 'Expiration Date',
    text: 'Food listing. Enter the expiration or best-before date so recipients know how fresh it is.',
  },
  pickup_by: {
    label: 'Pickup Deadline',
    text: 'Food listing. Optional — set a date and time by which the food must be picked up.',
  },
  dietary_tags: {
    label: 'Dietary Information',
    text: 'Food listing. Optional — check any dietary labels that apply, such as Vegetarian or Gluten-Free.',
  },
  allergens: {
    label: 'Allergens',
    text: 'Food listing. Optional — check all allergens present so recipients with restrictions stay safe.',
  },
  ingredients: {
    label: 'Ingredients',
    text: 'Food listing. Optional — list main ingredients if this is prepared or packaged food.',
  },
  image: {
    label: 'Photo',
    text: 'Food listing. Upload a real photo of the food. Clear photos help recipients decide faster.',
  },
}

export const REQUEST_FOOD_HINTS = {
  title: {
    label: 'Food Needed',
    text: 'What food do you need? Enter the name or type, such as Rice or Fresh Vegetables.',
  },
  category: {
    label: 'Category',
    text: 'Select the category that best matches the food you are looking for.',
  },
  quantity: {
    label: 'Quantity',
    text: 'Enter how much you need.',
  },
  unit: {
    label: 'Unit',
    text: 'Choose the unit for your quantity, such as items, pounds, or bags.',
  },
  needed_by: {
    label: 'Needed By',
    text: 'Optional — enter the date you need this food by.',
  },
  school_district: {
    label: 'Community',
    text: 'Choose your school or community so nearby donors can see your request.',
  },
  description: {
    label: 'Details',
    text: 'Optional — add details like household size or why you need this food.',
  },
  dietary_notes: {
    label: 'Dietary Needs',
    text: 'Optional — list dietary needs such as gluten-free or nut allergy.',
  },
  requester_name: {
    label: 'Your Name',
    text: 'Contact information. Enter your name so donors know who the request is from.',
  },
  requester_email: {
    label: 'Email',
    text: 'Contact information. Enter your email so donors or admins can reach you.',
  },
  requester_phone: {
    label: 'Phone',
    text: 'Contact information. Optional — add a phone number if you prefer phone contact.',
  },
  full_address: {
    label: 'Pickup Area',
    text: 'Optional — enter your neighborhood or address to help donors near you.',
  },
}

export const CLAIM_FOOD_HINTS = {
  claimQty: {
    label: 'Portions',
    text: 'Use the plus and minus buttons to choose how many portions you want, then press Confirm Claim.',
  },
}
