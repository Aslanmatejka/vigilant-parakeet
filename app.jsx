import React from 'react';
import ClaimFoodForm from './pages/ClaimFoodForm.jsx';
import ReactDOM from 'react-dom/client';
import { BrowserRouter as Router, Routes, Route, Navigate, useNavigate } from 'react-router-dom';
import HomePage from './pages/HomePage';
import HowItWorks from './pages/HowItWorks';
import TermsOfService from './pages/TermsOfService';
import PrivacyPolicy from './pages/PrivacyPolicy';
import CookiesPolicy from './pages/CookiesPolicy';
import LoginPage from './pages/LoginPage';  
import MainLayout from './components/layout/MainLayout';
import './styles/main.css';
import './styles/components.css';
import ProfilePage from './pages/ProfilePage';
import UserDashboard from './pages/UserDashboard';
import ShareFoodPage from './pages/ShareFoodPage';
import CommunityPage from './pages/CommunityPage';
import UserSettings from './pages/UserSettings';
import Notifications from './pages/Notifications';
import UserListings from './pages/UserListings';
import FindFoodPage from './pages/FindFoodPage';
import NearMePage from './pages/NearMePage';
import Blog from './pages/Blog';
import Success from './pages/Success';
import SignupPage from './pages/SignupPage';
import AdminDashboard from './pages/admin/AdminDashboard.jsx';
import AdminLayout from './pages/admin/AdminLayout';
import AdminLogin from './pages/admin/AdminLogin';
import AdminProfile from './pages/admin/AdminProfile';
import AdminReports from './pages/admin/AdminReports';
import AdminSettings from './pages/admin/AdminSettings';
import ContentModeration from './pages/admin/ContentModeration.jsx';
import DistributionAttendees from './pages/admin/DistributionAttendees.jsx';
import FoodDistributionManagement from './pages/admin/FoodDistributionManagement.jsx';
import UserManagement from './pages/admin/UserManagement.jsx';
import { AuthProvider, useAuthContext } from './utils/AuthContext';
import { useAuth } from './utils/hooks/useSupabase';
import { GoodsProvider, useGoods } from './utils/stores/goodsStore.jsx';
import { reportError } from './utils/helpers';
import Button from './components/common/Button';
import AdminRoute from './components/admin/AdminRoute.jsx';
import ErrorBoundary from './components/common/ErrorBoundary';


function AppContent() {
    // You can add authentication logic here if needed
    // ProtectedRoute: Only allows access if authenticated
    const ProtectedRoute = ({ children }) => {
        const { isAuthenticated, loading } = useAuthContext();
        const navigate = useNavigate();
        React.useEffect(() => {
            if (!loading && !isAuthenticated) {
                navigate('/login');
            }
        }, [isAuthenticated, loading, navigate]);
        if (loading) return <div className="min-h-screen flex items-center justify-center"><div className="text-center"><div className="animate-spin rounded-full h-12 w-12 border-b-2 border-green-600 mx-auto mb-4"></div><p className="text-gray-600">Loading...</p></div></div>;
        return isAuthenticated ? children : null;
    };

    return (
        <MainLayout>
            <Routes>
                <Route path="/" element={<HomePage />} />
                <Route path="/login" element={<LoginPage />} />
                <Route path="/signup" element={<SignupPage />} />
                <Route path="/find" element={<ProtectedRoute><FindFoodPage /></ProtectedRoute>} />
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
                <Route path="/community" element={<ProtectedRoute><CommunityPage /></ProtectedRoute>} />
                <Route path="/settings" element={<ProtectedRoute><UserSettings /></ProtectedRoute>} />
                <Route path="/notifications" element={<ProtectedRoute><Notifications /></ProtectedRoute>} />
                <Route path="/listings" element={<ProtectedRoute><UserListings /></ProtectedRoute>} />
                <Route path="/admin" element={<AdminRoute><AdminDashboard /></AdminRoute>} />
                {/* Add more protected routes as needed */}
                <Route path="*" element={<div>Page Not Found</div>} />
            </Routes>
        </MainLayout>
    );
}


function App() {
    return (
        <ErrorBoundary>
            <AuthProvider>
                <GoodsProvider>
                    <React.Suspense fallback={<div className="min-h-screen flex items-center justify-center"><div className="text-center"><div className="animate-spin rounded-full h-12 w-12 border-b-2 border-green-600 mx-auto mb-4"></div><p className="text-gray-600">Loading...</p></div></div>}>
                        <AppContent />
                    </React.Suspense>
                </GoodsProvider>
            </AuthProvider>
        </ErrorBoundary>
    );
}

const root = ReactDOM.createRoot(document.getElementById('root'));
root.render(
    <React.StrictMode>
        <Router>
            <App />
        </Router>
    </React.StrictMode>
); 