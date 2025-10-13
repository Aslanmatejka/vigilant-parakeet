import React from 'react';
import PropTypes from 'prop-types';
import { reportError } from '../../utils/helpers';

const VARIANTS = {
    primary: 'bg-green-600 text-white hover:bg-green-700 disabled:bg-green-300',
    secondary: 'bg-gray-200 text-gray-800 hover:bg-gray-300 disabled:bg-gray-100',
    outline: 'border-2 border-green-600 text-green-600 hover:bg-green-50 disabled:border-green-300 disabled:text-green-300',
    danger: 'bg-red-600 text-white hover:bg-red-700 disabled:bg-red-300'
};

const SIZES = {
    sm: 'px-3 py-1.5 text-sm',
    md: 'px-4 py-2 text-base',
    lg: 'px-6 py-3 text-lg'
};

function Button({ 
    children, 
    variant = 'primary', 
    size = 'md', 
    disabled = false, 
    fullWidth = false,
    icon = null,
    onClick,
    type = 'button',
    className = '',
    loading = false,
    ariaLabel
}) {
    // Validate variant and size
    if (!VARIANTS[variant]) {
        console.warn(`Invalid button variant: ${variant}. Using default 'primary' variant.`);
        variant = 'primary';
    }

    if (!SIZES[size]) {
        console.warn(`Invalid button size: ${size}. Using default 'md' size.`);
        size = 'md';
    }

    const baseStyles = 'inline-flex items-center justify-center font-medium rounded-lg transition-all duration-200 focus:outline-none focus:ring-2 focus:ring-offset-2';
    
    const focusRingColors = {
        primary: 'focus:ring-green-500',
        secondary: 'focus:ring-gray-400',
        outline: 'focus:ring-green-500',
        danger: 'focus:ring-red-500'
    };

    const isDisabled = disabled || loading;

    const classes = `
        ${baseStyles}
        ${VARIANTS[variant]}
        ${SIZES[size]}
        ${focusRingColors[variant]}
        ${fullWidth ? 'w-full' : ''}
        ${isDisabled ? 'cursor-not-allowed' : 'cursor-pointer'}
        ${loading ? 'opacity-75' : ''}
        ${className}
    `.trim().replace(/\s+/g, ' ');

    return (
        <button
            data-name="button"
            type={type}
            className={classes}
            disabled={isDisabled}
            onClick={!loading ? onClick : undefined}
            aria-label={ariaLabel || (typeof children === 'string' ? children : undefined)}
            aria-disabled={isDisabled}
            aria-busy={loading}
            role="button"
        >
            {loading ? (
                <>
                    <svg 
                        className="animate-spin -ml-1 mr-2 h-4 w-4" 
                        xmlns="http://www.w3.org/2000/svg" 
                        fill="none" 
                        viewBox="0 0 24 24"
                        aria-hidden="true"
                    >
                        <circle 
                            className="opacity-25" 
                            cx="12" 
                            cy="12" 
                            r="10" 
                            stroke="currentColor" 
                            strokeWidth="4"
                        />
                        <path 
                            className="opacity-75" 
                            fill="currentColor" 
                            d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"
                        />
                    </svg>
                    <span>Loading...</span>
                </>
            ) : (
                <>
                    {icon && <span className="mr-2" aria-hidden="true">{icon}</span>}
                    {children}
                </>
            )}
        </button>
    );
}

Button.propTypes = {
    children: PropTypes.node.isRequired,
    variant: PropTypes.oneOf(Object.keys(VARIANTS)),
    size: PropTypes.oneOf(Object.keys(SIZES)),
    disabled: PropTypes.bool,
    fullWidth: PropTypes.bool,
    icon: PropTypes.node,
    onClick: PropTypes.func,
    type: PropTypes.oneOf(['button', 'submit', 'reset']),
    className: PropTypes.string,
    loading: PropTypes.bool,
    ariaLabel: PropTypes.string
};

export default Button;
