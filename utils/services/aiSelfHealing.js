/**
 * Direct AI fetch — no circuit breaker, no retries, no fallbacks.
 * Calls the backend straight through and surfaces errors to the caller.
 */
import { withAiAuth } from './aiRequest.js'

export const AI_STATUS = { HEALTHY: 'healthy', DEGRADED: 'degraded', DOWN: 'down' }

// Stub health monitor so any remaining aiHealth imports don't break.
class StubHealth {
  getStatus() { return { status: AI_STATUS.HEALTHY, lastError: null, circuit: 'closed' } }
  subscribe(cb) { try { cb(this.getStatus()) } catch (_) {} ; return () => {} }
  recordSuccess() {}
  recordFailure() {}
}
export const aiHealth = new StubHealth()

/**
 * Direct fetch with Supabase auth headers injected.
 * The `opts` argument is accepted for call-site compatibility but ignored.
 */
export async function resilientFetch(url, init = {}, opts = {}) {
  const { signal: callerSignal = null, timeout = 30000 } = opts

  const controller = new AbortController()
  const timer = setTimeout(() => controller.abort(), timeout)
  if (callerSignal) {
    callerSignal.addEventListener('abort', () => controller.abort(), { once: true })
  }

  try {
    const authedInit = await withAiAuth({ ...init, signal: controller.signal })
    const response = await fetch(url, authedInit)
    clearTimeout(timer)
    return response
  } catch (err) {
    clearTimeout(timer)
    throw err
  }
}

/**
 * Convenience: POST JSON and return parsed response JSON.
 */
export async function resilientPostJson(url, body, opts = {}) {
  const response = await resilientFetch(
    url,
    {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    },
    opts
  )
  if (!response.ok) {
    const text = await response.text().catch(() => '')
    const err = new Error(`${opts.label || url} failed: HTTP ${response.status} ${text}`)
    err.status = response.status
    throw err
  }
  return response.json()
}
