/**
 * Motion / scroll helpers — keep UI snappy and respect reduced-motion.
 */

export function prefersReducedMotion() {
  if (typeof window === 'undefined' || typeof window.matchMedia !== 'function') {
    return false
  }
  try {
    return window.matchMedia('(prefers-reduced-motion: reduce)').matches
  } catch {
    return false
  }
}

/** Instant by default; optional smooth only when motion is allowed and asked for. */
export function scrollBehavior(preferSmooth = false) {
  if (!preferSmooth || prefersReducedMotion()) return 'auto'
  return 'smooth'
}

export function scrollIntoView(el, { smooth = false, block = 'nearest', inline = 'nearest' } = {}) {
  if (!el || typeof el.scrollIntoView !== 'function') return
  el.scrollIntoView({ behavior: scrollBehavior(smooth), block, inline })
}

export function scrollWindowTo({ top = 0, left = 0, smooth = false } = {}) {
  if (typeof window === 'undefined') return
  window.scrollTo({ top, left, behavior: scrollBehavior(smooth) })
}
