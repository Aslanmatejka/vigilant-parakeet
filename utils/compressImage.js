/**
 * Downscale + JPEG-compress an image File/Blob for upload.
 * Phone photos are often 5–12 MB; vision and storage APIs need something smaller.
 *
 * @param {File|Blob} file
 * @param {{ maxEdge?: number, quality?: number, maxBytes?: number }} [opts]
 * @returns {Promise<File>}
 */
export async function compressImage(file, opts = {}) {
  const maxEdge = opts.maxEdge ?? 1600
  const quality = opts.quality ?? 0.82
  const maxBytes = opts.maxBytes ?? 2.5 * 1024 * 1024

  if (!file || !(file instanceof Blob)) return file
  if (!String(file.type || '').startsWith('image/')) return file
  // Already small enough — skip work (and preserve original format).
  if (file.size <= maxBytes && file.size <= 900 * 1024) return file

  let bitmap
  try {
    bitmap = await createImageBitmap(file)
  } catch {
    return file
  }

  const scale = Math.min(1, maxEdge / Math.max(bitmap.width, bitmap.height))
  const width = Math.max(1, Math.round(bitmap.width * scale))
  const height = Math.max(1, Math.round(bitmap.height * scale))

  const canvas = document.createElement('canvas')
  canvas.width = width
  canvas.height = height
  const ctx = canvas.getContext('2d')
  if (!ctx) {
    bitmap.close?.()
    return file
  }
  ctx.drawImage(bitmap, 0, 0, width, height)
  bitmap.close?.()

  const blob = await new Promise((resolve) => {
    canvas.toBlob((b) => resolve(b), 'image/jpeg', quality)
  })
  if (!blob) return file

  const baseName = (file.name || 'photo.jpg').replace(/\.[^.]+$/, '') || 'photo'
  const out = new File([blob], `${baseName}.jpg`, { type: 'image/jpeg', lastModified: Date.now() })

  // If still huge (rare), try a second pass at lower quality.
  if (out.size > maxBytes && quality > 0.55) {
    return compressImage(out, { maxEdge: Math.min(maxEdge, 1280), quality: 0.65, maxBytes })
  }
  return out
}
