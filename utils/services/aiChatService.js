import { reportError } from '../helpers.js'
import { resilientFetch, resilientPostJson, aiHealth } from './aiSelfHealing.js'
import {
  parseAiErrorResponse,
  extractActionFromToolResults,
  throwAiHttpError,
} from './aiRequest.js'
import {
  getCachedInsights,
  cacheInsights,
  computeLocalInsights,
} from './insightsFallback.js'
import { buildChatFallback } from './chatFallback.js'
import { normalizeToolResults } from './normalizeToolResults.js'

/**
 * AI Chat Service — talks to the FastAPI backend at /api/ai/*
 *
 * The backend handles: system prompt, conversation history persistence,
 * tool calling, language detection, TTS, and OpenAI communication.
 * The frontend only sends user messages + user_id.
 *
 * All endpoints are wrapped by the self-healing layer
 * (utils/services/aiSelfHealing.js), which adds: retry-with-backoff,
 * a circuit breaker, automatic health probing, and graceful fallbacks.
 */

const API_BASE = '/api/ai'
const REQUEST_TIMEOUT = 60000 // allow time for tool-calling flows (GPT call + tool + follow-up)

// Re-export so callers / UI can subscribe to AI health without an extra import path
export { aiHealth }

/** Map a successful /api/ai/chat JSON body to the frontend contract. */
function mapChatSuccess(data, requestId = null) {
  const toolResults = normalizeToolResults(data.tool_results || [])
  return {
    response: data.text,
    lang: data.lang || 'en',
    audioUrl: data.audio_url || null,
    conversationId: data.conversation_id || null,
    toolResults,
    suggestions: data.suggestions || [],
    nextStep: data.next_step || null,
    action: extractActionFromToolResults(toolResults),
    requestId,
    error: null,
  }
}

/** Map a failed Response (typed AIError body) to the frontend contract. */
async function mapChatError(response) {
  const requestId = response.headers.get('X-Request-ID') || null
  const err = await parseAiErrorResponse(response)
  if (!err) return null
  return {
    response: null,
    lang: 'en',
    audioUrl: null,
    conversationId: null,
    toolResults: [],
    suggestions: [],
    action: null,
    requestId: err.requestId || requestId,
    error: err,
  }
}

class AIChatService {
  /**
   * Send a chat message via the FastAPI backend.
   * Backend handles: GPT, tools, history storage, language detection.
   *
   * Return shape:
   *   On success → { response, lang, audioUrl, conversationId, toolResults,
   *                  suggestions, requestId, error: null }
   *   On typed backend error (4xx/5xx with JSON body) →
   *     { response: null, error: { code, message, retryable, retryAfter,
   *       requestId, status }, requestId, lang }
   *   On full backend outage (network / circuit open) → buildChatFallback(...)
   *     which returns { response: "...", degraded: true, ... } so the UI
   *     never breaks.
   */
  async sendMessage(message, { userId, includeAudio = false, silent = false } = {}) {
    try {
      const response = await resilientFetch(
        `${API_BASE}/chat`,
        {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            user_id: userId,
            message,
            include_audio: includeAudio,
            silent,
          }),
        },
        {
          retries: 3,
          timeout: REQUEST_TIMEOUT,
          backoff: [500, 1500, 3000],
          label: 'ai/chat',
          // Self-healing: when the backend is unreachable, return a
          // deterministic helpful reply instead of throwing. The user
          // still gets value while the circuit breaker reconnects.
          fallback: () => buildChatFallback(message),
        }
      )

      // If the self-healing fallback fired, it returned a plain object,
      // not a Response — pass it through directly.
      if (!(response instanceof Response)) {
        return response
      }

      const requestId = response.headers.get('X-Request-ID') || null

      if (!response.ok) {
        const typed = await mapChatError(response)
        if (typed) {
          console.warn(
            `[ai/chat] backend error ${typed.error.code} (${typed.error.status})`,
            { requestId: typed.requestId, message: typed.error.message }
          )
          return typed
        }
        console.error('AI backend error (unstructured):', response.status)
        return buildChatFallback(message)
      }

      const data = await response.json()
      return mapChatSuccess(data, requestId)
    } catch (error) {
      console.error('AI chat service error:', error)
      reportError(error)
      // Last-resort heal: never let the chat UI break
      return buildChatFallback(message)
    }
  }

  /**
   * Send voice audio to the FastAPI backend for transcription + chat response.
   *
   * Uses the same self-healing layer as text chat (retry, circuit breaker,
   * timeout) so transient network blips don't kill a voice turn — but with
   * only 1 retry since audio uploads are bandwidth-heavy and Whisper itself
   * takes a few seconds, making longer backoff feel sluggish to the user.
   *
   * @param {Blob} audioBlob - recorded audio
   * @param {string} userId
   * @param {boolean} includeAudio - return TTS audio in response
   * @param {boolean} silent       - skip persisting the transcript as a user row
   * @returns {{ response: string, transcript: string, lang: string, audioUrl: string|null }}
   */
  async sendVoice(audioBlob, { userId, includeAudio = true, silent = false } = {}) {
    try {
      const formData = new FormData()
      formData.append('audio', audioBlob, 'audio.webm')
      formData.append('user_id', userId)
      formData.append('include_audio', includeAudio.toString())
      formData.append('silent', silent ? 'true' : 'false')

      const response = await resilientFetch(
        `${API_BASE}/voice`,
        { method: 'POST', body: formData },
        {
          retries: 2,
          timeout: 60000,
          backoff: [1000],
          label: 'ai/voice',
        }
      )

      // The resilientFetch fallback path is not configured for voice
      // (we'd rather surface the failure than fake a transcript), so the
      // return value is always a Response here.
      if (!(response instanceof Response)) {
        throw new Error('Unexpected voice fallback response')
      }

      if (!response.ok) {
        const typed = await mapChatError(response)
        if (typed?.error) {
          const e = new Error(typed.error.message)
          e.aiError = typed.error
          e.requestId = typed.requestId
          throw e
        }
        const errorText = await response.text().catch(() => '')
        console.error('AI voice error:', response.status, errorText)
        throw new Error(`Voice service error: ${response.status}`)
      }

      const data = await response.json()
      return {
        ...mapChatSuccess(data, response.headers.get('X-Request-ID')),
        transcript: data.transcript || '',
      }
    } catch (error) {
      // Unintelligible / noise audio is filtered server-side and comes back
      // as a benign `invalid_input` 400. That's an expected, user-side outcome
      // (background noise, an empty breath, the AI's own echo) — NOT a system
      // fault, so don't escalate it to reportError and pollute the logs /
      // error backend. Just surface it to the caller to handle softly.
      if (error?.aiError?.code === 'invalid_input') {
        console.debug('Voice input not understood (filtered):', error.message)
      } else {
        console.error('AI voice service error:', error)
        reportError(error)
      }
      throw error
    }
  }

  /**
   * Fetch role-specific dashboard insights for a user.
   *
   * @param {string} userId
   * @param {{ roleHint?: string }} [opts]
   * @returns {Promise<{ role: string, headline: string, insights: Array, generatedAt: string }>}
   */
  async getInsights(userId, { roleHint = null } = {}) {
    // Real self-healing strategy:
    //   1. Try the live backend (with retry + circuit breaker).
    //   2. If it fails, fall back to a deterministic Supabase-direct
    //      computation so the user still sees real, accurate insights.
    //   3. Cache every successful payload so the next mount is instant.
    const buildFallback = async () => {
      try {
        return await computeLocalInsights(userId, roleHint)
      } catch (err) {
        console.warn('Local insights fallback failed:', err?.message || err)
        // Last-resort: any cached payload, even if stale
        const cached = getCachedInsights(userId)
        if (cached?.payload) {
          return { ...cached.payload, _degraded: true, _source: 'cache' }
        }
        return {
          role: roleHint || 'recipient',
          headline: '',
          insights: [],
          profile_completion: null,
          profile_gaps: [],
          generated_at: new Date().toISOString(),
          _degraded: true,
          _source: 'empty',
        }
      }
    }

    try {
      const data = await resilientPostJson(
        `${API_BASE}/insights`,
        { user_id: userId, role_hint: roleHint },
        {
          retries: 3,
          timeout: 20000,
          backoff: [200, 800, 1600],
          label: 'ai/insights',
          fallback: buildFallback,
        }
      )

      const result = {
        role: data.role || 'recipient',
        headline: data.headline || '',
        insights: Array.isArray(data.insights) ? data.insights : [],
        profileCompletion: typeof data.profile_completion === 'number' ? data.profile_completion : null,
        profileGaps: Array.isArray(data.profile_gaps) ? data.profile_gaps : [],
        generatedAt: data.generated_at || new Date().toISOString(),
        degraded: !!data._degraded,
        source: data._source || 'live',
      }

      // Cache only authoritative (non-degraded) responses
      if (!result.degraded) {
        cacheInsights(userId, data)
      }

      return result
    } catch (error) {
      // resilientPostJson can still throw on unexpected programmer errors —
      // never let the panel break, always return something usable.
      console.error('AI insights service error:', error)
      reportError(error)
      const fallback = await buildFallback()
      return {
        role: fallback.role || 'recipient',
        headline: fallback.headline || '',
        insights: fallback.insights || [],
        profileCompletion: typeof fallback.profile_completion === 'number' ? fallback.profile_completion : null,
        profileGaps: fallback.profile_gaps || [],
        generatedAt: fallback.generated_at || new Date().toISOString(),
        degraded: true,
        source: fallback._source || 'fallback',
      }
    }
  }

  /**
   * Load conversation history from the backend.
   */
  async getHistory(userId, limit = 50) {
    try {
      const response = await resilientFetch(
        `${API_BASE}/history/${encodeURIComponent(userId)}?limit=${limit}`,
        { method: 'GET' },
        { retries: 2, timeout: 15000, label: 'ai/history' }
      )
      if (!response.ok) {
        await throwAiHttpError(response, 'History fetch failed')
      }
      const data = await response.json()
      return data.messages || []
    } catch (error) {
      console.error('Get AI history error:', error)
      reportError(error)
      return []
    }
  }

  /**
   * Clear conversation history for a user.
   */
  async clearHistory(userId) {
    try {
      const response = await resilientFetch(
        `${API_BASE}/history/${encodeURIComponent(userId)}`,
        { method: 'DELETE' },
        { retries: 1, timeout: 15000, label: 'ai/history-clear' }
      )
      if (!response.ok) {
        await throwAiHttpError(response, 'Clear history failed')
      }
    } catch (error) {
      console.error('Clear AI history error:', error)
      reportError(error)
      throw error
    }
  }

  /**
   * Submit feedback on an AI message.
   */
  async submitFeedback(conversationId, userId, rating, comment = null) {
    try {
      const response = await resilientFetch(
        `${API_BASE}/feedback`,
        {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            conversation_id: conversationId,
            user_id: userId,
            rating,
            comment,
          }),
        },
        { retries: 1, timeout: 10000, label: 'ai/feedback' }
      )
      if (!response.ok) {
        await throwAiHttpError(response, 'Feedback submission failed')
      }
    } catch (error) {
      console.error('Submit AI feedback error:', error)
      reportError(error)
      throw error
    }
  }

  /**
   * GPS + voice-driven food search ranked by urgency and distance.
   *
   * @param {string} userId
   * @param {object} opts
   * @param {string} opts.transcript           — recognized text (or typed query)
   * @param {number|null} opts.latitude        — GPS lat (optional but recommended)
   * @param {number|null} opts.longitude       — GPS lng (optional but recommended)
   * @param {number} [opts.maxDistanceKm=25]
   * @param {number} [opts.limit=10]
   * @returns {Promise<{headline:string, transcript:string, filters:object, results:Array, totalMatched:number, generatedAt:string, userLocation:object|null, maxDistanceKm:number}>}
   */
  async voiceSearch(userId, {
    transcript,
    latitude = null,
    longitude = null,
    maxDistanceKm = 25,
    limit = 10,
  } = {}) {
    try {
      const response = await resilientFetch(
        `${API_BASE}/voice-search`,
        {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            user_id: userId,
            transcript,
            latitude,
            longitude,
            max_distance_km: maxDistanceKm,
            limit,
          }),
        },
        {
          retries: 2,
          timeout: 25000,
          backoff: [400, 1200],
          label: 'ai/voice-search',
        }
      )
      if (!response.ok) {
        await throwAiHttpError(response, 'Voice search failed')
      }
      const data = await response.json()
      return {
        headline: data.headline || '',
        transcript: data.transcript || transcript,
        filters: data.filters || {},
        results: Array.isArray(data.results) ? data.results : [],
        totalMatched: typeof data.total_matched === 'number' ? data.total_matched : 0,
        userLocation: data.user_location || null,
        maxDistanceKm: typeof data.max_distance_km === 'number' ? data.max_distance_km : maxDistanceKm,
        generatedAt: data.generated_at || new Date().toISOString(),
      }
    } catch (error) {
      console.error('Voice search error:', error)
      reportError(error)
      throw error
    }
  }

  /**
   * Fetch a Mapbox Directions route (geometry + summary) for drawing on the map.
   * @param {Object} opts
   * @param {number} opts.originLat
   * @param {number} opts.originLng
   * @param {number} opts.destLat
   * @param {number} opts.destLng
   * @param {'driving'|'walking'|'cycling'} [opts.profile='driving']
   * @returns {Promise<object>} route payload from /api/ai/route
   */
  async getRoute({ originLat, originLng, destLat, destLng, profile = 'driving' } = {}) {
    try {
      const response = await resilientFetch(
        `${API_BASE}/route`,
        {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            origin_lat: originLat,
            origin_lng: originLng,
            dest_lat: destLat,
            dest_lng: destLng,
            profile,
          }),
        },
        {
          retries: 2,
          timeout: 15000,
          backoff: [300, 1000],
          label: 'ai/route',
        }
      )
      if (!response.ok) {
        await throwAiHttpError(response, 'Route lookup failed')
      }
      return await response.json()
    } catch (error) {
      console.error('Route lookup error:', error)
      reportError(error)
      throw error
    }
  }

  /**
   * Generate household-aware, low-resource recipes from claimed/available items.
   * @param {string} userId
   * @param {Object} opts
   * @param {string[]} [opts.ingredients]        — explicit list (overrides claimed)
   * @param {boolean}  [opts.useClaimed=true]    — pull user's active claims if no list
   * @param {boolean}  [opts.lowResource=true]   — constrain time/equipment/cost
   * @param {number}   [opts.householdSize]
   * @param {number}   [opts.maxRecipes=3]
   * @param {string[]} [opts.dietaryOverrides]
   * @param {string}   [opts.notes]
   * @returns {Promise<{headline:string, recipes:Array, source:string, householdSize:number, lowResource:boolean, dietaryRestrictions:string[], ingredientsUsed:string[], generatedAt:string}>}
   */
  async recipes(userId, {
    ingredients = null,
    useClaimed = true,
    lowResource = true,
    householdSize = null,
    maxRecipes = 3,
    dietaryOverrides = null,
    notes = null,
    signal = null,
  } = {}) {
    try {
      const response = await resilientFetch(
        `${API_BASE}/recipes`,
        {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            user_id: userId,
            ingredients,
            use_claimed: useClaimed,
            low_resource: lowResource,
            household_size: householdSize,
            max_recipes: maxRecipes,
            dietary_overrides: dietaryOverrides,
            notes,
          }),
        },
        {
          retries: 2,
          timeout: 30000,
          backoff: [500, 1500],
          label: 'ai/recipes',
          signal,
        }
      )
      if (!response.ok) {
        await throwAiHttpError(response, 'Recipe generation failed')
      }
      const data = await response.json()
      return {
        headline: data.headline || '',
        recipes: Array.isArray(data.recipes) ? data.recipes : [],
        source: data.source || 'empty',
        ingredientsUsed: Array.isArray(data.ingredients_used) ? data.ingredients_used : [],
        householdSize: data.household_size || householdSize || null,
        lowResource: typeof data.low_resource === 'boolean' ? data.low_resource : lowResource,
        dietaryRestrictions: Array.isArray(data.dietary_restrictions) ? data.dietary_restrictions : [],
        generatedAt: data.generated_at || new Date().toISOString(),
      }
    } catch (error) {
      console.error('Recipe generation error:', error)
      reportError(error)
      throw error
    }
  }

  /**
   * Natural-language query grounded in safe Supabase tool calls.
   * @param {string} userId
   * @param {string} question
   * @param {Object} [opts]
   * @param {number} [opts.maxSteps=3]
   * @returns {Promise<{question:string, answer:string, toolTrace:Array, steps:number, isAdmin:boolean, generatedAt:string}>}
   */
  async askQuery(userId, question, { maxSteps = 3 } = {}) {
    try {
      const response = await resilientFetch(
        `${API_BASE}/query`,
        {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            user_id: userId,
            question,
            max_steps: maxSteps,
          }),
        },
        {
          retries: 2,
          timeout: 30000,
          backoff: [400, 1200],
          label: 'ai/query',
        }
      )
      if (!response.ok) {
        await throwAiHttpError(response, 'Query failed')
      }
      const data = await response.json()
      return {
        question: data.question || question,
        answer: data.answer || '',
        toolTrace: Array.isArray(data.tool_trace) ? data.tool_trace : [],
        steps: typeof data.steps === 'number' ? data.steps : 0,
        isAdmin: !!data.is_admin,
        generatedAt: data.generated_at || new Date().toISOString(),
      }
    } catch (error) {
      console.error('AI query error:', error)
      reportError(error)
      throw error
    }
  }

  /**
   * Send a photo to the backend; GPT-4 vision returns a draft food listing
   * the chat UI can preview + confirm before insert.
   *
   * @param {File|Blob} file - image file
   * @param {{ userId: string }} opts
   * @returns {Promise<{ draft: object, confidence: number, raw: string }>}
   */
  async visionListing(file, { userId } = {}) {
    if (!file) throw new Error('No image file provided')
    const formData = new FormData()
    formData.append('user_id', userId || '00000000-0000-0000-0000-000000000000')
    formData.append('image', file, file.name || 'photo.jpg')

    try {
      const response = await resilientFetch(
        `${API_BASE}/vision-listing`,
        { method: 'POST', body: formData },
        { retries: 2, timeout: 60000, backoff: [800, 2000], label: 'ai/vision-listing' }
      )
      if (!response.ok) {
        await throwAiHttpError(response, 'Vision listing failed')
      }
      const data = await response.json()
      return {
        draft: data.draft || {},
        confidence: typeof data.confidence === 'number' ? data.confidence : 0,
        raw: data.raw || '',
      }
    } catch (error) {
      console.error('Vision listing error:', error)
      reportError(error)
      throw error
    }
  }

  /**
   * Ask the AI to fill gaps (description, dietary tags, allergens, expiry,
   * weak category) on parsed CSV / vision rows. Never overwrites user values.
   *
   * @param {Array<object>} rows - parsed listing drafts
   * @param {{ userId: string, language?: string }} opts
   * @returns {Promise<{ rows: object[], summary: string, filled: Array<{index:number,fields:string[]}> }>}
   */
  async enrichListings(rows, { userId, language = 'en' } = {}) {
    if (!Array.isArray(rows) || rows.length === 0) {
      throw new Error('No rows to enrich')
    }
    try {
      const response = await resilientFetch(
        `${API_BASE}/enrich-listings`,
        {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            user_id: userId || '00000000-0000-0000-0000-000000000000',
            rows,
            language,
          }),
        },
        { retries: 2, timeout: 45000, backoff: [500, 1500], label: 'ai/enrich-listings' }
      )
      if (!response.ok) {
        console.warn('Enrich listings HTTP error:', response.status)
        return { rows, summary: '', filled: [] }
      }
      const data = await response.json()
      return {
        rows: Array.isArray(data.rows) ? data.rows : rows,
        summary: typeof data.summary === 'string' ? data.summary : '',
        filled: Array.isArray(data.filled) ? data.filled : [],
      }
    } catch (error) {
      console.warn('Enrich listings unavailable, returning originals:', error?.message || error)
      return { rows, summary: '', filled: [] }
    }
  }

  /**
   * Bulk-insert food listings (used by the photo + CSV upload flows in chat).
   *
   * @param {Array<object>} listings - validated row drafts
   * @param {{ userId: string }} opts
   * @returns {Promise<{ created: number, failed: number, ids: string[], errors: any[] }>}
   */
  async bulkCreateListings(listings, { userId } = {}) {
    if (!Array.isArray(listings) || listings.length === 0) {
      throw new Error('No listings provided')
    }
    if (!userId) {
      throw new Error('userId is required for bulk listing creation')
    }
    try {
      const data = await resilientPostJson(
        `${API_BASE}/bulk-listings`,
        { user_id: userId, listings },
        {
          retries: 1,
          timeout: 45000,
          backoff: [800],
          label: 'ai/bulk-listings',
        }
      )
      if (data && typeof data === 'object' && ('created' in data || 'failed' in data)) {
        return {
          created: data.created || 0,
          failed: data.failed || 0,
          ids: Array.isArray(data.ids) ? data.ids : [],
          errors: Array.isArray(data.errors) ? data.errors : [],
        }
      }
      return {
        created: 0,
        failed: listings.length,
        ids: [],
        errors: [{ error: 'AI service offline or returned an unexpected response' }],
      }
    } catch (error) {
      console.error('Bulk create listings error:', error)
      reportError(error)
      throw error
    }
  }
}

const aiChatService = new AIChatService()
export default aiChatService
