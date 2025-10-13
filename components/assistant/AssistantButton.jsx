import React from 'react';
import PropTypes from 'prop-types';
import { reportError } from '../../utils/helpers';

function AssistantButton({ onClick, className = '' }) {
    return (
        <button
            data-name="assistant-button"
            onClick={onClick}
            className={`fixed bottom-6 right-6 w-14 h-14 bg-green-600 text-white rounded-full shadow-lg flex items-center justify-center hover:bg-green-700 focus:outline-none focus:ring-2 focus:ring-green-500 focus:ring-offset-2 transition-all transform hover:scale-105 active:scale-95 disabled:opacity-50 disabled:cursor-not-allowed ${className}`}
            aria-label="Open AI Assistant"
            type="button"
            title="Open AI Assistant"
            role="button"
        >
            <i className="fas fa-robot text-xl" aria-hidden="true"></i>
            <span className="sr-only">Open AI Assistant</span>
        </button>
    );
}

AssistantButton.propTypes = {
    onClick: PropTypes.func.isRequired,
    className: PropTypes.string
};

export default AssistantButton;
