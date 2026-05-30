/**
 * Normalize backend tool_results into a consistent { tool, ok, summary, result } shape.
 *
 * The backend may emit either:
 *   - New format: { tool, ok, summary, result: { ...full handler payload } }
 *   - Legacy flat: { tool, ok, summary, success, title, listings, ... }
 */
export function normalizeToolResults(raw) {
  if (!Array.isArray(raw)) return []

  const META = new Set(['tool', 'ok', 'summary', 'result'])

  return raw.map((entry) => {
    if (!entry || !entry.tool) return entry

    if (entry.result && typeof entry.result === 'object') {
      return entry
    }

    const result = {}
    for (const [key, value] of Object.entries(entry)) {
      if (!META.has(key) && value !== undefined) {
        result[key] = value
      }
    }

    if (result.success === undefined && result.created !== undefined) {
      result.success = !!result.created
    } else if (result.success === undefined && entry.ok !== undefined) {
      result.success = !!entry.ok && !result.error
    }

    // search_food_near_user returns `results`; UI expects `listings`
    if (!result.listings && Array.isArray(result.results)) {
      result.listings = result.results
    }

    return { ...entry, result }
  })
}

export default normalizeToolResults
