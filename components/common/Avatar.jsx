import React, { useState } from "react";
import PropTypes from 'prop-types';
import { reportError } from '../../utils/helpers';

// Avatar size configurations
const SIZES = {
    xs: 'w-6 h-6',
    sm: 'w-8 h-8',
    md: 'w-10 h-10',
    lg: 'w-12 h-12',
    xl: 'w-16 h-16',
    '2xl': 'w-20 h-20',
    '3xl': 'w-24 h-24'
};

// Status indicator configurations
const STATUS_COLORS = {
    online: 'bg-green-500',
    offline: 'bg-gray-400',
    away: 'bg-yellow-500',
    busy: 'bg-red-500'
};

const STATUS_LABELS = {
    online: 'Online',
    offline: 'Offline',
    away: 'Away',
    busy: 'Busy'
};

function Avatar({
    src,
    alt = 'User avatar',
    size = 'md',
    status,
    className = '',
    fallbackImage = null // Will be generated if not provided
}) {
    const [imageError, setImageError] = useState(false);
    const [isLoading, setIsLoading] = useState(true);

    // Generate a more reliable fallback image
    const getInitials = (name) => {
        if (!name) return 'U';
        return name.split(' ').map(n => n[0]).join('').toUpperCase().slice(0, 2);
    };

    const generateFallbackImage = () => {
        if (fallbackImage) return fallbackImage;
        
        const initials = getInitials(alt === 'User avatar' ? 'User' : alt);
        
        // Try to generate a canvas-based fallback, but fall back to placeholder service if canvas isn't available
        if (typeof document !== 'undefined' && document.createElement) {
            try {
                const canvas = document.createElement('canvas');
                canvas.width = 150;
                canvas.height = 150;
                const ctx = canvas.getContext('2d');
                
                // Fill background
                ctx.fillStyle = '#6366f1';
                ctx.fillRect(0, 0, 150, 150);
                
                // Add initials
                ctx.fillStyle = 'white';
                ctx.font = 'bold 60px sans-serif';
                ctx.textAlign = 'center';
                ctx.textBaseline = 'middle';
                ctx.fillText(initials, 75, 75);
                
                return canvas.toDataURL();
            } catch (error) {
                console.warn('Canvas fallback failed, using placeholder service');
            }
        }
        
        // Fallback to placeholder service
        return `https://ui-avatars.com/api/?name=${encodeURIComponent(initials)}&background=6366f1&color=ffffff&size=150`;
    };

    if (!SIZES[size]) {
        console.warn(`Invalid avatar size: ${size}. Using default 'md' size.`);
        size = 'md';
    }

    if (status && !STATUS_COLORS[status]) {
        console.warn(`Invalid status: ${status}. Status indicator will not be shown.`);
        status = null;
    }

    const handleImageError = () => {
        setImageError(true);
        setIsLoading(false);
        console.warn('Failed to load avatar image, using fallback');
        // Don't report this as an error since it's expected behavior when images fail to load
        // reportError(new Error('Avatar image failed to load'));
    };

    const handleImageLoad = () => {
        setIsLoading(false);
    };

    return (
        <div 
            data-name="avatar" 
            className="relative inline-block"
            role="img"
            aria-label={`${alt}${status ? ` (${STATUS_LABELS[status]})` : ''}`}
        >
            {isLoading && (
                <div className={`
                    rounded-full bg-gray-200 animate-pulse
                    ${SIZES[size]}
                    ${className}
                `} />
            )}
            <img
                src={imageError ? generateFallbackImage() : (src || generateFallbackImage())}
                alt={alt}
                className={`
                    rounded-full object-cover
                    ${SIZES[size]}
                    ${className}
                    ${isLoading ? 'hidden' : ''}
                    transition-opacity duration-200
                `}
                onError={handleImageError}
                onLoad={handleImageLoad}
            />
            
            {status && STATUS_COLORS[status] && (
                <span
                    className={`
                        absolute bottom-0 right-0
                        w-3 h-3 rounded-full
                        border-2 border-white
                        ${STATUS_COLORS[status]}
                    `}
                    role="status"
                    aria-label={STATUS_LABELS[status]}
                />
            )}
        </div>
    );
}

Avatar.propTypes = {
    src: PropTypes.string,
    alt: PropTypes.string,
    size: PropTypes.oneOf(Object.keys(SIZES)),
    status: PropTypes.oneOf([...Object.keys(STATUS_COLORS), null, undefined]),
    className: PropTypes.string,
    fallbackImage: PropTypes.string
};

export default Avatar;