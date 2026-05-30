/**
 * AI Agent — recipe suggestions via the shared aiChatService.
 * Replaces the duplicate circuit-breaker / fetch logic that lived here
 * previously; all resilience + auth now flows through one path.
 */
import aiChatService from './services/aiChatService.js'

/**
 * Get recipe suggestions for given ingredients.
 * Used by FoodCard component via useAI() hook.
 */
async function getRecipeSuggestions(ingredients, { userId } = {}) {
  if (!Array.isArray(ingredients) || ingredients.length === 0) {
    throw new Error('Invalid ingredients format. Must provide a non-empty array.')
  }

  try {
    const result = await aiChatService.recipes(
      userId || '00000000-0000-0000-0000-000000000000',
      {
        ingredients,
        useClaimed: false,
        lowResource: true,
        maxRecipes: 3,
        notes: 'Suggest recipes that reduce food waste.',
      }
    )

    if (result.degraded || !result.recipes?.length) {
      throw new Error(result.headline || 'Recipe AI unavailable')
    }

    return {
      recipes: result.recipes.map((r) => ({
        name: r.title || r.name || 'Recipe',
        ingredients: r.ingredients?.map((i) => (typeof i === 'string' ? i : i.name)).filter(Boolean)
          || ingredients,
        instructions: Array.isArray(r.steps) ? r.steps.join('\n') : (r.summary || ''),
        prepTime: r.time_minutes ? `${r.time_minutes} min` : 'N/A',
        cookTime: 'N/A',
        difficulty: r.difficulty || 'easy',
        servings: r.servings || 2,
      })),
    }
  } catch (error) {
    console.error('Recipe suggestion error:', error)
    if (error?.aiError) throw error
    throw new Error(error?.message || 'Unable to generate recipe suggestions. Please try again.')
  }
}

export { getRecipeSuggestions }
