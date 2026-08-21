/**
 * Human support escalation — tracks guide/AI failures and opens support chat.
 */

const STORAGE_KEY = 'nouri.guide.failures.v1'
const FAILURE_THRESHOLD = 3

/** @returns {number} */
export function getGuideFailureCount() {
  if (typeof sessionStorage === 'undefined') return 0
  try {
    const raw = sessionStorage.getItem(STORAGE_KEY)
    return raw ? Math.max(0, parseInt(raw, 10) || 0) : 0
  } catch {
    return 0
  }
}

function setGuideFailureCount(count) {
  if (typeof sessionStorage === 'undefined') return
  try {
    sessionStorage.setItem(STORAGE_KEY, String(Math.max(0, count)))
  } catch { /* private mode */ }
}

/** Reset after a successful interaction. */
export function recordGuideSuccess() {
  setGuideFailureCount(0)
}

/** Clear failure counter (e.g. when the user clears the chat). */
export function clearGuideFailures() {
  setGuideFailureCount(0)
}

/**
 * Increment failure counter (chat error, repeated validation, stuck field).
 * @param {string} [reason]
 */
export function recordGuideFailure(reason = '') {
  const next = getGuideFailureCount() + 1
  setGuideFailureCount(next)
  if (typeof window !== 'undefined' && next >= FAILURE_THRESHOLD) {
    window.dispatchEvent(new CustomEvent('nouri:handoff-suggested', {
      detail: { reason, count: next },
    }))
  }
  return next
}

export function shouldSuggestHumanHandoff() {
  return getGuideFailureCount() >= FAILURE_THRESHOLD
}

/**
 * Open the human support widget with optional prefilled message.
 * @param {{ message?: string, reason?: string }} [opts]
 */
export function openHumanSupport(opts = {}) {
  const count = getGuideFailureCount()
  const defaultMsg = count >= FAILURE_THRESHOLD
    ? 'Nouri could not help me after several tries. I need a person to assist.'
    : 'I need help from a person with DoGoods.'

  if (typeof window !== 'undefined') {
    window.dispatchEvent(new CustomEvent('nouri:open-human-support', {
      detail: {
        message: opts.message || defaultMsg,
        reason: opts.reason || '',
      },
    }))
  }
}

export const HUMAN_HANDOFF_THRESHOLD = FAILURE_THRESHOLD
