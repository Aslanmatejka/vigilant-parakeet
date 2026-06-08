/**
 * Shared helpers for every /api/ai/* client call.
 *
 * Centralises:
 *  • Supabase JWT injection (backend auth checks only fire when a Bearer
 *    token is present — without this, _authenticate_request always returns
 *    None and user_id spoofing is possible on authenticated endpoints)
 *  • Parsing the structured AIError JSON body the backend emits
 *  • Extracting navigate/ui actions from tool_results for the chat hook
 */
import supabase from '../supabaseClient.js'

/** Cached token so we don't hammer getSession on every keystroke. */
let _tokenCache = { value: null, expiresAt: 0 }

/**
 * Return Authorization headers for AI backend calls.
 * Uses a 30s cache — good enough for chat bursts, short enough that
 * token refresh isn't stale for long.
 */
export async function getAiAuthHeaders(extra = {}) {
  const headers = { ...extra }
  const now = Date.now()
  if (!_tokenCache.value || now >= _tokenCache.expiresAt) {
    try {
      const { data: { session } } = await supabase.auth.getSession()
      _tokenCache = {
        value: session?.access_token || null,
        expiresAt: now + 30_000,
      }
    } catch {
      _tokenCache = { value: null, expiresAt: now + 5_000 }
    }
  }
  if (_tokenCache.value) {
    headers.Authorization = `Bearer ${_tokenCache.value}`
  }
  return headers
}

/** Clear cached token on sign-out (call from auth listeners if needed). */
export function clearAiAuthCache() {
  _tokenCache = { value: null, expiresAt: 0 }
}

// Invalidate the cached bearer whenever the auth session changes. Without this
// the 30s cache can keep serving a stale token after a refresh (→ 401s) or a
// leftover token after sign-out. Guarded so the test mock (which only stubs
// getSession) doesn't blow up at import time.
if (typeof supabase?.auth?.onAuthStateChange === 'function') {
  supabase.auth.onAuthStateChange(() => {
    clearAiAuthCache()
  })
}

/**
 * Parse a failed Response into our structured error object, or null if the
 * body isn't the typed AIError shape.
 */
export async function parseAiErrorResponse(response) {
  if (!response || response.ok) return null
  let payload = null
  try {
    payload = await response.json()
  } catch {
    return null
  }
  if (!payload || typeof payload !== 'object' || !payload.error_code) return null
  const requestId = response.headers.get('X-Request-ID') || payload.request_id || null
  return {
    code: payload.error_code,
    message: payload.message || payload.detail || 'AI service error',
    retryable: !!payload.retryable,
    retryAfter: payload.retry_after_seconds ?? null,
    requestId,
    status: response.status,
  }
}

/**
 * Throw an Error with `.aiError` attached when the backend returns a typed body.
 */
export async function throwAiHttpError(response, fallbackMessage = 'AI request failed') {
  const err = await parseAiErrorResponse(response)
  const message = err?.message || `${fallbackMessage}: ${response.status}`
  const e = new Error(message)
  if (err) e.aiError = err
  e.requestId = err?.requestId || response.headers.get('X-Request-ID') || null
  throw e
}

/**
 * Pull the first navigate/ui directive out of normalized tool_results so
 * useAIChat can set msg.action without duplicating UIControlContext logic.
 */
export function extractActionFromToolResults(toolResults) {
  if (!Array.isArray(toolResults)) return null
  for (const entry of toolResults) {
    if (!entry || (entry.tool !== 'navigate_ui' && entry.tool !== 'ui_action')) continue
    const r = entry.result || entry
    if (r.action && r.target) {
      return { action: r.action, target: r.target, path: r.path, view: r.view, focus: r.focus }
    }
    if (r.path) return { action: 'navigate', target: r.path, path: r.path }
  }
  return null
}

/**
 * Merge auth headers into a fetch init object (immutable).
 */
export async function withAiAuth(init = {}) {
  const authHeaders = await getAiAuthHeaders()
  return {
    ...init,
    headers: {
      ...authHeaders,
      ...(init.headers || {}),
    },
  }
}
