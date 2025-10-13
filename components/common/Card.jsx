import React, { useState } from "react";
import PropTypes from 'prop-types';
import { reportError } from '../../utils/helpers';

function Card({
    children,
    title,
    subtitle,
    image,
    imageAlt,
    footer,
    className = '',
    onClick,
    hoverable = false,
    testId
}) {
    const [imageError, setImageError] = useState(false);
    const [imageLoading, setImageLoading] = useState(!!image);

    const handleImageLoad = () => {
        setImageLoading(false);
    };

    const handleImageError = () => {
        setImageError(true);
        setImageLoading(false);
        console.error('Failed to load card image');
        reportError(new Error('Card image failed to load'));
    };

    const handleKeyPress = (event) => {
        if (onClick && (event.key === 'Enter' || event.key === ' ')) {
            event.preventDefault();
            onClick(event);
        }
    };

    const cardStyles = `
        bg-white rounded-lg shadow-sm overflow-hidden
        ${hoverable ? 'transition-transform duration-200 hover:-translate-y-1 hover:shadow-md focus-within:translate-y-0 focus-within:shadow-md' : ''}
        ${onClick ? 'cursor-pointer' : ''}
        ${className}
    `.trim().replace(/\s+/g, ' ');

    const Element = onClick ? 'button' : 'div';

    return (
        <Element
            data-name="card"
            data-testid={testId}
            className={cardStyles}
            onClick={onClick}
            onKeyPress={onClick ? handleKeyPress : undefined}
            tabIndex={onClick ? 0 : undefined}
            role={onClick ? 'button' : 'article'}
            aria-labelledby={title ? 'card-title' : undefined}
        >
            {image && !imageError && (
                <div data-name="card-image" className="relative h-48">
                    {imageLoading && (
                        <div className="absolute inset-0 bg-gray-200 animate-pulse" />
                    )}
                    <img
                        src={image}
                        alt={imageAlt || title || ''}
                        className={`w-full h-full object-cover ${imageLoading ? 'invisible' : ''}`}
                        onLoad={handleImageLoad}
                        onError={handleImageError}
                    />
                </div>
            )}

            <div data-name="card-content" className="p-4">
                {title && (
                    <h3 
                        id="card-title"
                        className="text-lg font-semibold text-gray-900 mb-1"
                    >
                        {title}
                    </h3>
                )}

                {subtitle && (
                    <p 
                        className="text-sm text-gray-500 mb-4"
                        id="card-subtitle"
                    >
                        {subtitle}
                    </p>
                )}

                {children}
            </div>

            {footer && (
                <div 
                    data-name="card-footer" 
                    className="px-4 py-3 bg-gray-50 border-t"
                >
                    {footer}
                </div>
            )}
        </Element>
    );
}

Card.propTypes = {
    children: PropTypes.node,
    title: PropTypes.string,
    subtitle: PropTypes.string,
    image: PropTypes.string,
    imageAlt: PropTypes.string,
    footer: PropTypes.node,
    className: PropTypes.string,
    onClick: PropTypes.func,
    hoverable: PropTypes.bool,
    testId: PropTypes.string
};

export default Card;
