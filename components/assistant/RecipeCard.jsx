import React from 'react';
import PropTypes from 'prop-types';
import { reportError } from '../../utils/helpers';

function RecipeCard({ recipe }) {
    if (!recipe) {
        reportError(new Error('Recipe data is required'));
        return null;
    }

    const { 
        name, 
        ingredients = [], 
        instructions = '', 
        prepTime, 
        cookTime, 
        difficulty, 
        servings 
    } = recipe;

    if (!name || !ingredients.length || !instructions) {
        reportError(new Error('Recipe must have a name, ingredients, and instructions'));
        return null;
    }
    
    return (
        <article 
            data-name="recipe-card" 
            className="bg-white rounded-lg shadow-sm overflow-hidden border border-gray-200"
            aria-labelledby="recipe-title"
        >
            <div className="p-4">
                <h3 id="recipe-title" className="text-lg font-semibold mb-2">{name}</h3>
                
                <div className="flex flex-wrap gap-2 mb-4" role="list" aria-label="Recipe details">
                    {prepTime && (
                        <span className="bg-green-50 text-green-700 text-xs px-2 py-1 rounded-full" role="listitem">
                            <i className="far fa-clock mr-1" aria-hidden="true"></i>
                            <span className="sr-only">Preparation time:</span> Prep: {prepTime}
                        </span>
                    )}
                    {cookTime && (
                        <span className="bg-green-50 text-green-700 text-xs px-2 py-1 rounded-full" role="listitem">
                            <i className="fas fa-fire mr-1" aria-hidden="true"></i>
                            <span className="sr-only">Cooking time:</span> Cook: {cookTime}
                        </span>
                    )}
                    {difficulty && (
                        <span className="bg-green-50 text-green-700 text-xs px-2 py-1 rounded-full" role="listitem">
                            <i className="fas fa-chart-line mr-1" aria-hidden="true"></i>
                            <span className="sr-only">Difficulty level:</span> {difficulty}
                        </span>
                    )}
                    {servings && (
                        <span className="bg-green-50 text-green-700 text-xs px-2 py-1 rounded-full" role="listitem">
                            <i className="fas fa-utensils mr-1" aria-hidden="true"></i>
                            <span className="sr-only">Number of servings:</span> Serves {servings}
                        </span>
                    )}
                </div>
                
                <div className="mb-4">
                    <h4 id="ingredients-title" className="font-medium text-sm text-gray-700 mb-2">Ingredients:</h4>
                    <ul 
                        aria-labelledby="ingredients-title"
                        className="list-disc pl-5 space-y-1"
                    >
                        {ingredients.map((ingredient, index) => (
                            <li 
                                key={`ingredient-${index}`} 
                                className="text-sm text-gray-600"
                            >
                                {ingredient}
                            </li>
                        ))}
                    </ul>
                </div>
                
                <div>
                    <h4 id="instructions-title" className="font-medium text-sm text-gray-700 mb-2">Instructions:</h4>
                    <div 
                        aria-labelledby="instructions-title"
                        className="text-sm text-gray-600 whitespace-pre-line"
                    >
                        {instructions}
                    </div>
                </div>
            </div>
        </article>
    );
}

RecipeCard.propTypes = {
    recipe: PropTypes.shape({
        name: PropTypes.string.isRequired,
        ingredients: PropTypes.arrayOf(PropTypes.string).isRequired,
        instructions: PropTypes.string.isRequired,
        prepTime: PropTypes.string,
        cookTime: PropTypes.string,
        difficulty: PropTypes.string,
        servings: PropTypes.oneOfType([
            PropTypes.string,
            PropTypes.number
        ])
    }).isRequired
};

export default RecipeCard;
