/**
 * AI Agent — recipe suggestions via the shared aiChatService.
 * Replaces the duplicate circuit-breaker / fetch logic that lived here
 * previously; all resilience + auth now flows through one path.
 */
import aiChatService from './services/aiChatService.js'

/**
 * Get recipe suggestions for given ingredients.
 * Used by FoodCard component via useAI() hook.
 *
 * Return shape (always resolves on non-error paths):
 *   { recipes: RecipeView[], headline?: string, requiresAuth?: boolean }
 *
 * "No recipes available" is NOT an error — callers render an empty state
 * with the optional headline. Only true failures (network, backend down,
 * malformed response) throw.
 *
 * @param {string[]} ingredients
 * @param {object} [opts]
 * @param {string|null} [opts.userId]   — required for the backend; missing
 *                                         userId short-circuits with a
 *                                         requiresAuth payload (never hits
 *                                         the network, never burns the
 *                                         per-IP rate-limit bucket).
 * @param {AbortSignal} [opts.signal]   — caller-controlled cancellation; on
 *                                         abort, the in-flight fetch is
 *                                         dropped without state updates.
 */
async function getRecipeSuggestions(ingredients, { userId, signal } = {}) {
  if (!Array.isArray(ingredients) || ingredients.length === 0) {
    throw new Error('Invalid ingredients format. Must provide a non-empty array.')
  }

  // The backend requires a real authenticated user_id (Pydantic rejects
  // empty / non-UUID values with 422, and the auth check rejects mismatched
  // tokens). Calling without a user is guaranteed to fail server-side, so
  // short-circuit with a gentle empty-state instead of burning a request.
  if (!userId || typeof userId !== 'string') {
    return {
      recipes: [],
      headline: 'Sign in to get personalized recipe suggestions.',
      requiresAuth: true,
    }
  }

  try {
    const result = await aiChatService.recipes(userId, {
      ingredients,
      useClaimed: false,
      lowResource: true,
      maxRecipes: 3,
      notes: 'Suggest recipes that reduce food waste.',
      signal,
    })

    // Empty recipe list is a legitimate outcome (unusual ingredients, the
    // model couldn't think of anything). Return the friendly headline as
    // an empty-state payload instead of throwing — UI renders it calmly.
    if (!result?.recipes?.length) {
      return {
        recipes: [],
        headline: result?.headline || 'No recipes available for these ingredients.',
      }
    }

    return {
      recipes: result.recipes.map((r) => {
        const rawIngredients = Array.isArray(r?.ingredients)
          ? r.ingredients
              .map((i) => (typeof i === 'string' ? i : (i?.name || i?.item || i?.ingredient || '')))
              .filter(Boolean)
          : []
        const steps = Array.isArray(r?.steps)
          ? r.steps
              .map((s) => (typeof s === 'string' ? s : (s?.text || s?.instruction || '')))
              .filter(Boolean)
          : []
        const title = String(r?.title || r?.name || 'Recipe').trim() || 'Recipe'
        return {
          name: title,
          // Empty array means "the model didn't list ingredients for this
          // recipe" — never substitute the user's input list, which would
          // falsely claim every recipe uses every ingredient they provided.
          ingredients: rawIngredients,
          instructions: steps.length ? steps.join('\n') : (r?.summary || ''),
          prepTime: typeof r?.time_minutes === 'number' ? `${r.time_minutes} min` : 'N/A',
          cookTime: 'N/A',
          difficulty: (typeof r?.difficulty === 'string' && r.difficulty.trim()) || 'easy',
          servings: typeof r?.servings === 'number' && r.servings > 0 ? r.servings : 2,
        }
      }),
      headline: result.headline || '',
    }
  } catch (error) {
    // Caller cancelled — propagate quietly without console noise.
    if (error?.name === 'AbortError') throw error
    console.error('Recipe suggestion error:', error)
    if (error?.aiError) throw error
    throw new Error(
      error?.message || 'Unable to generate recipe suggestions. Please try again.',
      { cause: error },
    )
  }
}

export { getRecipeSuggestions }

