import supabase from './supabaseClient'
import {
  buildAccessibilityProfilePayload,
  mergeAccessibilitySettings,
} from './accessibilityStorage'

const PROFILE_KEY = 'accessibility'

/**
 * Load saved accessibility profile for an authenticated user.
 * @param {string} userId
 * @returns {Promise<import('./accessibilityStorage').AccessibilitySettings|null>}
 */
export async function loadAccessibilityProfile(userId) {
  if (!userId) return null
  try {
    const { data, error } = await supabase
      .from('user_preferences')
      .select('preferences')
      .eq('user_id', userId)
      .maybeSingle()

    if (error) {
      console.warn('[a11y profile] load failed:', error.message)
      return null
    }

    const stored = data?.preferences?.[PROFILE_KEY]
    if (!stored || typeof stored !== 'object') return null
    return mergeAccessibilitySettings(stored)
  } catch (err) {
    console.warn('[a11y profile] load error:', err)
    return null
  }
}

/**
 * Persist accessibility settings to user_preferences (merge into JSONB).
 * @param {string} userId
 * @param {import('./accessibilityStorage').AccessibilitySettings} settings
 */
export async function saveAccessibilityProfile(userId, settings) {
  if (!userId || !settings) return

  const payload = buildAccessibilityProfilePayload(settings)

  try {
    const { data: existing, error: readErr } = await supabase
      .from('user_preferences')
      .select('id, preferences')
      .eq('user_id', userId)
      .maybeSingle()

    if (readErr) {
      console.warn('[a11y profile] read before save failed:', readErr.message)
      return
    }

    const mergedPrefs = {
      ...(existing?.preferences || {}),
      [PROFILE_KEY]: payload,
    }

    if (existing?.id) {
      const { error } = await supabase
        .from('user_preferences')
        .update({ preferences: mergedPrefs })
        .eq('id', existing.id)
      if (error) console.warn('[a11y profile] update failed:', error.message)
      return
    }

    const { error } = await supabase
      .from('user_preferences')
      .insert({ user_id: userId, preferences: mergedPrefs })
    if (error) console.warn('[a11y profile] insert failed:', error.message)
  } catch (err) {
    console.warn('[a11y profile] save error:', err)
  }
}

export { buildAccessibilityProfilePayload }
