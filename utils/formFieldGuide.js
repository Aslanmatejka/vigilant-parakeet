/** Hidden description node id — linked via aria-describedby on guided fields. */
export const FORM_GUIDE_DESC_ID = 'nouri-form-guide-desc'

let lastGuidedField = null
/** @type {{ fieldName: string, guideText: string, attempts: number, timer: ReturnType<typeof setTimeout>|null } | null} */
let pendingGuide = null

function escapeFieldName(name) {
  if (typeof CSS !== 'undefined' && CSS.escape) return CSS.escape(name)
  return String(name).replace(/["\\]/g, '\\$&')
}

function mergeDescribedBy(el, guideId) {
  const prev = el.getAttribute('aria-describedby') || ''
  const ids = prev.split(/\s+/).filter(Boolean)
  if (!ids.includes(guideId)) ids.push(guideId)
  el.setAttribute('aria-describedby', ids.join(' '))
}

function restoreDescribedBy(el) {
  const saved = el.getAttribute('data-nouri-prev-describedby')
  if (saved === null) return
  if (saved) el.setAttribute('aria-describedby', saved)
  else el.removeAttribute('aria-describedby')
  el.removeAttribute('data-nouri-prev-describedby')
}

/**
 * Resolve the best element to highlight for a form field.
 * Prefer an explicit data-guide-field wrapper (whole row), then the control.
 */
export function resolveGuideTarget(fieldName) {
  if (!fieldName || typeof document === 'undefined') return null
  const key = escapeFieldName(fieldName)
  const byData = document.querySelector(`[data-guide-field="${key}"]`)
  if (byData) return byData

  const control =
    document.querySelector(`[name="${key}"]`)
    || document.querySelector(`#${key}`)
  if (!control) return null

  // Prefer the Input wrapper / labeled group so the highlight is obvious.
  const wrapper = control.closest('[data-guide-field], [data-name="input-wrapper"], .nouri-guide-target')
  return wrapper || control
}

function clearPendingGuide() {
  if (pendingGuide?.timer) clearTimeout(pendingGuide.timer)
  pendingGuide = null
}

function scheduleRetry(fieldName, guideText, scroll) {
  if (pendingGuide?.timer) clearTimeout(pendingGuide.timer)
  const attempts = (pendingGuide?.fieldName === fieldName ? pendingGuide.attempts : 0) + 1
  if (attempts > 20) {
    pendingGuide = { fieldName, guideText, attempts, timer: null }
    return
  }
  pendingGuide = {
    fieldName,
    guideText,
    attempts,
    timer: setTimeout(() => {
      guideFormField(fieldName, { guideText, scroll, _fromRetry: true })
    }, 150),
  }
}

/**
 * Scroll to a form field, highlight it, and link the guide text for screen readers.
 * Retries briefly when the field is not mounted yet (route change / Easy Mode section).
 * @param {string} fieldName - matches input `name` or `data-guide-field`
 * @param {{ guideText?: string, scroll?: boolean, _fromRetry?: boolean }} [options]
 */
export function guideFormField(fieldName, { guideText = '', scroll = true, _fromRetry = false } = {}) {
  if (!fieldName || typeof document === 'undefined') return null

  if (lastGuidedField && lastGuidedField !== fieldName) {
    clearFormFieldGuide(lastGuidedField)
  }

  const el = resolveGuideTarget(fieldName)
  if (!el) {
    scheduleRetry(fieldName, guideText, scroll)
    return null
  }

  clearPendingGuide()

  const guideEl = document.getElementById(FORM_GUIDE_DESC_ID)
  if (guideEl && guideText) {
    guideEl.textContent = guideText
  }

  const focusEl =
    el.matches('input, select, textarea, button')
      ? el
      : el.querySelector('input, select, textarea, button')

  if (focusEl) {
    if (!focusEl.hasAttribute('data-nouri-prev-describedby')) {
      focusEl.setAttribute(
        'data-nouri-prev-describedby',
        focusEl.getAttribute('aria-describedby') || '',
      )
    }
    mergeDescribedBy(focusEl, FORM_GUIDE_DESC_ID)
  }

  el.classList.add('nouri-field-guided')
  lastGuidedField = fieldName

  if (scroll) {
    el.scrollIntoView({
      behavior: 'auto',
      block: 'center',
    })
  }

  return el
}

/** Re-run highlight for a pending field (call when a form mounts / section opens). */
export function reapplyPendingGuideField() {
  if (!pendingGuide?.fieldName && !lastGuidedField) return null
  const fieldName = pendingGuide?.fieldName || lastGuidedField
  const guideText = pendingGuide?.guideText || ''
  return guideFormField(fieldName, { guideText, scroll: true })
}

/** @param {string} [fieldName] */
export function clearFormFieldGuide(fieldName) {
  const target = fieldName || lastGuidedField
  if (!target || typeof document === 'undefined') return

  if (pendingGuide?.fieldName === target) clearPendingGuide()

  const el = resolveGuideTarget(target)
  if (el) {
    el.classList.remove('nouri-field-guided')
    const focusEl =
      el.matches('input, select, textarea, button')
        ? el
        : el.querySelector('input, select, textarea, button')
    if (focusEl) restoreDescribedBy(focusEl)
  }

  // Also clear legacy class on the raw control if wrapper differed.
  document.querySelectorAll('.nouri-field-guided').forEach((node) => {
    const name = node.getAttribute('name') || node.getAttribute('data-guide-field')
    if (name === target) node.classList.remove('nouri-field-guided')
  })

  if (lastGuidedField === target) lastGuidedField = null
}

export function clearAllFormFieldGuides() {
  clearPendingGuide()
  if (typeof document !== 'undefined') {
    document.querySelectorAll('.nouri-field-guided').forEach((node) => {
      node.classList.remove('nouri-field-guided')
    })
  }
  if (lastGuidedField) {
    const t = lastGuidedField
    lastGuidedField = null
    clearFormFieldGuide(t)
  }
}
