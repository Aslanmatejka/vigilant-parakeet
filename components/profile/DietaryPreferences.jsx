import React, { useState, useEffect } from 'react';
import PropTypes from 'prop-types';

// Common dietary options
export const DIETARY_OPTIONS = {
    restrictions: [
        { value: 'vegetarian', label: '🥗 Vegetarian', description: 'No meat or fish' },
        { value: 'vegan', label: '🌱 Vegan', description: 'No animal products' },
        { value: 'pescatarian', label: '🐟 Pescatarian', description: 'Fish but no meat' },
        { value: 'halal', label: '☪️ Halal', description: 'Islamic dietary laws' },
        { value: 'kosher', label: '✡️ Kosher', description: 'Jewish dietary laws' },
        { value: 'gluten-free', label: '🌾 Gluten-Free', description: 'No gluten' },
        { value: 'dairy-free', label: '🥛 Dairy-Free', description: 'No dairy products' },
        { value: 'low-carb', label: '🥩 Low-Carb', description: 'Reduced carbohydrates' },
        { value: 'keto', label: '🥑 Keto', description: 'Ketogenic diet' },
        { value: 'paleo', label: '🦴 Paleo', description: 'Paleolithic diet' }
    ],
    allergies: [
        { value: 'nuts', label: '🥜 Nuts', icon: '🥜' },
        { value: 'peanuts', label: '🥜 Peanuts', icon: '🥜' },
        { value: 'tree-nuts', label: '🌰 Tree Nuts', icon: '🌰' },
        { value: 'dairy', label: '🥛 Dairy', icon: '🥛' },
        { value: 'eggs', label: '🥚 Eggs', icon: '🥚' },
        { value: 'soy', label: '🫘 Soy', icon: '🫘' },
        { value: 'wheat', label: '🌾 Wheat/Gluten', icon: '🌾' },
        { value: 'shellfish', label: '🦐 Shellfish', icon: '🦐' },
        { value: 'fish', label: '🐟 Fish', icon: '🐟' },
        { value: 'sesame', label: '🌰 Sesame', icon: '🌰' },
        { value: 'mustard', label: '🌭 Mustard', icon: '🌭' },
        { value: 'celery', label: '🥬 Celery', icon: '🥬' }
    ],
    preferences: [
        { value: 'organic', label: '🌿 Organic', description: 'Prefer organic foods' },
        { value: 'local', label: '📍 Local', description: 'Prefer locally sourced' },
        { value: 'non-gmo', label: '🧬 Non-GMO', description: 'No genetically modified' },
        { value: 'sugar-free', label: '🚫 Sugar-Free', description: 'No added sugar' },
        { value: 'low-sodium', label: '🧂 Low Sodium', description: 'Reduced salt' },
        { value: 'whole-foods', label: '🥗 Whole Foods', description: 'Minimally processed' }
    ]
};

function DietaryPreferences({ 
    initialRestrictions = [], 
    initialAllergies = [], 
    initialPreferences = [],
    onChange,
    readOnly = false
}) {
    const [dietaryRestrictions, setDietaryRestrictions] = useState(initialRestrictions);
    const [allergies, setAllergies] = useState(initialAllergies);
    const [preferences, setPreferences] = useState(initialPreferences);
    const [activeTab, setActiveTab] = useState('restrictions');

    useEffect(() => {
        if (onChange) {
            onChange({
                dietary_restrictions: dietaryRestrictions,
                allergies: allergies,
                dietary_preferences: preferences
            });
        }
    }, [dietaryRestrictions, allergies, preferences, onChange]);

    const toggleItem = (category, value) => {
        if (readOnly) return;

        const setter = {
            'restrictions': setDietaryRestrictions,
            'allergies': setAllergies,
            'preferences': setPreferences
        }[category];

        const current = {
            'restrictions': dietaryRestrictions,
            'allergies': allergies,
            'preferences': preferences
        }[category];

        if (current.includes(value)) {
            setter(current.filter(item => item !== value));
        } else {
            setter([...current, value]);
        }
    };

    const isSelected = (category, value) => {
        const current = {
            'restrictions': dietaryRestrictions,
            'allergies': allergies,
            'preferences': preferences
        }[category];
        return current.includes(value);
    };

    const tabs = [
        { id: 'restrictions', label: 'Dietary Restrictions', icon: '🥗' },
        { id: 'allergies', label: 'Allergies', icon: '⚠️' },
        { id: 'preferences', label: 'Preferences', icon: '⭐' }
    ];

    return (
        <div className="dietary-preferences">
            {/* Tabs */}
            <div className="flex space-x-2 mb-4 border-b border-gray-200">
                {tabs.map(tab => (
                    <button
                        key={tab.id}
                        onClick={() => setActiveTab(tab.id)}
                        className={`px-4 py-2 font-medium transition-colors ${
                            activeTab === tab.id
                                ? 'text-primary-600 border-b-2 border-primary-600'
                                : 'text-gray-500 hover:text-gray-700'
                        }`}
                    >
                        <span className="mr-2">{tab.icon}</span>
                        {tab.label}
                    </button>
                ))}
            </div>

            {/* Dietary Restrictions */}
            {activeTab === 'restrictions' && (
                <div className="space-y-2">
                    <p className="text-sm text-gray-600 mb-3">
                        Select your dietary restrictions to help us match you with suitable food
                    </p>
                    <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                        {DIETARY_OPTIONS.restrictions.map(option => (
                            <button
                                key={option.value}
                                type="button"
                                onClick={() => toggleItem('restrictions', option.value)}
                                disabled={readOnly}
                                className={`p-3 rounded-lg border-2 text-left transition-all ${
                                    isSelected('restrictions', option.value)
                                        ? 'border-primary-500 bg-primary-50'
                                        : 'border-gray-200 hover:border-primary-300'
                                } ${readOnly ? 'cursor-default opacity-70' : 'cursor-pointer'}`}
                            >
                                <div className="flex items-start justify-between">
                                    <div className="flex-1">
                                        <div className="font-medium text-gray-900">{option.label}</div>
                                        <div className="text-xs text-gray-500 mt-1">{option.description}</div>
                                    </div>
                                    {isSelected('restrictions', option.value) && (
                                        <svg className="w-5 h-5 text-primary-600 flex-shrink-0 ml-2" fill="currentColor" viewBox="0 0 20 20">
                                            <path fillRule="evenodd" d="M16.707 5.293a1 1 0 010 1.414l-8 8a1 1 0 01-1.414 0l-4-4a1 1 0 011.414-1.414L8 12.586l7.293-7.293a1 1 0 011.414 0z" clipRule="evenodd" />
                                        </svg>
                                    )}
                                </div>
                            </button>
                        ))}
                    </div>
                </div>
            )}

            {/* Allergies */}
            {activeTab === 'allergies' && (
                <div className="space-y-2">
                    <p className="text-sm text-red-600 mb-3 flex items-center">
                        <svg className="w-5 h-5 mr-2" fill="currentColor" viewBox="0 0 20 20">
                            <path fillRule="evenodd" d="M8.257 3.099c.765-1.36 2.722-1.36 3.486 0l5.58 9.92c.75 1.334-.213 2.98-1.742 2.98H4.42c-1.53 0-2.493-1.646-1.743-2.98l5.58-9.92zM11 13a1 1 0 11-2 0 1 1 0 012 0zm-1-8a1 1 0 00-1 1v3a1 1 0 002 0V6a1 1 0 00-1-1z" clipRule="evenodd" />
                        </svg>
                        Critical: Select all food items you're allergic to
                    </p>
                    <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-3">
                        {DIETARY_OPTIONS.allergies.map(option => (
                            <button
                                key={option.value}
                                type="button"
                                onClick={() => toggleItem('allergies', option.value)}
                                disabled={readOnly}
                                className={`p-3 rounded-lg border-2 text-center transition-all ${
                                    isSelected('allergies', option.value)
                                        ? 'border-red-500 bg-red-50'
                                        : 'border-gray-200 hover:border-red-300'
                                } ${readOnly ? 'cursor-default opacity-70' : 'cursor-pointer'}`}
                            >
                                <div className="text-2xl mb-1">{option.icon}</div>
                                <div className="text-sm font-medium text-gray-900">{option.label.replace(/^[🥜🌰🥛🥚🫘🌾🦐🐟🌭🥬]\s/u, '')}</div>
                                {isSelected('allergies', option.value) && (
                                    <div className="mt-1">
                                        <svg className="w-4 h-4 text-red-600 mx-auto" fill="currentColor" viewBox="0 0 20 20">
                                            <path fillRule="evenodd" d="M16.707 5.293a1 1 0 010 1.414l-8 8a1 1 0 01-1.414 0l-4-4a1 1 0 011.414-1.414L8 12.586l7.293-7.293a1 1 0 011.414 0z" clipRule="evenodd" />
                                        </svg>
                                    </div>
                                )}
                            </button>
                        ))}
                    </div>
                </div>
            )}

            {/* Preferences */}
            {activeTab === 'preferences' && (
                <div className="space-y-2">
                    <p className="text-sm text-gray-600 mb-3">
                        Optional: Set your food preferences for better recommendations
                    </p>
                    <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                        {DIETARY_OPTIONS.preferences.map(option => (
                            <button
                                key={option.value}
                                type="button"
                                onClick={() => toggleItem('preferences', option.value)}
                                disabled={readOnly}
                                className={`p-3 rounded-lg border-2 text-left transition-all ${
                                    isSelected('preferences', option.value)
                                        ? 'border-primary-500 bg-primary-50'
                                        : 'border-gray-200 hover:border-primary-300'
                                } ${readOnly ? 'cursor-default opacity-70' : 'cursor-pointer'}`}
                            >
                                <div className="flex items-start justify-between">
                                    <div className="flex-1">
                                        <div className="font-medium text-gray-900">{option.label}</div>
                                        <div className="text-xs text-gray-500 mt-1">{option.description}</div>
                                    </div>
                                    {isSelected('preferences', option.value) && (
                                        <svg className="w-5 h-5 text-primary-600 flex-shrink-0 ml-2" fill="currentColor" viewBox="0 0 20 20">
                                            <path fillRule="evenodd" d="M16.707 5.293a1 1 0 010 1.414l-8 8a1 1 0 01-1.414 0l-4-4a1 1 0 011.414-1.414L8 12.586l7.293-7.293a1 1 0 011.414 0z" clipRule="evenodd" />
                                        </svg>
                                    )}
                                </div>
                            </button>
                        ))}
                    </div>
                </div>
            )}

            {/* Summary */}
            {!readOnly && (dietaryRestrictions.length > 0 || allergies.length > 0 || preferences.length > 0) && (
                <div className="mt-6 p-4 bg-blue-50 border border-blue-200 rounded-lg">
                    <h4 className="font-semibold text-blue-900 mb-2">Your Dietary Profile Summary:</h4>
                    <div className="space-y-2 text-sm">
                        {dietaryRestrictions.length > 0 && (
                            <div>
                                <span className="font-medium text-blue-800">Restrictions:</span>
                                <span className="ml-2 text-blue-700">{dietaryRestrictions.join(', ')}</span>
                            </div>
                        )}
                        {allergies.length > 0 && (
                            <div>
                                <span className="font-medium text-red-800">Allergies:</span>
                                <span className="ml-2 text-red-700">{allergies.join(', ')}</span>
                            </div>
                        )}
                        {preferences.length > 0 && (
                            <div>
                                <span className="font-medium text-primary-800">Preferences:</span>
                                <span className="ml-2 text-primary-700">{preferences.join(', ')}</span>
                            </div>
                        )}
                    </div>
                </div>
            )}
        </div>
    );
}

DietaryPreferences.propTypes = {
    initialRestrictions: PropTypes.arrayOf(PropTypes.string),
    initialAllergies: PropTypes.arrayOf(PropTypes.string),
    initialPreferences: PropTypes.arrayOf(PropTypes.string),
    onChange: PropTypes.func,
    readOnly: PropTypes.bool
};

export default DietaryPreferences;
