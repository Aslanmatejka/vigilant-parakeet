/**
 * Voice Services — Whisper STT + TTS via FastAPI backend
 * All requests go through /api/ai/* with self-healing + auth headers.
 */
import { resilientFetch } from './services/aiSelfHealing.js'
import { throwAiHttpError } from './services/aiRequest.js'

/**
 * Transcribe audio using backend Whisper endpoint
 * @param {Blob} audioBlob - Audio blob (webm, mp4, wav, etc.)
 * @param {string} language - Language hint ('en' or 'es') — Whisper auto-detects
 * @returns {Promise<string>} - Transcribed text
 */
export async function transcribeAudio(audioBlob, language = 'en') {
  const formData = new FormData()
  formData.append('audio', audioBlob, 'audio.webm')

  const response = await resilientFetch(
    '/api/ai/transcribe',
    { method: 'POST', body: formData },
    { retries: 2, timeout: 45000, backoff: [800, 2000], label: 'ai/transcribe' }
  )

  if (!response.ok) {
    await throwAiHttpError(response, 'Whisper transcription failed')
  }

  const data = await response.json()
  if (data.filtered) return ''
  return data.transcript || ''
}

/**
 * Generate speech audio from text using backend TTS endpoint
 * @param {string} text - Text to convert to speech
 * @param {Object} options - { lang }
 * @returns {Promise<Blob>} - Audio blob (mp3)
 */
export async function textToSpeech(text, options = {}) {
  const response = await resilientFetch(
    '/api/ai/tts',
    {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        text: text.slice(0, 4096),
        lang: options.lang || 'en',
      }),
    },
    { retries: 2, timeout: 30000, backoff: [500, 1500], label: 'ai/tts' }
  )

  if (!response.ok) {
    await throwAiHttpError(response, 'Text-to-speech failed')
  }

  return await response.blob()
}

/**
 * Play an audio blob and return a promise that resolves when playback ends
 * @param {Blob} audioBlob - Audio blob to play
 * @param {Function} onStart - Called when playback starts
 * @param {Function} onEnd - Called when playback ends
 * @returns {{ play: Promise<void>, stop: Function }}
 */
export function playAudioBlob(audioBlob, onStart, onEnd) {
  const url = URL.createObjectURL(audioBlob)
  const audio = new Audio(url)

  const stop = () => {
    audio.pause()
    audio.currentTime = 0
    URL.revokeObjectURL(url)
    onEnd?.()
  }

  const play = new Promise((resolve) => {
    audio.onplay = () => onStart?.()
    audio.onended = () => {
      URL.revokeObjectURL(url)
      onEnd?.()
      resolve()
    }
    audio.onerror = () => {
      URL.revokeObjectURL(url)
      onEnd?.()
      resolve()
    }
    audio.play().catch(() => {
      onEnd?.()
      resolve()
    })
  })

  return { play, stop, audio }
}
