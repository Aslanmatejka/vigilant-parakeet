import React from 'react';
import PropTypes from 'prop-types';
import { DIETARY_OPTIONS } from '../profile/DietaryPreferences';

function FoodDietaryTags({ 
    selectedTags = [],
    selectedAllergens = [],
    ingredients = '',
    onChange,
    readOnly = false,
    compact = false,
    food = null
}) {
    // If food object is passed and compact mode, use it directly for display
    const displayTags = food?.dietary_tags || selectedTags;
    const displayAllergens = food?.allergen_info || food?.allergens || selectedAllergens;
    const displayIngredients = food?.ingredients || ingredients;

    const [dietaryTags, setDietaryTags] = React.useState(selectedTags);
    const [allergens, setAllergens] = React.useState(selectedAllergens);
    const [ingredientsText, setIngredientsText] = React.useState(ingredients);

    const commonDietaryTags = [
        { value: 'vegetarian', label: '🥗 Vegetarian' },
        { value: 'vegan', label: '🌱 Vegan' },
        { value: 'gluten-free', label: '🌾 Gluten-Free' },
        { value: 'dairy-free', label: '🥛 Dairy-Free' },
        { value: 'halal', label: '☪️ Halal' },
        { value: 'kosher', label: '✡️ Kosher' },
        { value: 'organic', label: '🌿 Organic' },
        { value: 'non-gmo', label: '🧬 Non-GMO' },
        { value: 'sugar-free', label: '🚫 Sugar-Free' },
        { value: 'low-sodium', label: '🧂 Low Sodium' }
    ];

    // Hooks must run before any early return (Rules of Hooks).
    React.useEffect(() => {
        if (compact || !onChange) return;
        onChange({
            dietary_tags: dietaryTags,
            allergens: allergens,
            ingredients: ingredientsText
        });
    }, [compact, onChange, dietaryTags, allergens, ingredientsText]);

    // Compact display mode - only show selected tags/allergens
    if (compact) {
        const hasAnyInfo = displayTags.length > 0 || displayAllergens.length > 0 || displayIngredients;
        
        if (!hasAnyInfo) {
            return null;
        }

        return (
            <div className="space-y-2 text-sm">
                {displayTags.length > 0 && (
                    <div className="flex flex-wrap gap-1">
                        {displayTags.map(tag => {
                            const tagInfo = commonDietaryTags.find(t => t.value === tag);
                            return (
                                <span 
                                    key={tag}
                                    className="inline-flex items-center px-2 py-1 rounded-full text-xs font-medium bg-primary-100 text-primary-800"
                                >
                                    {tagInfo?.label || tag}
                                </span>
                            );
                        })}
                    </div>
                )}
                {displayAllergens.length > 0 && (
                    <div className="flex flex-wrap gap-1">
                        <span className="inline-flex items-center px-2 py-1 rounded-full text-xs font-medium bg-red-100 text-red-800">
                            ⚠ Contains: {displayAllergens.join(', ')}
                        </span>
                    </div>
                )}
                {displayIngredients && (
                    <div className="text-xs text-gray-600">
                        <span className="font-medium">Ingredients:</span> {displayIngredients}
                    </div>
                )}
            </div>
        );
    }

    const toggleTag = (value) => {
        if (readOnly) return;
        
        if (dietaryTags.includes(value)) {
            setDietaryTags(dietaryTags.filter(tag => tag !== value));
        } else {
            setDietaryTags([...dietaryTags, value]);
        }
    };

    const toggleAllergen = (value) => {
        if (readOnly) return;
        
        if (allergens.includes(value)) {
            setAllergens(allergens.filter(a => a !== value));
        } else {
            setAllergens([...allergens, value]);
        }
    };

    return (
        <div className="space-y-6">
            {/* Dietary Tags */}
            <div>
                <label className="block text-sm font-medium text-gray-700 mb-2">
                    Dietary Tags (Select all that apply)
                </label>
                <p className="text-xs text-gray-500 mb-3">
                    Help recipients find food that matches their dietary needs
                </p>
                <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-5 gap-2">
                    {commonDietaryTags.map(tag => (
                        <button
                            key={tag.value}
                            type="button"
                            onClick={() => toggleTag(tag.value)}
                            disabled={readOnly}
                            className={`px-3 py-2 text-sm rounded-md border-2 transition-all ${
                                dietaryTags.includes(tag.value)
                                    ? 'border-primary-500 bg-primary-50 text-primary-700'
                                    : 'border-gray-200 hover:border-primary-300'
                            } ${readOnly ? 'cursor-default' : 'cursor-pointer'}`}
                        >
                            {tag.label}
                        </button>
                    ))}
                </div>
            </div>

            {/* Allergen Information */}
            <div>
                <label className="block text-sm font-medium text-gray-700 mb-2">
                    <svg className="inline w-5 h-5 text-orange-500 mr-1" fill="currentColor" viewBox="0 0 20 20">
                        <path fillRule="evenodd" d="M8.257 3.099c.765-1.36 2.722-1.36 3.486 0l5.58 9.92c.75 1.334-.213 2.98-1.742 2.98H4.42c-1.53 0-2.493-1.646-1.743-2.98l5.58-9.92zM11 13a1 1 0 11-2 0 1 1 0 012 0zm-1-8a1 1 0 00-1 1v3a1 1 0 002 0V6a1 1 0 00-1-1z" clipRule="evenodd" />
                    </svg>
                    Allergen Warning (Check all that apply)
                </label>
                <p className="text-xs text-red-600 mb-3">
                    Important: Select all allergens present in this food
                </p>
                <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-2">
                    {DIETARY_OPTIONS.allergies.map(allergen => (
                        <button
                            key={allergen.value}
                            type="button"
                            onClick={() => toggleAllergen(allergen.value)}
                            disabled={readOnly}
                            className={`px-3 py-2 text-sm rounded-md border-2 transition-all ${
                                allergens.includes(allergen.value)
                                    ? 'border-red-500 bg-red-50 text-red-700'
                                    : 'border-gray-200 hover:border-red-300'
                            } ${readOnly ? 'cursor-default' : 'cursor-pointer'}`}
                        >
                            <span className="mr-1">{allergen.icon}</span>
                            {allergen.label.replace(/^[🥜🌰🥛🥚🫘🌾🦐🐟🌭🥬]\s/u, '')}
                        </button>
                    ))}
                </div>
            </div>

            {/* Ingredients List */}
            <div>
                <label htmlFor="ingredients" className="block text-sm font-medium text-gray-700 mb-2">
                    Ingredients (Optional)
                </label>
                <p className="text-xs text-gray-500 mb-2">
                    List the main ingredients to help people with allergies make informed decisions
                </p>
                <textarea
                    id="ingredients"
                    value={ingredientsText}
                    onChange={(e) => setIngredientsText(e.target.value)}
                    disabled={readOnly}
                    placeholder="e.g., Flour, eggs, milk, sugar, vanilla extract, baking powder..."
                    rows="3"
                    className="w-full px-3 py-2 border border-gray-300 rounded-md focus:ring-2 focus:ring-primary-500 focus:border-primary-500 resize-none"
                />
            </div>

            {/* Summary */}
            {(dietaryTags.length > 0 || allergens.length > 0) && (
                <div className="p-4 bg-gray-50 border border-gray-200 rounded-lg">
                    <h4 className="font-semibold text-gray-900 mb-2">Food Profile Summary:</h4>
                    <div className="space-y-1 text-sm">
                        {dietaryTags.length > 0 && (
                            <div>
                                <span className="font-medium text-primary-700">✓ Suitable for:</span>
                                <span className="ml-2 text-gray-700">{dietaryTags.join(', ')}</span>
                            </div>
                        )}
                        {allergens.length > 0 && (
                            <div>
                                <span className="font-medium text-red-700">⚠ Contains allergens:</span>
                                <span className="ml-2 text-gray-700">{allergens.join(', ')}</span>
                            </div>
                        )}
                    </div>
                </div>
            )}
        </div>
    );
}

FoodDietaryTags.propTypes = {
    selectedTags: PropTypes.arrayOf(PropTypes.string),
    selectedAllergens: PropTypes.arrayOf(PropTypes.string),
    ingredients: PropTypes.string,
    onChange: PropTypes.func,
    readOnly: PropTypes.bool,
    compact: PropTypes.bool,
    food: PropTypes.object
};

export default FoodDietaryTags;
