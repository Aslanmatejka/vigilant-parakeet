import React from "react";
import { useNavigate, Link } from "react-router-dom";
import { useAuth } from "../utils/hooks/useSupabase";
import ErrorBoundary from "../components/common/ErrorBoundary";
import Button from "../components/common/Button";

function SignupPageContent() {
    const navigate = useNavigate();
    const { signUp, loading } = useAuth();
    const [formData, setFormData] = React.useState({
        name: '',
        email: '',
        password: '',
        confirmPassword: '',
        accountType: 'individual',
        agreeToTerms: false
    });

    const [errors, setErrors] = React.useState({});

    const handleChange = (e) => {
        const { name, value, type, checked } = e.target;
        setFormData(prev => ({
            ...prev,
            [name]: type === 'checkbox' ? checked : value
        }));

        // Clear error when field is modified
        if (errors[name]) {
            setErrors(prev => ({
                ...prev,
                [name]: null
            }));
        }
    };

    const validateForm = () => {
        const newErrors = {};

        if (!formData.name.trim()) newErrors.name = 'Name is required';
        if (!formData.email.trim()) {
            newErrors.email = 'Email is required';
        } else if (!/^[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}$/i.test(formData.email)) {
            newErrors.email = 'Invalid email address';
        }
        
        if (!formData.password) {
            newErrors.password = 'Password is required';
        } else if (formData.password.length < 8) {
            newErrors.password = 'Password must be at least 8 characters';
        }
        
        if (formData.password !== formData.confirmPassword) {
            newErrors.confirmPassword = 'Passwords do not match';
        }
        
        if (!formData.agreeToTerms) {
            newErrors.agreeToTerms = 'You must agree to the terms and conditions';
        }

        setErrors(newErrors);
        return Object.keys(newErrors).length === 0;
    };

    const handleSubmit = async (e) => {
        e.preventDefault();
        
        if (!validateForm()) {
            return;
        }

        try {
            const userData = {
                email: formData.email.toLowerCase().trim(),
                password: formData.password,
                options: {
                    data: {
                        name: formData.name.trim(),
                        account_type: formData.accountType
                    }
                }
            };

            const { user, error } = await signUp(userData);
            
            if (error) {
                console.error('Detailed signup error:', error);
                setErrors({ form: error.message || 'Error during signup. Please try again.' });
                return;
            }

            if (user) {
                // Show success message and redirect
                // Use setTimeout to avoid DOM manipulation during render
                setTimeout(() => {
                    navigate('/profile');
                }, 0);
            }
        } catch (error) {
            console.error('Signup error:', error);
            setErrors({ form: error.message || 'An unexpected error occurred. Please try again.' });
        }
    };

    return (
        <div className="min-h-screen bg-gray-100 py-12 px-4 sm:px-6 lg:px-8">
            <div className="absolute top-4 left-4">
                <Button
                                            onClick={() => navigate('/')}
                    variant="secondary"
                    size="sm"
                    icon={<i className="fas fa-arrow-left" aria-hidden="true"></i>}
                >
                    Return to Site
                </Button>
            </div>

            <div className="max-w-md mx-auto">
                <div className="text-center mb-8">
                    <div className="flex justify-center mb-4">
                        <div className="h-12 w-12 bg-green-600 rounded-full flex items-center justify-center">
                            <i className="fas fa-seedling text-white text-2xl" aria-hidden="true"></i>
                        </div>
                    </div>
                    <h1 className="text-3xl font-bold text-gray-900">Join DoGoods</h1>
                    <p className="mt-2 text-gray-600">
                        Create your account and start sharing food with your community
                    </p>
                </div>

                <div className="bg-white rounded-lg shadow-sm p-6 mb-6">
                    {errors.form && (
                        <div className="mb-4 p-3 bg-red-50 text-red-700 rounded-lg" role="alert">
                            <p>{errors.form}</p>
                        </div>
                    )}

                    <form onSubmit={handleSubmit} className="space-y-6" noValidate>
                        <div>
                            <label htmlFor="name" className="block text-sm font-medium text-gray-700 mb-1">
                                Full Name <span className="text-red-500" aria-hidden="true">*</span>
                            </label>
                            <input
                                id="name"
                                name="name"
                                type="text"
                                value={formData.name}
                                onChange={handleChange}
                                className={`w-full px-4 py-2 rounded-lg border focus:outline-none focus:ring-2 focus:ring-green-500 ${errors.name ? 'border-red-500' : 'border-gray-300'}`}
                                placeholder="John Doe"
                                aria-required="true"
                                aria-invalid={!!errors.name}
                                aria-describedby={errors.name ? "name-error" : undefined}
                            />
                            {errors.name && (
                                <p id="name-error" className="mt-1 text-sm text-red-500" role="alert">{errors.name}</p>
                            )}
                        </div>

                        <div>
                            <label htmlFor="email" className="block text-sm font-medium text-gray-700 mb-1">
                                Email Address <span className="text-red-500" aria-hidden="true">*</span>
                            </label>
                            <input
                                id="email"
                                name="email"
                                type="email"
                                value={formData.email}
                                onChange={handleChange}
                                className={`w-full px-4 py-2 rounded-lg border focus:outline-none focus:ring-2 focus:ring-green-500 ${errors.email ? 'border-red-500' : 'border-gray-300'}`}
                                placeholder="johndoe@example.com"
                                aria-required="true"
                                aria-invalid={!!errors.email}
                                aria-describedby={errors.email ? "email-error" : undefined}
                            />
                            {errors.email && (
                                <p id="email-error" className="mt-1 text-sm text-red-500" role="alert">{errors.email}</p>
                            )}
                        </div>

                        <div>
                            <label htmlFor="password" className="block text-sm font-medium text-gray-700 mb-1">
                                Password <span className="text-red-500" aria-hidden="true">*</span>
                            </label>
                            <input
                                id="password"
                                name="password"
                                type="password"
                                value={formData.password}
                                onChange={handleChange}
                                className={`w-full px-4 py-2 rounded-lg border focus:outline-none focus:ring-2 focus:ring-green-500 ${errors.password ? 'border-red-500' : 'border-gray-300'}`}
                                placeholder="At least 8 characters"
                                aria-required="true"
                                aria-invalid={!!errors.password}
                                aria-describedby={errors.password ? "password-error" : undefined}
                            />
                            {errors.password && (
                                <p id="password-error" className="mt-1 text-sm text-red-500" role="alert">{errors.password}</p>
                            )}
                        </div>

                        <div>
                            <label htmlFor="confirmPassword" className="block text-sm font-medium text-gray-700 mb-1">
                                Confirm Password <span className="text-red-500" aria-hidden="true">*</span>
                            </label>
                            <input
                                id="confirmPassword"
                                name="confirmPassword"
                                type="password"
                                value={formData.confirmPassword}
                                onChange={handleChange}
                                className={`w-full px-4 py-2 rounded-lg border focus:outline-none focus:ring-2 focus:ring-green-500 ${errors.confirmPassword ? 'border-red-500' : 'border-gray-300'}`}
                                placeholder="Confirm your password"
                                aria-required="true"
                                aria-invalid={!!errors.confirmPassword}
                                aria-describedby={errors.confirmPassword ? "confirm-password-error" : undefined}
                            />
                            {errors.confirmPassword && (
                                <p id="confirm-password-error" className="mt-1 text-sm text-red-500" role="alert">{errors.confirmPassword}</p>
                            )}
                        </div>

                        <div>
                            <label htmlFor="accountType" className="block text-sm font-medium text-gray-700 mb-1">
                                Account Type
                            </label>
                            <select
                                id="accountType"
                                name="accountType"
                                value={formData.accountType}
                                onChange={handleChange}
                                className="w-full px-4 py-2 rounded-lg border border-gray-300 focus:outline-none focus:ring-2 focus:ring-green-500"
                            >
                                <option value="individual">Individual</option>
                                <option value="business">Business</option>
                                <option value="nonprofit">Non-profit Organization</option>
                            </select>
                        </div>

                        <div className="flex items-start">
                            <div className="flex items-center h-5">
                                <input
                                    id="agreeToTerms"
                                    name="agreeToTerms"
                                    type="checkbox"
                                    checked={formData.agreeToTerms}
                                    onChange={handleChange}
                                    className="h-4 w-4 text-green-600 focus:ring-green-500 border-gray-300 rounded"
                                    aria-required="true"
                                    aria-invalid={!!errors.agreeToTerms}
                                    aria-describedby={errors.agreeToTerms ? "terms-error" : undefined}
                                />
                            </div>
                            <div className="ml-3 text-sm">
                                <label htmlFor="agreeToTerms" className="text-gray-700">
                                    I agree to the {' '}
                                    <Link to="/terms" className="text-green-600 hover:text-green-500">
                                        Terms of Service
                                    </Link>
                                    {' '} and {' '}
                                    <Link to="/privacy" className="text-green-600 hover:text-green-500">
                                        Privacy Policy
                                    </Link>
                                </label>
                                {errors.agreeToTerms && (
                                    <p id="terms-error" className="mt-1 text-sm text-red-500" role="alert">{errors.agreeToTerms}</p>
                                )}
                            </div>
                        </div>

                        <div>
                            <Button
                                type="submit"
                                disabled={loading}
                                variant="primary"
                                className="w-full"
                            >
                                {loading ? (
                                    <div className="flex items-center justify-center">
                                        <i className="fas fa-spinner fa-spin mr-2" aria-hidden="true"></i>
                                        Creating account...
                                    </div>
                                ) : (
                                    'Sign Up'
                                )}
                            </Button>
                        </div>
                    </form>
                </div>

                <div className="text-center">
                    <p className="text-gray-600">
                        Already have an account?{' '}
                        <Link to="/login" className="text-green-600 hover:text-green-500 font-medium">
                            Sign in
                        </Link>
                    </p>
                </div>
            </div>
        </div>
    );
}

function SignupPage() {
    return (
        <ErrorBoundary>
            <SignupPageContent />
        </ErrorBoundary>
    );
}

export default SignupPage;