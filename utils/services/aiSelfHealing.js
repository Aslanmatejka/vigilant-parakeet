/**
 * AI Self-Healing Layer
 * ----------------------
 * Provides automatic recovery for transient AI/backend failures:
 *   - Retry with exponential backoff (network + 5xx only)
 *   - Circuit breaker (stops hammering a down backend, auto-recovers)
 *   - Health monitor (periodic /health probe + pub/sub for UI)
 *   - Per-call timeout via AbortController
 *   - Optional fallback responses so the UI never hard-fails
 *
 * Usage:
 *   import { resilientFetch, aiHealth } from './aiSelfHealing.js'
 *   const data = await resilientFetch('/api/ai/insights', {
 *     method: 'POST',
 *     body: JSON.stringify({...}),
 *   }, { retries: 3, timeout: 20000, fallback: () => ({ insights: [] }) })
 */

import { withAiAuth } from './aiRequest.js'

// Use a proxied URL so the dev server forwards to the backend.
// Fallback to /health for non-Vite environments where '/' is the backend.
const HEALTH_URL = '/api/ai/health'
const PROBE_INTERVAL_MS = 15000

const STATUS = {
  HEALTHY: 'healthy',
  DEGRADED: 'degraded',
  DOWN: 'down',
}

// ---------------------------------------------------------------------------
// Circuit Breaker
// ---------------------------------------------------------------------------
class CircuitBreaker {
  constructor({ failureThreshold = 5, cooldownMs = 20000 } = {}) {
    this.failureThreshold = failureThreshold
    this.cooldownMs = cooldownMs
    this.failureCount = 0
    this.state = 'closed' // 'closed' | 'open' | 'half-open'
    this.openedAt = 0
  }

  canRequest() {
    if (this.state === 'closed') return true
    if (this.state === 'open') {
      if (Date.now() - this.openedAt >= this.cooldownMs) {
        this.state = 'half-open'
        return true
      }
      return false
    }
    // half-open: allow a single probe through
    return true
  }

  recordSuccess() {
    this.failureCount = 0
    if (this.state !== 'closed') {
      this.state = 'closed'
    }
  }

  recordFailure() {
    this.failureCount += 1
    if (this.state === 'half-open' || this.failureCount >= this.failureThreshold) {
      this.state = 'open'
      this.openedAt = Date.now()
    }
  }

  getState() {
    return this.state
  }
}

const breaker = new CircuitBreaker({ failureThreshold: 5, cooldownMs: 20000 })

// ---------------------------------------------------------------------------
// Health Monitor (pub/sub)
// ---------------------------------------------------------------------------
class AiHealthMonitor {
  constructor() {
    this.status = STATUS.HEALTHY
    this.lastError = null
    this.lastChangedAt = Date.now()
    this.listeners = new Set()
    this.probeTimer = null
    this.consecutiveFailures = 0
  }

  getStatus() {
    return {
      status: this.status,
      lastError: this.lastError,
      lastChangedAt: this.lastChangedAt,
      circuit: breaker.getState(),
    }
  }

  subscribe(cb) {
    this.listeners.add(cb)
    try {
      cb(this.getStatus())
    } catch (_) {
      /* ignore */
    }
    return () => this.listeners.delete(cb)
  }

  _setStatus(next, error = null) {
    if (next === this.status) return
    this.status = next
    this.lastError = error ? String(error.message || error) : null
    this.lastChangedAt = Date.now()
    for (const cb of this.listeners) {
      try {
        cb(this.getStatus())
      } catch (_) {
        /* ignore listener errors */
      }
    }
  }

  recordSuccess() {
    this.consecutiveFailures = 0
    breaker.recordSuccess()
    this._setStatus(STATUS.HEALTHY)
    this._stopProbing()
  }

  recordFailure(error) {
    this.consecutiveFailures += 1
    breaker.recordFailure()
    if (breaker.getState() === 'open') {
      this._setStatus(STATUS.DOWN, error)
      this._startProbing()
    } else if (this.consecutiveFailures >= 2) {
      this._setStatus(STATUS.DEGRADED, error)
      // Also probe in degraded state so we can auto-recover without
      // waiting for the user to make another AI call.
      this._startProbing()
    }
  }

  _startProbing() {
    if (this.probeTimer || typeof window === 'undefined') return
    this.probeTimer = setInterval(() => this._probe(), PROBE_INTERVAL_MS)
  }

  _stopProbing() {
    if (this.probeTimer) {
      clearInterval(this.probeTimer)
      this.probeTimer = null
    }
  }

  async _probe() {
    try {
      const controller = new AbortController()
      const t = setTimeout(() => controller.abort(), 5000)
      const res = await fetch(HEALTH_URL, {
        signal: controller.signal,
        cache: 'no-store',
        headers: { Accept: 'application/json' },
      })
      clearTimeout(t)
      // Must be ok AND actually JSON from the backend — Vite's SPA fallback
      // returns HTML with 200 OK, which would falsely look healthy.
      const ct = res.headers.get('content-type') || ''
      if (res.ok && ct.includes('application/json')) {
        breaker.recordSuccess()
        this.consecutiveFailures = 0
        this._setStatus(STATUS.HEALTHY)
        this._stopProbing()
      }
    } catch (_) {
      /* still down — keep probing */
    }
  }
}

export const aiHealth = new AiHealthMonitor()

// ---------------------------------------------------------------------------
// resilientFetch
// ---------------------------------------------------------------------------
const sleep = (ms) => new Promise((r) => setTimeout(r, ms))

/**
 * Fetch with retry + circuit breaker + per-attempt timeout.
 *
 * @param {string} url
 * @param {RequestInit} init
 * @param {object} opts
 * @param {number} [opts.retries=3]   Total attempts (including the first)
 * @param {number} [opts.timeout=20000] Per-attempt timeout in ms
 * @param {number[]} [opts.backoff=[200,800,1600]] Delays between attempts
 * @param {Function} [opts.fallback]   Called when all retries fail / circuit open
 * @param {string} [opts.label]        For logging
 * @returns {Promise<Response>} Response (or whatever fallback returns)
 */
export async function resilientFetch(url, init = {}, opts = {}) {
  const {
    retries = 3,
    timeout = 20000,
    backoff = [200, 800, 1600],
    fallback = null,
    label = url,
  } = opts

  // Circuit open — fail fast and use fallback if available
  if (!breaker.canRequest()) {
    const err = new Error(`AI circuit open for ${label}`)
    err.code = 'CIRCUIT_OPEN'
    if (fallback) {
      console.warn(`[self-heal] Circuit open, using fallback for ${label}`)
      return fallback(err)
    }
    throw err
  }

  let lastError = null

  for (let attempt = 0; attempt < retries; attempt++) {
    const controller = new AbortController()
    const timer = setTimeout(() => controller.abort(), timeout)

    try {
      const authedInit = await withAiAuth({ ...init, signal: controller.signal })
      const response = await fetch(url, authedInit)
      clearTimeout(timer)

      if (response.ok) {
        aiHealth.recordSuccess()
        return response
      }

      // 4xx — client error, do not retry
      if (response.status >= 400 && response.status < 500) {
        aiHealth.recordSuccess() // backend is reachable, just a client-side issue
        return response
      }

      // 5xx — retryable
      lastError = new Error(`${label} failed: HTTP ${response.status}`)
      lastError.status = response.status
      console.warn(`[self-heal] ${label} attempt ${attempt + 1}/${retries} → ${response.status}`)
    } catch (err) {
      clearTimeout(timer)
      lastError = err
      const reason = err.name === 'AbortError' ? 'timeout' : err.message
      console.warn(`[self-heal] ${label} attempt ${attempt + 1}/${retries} failed: ${reason}`)
    }

    if (attempt < retries - 1) {
      const delay = backoff[attempt] ?? backoff[backoff.length - 1] ?? 1000
      await sleep(delay)
    }
  }

  // All attempts failed
  aiHealth.recordFailure(lastError)
  if (fallback) {
    console.warn(`[self-heal] All attempts failed for ${label}, using fallback`)
    return fallback(lastError)
  }
  throw lastError
}

/**
 * Convenience: resilient POST JSON helper that returns parsed JSON or fallback.
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

  // If fallback was used, it returned a value directly (not a Response)
  if (!(response instanceof Response)) return response

  if (!response.ok) {
    const text = await response.text().catch(() => '')
    const err = new Error(`${opts.label || url} failed: HTTP ${response.status} ${text}`)
    err.status = response.status
    if (response.status >= 400 && response.status < 500 && opts.fallback) {
      return opts.fallback(err)
    }
    throw err
  }

  return response.json()
}

export { STATUS as AI_STATUS }
