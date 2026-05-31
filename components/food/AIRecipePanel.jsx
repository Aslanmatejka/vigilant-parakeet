import React from 'react';
import PropTypes from 'prop-types';
import { useAuthContext } from '../../utils/AuthContext';
import aiChatService from '../../utils/services/aiChatService';
import { AIThinkingPanel } from '../common/AIThinking.jsx';

/**
 * GPT-4o-powered recipe generator.
 *
 * - Defaults to "use my claimed items" so recipes are anchored to food the user
 *   has actually picked up (or is about to pick up).
 * - Household-aware (servings) and low-resource (time / equipment / cost caps).
 * - Allows ad-hoc ingredient lists and dietary overrides.
 */
export default function AIRecipePanel({ className = '' }) {
    const { user, isAuthenticated } = useAuthContext();

    const [ingredientsText, setIngredientsText] = React.useState('');
    const [useClaimed, setUseClaimed] = React.useState(true);
    const [lowResource, setLowResource] = React.useState(true);
    const [householdSize, setHouseholdSize] = React.useState(2);
    const [maxRecipes, setMaxRecipes] = React.useState(3);
    const [dietaryText, setDietaryText] = React.useState('');
    const [notes, setNotes] = React.useState('');

    const [loading, setLoading] = React.useState(false);
    const [error, setError] = React.useState(null);
    const [errorMeta, setErrorMeta] = React.useState(null);
    const [result, setResult] = React.useState(null);
    const [expandedIdx, setExpandedIdx] = React.useState(null);

    const handleGenerate = async () => {
        if (!isAuthenticated || !user?.id) {
            setError('Please sign in to generate recipes.');
            setErrorMeta(null);
            return;
        }
        setLoading(true);
        setError(null);
        setErrorMeta(null);
        try {
            const explicit = ingredientsText
                .split(/[,\n]/)
                .map((s) => s.trim())
                .filter(Boolean);
            const dietary = dietaryText
                .split(/[,\n]/)
                .map((s) => s.trim())
                .filter(Boolean);

            const res = await aiChatService.recipes(user.id, {
                ingredients: explicit.length ? explicit : null,
                useClaimed: explicit.length ? false : useClaimed,
                lowResource,
                householdSize: Number(householdSize) || 2,
                maxRecipes: Number(maxRecipes) || 3,
                dietaryOverrides: dietary.length ? dietary : null,
                notes: notes.trim() || null,
            });
            setResult(res);
            setExpandedIdx(res.recipes?.length ? 0 : null);
        } catch (err) {
            const aiError = err?.aiError || null;
            setError(aiError?.message || err?.message || 'Failed to generate recipes.');
            setErrorMeta(aiError ? {
                code: aiError.code || aiError.errorCode || null,
                retryable: !!aiError.retryable,
                requestId: aiError.requestId || err?.requestId || null,
            } : null);
        } finally {
            setLoading(false);
        }
    };

    return (
        <section
            className={`bg-white rounded-2xl shadow-md border border-gray-100 overflow-hidden ${className}`}
            aria-label="AI recipe generator"
        >
            <header className="px-5 py-3 border-b border-gray-100 bg-gradient-to-r from-amber-50 to-white">
                <div className="flex items-center gap-2 text-gray-800">
                    <i className="fas fa-utensils text-amber-600" aria-hidden="true" />
                    <h2 className="text-sm font-semibold">AI recipe ideas</h2>
                    <span className="ml-2 text-xs text-gray-500">household-aware · low-resource</span>
                </div>
            </header>

            <div className="px-5 py-4 space-y-4">
                {/* Inputs */}
                <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                    <label className="block text-xs text-gray-600">
                        Ingredients (comma or newline)
                        <textarea
                            value={ingredientsText}
                            onChange={(e) => setIngredientsText(e.target.value)}
                            rows={2}
                            placeholder={useClaimed ? 'Leave blank to use your claimed items' : 'e.g. tomatoes, bread, lentils'}
                            className="mt-1 w-full rounded-md border border-gray-200 p-2 text-sm focus:border-amber-500 focus:ring focus:ring-amber-100"
                        />
                    </label>
                    <label className="block text-xs text-gray-600">
                        Dietary restrictions (optional)
                        <textarea
                            value={dietaryText}
                            onChange={(e) => setDietaryText(e.target.value)}
                            rows={2}
                            placeholder="e.g. vegetarian, halal, gluten-free"
                            className="mt-1 w-full rounded-md border border-gray-200 p-2 text-sm focus:border-amber-500 focus:ring focus:ring-amber-100"
                        />
                    </label>
                </div>

                <div className="flex flex-wrap items-end gap-3 text-xs text-gray-700">
                    <label className="inline-flex items-center gap-2">
                        <span>Household</span>
                        <input
                            type="number"
                            min={1}
                            max={20}
                            value={householdSize}
                            onChange={(e) => setHouseholdSize(e.target.value)}
                            className="w-16 rounded border border-gray-200 px-2 py-1 text-sm"
                        />
                    </label>
                    <label className="inline-flex items-center gap-2">
                        <span>Recipes</span>
                        <select
                            value={maxRecipes}
                            onChange={(e) => setMaxRecipes(Number(e.target.value))}
                            className="rounded border border-gray-200 px-2 py-1 text-sm"
                        >
                            <option value={1}>1</option>
                            <option value={2}>2</option>
                            <option value={3}>3</option>
                            <option value={4}>4</option>
                            <option value={5}>5</option>
                        </select>
                    </label>
                    <label className="inline-flex items-center gap-2 cursor-pointer">
                        <input
                            type="checkbox"
                            checked={useClaimed}
                            onChange={(e) => setUseClaimed(e.target.checked)}
                            className="rounded text-amber-600 focus:ring-amber-500"
                        />
                        <span>Use my claimed items</span>
                    </label>
                    <label className="inline-flex items-center gap-2 cursor-pointer">
                        <input
                            type="checkbox"
                            checked={lowResource}
                            onChange={(e) => setLowResource(e.target.checked)}
                            className="rounded text-amber-600 focus:ring-amber-500"
                        />
                        <span>Low-resource mode</span>
                    </label>
                </div>

                <label className="block text-xs text-gray-600">
                    Notes for the chef (optional)
                    <input
                        value={notes}
                        onChange={(e) => setNotes(e.target.value)}
                        placeholder="e.g. no oven, kids-friendly, need leftovers"
                        className="mt-1 w-full rounded-md border border-gray-200 p-2 text-sm focus:border-amber-500 focus:ring focus:ring-amber-100"
                    />
                </label>

                <div className="flex items-center justify-between gap-3">
                    <button
                        type="button"
                        onClick={handleGenerate}
                        disabled={loading || !isAuthenticated}
                        className="inline-flex items-center gap-2 rounded-md bg-amber-600 px-4 py-2 text-sm font-medium text-white hover:bg-amber-700 disabled:bg-gray-300"
                    >
                        <i className={`fas ${loading ? 'fa-spinner animate-spin' : 'fa-wand-magic-sparkles'}`} aria-hidden="true" />
                        {loading ? 'Generating…' : 'Generate recipes'}
                    </button>
                    {result?.headline && !loading && (
                        <p className="text-xs text-gray-600 truncate">{result.headline}</p>
                    )}
                </div>

                {error && (
                    <div className="rounded-md border border-red-100 bg-red-50 px-3 py-2 text-xs text-red-700">
                        <div className="flex items-start justify-between gap-2">
                            <div className="min-w-0">
                                <p className="font-medium leading-snug">{error}</p>
                                {(errorMeta?.code || errorMeta?.requestId) && (
                                    <p className="mt-0.5 text-[10px] text-red-500/80 truncate">
                                        {errorMeta?.code ? <span className="uppercase">{errorMeta.code}</span> : null}
                                        {errorMeta?.code && errorMeta?.requestId ? ' · ' : null}
                                        {errorMeta?.requestId ? <span>req {errorMeta.requestId}</span> : null}
                                    </p>
                                )}
                            </div>
                            {(errorMeta?.retryable ?? true) && (
                                <button
                                    type="button"
                                    onClick={handleGenerate}
                                    disabled={loading}
                                    className="shrink-0 rounded-md bg-red-600 px-2.5 py-1 text-[11px] font-medium text-white hover:bg-red-700 disabled:bg-red-300"
                                >
                                    Retry
                                </button>
                            )}
                        </div>
                    </div>
                )}
                {!isAuthenticated && (
                    <p className="text-xs text-gray-500">Sign in to anchor recipes to your claimed pickups.</p>
                )}

                {loading && (
                    <AIThinkingPanel
                        title="AI recipe ideas"
                        stages={[
                            { icon: 'basket-shopping', label: 'Reading your claimed ingredients' },
                            { icon: 'leaf', label: 'Matching dietary preferences' },
                            { icon: 'utensils', label: 'Designing balanced meals' },
                            { icon: 'wand-magic-sparkles', label: 'Plating your recipes' },
                        ]}
                    />
                )}

                {/* Results */}
                {!loading && result?.recipes?.length > 0 && (
                    <ul className="space-y-3 pt-2">
                        {result.recipes.map((r, idx) => {
                            const open = expandedIdx === idx;
                            return (
                                <li
                                    key={`${r.title}-${idx}`}
                                    className="rounded-lg border border-gray-100 bg-white"
                                >
                                    <button
                                        type="button"
                                        onClick={() => setExpandedIdx(open ? null : idx)}
                                        className="flex w-full items-start justify-between gap-3 px-4 py-3 text-left"
                                        aria-expanded={open}
                                    >
                                        <div className="min-w-0">
                                            <div className="flex items-center gap-2">
                                                <h3 className="text-sm font-semibold text-gray-900 truncate">{r.title}</h3>
                                                <span className="rounded-full bg-amber-100 px-2 py-0.5 text-[10px] font-medium text-amber-800">
                                                    {r.cost_tier} cost
                                                </span>
                                                <span className="rounded-full bg-gray-100 px-2 py-0.5 text-[10px] font-medium text-gray-700">
                                                    {r.difficulty}
                                                </span>
                                            </div>
                                            {r.summary && (
                                                <p className="mt-1 text-xs text-gray-600 line-clamp-2">{r.summary}</p>
                                            )}
                                            <div className="mt-1 flex flex-wrap items-center gap-x-3 gap-y-1 text-[11px] text-gray-600">
                                                {r.servings && (
                                                    <span><i className="fas fa-user-group mr-1 text-gray-400" aria-hidden="true" />{r.servings} servings</span>
                                                )}
                                                {r.time_minutes && (
                                                    <span><i className="fas fa-clock mr-1 text-gray-400" aria-hidden="true" />{r.time_minutes} min</span>
                                                )}
                                                {r.dietary_tags?.slice(0, 3).map((t) => (
                                                    <span key={t} className="rounded-full bg-emerald-50 px-2 py-0.5 text-[10px] text-emerald-700 ring-1 ring-emerald-200">
                                                        {t}
                                                    </span>
                                                ))}
                                            </div>
                                        </div>
                                        <i className={`fas fa-chevron-${open ? 'up' : 'down'} text-gray-400 mt-1`} aria-hidden="true" />
                                    </button>

                                    {open && (
                                        <div className="border-t border-gray-100 px-4 py-3 text-sm text-gray-700 space-y-3">
                                            <div>
                                                <h4 className="text-xs font-semibold uppercase tracking-wide text-gray-500">Ingredients</h4>
                                                <ul className="mt-1 list-disc pl-5 space-y-0.5 text-sm">
                                                    {r.ingredients.map((ing, i) => (
                                                        <li key={i} className={ing.optional ? 'text-gray-500' : ''}>
                                                            {ing.quantity ? <span className="text-gray-500">{ing.quantity} </span> : null}
                                                            {ing.name}
                                                            {ing.optional && <span className="ml-1 text-[10px] uppercase tracking-wide text-gray-400">optional</span>}
                                                        </li>
                                                    ))}
                                                </ul>
                                            </div>
                                            <div>
                                                <h4 className="text-xs font-semibold uppercase tracking-wide text-gray-500">Steps</h4>
                                                <ol className="mt-1 list-decimal pl-5 space-y-1 text-sm">
                                                    {r.steps.map((s, i) => (
                                                        <li key={i}>{s}</li>
                                                    ))}
                                                </ol>
                                            </div>
                                            {r.equipment?.length > 0 && (
                                                <p className="text-xs text-gray-500">
                                                    <span className="font-semibold uppercase tracking-wide">Equipment:</span>{' '}
                                                    {r.equipment.join(', ')}
                                                </p>
                                            )}
                                            {r.tips && (
                                                <p className="rounded-md bg-amber-50 px-3 py-2 text-xs text-amber-900 ring-1 ring-amber-200">
                                                    <i className="fas fa-lightbulb mr-1" aria-hidden="true" />
                                                    {r.tips}
                                                </p>
                                            )}
                                        </div>
                                    )}
                                </li>
                            );
                        })}
                    </ul>
                )}

                {result && result.recipes?.length === 0 && !loading && (
                    <p className="text-xs text-gray-500">{result.headline || 'No recipes generated.'}</p>
                )}
            </div>
        </section>
    );
}

AIRecipePanel.propTypes = {
    className: PropTypes.string,
};
