/**
 * Stuck-field and validation-error detection for Nouri guide.
 */
import { updateGuide } from './engine'
import { recordGuideFailure } from './humanHandoff'

const STUCK_MS = 2 * 60 * 1000

let stuckTimer = null
let activeField = null
let activeFormId = null

function clearStuckTimer() {
  if (stuckTimer) {
    clearTimeout(stuckTimer)
    stuckTimer = null
  }
}

function buildStuckMessage(fieldName, label) {
  const name = label || fieldName
  return `Need help with ${name}? Take your time. Say "help" in Nouri chat, or check the hint above. You can also tap another field.`
}

/**
 * @param {string} formId
 * @param {string} fieldName
 * @param {string} [label]
 */
export function trackFieldFocus(formId, fieldName, label) {
  if (!fieldName) return
  if (activeField === fieldName && activeFormId === formId) return

  clearStuckTimer()
  activeField = fieldName
  activeFormId = formId

  stuckTimer = setTimeout(() => {
    recordGuideFailure('stuck_field')
    updateGuide({
      source: 'system',
      formId,
      fieldName,
      label: label || fieldName,
      text: buildStuckMessage(fieldName, label),
      caption: buildStuckMessage(fieldName, label),
      section: 'Need help?',
    }, { speak: true, focusField: false })
  }, STUCK_MS)
}

export function notifyFieldChanged() {
  clearStuckTimer()
}

/**
 * @param {string} formId
 * @param {string} fieldName
 * @param {string} errorMessage
 * @param {string} [label]
 */
export function reportFieldError(formId, fieldName, errorMessage, label) {
  clearStuckTimer()
  recordGuideFailure('field_error')
  const text = errorMessage
    ? `That did not work: ${errorMessage}. Fix ${label || fieldName} and try again.`
    : `Please check ${label || fieldName} and try again.`

  updateGuide({
    source: 'system',
    formId,
    fieldName,
    label: label || fieldName,
    text,
    caption: text,
    section: 'Fix this field',
  }, { speak: true, focusField: true })
}

export function resetStuckTracking() {
  clearStuckTimer()
  activeField = null
  activeFormId = null
}
