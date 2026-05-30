import React from "react";
import { useNavigate, Link } from "react-router-dom";
import { useAuthContext } from "../utils/AuthContext";
import ErrorBoundary from "../components/common/ErrorBoundary";
import Button from "../components/common/Button";
import supabase from "../utils/supabaseClient";

function SignupPageContent() {
    const navigate = useNavigate();
    const { signUp, loading } = useAuthContext();
    const [formData, setFormData] = React.useState({
        name: '',
        email: '',
        phone: '',
        approvalNumber: '',
        password: '',
        confirmPassword: '',
        agreeToTerms: false,
        smsOptIn: false
    });

    const [errors, setErrors] = React.useState({});
    const [submitting, setSubmitting] = React.useState(false);

    React.useEffect(() => {
        // Scroll to top when page loads
        window.scrollTo(0, 0);
    }, []);

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
        
        if (!formData.approvalNumber.trim()) {
            newErrors.approvalNumber = 'Approval number is required';
        } else if (!/^[A-Za-z]{3}\d{6}$/.test(formData.approvalNumber.trim())) {
            newErrors.approvalNumber = 'Approval number must be 3 letters followed by 6 digits (e.g. RBE123456)';
        }
        
        // Validate phone if SMS opt-in is checked
        if (formData.smsOptIn) {
            if (!formData.phone.trim()) {
                newErrors.phone = 'Phone number is required for SMS notifications';
            } else if (!/^\+?[1-9]\d{1,14}$/.test(formData.phone.replace(/[\s()-]/g, ''))) {
                newErrors.phone = 'Invalid phone number format (use format: +1234567890)';
            }
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
        
        if (!validateForm() || submitting) {
            return;
        }

        setSubmitting(true);
        try {
            // Validate the approval code against the database.
            // Plain REST fetch (with 6s timeout) so a hung Supabase JS client doesn't freeze signup.
            const codeValue = formData.approvalNumber.trim().toUpperCase();
            const supabaseUrl = import.meta.env.VITE_SUPABASE_URL;
            const supabaseKey = import.meta.env.VITE_SUPABASE_ANON_KEY;
            let codeRecord = null;
            try {
                const controller = new AbortController();
                const timer = setTimeout(() => controller.abort(), 6000);
                const resp = await fetch(
                    `${supabaseUrl}/rest/v1/approval_codes?select=*&code=eq.${encodeURIComponent(codeValue)}&limit=1`,
                    {
                        headers: {
                            'apikey': supabaseKey,
                            'Authorization': `Bearer ${supabaseKey}`,
                            'Accept': 'application/json',
                        },
                        signal: controller.signal,
                    }
                );
                clearTimeout(timer);
                if (resp.ok) {
                    const rows = await resp.json();
                    codeRecord = Array.isArray(rows) && rows.length > 0 ? rows[0] : null;
                }
            } catch (e) {
                console.warn('Approval code lookup failed:', e);
            }

            if (!codeRecord) {
                setErrors({ approvalNumber: 'Approval number is invalid. Please double check that it was entered correctly. If that doesn\'t work, contact your school community closet representative to get a new approval number.' });
                return;
            }

            if (codeRecord.is_claimed) {
                setErrors({ approvalNumber: 'This approval number has already been used. Please contact your school community closet representative to get a new approval number.' });
                return;
            }

            const userData = {
                email: formData.email.toLowerCase().trim(),
                password: formData.password,
                options: {
                    data: {
                        name: formData.name.trim(),
                        approval_number: codeValue,
                        community_id: codeRecord.community_id,
                        phone: formData.phone.trim() || null,
                        sms_opt_in: formData.smsOptIn,
                        sms_opt_in_date: formData.smsOptIn ? new Date().toISOString() : null,
                        sms_notifications_enabled: formData.smsOptIn
                    }
                }
            };

            const { user, session, error } = await signUp(userData);
            
            if (error) {
                console.error('Detailed signup error:', error);
                setErrors({ form: error.message || 'Error during signup. Please try again.' });
                return;
            }

            if (user) {
                // Mark the approval code as claimed — fire-and-forget so it never blocks navigation.
                // Admin can reconcile if this fails. Cannot block on this: the JS client is known to hang.
                supabase
                    .from('approval_codes')
                    .update({
                        is_claimed: true,
                        claimed_by: user.id,
                        claimed_at: new Date().toISOString()
                    })
                    .eq('code', codeValue)
                    .then(({ error: claimErr }) => {
                        if (claimErr) console.warn('Failed to mark approval code as claimed:', claimErr);
                    });

                if (session) {
                    // User was auto-confirmed (no email confirmation required)
                    navigate('/login', { 
                        state: { message: 'Account created successfully! Please sign in.' },
                        replace: true 
                    });
                } else {
                    // Email confirmation required
                    navigate('/email-confirmation', { 
                        state: { email: formData.email.toLowerCase().trim() },
                        replace: true 
                    });
                }
            }
        } catch (error) {
            console.error('Signup error:', error);
            setErrors({ form: error.message || 'An unexpected error occurred. Please try again.' });
        } finally {
            setSubmitting(false);
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
                        <div className="h-12 w-12 bg-primary-600 rounded-full flex items-center justify-center">
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
                                className={`w-full px-4 py-2 rounded-lg border focus:outline-none focus:ring-2 focus:ring-primary-500 ${errors.name ? 'border-red-500' : 'border-gray-300'}`}
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
                                className={`w-full px-4 py-2 rounded-lg border focus:outline-none focus:ring-2 focus:ring-primary-500 ${errors.email ? 'border-red-500' : 'border-gray-300'}`}
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
                            <label htmlFor="approvalNumber" className="block text-sm font-medium text-gray-700 mb-1">
                                Approval Number <span className="text-red-500" aria-hidden="true">*</span>
                            </label>
                            <input
                                id="approvalNumber"
                                name="approvalNumber"
                                type="text"
                                value={formData.approvalNumber}
                                onChange={handleChange}
                                className={`w-full px-4 py-2 rounded-lg border focus:outline-none focus:ring-2 focus:ring-primary-500 ${errors.approvalNumber ? 'border-red-500' : 'border-gray-300'}`}
                                placeholder="e.g. RBE123456"
                                aria-required="true"
                                aria-invalid={!!errors.approvalNumber}
                                aria-describedby="approval-number-description approval-number-error"
                            />
                            <p id="approval-number-description" className="mt-2 text-sm text-gray-600">
                                You should have received an approval number from your school community closet contact. If you do not have this number, please speak to your school to get this approval number before signing up. An approval number is required to claim food from our community closets.
                            </p>
                            {errors.approvalNumber && (
                                <p id="approval-number-error" className="mt-1 text-sm text-red-500" role="alert">{errors.approvalNumber}</p>
                            )}
                        </div>

                        <div>
                            <label htmlFor="phone" className="block text-sm font-medium text-gray-700 mb-1">
                                Phone Number {formData.smsOptIn && <span className="text-red-500" aria-hidden="true">*</span>}
                            </label>
                            <input
                                id="phone"
                                name="phone"
                                type="tel"
                                value={formData.phone}
                                onChange={handleChange}
                                className={`w-full px-4 py-2 rounded-lg border focus:outline-none focus:ring-2 focus:ring-[#2CABE3] ${errors.phone ? 'border-red-500' : 'border-gray-300'}`}
                                placeholder="+1234567890 or (123) 456-7890"
                                aria-required={formData.smsOptIn}
                                aria-invalid={!!errors.phone}
                                aria-describedby="phone-description phone-error"
                            />
                            <p id="phone-description" className="mt-2 text-sm text-gray-600">
                                Optional. Provide your phone number to receive SMS notifications about food claims and pickups.
                            </p>
                            {errors.phone && (
                                <p id="phone-error" className="mt-1 text-sm text-red-500" role="alert">{errors.phone}</p>
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
                                className={`w-full px-4 py-2 rounded-lg border focus:outline-none focus:ring-2 focus:ring-primary-500 ${errors.password ? 'border-red-500' : 'border-gray-300'}`}
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
                                className={`w-full px-4 py-2 rounded-lg border focus:outline-none focus:ring-2 focus:ring-primary-500 ${errors.confirmPassword ? 'border-red-500' : 'border-gray-300'}`}
                                placeholder="Confirm your password"
                                aria-required="true"
                                aria-invalid={!!errors.confirmPassword}
                                aria-describedby={errors.confirmPassword ? "confirm-password-error" : undefined}
                            />
                            {errors.confirmPassword && (
                                <p id="confirm-password-error" className="mt-1 text-sm text-red-500" role="alert">{errors.confirmPassword}</p>
                            )}
                        </div>

                        <div className="border-t border-gray-200 pt-4">
                            <div className="flex items-start mb-4">
                                <div className="flex items-center h-5">
                                    <input
                                        id="smsOptIn"
                                        name="smsOptIn"
                                        type="checkbox"
                                        checked={formData.smsOptIn}
                                        onChange={handleChange}
                                        className="h-4 w-4 text-[#2CABE3] focus:ring-[#2CABE3] border-gray-300 rounded"
                                        aria-describedby="sms-opt-in-description"
                                    />
                                </div>
                                <div className="ml-3">
                                    <label htmlFor="smsOptIn" className="text-sm font-medium text-gray-700">
                                        Send me SMS notifications <span className="text-gray-500">(Optional)</span>
                                    </label>
                                    <p id="sms-opt-in-description" className="mt-1 text-xs text-gray-600">
                                        By checking this box, you consent to receive SMS text messages from DoGoods about food claims, pickup reminders, and important updates. 
                                        Message and data rates may apply. You can opt out at any time in your profile settings. 
                                        By providing your phone number and opting in, you agree to our <Link to="/terms" className="text-[#2CABE3] hover:underline">SMS Terms of Service</Link>.
                                    </p>
                                </div>
                            </div>
                        </div>

                        <div className="flex items-start">
                            <div className="flex items-center h-5">
                                <input
                                    id="agreeToTerms"
                                    name="agreeToTerms"
                                    type="checkbox"
                                    checked={formData.agreeToTerms}
                                    onChange={handleChange}
                                    className="h-4 w-4 text-primary-600 focus:ring-primary-500 border-gray-300 rounded"
                                    aria-required="true"
                                    aria-invalid={!!errors.agreeToTerms}
                                    aria-describedby={errors.agreeToTerms ? "terms-error" : undefined}
                                />
                            </div>
                            <div className="ml-3 text-sm">
                                <label htmlFor="agreeToTerms" className="text-gray-700">
                                    I agree to the {' '}
                                    <Link to="/terms" className="text-primary-600 hover:text-primary-500">
                                        Terms of Service
                                    </Link>
                                    {' '} and {' '}
                                    <Link to="/privacy" className="text-primary-600 hover:text-primary-500">
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
                                disabled={submitting}
                                variant="primary"
                                className="w-full"
                            >
                                {submitting ? (
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
                        <Link to="/login" className="text-primary-600 hover:text-primary-500 font-medium">
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