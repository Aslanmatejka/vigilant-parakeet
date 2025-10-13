import React from 'react';
import PropTypes from 'prop-types';
import { reportError } from '../../utils/helpers';

function StorageTipCard({ foodItem, tips = [] }) {
    if (!foodItem) {
        reportError(new Error('Food item is required'));
        return null;
    }

    if (!Array.isArray(tips) || tips.length === 0) {
        reportError(new Error('At least one storage tip is required'));
        return null;
    }

    return (
        <article 
            data-name="storage-tip-card" 
            className="bg-white rounded-lg shadow-sm overflow-hidden border border-gray-200"
            aria-labelledby="storage-tips-title"
        >
            <div className="bg-green-50 px-4 py-3 border-b border-green-100">
                <h3 
                    id="storage-tips-title" 
                    className="font-medium text-green-800"
                >
                    Storage Tips for {foodItem}
                </h3>
            </div>
            <div className="p-4">
                <ul 
                    className="space-y-2"
                    role="list"
                    aria-label={`Storage tips for ${foodItem}`}
                >
                    {tips.map((tip, index) => (
                        <li 
                            key={`storage-tip-${index}`} 
                            className="flex items-start"
                            role="listitem"
                        >
                            <i 
                                className="fas fa-check-circle text-green-500 mt-1 mr-2" 
                                aria-hidden="true"
                            ></i>
                            <span className="text-gray-700">{tip}</span>
                        </li>
                    ))}
                </ul>
            </div>
        </article>
    );
}

StorageTipCard.propTypes = {
    foodItem: PropTypes.string.isRequired,
    tips: PropTypes.arrayOf(PropTypes.string).isRequired
};

export default StorageTipCard;
