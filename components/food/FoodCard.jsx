import React from 'react';
import PropTypes from 'prop-types';
import { formatDate, getExpirationStatus, reportError } from "../../utils/helpers";
import { assignFoodImage } from "../../utils/foodImages.js";
import Card from "../common/Card";
import Avatar from "../common/Avatar";
import Button from "../common/Button";
import { useAI } from "../../utils/hooks/useSupabase";
import { UrgencyIndicator } from "./UrgencyBadge";
import VerificationStatus from "./VerificationStatus";
import FoodDietaryTags from "./FoodDietaryTags";
import { AIThinkingInline } from "../common/AIThinking.jsx";

const formatDistance = (dist) => {
    if (!dist) return '';
    if (dist < 1) return `${Math.round(dist * 1000)}m away`;
    return `${dist.toFixed(1)}km away`;
};

function FoodCard({
    food,
    onClaim,
    onTrade,
    className = '',
    showReturnButton = false,
    distance
}) {
    const { getRecipeSuggestions, isLoading: aiLoading } = useAI();
    const [showAITips, setShowAITips] = React.useState(false);
    const [aiSuggestions, setAISuggestions] = React.useState(null);

    if (!food) {
        reportError(new Error('Food data is required'));
        return null;
    }

    const {
        title,
        description,
        image_url,
        quantity,
        unit,
        expiry_date,
        location,
        full_address,
        users,
        donor_name,
        donor_city,
        donor_state,
        type = 'donation', // 'donation' or 'trade'
    } = food;

    const donor = {
        name: donor_name || (users?.[0] || users)?.organization || (users?.[0] || users)?.name || 'Anonymous',
        avatar: (users?.[0] || users)?.avatar_url
    };

    // Use expiry_date from DB, fallback to empty string if missing
    const expirationStatus = getExpirationStatus(expiry_date || '');

    const handleClaim = () => {
        if (typeof onClaim === 'function') {
            onClaim(food);
        } else {
            console.warn('onClaim handler is not defined');
        }
    };

    const handleTrade = () => {
        if (typeof onTrade === 'function') {
            onTrade(food);
        } else {
            console.warn('onTrade handler is not defined');
        }
    };

    const handleReturn = () => {
        window.location.href = '/';
    };

    const handleAIRecipes = async () => {
        if (showAITips) {
            setShowAITips(false);
            return;
        }

        // Open the panel immediately so the user sees the AI working state.
        setAISuggestions(null);
        setShowAITips(true);
        try {
            const ingredients = [title];
            const recipes = await getRecipeSuggestions(ingredients);
            setAISuggestions(recipes);
        } catch (error) {
            setAISuggestions({ error: error.message || 'Failed to get recipe suggestions.' });
        }
    };

    return (
        <Card
            className={`food-card ${className}`}
            image={image_url || assignFoodImage(food)}
            title={title}
            subtitle={
                <div className="space-y-2.5 text-sm">
                    {/* Location */}
                    <div className="flex items-start text-gray-600">
                        <i className="fas fa-map-marker-alt text-green-500 mr-2 mt-0.5" aria-hidden="true"></i>
                        <span>
                            {donor_city || donor_state ? 
                                [donor_city, donor_state].filter(Boolean).join(', ') :
                                (typeof location === 'object' && location?.address ? 
                                    location.address :
                                    (typeof location === 'string' && location ? 
                                        location : 
                                        (full_address || 'No location available'))
                                )}
                            {distance && <span className="ml-1 text-gray-400">({formatDistance(distance)})</span>}
                        </span>
                    </div>

                    {/* Expiry date */}
                    <div className="flex items-center text-gray-600">
                        <i className="fas fa-calendar-alt text-green-500 mr-2" aria-hidden="true"></i>
                        <span className="font-medium text-gray-500 mr-1">Expires:</span>
                        <span>{expiry_date ? formatDate(expiry_date) : 'No expiry date'}</span>
                    </div>

                    {/* Status badges */}
                    <div className="flex items-center flex-wrap gap-1.5">
                        <UrgencyIndicator foodListing={food} />
                        {food.verification_status && food.verification_status !== 'pending' && (
                            <VerificationStatus status={food.verification_status} compact={true} />
                        )}
                        <span
                            className={`badge badge-${expirationStatus.status}`}
                            role="status"
                            aria-label={`Expiration status: ${expirationStatus.label}`}
                        >
                            {expirationStatus.label}
                        </span>
                    </div>

                    {/* Dietary Tags */}
                    {(food.dietary_tags?.length > 0 || food.allergen_info?.length > 0) && (
                        <div>
                            <FoodDietaryTags food={food} compact={true} />
                        </div>
                    )}
                </div>
            }
            footer={
                <div className="flex items-center justify-between gap-2 flex-wrap">
                    <Button
                        variant="secondary"
                        size="sm"
                        onClick={handleAIRecipes}
                        loading={aiLoading}
                        aria-label={showAITips ? `Hide AI recipe tips for ${title}` : `Get AI recipe ideas for ${title}`}
                        aria-pressed={showAITips}
                    >
                        <i className={`fas ${showAITips ? 'fa-chevron-up' : 'fa-utensils'} mr-1.5`} aria-hidden="true" />
                        {showAITips ? 'Hide tips' : 'AI recipes'}
                    </Button>
                    <div className="flex space-x-2">
                        {type === 'donation' ? (
                            <Button
                                variant="primary"
                                size="sm"
                                onClick={handleClaim}
                                aria-label={`Claim ${title}`}
                                disabled={!onClaim}
                            >
                                Claim
                            </Button>
                        ) : (
                            <Button
                                variant="secondary"
                                size="sm"
                                onClick={handleTrade}
                                aria-label={`Trade ${title}`}
                                disabled={!onTrade}
                            >
                                Trade
                            </Button>
                        )}
                        {/* Recipes button removed for shared food */}
                        {showReturnButton && (
                            <Button
                                variant="secondary"
                                size="sm"
                                onClick={handleReturn}
                                aria-label="Return to main site"
                            >
                                Return to Site
                            </Button>
                        )}
                    </div>
                </div>
            }
        >
            <div className="space-y-2">
                <p className="text-gray-600">{description}</p>
                <div className="flex items-center">
                    <div className="flex items-center">
                        <i className="fas fa-box-open text-gray-400 mr-2" aria-hidden="true"></i>
                        <span>{quantity} {unit}</span>
                    </div>
                </div>
                
                {/* AI Recipe Suggestions */}
                {showAITips && (
                    <div className="mt-4 p-3 bg-blue-50 border border-blue-200 rounded-lg">
                        <h4 className="font-semibold text-blue-800 mb-2 flex items-center">
                            <i className="fas fa-robot mr-2"></i>
                            AI Recipe Suggestions
                        </h4>
                        {aiSuggestions?.error ? (
                            <p className="text-sm text-red-600">{aiSuggestions.error}</p>
                        ) : aiSuggestions?.recipes && aiSuggestions.recipes.length > 0 ? (
                            <div className="space-y-2">
                                {aiSuggestions.recipes.slice(0, 2).map((recipe, index) => (
                                    <div key={index} className="text-sm">
                                        <p className="font-medium text-blue-700">{recipe.name}</p>
                                        <p className="text-blue-600 text-xs">{recipe.instructions}</p>
                                    </div>
                                ))}
                            </div>
                        ) : aiLoading || !aiSuggestions ? (
                            <AIThinkingInline
                                dark={false}
                                size={36}
                                stages={[
                                    { icon: 'utensils', label: 'Reading ingredients' },
                                    { icon: 'book', label: 'Searching recipes' },
                                    { icon: 'wand-magic-sparkles', label: 'Crafting suggestions' },
                                ]}
                            />
                        ) : (
                            <p className="text-sm text-blue-600">No recipes found.</p>
                        )}
                    </div>
                )}
            </div>
        </Card>
    );
}

FoodCard.propTypes = {
    food: PropTypes.shape({
        id: PropTypes.string.isRequired,
        title: PropTypes.string.isRequired,
        description: PropTypes.string,
        image_url: PropTypes.string,
        quantity: PropTypes.number,
        unit: PropTypes.string,
        expiry_date: PropTypes.string,
        location: PropTypes.oneOfType([PropTypes.string, PropTypes.object]),
        type: PropTypes.oneOf(['donation', 'trade']),
        donor_name: PropTypes.string,
        donor_city: PropTypes.string,
        donor_state: PropTypes.string,
        users: PropTypes.oneOfType([PropTypes.object, PropTypes.array])
    }).isRequired,
    onClaim: PropTypes.func,
    onTrade: PropTypes.func,
    className: PropTypes.string,
    showReturnButton: PropTypes.bool,
    distance: PropTypes.number
};

export default FoodCard;