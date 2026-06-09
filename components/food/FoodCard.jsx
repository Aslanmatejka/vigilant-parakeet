import React from 'react';
import PropTypes from 'prop-types';
import { formatDate, getExpirationStatus, reportError } from "../../utils/helpers";
import Card from "../common/Card";
import Avatar from "../common/Avatar";
import Button from "../common/Button";
import { useAI } from "../../utils/hooks/useSupabase";
import { UrgencyIndicator, ExpiryCountdown } from "./UrgencyBadge";
import VerificationStatus from "./VerificationStatus";
import FoodDietaryTags from "./FoodDietaryTags";
import CommunityPinIcon from "../common/CommunityPinIcon";
import { AIThinkingInline } from "../common/AIThinking.jsx";

const formatDistance = (dist) => {
    if (!dist) return '';
    if (dist < 1) return `${Math.round(dist * 1000)}m away`;
    return `${dist.toFixed(1)}km away`;
};

const parseLocationAddress = (location) => {
    if (!location) return null;
    if (typeof location === 'string') {
        const trimmed = location.trim();
        if (!trimmed) return null;
        if (trimmed.startsWith('{')) {
            try {
                const parsed = JSON.parse(trimmed);
                if (parsed && typeof parsed === 'object') {
                    return parsed.address || parsed.full_address || null;
                }
            } catch {
                // plain address string
            }
        }
        return trimmed;
    }
    if (typeof location === 'object') {
        return location.address || location.full_address || null;
    }
    return null;
};

const looksLikeCityOnly = (address) => {
    if (!address || typeof address !== 'string') return false;
    const text = address.trim();
    if (!text) return false;
    if (/^\d+\s/.test(text)) return false;
    if (/\b(st|street|ste|suite|ave|avenue|rd|road|blvd|boulevard|dr|drive|ln|lane|way|ct|court|pl|place|hwy|highway|pkwy|parkway)\b/i.test(text)) {
        return false;
    }
    return true;
};

function FoodCard({
    food,
    onClaim,
    onTrade,
    className = '',
    showReturnButton = false,
    distance,
    communityName = null,
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
        pickup_by,
        location,
        full_address,
        users,
        donor_name,
        donor_city,
        donor_state,
        listing_type,
        type: legacyType,
    } = food;
    // DB column is listing_type ('donation' | 'request').
    // Fall back to legacy type field for any old in-memory objects.
    const type = listing_type || legacyType || 'donation';

    const donor = {
        name: donor_name || (users?.[0] || users)?.organization || (users?.[0] || users)?.name || 'Anonymous',
        avatar: (users?.[0] || users)?.avatar_url
    };

    // Prefer explicit expiry; fall back to pickup deadline when present.
    const displayExpiryDate = expiry_date || pickup_by || null;
    const expirationStatus = getExpirationStatus(displayExpiryDate);

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

    const userRecord = users?.[0] || users;
    const donorProfileAddress = userRecord?.address?.trim?.() || userRecord?.address || null;
    const cityFallback = [donor_city, donor_state, food.donor_zip].filter(Boolean).join(', ');

    let pickupAddress =
        (full_address && String(full_address).trim())
        || parseLocationAddress(location)
        || donorProfileAddress
        || cityFallback
        || 'Address not available';

    if (looksLikeCityOnly(pickupAddress) && donorProfileAddress && !looksLikeCityOnly(donorProfileAddress)) {
        pickupAddress = donorProfileAddress;
    }

    const resolvedCommunityId =
        food.community_id
        || food.communities?.id
        || (Array.isArray(food.communities) ? food.communities[0]?.id : null);

    const resolvedCommunityName =
        communityName
        || food.community_name
        || food.communities?.name
        || (Array.isArray(food.communities) ? food.communities[0]?.name : null);

    const communityLabel = resolvedCommunityName || 'Community not listed';

    return (
        <Card
            className={`food-card ${className}`}
            image={image_url}
            title={title}
            subtitle={
                <div className="space-y-1.5 sm:space-y-2.5 text-xs sm:text-sm">
                    {/* Location */}
                    <div className="flex items-start text-gray-600">
                        <i className="fas fa-map-marker-alt text-green-500 mr-1.5 sm:mr-2 mt-0.5 text-[10px] sm:text-sm shrink-0" aria-hidden="true"></i>
                        <span className="line-clamp-2 sm:line-clamp-none">
                            {pickupAddress}
                            {distance && <span className="ml-1 text-gray-400">({formatDistance(distance)})</span>}
                        </span>
                    </div>
                    <div className="flex items-center text-gray-600 min-w-0">
                        <CommunityPinIcon
                            communityId={resolvedCommunityId}
                            size={22}
                            className="mr-1.5 sm:mr-2.5 flex-shrink-0 sm:hidden"
                            title={communityLabel}
                        />
                        <CommunityPinIcon
                            communityId={resolvedCommunityId}
                            size={32}
                            className="mr-2.5 flex-shrink-0 hidden sm:block"
                            title={communityLabel}
                        />
                        <span className={`truncate sm:whitespace-normal ${resolvedCommunityName ? undefined : 'text-gray-400 italic'}`}>
                            {communityLabel}
                        </span>
                    </div>

                    {/* Expiry date + live countdown */}
                    <div className="flex items-center text-gray-600 min-w-0">
                        <i className="fas fa-calendar-alt text-green-500 mr-1.5 sm:mr-2 text-[10px] sm:text-sm shrink-0" aria-hidden="true"></i>
                        <span className="min-w-0 flex flex-wrap items-center gap-1.5">
                            <span>
                                <span className="font-medium text-gray-500 mr-1">
                                    {pickup_by && !expiry_date ? 'Pickup by:' : 'Expires:'}
                                </span>
                                <span className="whitespace-nowrap sm:whitespace-normal">
                                    {displayExpiryDate ? formatDate(displayExpiryDate) : 'No expiry date'}
                                </span>
                            </span>
                            {displayExpiryDate && <ExpiryCountdown foodListing={food} />}
                        </span>
                    </div>

                    {/* Status badges */}
                    <div className="flex items-center flex-wrap gap-1.5">
                        <UrgencyIndicator foodListing={food} />
                        {food.verification_status && food.verification_status !== 'pending' && (
                            <VerificationStatus status={food.verification_status} compact={true} />
                        )}
                        <span
                            className={`badge ${expirationStatus.badgeClass}`}
                            role="status"
                            aria-label={`Expiration status: ${expirationStatus.label}`}
                        >
                            {expirationStatus.label}
                        </span>
                    </div>

                    {/* Dietary Tags */}
                    {/* Note: the DB column is `allergens`, not `allergen_info`. */}
                    {(food.dietary_tags?.length > 0 || food.allergens?.length > 0) && (
                        <div>
                            <FoodDietaryTags food={food} compact={true} />
                        </div>
                    )}
                </div>
            }
            footer={
                <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-1.5 sm:gap-2 sm:flex-wrap">
                    <Button
                        variant="secondary"
                        size="sm"
                        className="w-full sm:w-auto text-xs sm:text-sm px-2 sm:px-3"
                        onClick={handleAIRecipes}
                        loading={aiLoading}
                        aria-label={showAITips ? `Hide AI recipe tips for ${title}` : `Get AI recipe ideas for ${title}`}
                        aria-pressed={showAITips}
                    >
                        <i className={`fas ${showAITips ? 'fa-chevron-up' : 'fa-utensils'} mr-1.5`} aria-hidden="true" />
                        {showAITips ? 'Hide tips' : 'AI recipes'}
                    </Button>
                    <div className="flex gap-1.5 sm:gap-2 w-full sm:w-auto">
                        {type === 'donation' ? (
                            <Button
                                variant="primary"
                                size="sm"
                                className="flex-1 sm:flex-none text-xs sm:text-sm px-2 sm:px-3"
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
    distance: PropTypes.number,
    communityName: PropTypes.string,
};

export default FoodCard;