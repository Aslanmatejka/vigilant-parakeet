/**
 * Validate post-login redirect targets — internal paths only (no open redirects).
 */
export function safeInternalRedirect(path, fallback = '/') {
  if (!path || typeof path !== 'string') return fallback;
  const trimmed = path.trim();
  if (!trimmed.startsWith('/') || trimmed.startsWith('//')) return fallback;
  if (/^[a-zA-Z][a-zA-Z\d+\-.]*:/.test(trimmed)) return fallback;
  return trimmed;
}

export default safeInternalRedirect;
