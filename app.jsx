import React from 'react';
import { Routes, Route, Navigate, useNavigate, useLocation } from 'react-router-dom';
import ClaimFoodForm from './pages/ClaimFoodForm.jsx';
import HomePage from './pages/HomePage';
import HowItWorks from './pages/HowItWorks';
import TermsOfService from './pages/TermsOfService';
import PrivacyPolicy from './pages/PrivacyPolicy';
import CookiesPolicy from './pages/CookiesPolicy';
import LoginPage from './pages/LoginPage';
import MainLayout from './components/layout/MainLayout';
import ProfilePage from './pages/ProfilePage';
import UserDashboard from './pages/UserDashboard';
import ShareFoodPage from './pages/ShareFoodPage';
import UserSettings from './pages/UserSettings';
import Notifications from './pages/Notifications';
import UserListings from './pages/UserListings';
import UserReceipts from './pages/UserReceipts';
import FindFoodPage from './pages/FindFoodPage';
import NearMePage from './pages/NearMePage';
import Blog from './pages/Blog';
import Success from './pages/Success';
import SignupPage from './pages/SignupPage';
import EmailConfirmationPage from './pages/EmailConfirmationPage';
import ForgotPasswordPage from './pages/ForgotPasswordPage';
import ResetPasswordPage from './pages/ResetPasswordPage';
import SponsorsPage from './pages/SponsorsPage';
import ImpactStory from './pages/ImpactStory';
import TestimonialsPage from './pages/TestimonialsPage';
import NewsPage from './pages/NewsPage';
import FeaturedPage from './pages/FeaturedPage';
import RecipesPage from './pages/RecipesPage';
import DonationSchedules from './pages/DonationSchedules';
import FAQs from './pages/FAQs';
import ContactPage from './pages/ContactPage';
import DonatePage from './pages/DonatePage';
import CommunityDetailPage from './pages/CommunityDetailPage';
import AdminDashboard from './pages/admin/AdminDashboard.jsx';
import { TutorialProvider } from './utils/TutorialContext.jsx';
import DistributionAttendees from './pages/admin/DistributionAttendees.jsx';
import FoodDistributionManagement from './pages/admin/FoodDistributionManagement.jsx';
import UserManagement from './pages/admin/UserManagement.jsx';
import AdminSettings from './pages/admin/AdminSettings.jsx';
import AdminReports from './pages/admin/AdminReports.jsx';
import ImpactDataEntry from './pages/admin/ImpactDataEntry.jsx';
import ImpactContentManagement from './pages/admin/ImpactContentManagement.jsx';
import AdminMessages from './pages/admin/AdminMessages.jsx';
import AdminBroadcasts from './pages/admin/AdminBroadcasts.jsx';
import UserFeedback from './pages/admin/UserFeedback.jsx';
import VerificationManagement from './pages/admin/VerificationManagement.jsx';
import ApprovalCodeManagement from './pages/admin/ApprovalCodeManagement.jsx';
import CommunityManagement from './pages/admin/CommunityManagement.jsx';
import AdminShareFood from './pages/admin/AdminShareFood.jsx';
import { AuthProvider, useAuthContext } from './utils/AuthContext';
import { GoodsProvider } from './utils/stores/goodsStore.jsx';
import { MapProvider } from './utils/MapContext.jsx';
import { UIControlProvider } from './utils/UIControlContext.jsx';
import AdminRoute from './components/admin/AdminRoute.jsx';
import ErrorBoundary from './components/common/ErrorBoundary';

// ProtectedRoute defined outside AppContent to prevent remounts on every render
// Uses declarative <Navigate> instead of useEffect for synchronous, predictable redirects
const ProtectedRoute = ({ children }) => {
    const { isAuthenticated, loading, initialized } = useAuthContext();
    const currentLocation = useLocation();
    
    // If localStorage says authenticated, show page immediately (even during init)
    // This prevents the flash/redirect on page refresh
    if (isAuthenticated) {
        return children;
    }
    
    // Not authenticated per localStorage - wait for init to confirm
    if (loading || !initialized) {
        return (
            <div className="min-h-screen flex items-center justify-center">
                <div className="text-center">
                    <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-[#2CABE3] mx-auto mb-4"></div>
                    <p className="text-gray-600">Loading...</p>
                </div>
            </div>
        );
    }
    
    // Init complete and still not authenticated - redirect to login
    const redirectPath = currentLocation.pathname + currentLocation.search;
    return <Navigate to={`/login?redirect=${encodeURIComponent(redirectPath)}`} replace />;
};

function AppContent() {
    const location = useLocation();
    const navigate = useNavigate();
    
    // Scroll to top on route change (handles forward navigation, back button, and all route changes)
    React.useEffect(() => {
        // Don't scroll if there's a hash (user wants to go to a specific section)
        if (location.hash) {
            // Let the browser handle hash navigation
            const element = document.getElementById(location.hash.slice(1));
            if (element) {
                setTimeout(() => element.scrollIntoView({ behavior: 'smooth' }), 0);
            }
            return;
        }
        
        // Use setTimeout to ensure the scroll happens after React finishes rendering
        const scrollTimeout = setTimeout(() => {
            window.scrollTo({
                top: 0,
                left: 0,
                behavior: 'instant' // Use 'instant' to avoid smooth scroll conflicts
            });
        }, 0);
        
        return () => clearTimeout(scrollTimeout);
    }, [location.pathname, location.search, location.hash]);

    return (
        <UIControlProvider navigate={navigate}>
        <MainLayout>
            <Routes>
                <Route path="/" element={<HomePage />} />
                <Route path="/community/:id" element={<CommunityDetailPage />} />
                <Route path="/login" element={<LoginPage />} />
                <Route path="/signup" element={<SignupPage />} />
                <Route path="/email-confirmation" element={<EmailConfirmationPage />} />
                <Route path="/forgot-password" element={<ForgotPasswordPage />} />
                <Route path="/reset-password" element={<ResetPasswordPage />} />
                <Route path="/impact-story" element={<ImpactStory />} />
                <Route path="/news" element={<NewsPage />} />
                <Route path="/featured" element={<FeaturedPage />} />
                <Route path="/testimonials" element={<TestimonialsPage />} />
                <Route path="/recipes" element={<RecipesPage />} />
                <Route path="/sponsors" element={<SponsorsPage />} />
                <Route path="/faqs" element={<FAQs />} />
                <Route path="/contact" element={<ContactPage />} />
                <Route path="/donate" element={<DonatePage />} />
                <Route path="/find" element={<FindFoodPage />} />
                <Route path="/near-me" element={<ProtectedRoute><NearMePage /></ProtectedRoute>} />
                <Route path="/blog" element={<ProtectedRoute><Blog /></ProtectedRoute>} />
                <Route path="/success" element={<ProtectedRoute><Success /></ProtectedRoute>} />
                <Route path="/how-it-works" element={<ProtectedRoute><HowItWorks /></ProtectedRoute>} />
                <Route path="/terms" element={<ProtectedRoute><TermsOfService /></ProtectedRoute>} />
                <Route path="/privacy" element={<ProtectedRoute><PrivacyPolicy /></ProtectedRoute>} />
                <Route path="/cookies" element={<ProtectedRoute><CookiesPolicy /></ProtectedRoute>} />
                <Route path="/profile" element={<ProtectedRoute><ProfilePage /></ProtectedRoute>} />
                <Route path="/dashboard" element={<ProtectedRoute><UserDashboard /></ProtectedRoute>} />
                <Route path="/share" element={<ProtectedRoute><ShareFoodPage /></ProtectedRoute>} />
                <Route path="/claim" element={<ProtectedRoute><ClaimFoodForm /></ProtectedRoute>} />
                <Route path="/settings" element={<ProtectedRoute><UserSettings /></ProtectedRoute>} />
                <Route path="/notifications" element={<ProtectedRoute><Notifications /></ProtectedRoute>} />
                <Route path="/listings" element={<ProtectedRoute><UserListings /></ProtectedRoute>} />
                <Route path="/receipts" element={<ProtectedRoute><UserReceipts /></ProtectedRoute>} />
                <Route path="/donations" element={<ProtectedRoute><DonationSchedules /></ProtectedRoute>} />
                <Route path="/admin" element={<AdminRoute><AdminDashboard /></AdminRoute>} />
                <Route path="/admin/users" element={<AdminRoute><UserManagement /></AdminRoute>} />
                <Route path="/admin/distribution" element={<AdminRoute><FoodDistributionManagement /></AdminRoute>} />
                <Route path="/admin/attendees" element={<AdminRoute><DistributionAttendees /></AdminRoute>} />
                <Route path="/admin/settings" element={<AdminRoute><AdminSettings /></AdminRoute>} />
                <Route path="/admin/reports" element={<AdminRoute><AdminReports /></AdminRoute>} />
                <Route path="/admin/impact" element={<AdminRoute><ImpactDataEntry /></AdminRoute>} />
                <Route path="/admin/impact-content" element={<AdminRoute><ImpactContentManagement /></AdminRoute>} />
                <Route path="/admin/messages" element={<AdminRoute><AdminMessages /></AdminRoute>} />
                <Route path="/admin/broadcasts" element={<AdminRoute><AdminBroadcasts /></AdminRoute>} />
                <Route path="/admin/feedback" element={<AdminRoute><UserFeedback /></AdminRoute>} />
                <Route path="/admin/verifications" element={<AdminRoute><VerificationManagement /></AdminRoute>} />
                <Route path="/admin/approval-codes" element={<AdminRoute><ApprovalCodeManagement /></AdminRoute>} />
                <Route path="/admin/communities" element={<AdminRoute><CommunityManagement /></AdminRoute>} />
                <Route path="/admin/share-food" element={<AdminRoute><AdminShareFood /></AdminRoute>} />
                <Route path="*" element={<div>Page Not Found</div>} />
            </Routes>
        </MainLayout>
        </UIControlProvider>
    );
}

export default function App() {
    return (
        <ErrorBoundary>
            <AuthProvider>
                <GoodsProvider>
                    <TutorialProvider>
                        <MapProvider>
                            <React.Suspense fallback={<div className="min-h-screen flex items-center justify-center"><div className="text-center"><div className="animate-spin rounded-full h-12 w-12 border-b-2 border-[#2CABE3] mx-auto mb-4"></div><p className="text-gray-600">Loading...</p></div></div>}>
                                <AppContent />
                            </React.Suspense>
                        </MapProvider>
                    </TutorialProvider>
                </GoodsProvider>
            </AuthProvider>
        </ErrorBoundary>
    );
} 
