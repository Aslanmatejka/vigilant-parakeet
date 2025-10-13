import { useNavigate } from "react-router-dom";
import Button from "../components/common/Button";
import ErrorBoundary from "../components/common/ErrorBoundary";

function HowItWorks() {
    const navigate = useNavigate();
    
    try {
        const steps = [
            {
                title: 'Create an Account',
                description: 'Sign up as a donor, recipient, or both. Complete your profile with necessary details.',
                icon: 'fa-user-plus'
            },
            {
                title: 'List or Find Food',
                description: 'Share your surplus food or browse available donations and trades in your area.',
                icon: 'fa-search'
            },
            {
                title: 'Connect & Arrange',
                description: 'Message other users to arrange pickup or delivery of food items.',
                icon: 'fa-comments'
            },
            {
                title: 'Complete the Exchange',
                description: 'Meet safely to exchange food items and confirm the transaction.',
                icon: 'fa-handshake'
            }
        ];

        const features = [
            {
                title: 'Smart Matching',
                description: 'AI-powered system connects donors with nearby recipients.',
                icon: 'fa-brain'
            },
            {
                title: 'Verified Users',
                description: 'Trust & safety measures ensure reliable exchanges.',
                icon: 'fa-shield-alt'
            },
            {
                title: 'Impact Tracking',
                description: 'Monitor your contribution to reducing food waste.',
                icon: 'fa-chart-line'
            }
        ];

        return (
            <ErrorBoundary>
                <div 
                    data-name="how-it-works" 
                    className="max-w-7xl mx-auto py-12 px-4"
                    role="main"
                >
                    <div className="text-center mb-16">
                        <h1 
                            className="text-4xl font-bold text-gray-900 mb-4"
                            id="page-title"
                        >
                            How ShareFoods Works
                        </h1>
                        <p className="text-xl text-gray-600 max-w-3xl mx-auto">
                            Join our community and start making a difference in reducing food waste
                            while helping those in need.
                        </p>
                    </div>

                    <section 
                        className="mb-20"
                        aria-labelledby="steps-heading"
                    >
                        <h2 
                            id="steps-heading" 
                            className="sr-only"
                        >
                            How to use ShareFoods
                        </h2>
                        <div 
                            className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-8"
                            role="list"
                            aria-label="Steps to use ShareFoods"
                        >
                            {steps.map((step, index) => (
                                <div 
                                    key={index} 
                                    className="relative"
                                    role="listitem"
                                >
                                    {index < steps.length - 1 && (
                                        <div 
                                            className="hidden lg:block absolute top-12 right-0 w-full border-t-2 border-dashed border-gray-200"
                                            aria-hidden="true"
                                        />
                                    )}
                                    <div className="relative bg-white p-6 rounded-lg shadow-sm text-center">
                                        <div 
                                            className="w-16 h-16 bg-green-100 rounded-full flex items-center justify-center mx-auto mb-4"
                                            aria-hidden="true"
                                        >
                                            <i className={`fas ${step.icon} text-2xl text-green-600`}></i>
                                        </div>
                                        <h3 className="text-xl font-semibold mb-2">
                                            {`Step ${index + 1}: ${step.title}`}
                                        </h3>
                                        <p className="text-gray-600">{step.description}</p>
                                    </div>
                                </div>
                            ))}
                        </div>
                    </section>

                    <section 
                        className="bg-gray-50 rounded-2xl p-12 mb-20"
                        aria-labelledby="features-heading"
                    >
                        <div className="text-center mb-12">
                            <h2 
                                id="features-heading"
                                className="text-3xl font-bold text-gray-900 mb-4"
                            >
                                Platform Features
                            </h2>
                            <p className="text-lg text-gray-600">
                                Advanced features to make food sharing easy and efficient
                            </p>
                        </div>

                        <div 
                            className="grid grid-cols-1 md:grid-cols-3 gap-8"
                            role="list"
                            aria-label="Platform features"
                        >
                            {features.map((feature, index) => (
                                <div 
                                    key={index} 
                                    className="bg-white p-6 rounded-lg shadow-sm"
                                    role="listitem"
                                >
                                    <div 
                                        className="w-12 h-12 bg-green-100 rounded-full flex items-center justify-center mb-4"
                                        aria-hidden="true"
                                    >
                                        <i className={`fas ${feature.icon} text-xl text-green-600`}></i>
                                    </div>
                                    <h3 className="text-lg font-semibold mb-2">{feature.title}</h3>
                                    <p className="text-gray-600">{feature.description}</p>
                                </div>
                            ))}
                        </div>
                    </section>

                    <section 
                        className="text-center"
                        aria-labelledby="cta-heading"
                    >
                        <h2 
                            id="cta-heading"
                            className="text-3xl font-bold text-gray-900 mb-8"
                        >
                            Ready to Get Started?
                        </h2>
                        <div className="flex justify-center space-x-4">
                            <Button
                                variant="primary"
                                size="lg"
                                onClick={() => navigate('/signup')}
                                aria-label="Create a new account"
                            >
                                <i className="fas fa-user-plus mr-2" aria-hidden="true"></i>
                                Sign Up Now
                            </Button>
                            <Button
                                variant="secondary"
                                size="lg"
                                onClick={() => {/* Add demo video functionality */}}
                                aria-label="Watch platform demonstration video"
                            >
                                <i className="fas fa-play mr-2" aria-hidden="true"></i>
                                Watch Demo
                            </Button>
                        </div>
                    </section>
                </div>
            </ErrorBoundary>
        );
    } catch (error) {
        console.error('HowItWorks page error:', error);
        return (
            <div className="text-center py-12" role="alert">
                <i className="fas fa-exclamation-circle text-red-500 text-4xl mb-4" aria-hidden="true"></i>
                <h2 className="text-xl font-bold mb-2">Something went wrong</h2>
                <p className="text-gray-600 mb-4">We&apos;re sorry, but there was an error loading this page.</p>
                <Button
                    variant="secondary"
                    onClick={() => window.location.reload()}
                >
                    Reload Page
                </Button>
            </div>
        );
    }
}

export default HowItWorks;
