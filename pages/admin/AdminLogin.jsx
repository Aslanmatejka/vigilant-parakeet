import React from 'react';
import { useNavigate, Link } from 'react-router-dom';
import { useAuth } from '../../utils/hooks/useSupabase';
import { reportError } from '../../utils/helpers';

function AdminLogin() {
    const navigate = useNavigate();
    const { signIn, user: authUser, isAuthenticated } = useAuth();
    
    try {
        const [formData, setFormData] = React.useState({
            email: '',
            password: '',
            rememberMe: false
        });

        const [loading, setLoading] = React.useState(false);
        const [error, setError] = React.useState(null);
        const [showPassword, setShowPassword] = React.useState(false);

        React.useEffect(() => {
            // Check if already authenticated
            if (isAuthenticated && authUser?.role === 'admin') {
                navigate('/admin');
                return;
            }
        }, [isAuthenticated, authUser, navigate]);

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
            setLoading(true);
            setError(null);
            
            try {
                // Authenticate user with Supabase
                const { user, error } = await signIn(formData.email, formData.password);
                
                if (error) {
                    setError('Invalid admin credentials');
                } else if (user && user.role === 'admin') {
                    navigate('/admin');
                } else {
                    setError('Access denied. Admin privileges required.');
                }
            } catch (error) {
                console.error('Login error:', error);
                setError('An error occurred during login. Please try again.');
            } finally {
                setLoading(false);
            }
        };

        const togglePasswordVisibility = () => {
            setShowPassword(!showPassword);
        };

        return (
            <div className="min-h-screen flex items-center justify-center bg-gray-100">
                <div className="max-w-md w-full mx-auto">
                    <div className="text-center mb-8">
                        <div className="flex justify-center mb-4">
                            <div className="h-12 w-12 bg-green-600 rounded-full flex items-center justify-center">
                                <i className="fas fa-seedling text-white text-2xl"></i>
                            </div>
                        </div>
                        <h2 className="text-3xl font-bold text-gray-900">Admin Login</h2>
                        <p className="mt-2 text-gray-600">Sign in to access admin dashboard</p>
                    </div>

                    <div className="bg-white rounded-lg shadow-sm p-6 mb-6">
                        {error && (
                            <div className="mb-4 p-3 bg-red-50 text-red-700 rounded-lg">
                                <p>{error}</p>
                            </div>
                        )}

                        <form onSubmit={handleSubmit} className="space-y-6">
                            <div>
                                <label htmlFor="email" className="block text-sm font-medium text-gray-700">
                                    Email address
                                </label>
                                <input
                                    id="email"
                                    name="email"
                                    type="email"
                                    value={formData.email}
                                    onChange={handleChange}
                                    className="mt-1 block w-full px-3 py-2 border border-gray-300 rounded-md shadow-sm focus:outline-none focus:ring-green-500 focus:border-green-500"
                                    required
                                />
                            </div>

                            <div>
                                <label htmlFor="password" className="block text-sm font-medium text-gray-700">
                                    Password
                                </label>
                                <div className="relative">
                                    <input
                                        id="password"
                                        name="password"
                                        type={showPassword ? 'text' : 'password'}
                                        value={formData.password}
                                        onChange={handleChange}
                                        className="mt-1 block w-full px-3 py-2 border border-gray-300 rounded-md shadow-sm focus:outline-none focus:ring-green-500 focus:border-green-500"
                                        required
                                    />
                                    <button
                                        type="button"
                                        className="absolute inset-y-0 right-0 pr-3 flex items-center"
                                        onClick={togglePasswordVisibility}
                                    >
                                        <i className={`fas ${showPassword ? 'fa-eye-slash' : 'fa-eye'} text-gray-400`}></i>
                                    </button>
                                </div>
                            </div>

                            <div className="flex items-center justify-between">
                                <div className="flex items-center">
                                    <input
                                        id="rememberMe"
                                        name="rememberMe"
                                        type="checkbox"
                                        checked={formData.rememberMe}
                                        onChange={handleChange}
                                        className="h-4 w-4 text-green-600 focus:ring-green-500 border-gray-300 rounded"
                                    />
                                    <label htmlFor="rememberMe" className="ml-2 block text-sm text-gray-700">
                                        Remember me
                                    </label>
                                </div>
                            </div>

                            <div>
                                <button
                                    type="submit"
                                    disabled={loading}
                                    className="w-full py-3 px-4 bg-green-600 hover:bg-green-700 text-white font-medium rounded-lg transition-colors duration-200 flex items-center justify-center"
                                >
                                    {loading ? (
                                        <div className="flex items-center">
                                            <i className="fas fa-spinner fa-spin mr-2"></i>
                                            Signing in...
                                        </div>
                                    ) : (
                                        'Sign In'
                                    )}
                                </button>
                            </div>
                        </form>

                        {process.env.NODE_ENV === 'development' && (
                            <div className="mt-6">
                                <div className="relative">
                                    <div className="absolute inset-0 flex items-center">
                                        <div className="w-full border-t border-gray-300"></div>
                                    </div>
                                    <div className="relative flex justify-center text-sm">
                                        <span className="px-2 bg-white text-gray-500">Development Credentials</span>
                                    </div>
                                </div>

                                <div className="mt-6">
                                    <div className="bg-gray-50 p-4 rounded-lg">
                                        <p className="text-sm text-gray-600">Email: admin@sharefoods.com</p>
                                        <p className="text-sm text-gray-600">Password: admin123</p>
                                        <p className="text-xs text-gray-500 mt-2">Note: These credentials are only visible in development mode</p>
                                    </div>
                                </div>
                            </div>
                        )}
                    </div>

                    <div className="text-center">
                        <Link to="/" className="text-sm font-medium text-green-600 hover:text-green-500">
                            <i className="fas fa-arrow-left mr-1"></i>
                            Return to main site
                        </Link>
                    </div>
                </div>
            </div>
        );
    } catch (error) {
        console.error('AdminLogin error:', error);
        reportError(error);
        return null;
    }
}

export default AdminLogin;
