import { useNavigate, useSearchParams } from "react-router-dom";
import { useAuthContext } from "../utils/AuthContext";
import Button from "../components/common/Button";
import Input from "../components/common/Input";
import React from "react";

function LoginPage() {
    const navigate = useNavigate();
    const [searchParams] = useSearchParams();
    const { signIn, isAuthenticated, loading: authLoading } = useAuthContext();
    const [formData, setFormData] = React.useState({
        email: '',
        password: '',
        rememberMe: false
    });

    const [error, setError] = React.useState(null);
    const [submitting, setSubmitting] = React.useState(false);
    const [successMessage, setSuccessMessage] = React.useState(null);
    const [showPassword, setShowPassword] = React.useState(false);

    // Redirect if already authenticated
    React.useEffect(() => {
        if (!authLoading && isAuthenticated) {
            const redirectPath = searchParams.get('redirect') || '/';
            navigate(redirectPath, { replace: true });
        }
    }, [isAuthenticated, authLoading, navigate, searchParams]);

    React.useEffect(() => {
        // Scroll to top when page loads
        window.scrollTo(0, 0);
    }, []);

    React.useEffect(() => {
        // Check for success message in URL
        const message = searchParams.get('message');
        if (message === 'password-reset-success') {
            setSuccessMessage('Password reset successful! You can now log in with your new password.');
            // Clear the message from URL
            window.history.replaceState({}, '', '/login');
        } else if (message === 'email-confirmed') {
            setSuccessMessage('Email confirmed successfully! You can now sign in to your account.');
            window.history.replaceState({}, '', '/login');
        } else if (message === 'signup-success') {
            setSuccessMessage('Account created! Please check your email to confirm your account before signing in.');
            window.history.replaceState({}, '', '/login');
        }
    }, [searchParams]);

    const validateForm = () => {
        if (!formData.email || !formData.password) {
            setError('Please fill in all required fields');
            return false;
        }
        if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(formData.email)) {
            setError('Please enter a valid email address');
            return false;
        }
        if (formData.password.length < 8) {
            setError('Password must be at least 8 characters long');
            return false;
        }
        return true;
    };

    const handleChange = (e) => {
        const { name, value, type, checked } = e.target;
        setFormData(prev => ({
            ...prev,
            [name]: type === 'checkbox' ? checked : value
        }));

        // Clear error when field is modified
        if (error) {
            setError(null);
        }
    };

    const handleSubmit = async (e) => {
        e.preventDefault();
        
        if (!validateForm()) {
            return;
        }

        setError(null);
        setSubmitting(true);
        
        try {
            const { email, password } = formData;
            
            await signIn(email, password);
            // Navigation is handled by the useEffect watching isAuthenticated
            // signIn now calls setUser() internally, so context will update and
            // the useEffect will fire automatically
        } catch (error) {
            console.error('Login error:', error);
            console.warn('Login error details:', { type: typeof error, message: error?.message, name: error?.name, code: error?.code, status: error?.status, raw: error });
            
            // Extract error message from any possible format
            const msg = error?.message || error?.msg || error?.error_description || 
                        (typeof error === 'string' ? error : null) ||
                        (error ? String(error) : 'An unexpected error occurred. Please try again.');
            
            // Handle specific Supabase auth errors
            if (msg.includes('Invalid login credentials')) {
                setError('Invalid email or password');
            } else if (msg.includes('Email not confirmed')) {
                setError('Please check your email and confirm your account before signing in.');
            } else if (msg.includes('Failed to fetch') || msg.includes('NetworkError') || msg.includes('network')) {
                setError('Network error. Please check your connection and try again.');
            } else if (msg.includes('Too many requests') || msg.includes('rate limit')) {
                setError('Too many login attempts. Please wait a moment and try again.');
            } else {
                setError(msg);
            }
        } finally {
            setSubmitting(false);
        }
    };

    const togglePasswordVisibility = () => {
        setShowPassword(!showPassword);
    };

    
    return (
            <div className="min-h-screen bg-gradient-to-b from-[#2CABE3]/5 via-white to-emerald-50/40 flex flex-col justify-center py-12 sm:px-6 lg:px-8">
                <div className="sm:mx-auto sm:w-full sm:max-w-md">
                    <h2 className="mt-6 text-center text-3xl font-extrabold text-gray-900">
                        Sign in to your{" "}
                        <span className="bg-gradient-to-r from-[#2CABE3] to-emerald-500 bg-clip-text text-transparent">account</span>
                    </h2>
                </div>

                <div className="mt-8 sm:mx-auto sm:w-full sm:max-w-md">
                    <div className="bg-white py-8 px-4 shadow sm:rounded-lg sm:px-10">
                        {successMessage && (
                            <div className="mb-6 rounded-md bg-primary-50 p-4">
                                <div className="flex">
                                    <div className="flex-shrink-0">
                                        <i className="fas fa-check-circle text-primary-400"></i>
                                    </div>
                                    <div className="ml-3">
                                        <p className="text-sm text-primary-800">{successMessage}</p>
                                    </div>
                                    <div className="ml-auto pl-3">
                                        <button
                                            type="button"
                                            onClick={() => setSuccessMessage(null)}
                                            className="inline-flex rounded-md text-primary-400 hover:text-primary-500"
                                        >
                                            <i className="fas fa-times"></i>
                                        </button>
                                    </div>
                                </div>
                            </div>
                        )}
                        
                        <form className="space-y-6" onSubmit={handleSubmit}>
                            <div>
                                <label htmlFor="email" className="block text-sm font-medium text-gray-700">
                                    Email address
                                </label>
                                <div className="mt-1">
                                    <Input
                                        id="email"
                                        name="email"
                                        type="email"
                                        autoComplete="email"
                                        required
                                        value={formData.email}
                                        onChange={handleChange}
                                        className="appearance-none block w-full px-3 py-2 border border-gray-300 rounded-md shadow-sm placeholder-gray-400 focus:outline-none focus:ring-primary-500 focus:border-primary-500 sm:text-sm"
                                    />
                                </div>
                            </div>

                            <div>
                                <label htmlFor="password" className="block text-sm font-medium text-gray-700">
                                    Password
                                </label>
                                <div className="mt-1 relative">
                                    <Input
                                        id="password"
                                        name="password"
                                        type={showPassword ? "text" : "password"}
                                        autoComplete="current-password"
                                        required
                                        value={formData.password}
                                        onChange={handleChange}
                                        className="appearance-none block w-full px-3 py-2 border border-gray-300 rounded-md shadow-sm placeholder-gray-400 focus:outline-none focus:ring-primary-500 focus:border-primary-500 sm:text-sm"
                                    />
                                    <button
                                        type="button"
                                        onClick={togglePasswordVisibility}
                                        className="absolute inset-y-0 right-0 pr-3 flex items-center"
                                    >
                                        <i className={`fas fa-eye${showPassword ? '-slash' : ''}`}></i>
                                    </button>
                                </div>
                            </div>

                            <div className="flex items-center justify-between">
                                <div className="flex items-center">
                                    <input
                                        id="remember-me"
                                        name="rememberMe"
                                        type="checkbox"
                                        checked={formData.rememberMe}
                                        onChange={handleChange}
                                        className="h-4 w-4 text-primary-600 focus:ring-primary-500 border-gray-300 rounded"
                                    />
                                    <label htmlFor="remember-me" className="ml-2 block text-sm text-gray-900">
                                        Remember me
                                    </label>
                                </div>

                                <div className="text-sm">
                                    <Button
                                        variant="secondary"
                                        size="sm"
                                        onClick={() => navigate('/forgot-password')}
                                    >
                                        Forgot password?
                                    </Button>
                                </div>
                            </div>

                            {error && (
                                <div className="text-red-600 text-sm mt-2">
                                    {error}
                                </div>
                            )}

                            <div>
                                <Button
                                    type="submit"
                                    variant="primary"
                                    className="w-full"
                                    disabled={submitting}
                                >
                                    {submitting ? (
                                        <div className="flex items-center justify-center">
                                            <i className="fas fa-spinner fa-spin mr-2" aria-hidden="true"></i>
                                            Signing in...
                                        </div>
                                    ) : 'Sign in'}
                                </Button>
                            </div>
                        </form>

                        <div className="mt-6">
                            <div className="relative">
                                <div className="absolute inset-0 flex items-center">
                                    <div className="w-full border-t border-gray-300"></div>
                                </div>
                                <div className="relative flex justify-center text-sm">
                                    <span className="px-2 bg-white text-gray-500">
                                        Or
                                    </span>
                                </div>
                            </div>

                            <div className="mt-6">
                                <button
                                    onClick={() => navigate('/signup')}
                                    className="w-full bg-orange-600 text-white px-6 py-4 rounded-lg text-lg font-bold hover:bg-orange-700 transition-colors shadow-lg"
                                >
                                    Sign up
                                </button>
                            </div>
                        </div>
                    </div>
                </div>
            </div>
    );
}

export default LoginPage;
