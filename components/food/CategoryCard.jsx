import React, { useState } from "react";
import PropTypes from 'prop-types';
import { reportError } from '../../utils/helpers';

function CategoryCard({
    category,
    onClick
}) {
    const [imageError, setImageError] = useState(false);
    const [imageLoaded, setImageLoaded] = useState(false);

    const handleClick = () => {
        if (onClick) {
            onClick(category);
        } else {
            // Navigate to find page with category filter
            window.location.href = `/find?category=${category.id}`;
        }
    };

    const handleImageError = () => {
        setImageError(true);
        reportError(new Error(`Failed to load image for category: ${category.id}`));
    };

    const handleImageLoad = () => {
        setImageLoaded(true);
    };

    return (
        <div 
            data-name="category-card"
            className="bg-white rounded-lg shadow-sm overflow-hidden hover:shadow-md transition-shadow duration-300 cursor-pointer"
            onClick={handleClick}
            onKeyPress={(e) => {
                if (e.key === 'Enter' || e.key === ' ') {
                    e.preventDefault();
                    handleClick(e);
                }
            }}
            role="button"
            tabIndex={0}
            aria-label={`${category.title} category with ${category.itemCount} items`}
        >
            <div className="relative h-48">
                {!imageLoaded && !imageError && (
                    <div className="absolute inset-0 bg-gray-100 flex items-center justify-center">
                        <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-gray-400"></div>
                    </div>
                )}
                {!imageError ? (
                    <img 
                        src={category.image} 
                        alt={category.title}
                        className={`w-full h-full object-cover ${!imageLoaded ? 'invisible' : ''}`}
                        onError={handleImageError}
                        onLoad={handleImageLoad}
                    />
                ) : (
                    <div className="w-full h-full bg-gray-200 flex items-center justify-center">
                        <span className="text-gray-400">
                            <i className="fas fa-image mr-2"></i>
                            Image not available
                        </span>
                    </div>
                )}
                <div className="absolute inset-0 bg-black bg-opacity-30 flex items-center justify-center">
                    <div className="text-center text-white p-4">
                        <h3 className="text-2xl font-bold mb-1">{category.title}</h3>
                        <p className="mb-2">{category.description}</p>
                        <div className="inline-block px-3 py-1 bg-white bg-opacity-20 rounded-full text-sm">
                            {category.itemCount} items
                        </div>
                    </div>
                </div>
            </div>
        </div>
    );
}

CategoryCard.propTypes = {
    category: PropTypes.shape({
        id: PropTypes.string.isRequired,
        title: PropTypes.string.isRequired,
        description: PropTypes.string.isRequired,
        image: PropTypes.string.isRequired,
        itemCount: PropTypes.number.isRequired
    }).isRequired,
    onClick: PropTypes.func
};

export default CategoryCard;