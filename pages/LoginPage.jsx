import { useNavigate } from "react-router-dom";
import { useAuth } from "../utils/hooks/useSupabase";
import Button from "../components/common/Button";
import Input from "../components/common/Input";
import React from "react";

function LoginPage() {
    const navigate = useNavigate();
    const { signIn, loading } = useAuth();
    const [formData, setFormData] = React.useState({
        email: '',
        password: '',
        rememberMe: false
    });

    const [error, setError] = React.useState(null);
    const [showPassword, setShowPassword] = React.useState(false);

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
        
        try {
            const { email, password } = formData;
            
            await signIn(email, password);
            
            // Use setTimeout to avoid DOM manipulation during render
            setTimeout(() => {
                navigate('/dashboard');
            }, 0);
        } catch (error) {
            console.error('Login error:', error);
            
            // Handle specific Supabase auth errors
            if (error.message.includes('Invalid login credentials')) {
                setError('Invalid email or password');
            } else if (error.message.includes('Email not confirmed')) {
                setError('Please check your email and confirm your account');
            } else {
                setError('An error occurred during login. Please try again.');
            }
        }
    };

    const togglePasswordVisibility = () => {
        setShowPassword(!showPassword);
    };

    
    return (
            <div className="min-h-screen bg-gray-100 flex flex-col justify-center py-12 sm:px-6 lg:px-8">
                <div className="sm:mx-auto sm:w-full sm:max-w-md">
                    <h2 className="mt-6 text-center text-3xl font-extrabold text-gray-900">
                        Sign in to your account
                    </h2>
                </div>

                <div className="mt-8 sm:mx-auto sm:w-full sm:max-w-md">
                    <div className="bg-white py-8 px-4 shadow sm:rounded-lg sm:px-10">
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
                                        className="appearance-none block w-full px-3 py-2 border border-gray-300 rounded-md shadow-sm placeholder-gray-400 focus:outline-none focus:ring-green-500 focus:border-green-500 sm:text-sm"
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
                                        className="appearance-none block w-full px-3 py-2 border border-gray-300 rounded-md shadow-sm placeholder-gray-400 focus:outline-none focus:ring-green-500 focus:border-green-500 sm:text-sm"
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
                                        className="h-4 w-4 text-green-600 focus:ring-green-500 border-gray-300 rounded"
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
                                    disabled={loading}
                                >
                                    {loading ? 'Signing in...' : 'Sign in'}
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
                                <Button
                                    variant="secondary"
                                    onClick={() => navigate('/signup')}
                                >
                                    Sign up
                                </Button>
                            </div>
                        </div>
                    </div>
                </div>
            </div>
    );
}

export default LoginPage;
