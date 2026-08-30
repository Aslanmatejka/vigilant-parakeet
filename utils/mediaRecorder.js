/**
 * Cross-browser MediaRecorder helpers.
 * Safari (especially iOS) often lacks webm — prefer mp4 when needed.
 */

const MIME_CANDIDATES = [
  'audio/webm;codecs=opus',
  'audio/webm',
  'audio/mp4',
  'audio/ogg;codecs=opus',
]

/**
 * Pick the first mime type this browser can record.
 * @returns {string} mime type or '' when none advertised
 */
export function pickMediaRecorderMimeType() {
  if (typeof MediaRecorder === 'undefined' || !MediaRecorder.isTypeSupported) {
    return ''
  }
  return MIME_CANDIDATES.find((t) => MediaRecorder.isTypeSupported(t)) || ''
}

/**
 * Create a MediaRecorder with a Safari-safe mime when available.
 * @param {MediaStream} stream
 * @returns {MediaRecorder}
 */
export function createMediaRecorder(stream) {
  const mimeType = pickMediaRecorderMimeType()
  return mimeType
    ? new MediaRecorder(stream, { mimeType })
    : new MediaRecorder(stream)
}
