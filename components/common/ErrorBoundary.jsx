import React from 'react';
import PropTypes from 'prop-types';

class ErrorBoundary extends React.Component {
    constructor(props) {
        super(props);
        this.state = { hasError: false, error: null };
    }

    static getDerivedStateFromError(error) {
        return { hasError: true, error };
    }

    componentDidCatch(error, errorInfo) {
        // Log the error to an error reporting service
        console.error('ErrorBoundary caught an error:', error, errorInfo);
        
        if (this.props.onError) {
            try {
                this.props.onError(error, errorInfo);
            } catch (callbackError) {
                console.error('Error in ErrorBoundary callback:', callbackError);
            }
        }
    }

    componentWillUnmount() {
        // Cleanup to prevent memory leaks
        this.setState({ hasError: false, error: null });
    }

    render() {
        if (this.state.hasError) {
            if (this.props.fallback) {
                return this.props.fallback(this.state.error);
            }

            return (
                <div className="text-center py-8" role="alert">
                    <i className="fas fa-exclamation-circle text-red-500 text-4xl mb-4"></i>
                    <h2 className="text-xl font-bold mb-2">Something went wrong</h2>
                    <p className="text-gray-600 mb-4">We&apos;re sorry, but there was an error loading this content.</p>
                    <button
                        onClick={() => this.setState({ hasError: false, error: null })}
                        className="px-4 py-2 bg-green-600 text-white rounded hover:bg-green-700"
                    >
                        Try Again
                    </button>
                </div>
            );
        }

        return this.props.children;
    }
}

ErrorBoundary.propTypes = {
    children: PropTypes.node.isRequired,
    fallback: PropTypes.func,
    onError: PropTypes.func
};

export default ErrorBoundary;