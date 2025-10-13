import React from "react";
import Card from "../components/common/Card";
import Input from "../components/common/Input";
import Button from "../components/common/Button";
import { useAuth } from "../utils/hooks/useSupabase";

function UserSettings() {
    const { user: authUser, isAuthenticated, updateProfile } = useAuth();
    
    const [loading, setLoading] = React.useState(false);
    const [error, setError] = React.useState(null);
    const [showDeleteConfirm, setShowDeleteConfirm] = React.useState(false);
    const [formData, setFormData] = React.useState({
        name: '',
        email: '',
        notifications: {
            email: false,
            push: false
        },
        privacy: {
            profileVisibility: false,
            locationSharing: false
        }
    });
    const [successMessage, setSuccessMessage] = React.useState('');

    React.useEffect(() => {
        if (authUser) {
            setFormData({
                name: authUser.name || '',
                email: authUser.email || '',
                notifications: authUser.notifications || {
                    email: false,
                    push: false
                },
                privacy: authUser.privacy || {
                    profileVisibility: false,
                    locationSharing: false
                }
            });
        }
    }, [authUser]);

    const handleInputChange = (field, value) => {
        setFormData(prev => ({
            ...prev,
            [field]: value
        }));
    };

    const handleNestedInputChange = (category, field, value) => {
        setFormData(prev => ({
            ...prev,
            [category]: {
                ...prev[category],
                [field]: value
            }
        }));
    };

    const handleCheckboxChange = (section, field) => {
        setFormData(prev => ({
            ...prev,
            [section]: {
                ...prev[section],
                [field]: !prev[section][field]
            }
        }));
    };

    const handleSaveSettings = async (section) => {
        setLoading(true);
        setError(null);
        setSuccessMessage('');
        
        try {
            // Update user profile in Supabase
            if (updateProfile) {
                await updateProfile(formData);
            }
            
            setSuccessMessage(`${section} settings saved successfully`);
            
            // Clear success message after 3 seconds
            setTimeout(() => {
                setSuccessMessage('');
            }, 3000);
        } catch (error) {
            console.error('Save settings error:', error);
            setError('Failed to save settings. Please try again.');
        } finally {
            setLoading(false);
        }
    };

    const handleDeleteAccount = async () => {
        setLoading(true);
        try {
            // In a real app, this would delete the account from Supabase
            // For now, just show success message
            setSuccessMessage('Account deletion initiated. Please contact support for confirmation.');
            setTimeout(() => {
                setSuccessMessage('');
            }, 3000);
        } catch (error) {
            console.error('Delete account error:', error);
            setError('Failed to delete account. Please try again.');
        } finally {
            setLoading(false);
            setShowDeleteConfirm(false);
        }
    };

    if (!isAuthenticated) {
        return (
            <div className="text-center py-12" role="status" aria-busy="true">
                <div className="animate-spin rounded-full h-12 w-12 border-t-2 border-b-2 border-green-500 mx-auto"></div>
                <div className="sr-only">Loading user settings...</div>
                <p className="mt-4 text-gray-600" aria-live="polite">Loading user settings...</p>
            </div>
        );
    }

    return (
        <div className="max-w-4xl mx-auto py-8 px-4">
            <h1 className="text-3xl font-bold text-gray-900 mb-8">Settings</h1>

            {error && (
                <div 
                    className="mb-6 bg-red-50 border border-red-200 text-red-700 px-4 py-3 rounded relative" 
                    role="alert"
                >
                    <i className="fas fa-exclamation-circle mr-2" aria-hidden="true"></i>
                    {error}
                </div>
            )}

            {successMessage && (
                <div 
                    className="mb-6 bg-green-50 border border-green-200 text-green-700 px-4 py-3 rounded relative"
                    role="status"
                >
                    <i className="fas fa-check-circle mr-2" aria-hidden="true"></i>
                    {successMessage}
                </div>
            )}

            <div className="space-y-6">
                {/* Account Settings */}
                <Card>
                    <div className="p-6">
                        <h2 className="text-xl font-semibold mb-6">Account Settings</h2>
                        <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                            <Input
                                label="Email"
                                value={formData.email}
                                disabled
                                aria-label="Email address"
                            />
                            <Input
                                label="Display Name"
                                value={formData.name}
                                onChange={(e) => handleInputChange('name', e.target.value)}
                                aria-label="Display name"
                            />
                        </div>
                        <div className="mt-6 flex justify-end">
                            <Button
                                variant="primary"
                                onClick={() => handleSaveSettings('Account')}
                                disabled={loading}
                                aria-label="Save account settings"
                            >
                                {loading ? 'Saving...' : 'Save Changes'}
                            </Button>
                        </div>
                    </div>
                </Card>

                {/* Notification Settings */}
                <Card>
                    <div className="p-6">
                        <h2 className="text-xl font-semibold mb-6">Notification Settings</h2>
                        <div className="space-y-4" role="group" aria-labelledby="notification-settings">
                            <div className="flex items-center">
                                <input
                                    type="checkbox"
                                    id="emailNotifications"
                                    checked={formData.notifications.email}
                                    onChange={() => handleCheckboxChange('notifications', 'email')}
                                    className="h-4 w-4 text-green-600 focus:ring-green-500 border-gray-300 rounded"
                                    aria-label="Enable email notifications"
                                />
                                <label htmlFor="emailNotifications" className="ml-2 block text-sm text-gray-900">
                                    Email Notifications
                                </label>
                            </div>
                            <div className="flex items-center">
                                <input
                                    type="checkbox"
                                    id="pushNotifications"
                                    checked={formData.notifications.push}
                                    onChange={() => handleCheckboxChange('notifications', 'push')}
                                    className="h-4 w-4 text-green-600 focus:ring-green-500 border-gray-300 rounded"
                                    aria-label="Enable push notifications"
                                />
                                <label htmlFor="pushNotifications" className="ml-2 block text-sm text-gray-900">
                                    Push Notifications
                                </label>
                            </div>
                        </div>
                        <div className="mt-6 flex justify-end">
                            <Button
                                variant="primary"
                                onClick={() => handleSaveSettings('Notification')}
                                disabled={loading}
                                aria-label="Save notification settings"
                            >
                                {loading ? 'Saving...' : 'Save Changes'}
                            </Button>
                        </div>
                    </div>
                </Card>

                {/* Privacy Settings */}
                <Card>
                    <div className="p-6">
                        <h2 className="text-xl font-semibold mb-6">Privacy Settings</h2>
                        <div className="space-y-4" role="group" aria-labelledby="privacy-settings">
                            <div className="flex items-center">
                                <input
                                    type="checkbox"
                                    id="profileVisibility"
                                    checked={formData.privacy.profileVisibility}
                                    onChange={() => handleCheckboxChange('privacy', 'profileVisibility')}
                                    className="h-4 w-4 text-green-600 focus:ring-green-500 border-gray-300 rounded"
                                    aria-label="Make profile visible to other users"
                                />
                                <label htmlFor="profileVisibility" className="ml-2 block text-sm text-gray-900">
                                    Make profile visible to other users
                                </label>
                            </div>
                            <div className="flex items-center">
                                <input
                                    type="checkbox"
                                    id="locationSharing"
                                    checked={formData.privacy.locationSharing}
                                    onChange={() => handleCheckboxChange('privacy', 'locationSharing')}
                                    className="h-4 w-4 text-green-600 focus:ring-green-500 border-gray-300 rounded"
                                    aria-label="Share location with food listings"
                                />
                                <label htmlFor="locationSharing" className="ml-2 block text-sm text-gray-900">
                                    Share location with food listings
                                </label>
                            </div>
                        </div>
                        <div className="mt-6 flex justify-end">
                            <Button
                                variant="primary"
                                onClick={() => handleSaveSettings('Privacy')}
                                disabled={loading}
                                aria-label="Save privacy settings"
                            >
                                {loading ? 'Saving...' : 'Save Changes'}
                            </Button>
                        </div>
                    </div>
                </Card>

                {/* Danger Zone */}
                <Card>
                    <div className="p-6">
                        <h2 className="text-xl font-semibold mb-6 text-red-600">Danger Zone</h2>
                        <div className="space-y-4">
                            <Button
                                variant="danger"
                                onClick={() => setShowDeleteConfirm(true)}
                                aria-label="Delete account"
                            >
                                Delete Account
                            </Button>
                        </div>
                    </div>
                </Card>
            </div>

            {/* Delete Account Confirmation Modal */}
            {showDeleteConfirm && (
                <div 
                    className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center p-4"
                    role="dialog"
                    aria-labelledby="delete-account-title"
                    aria-describedby="delete-account-description"
                >
                    <div className="bg-white rounded-lg p-6 max-w-sm w-full">
                        <h3 id="delete-account-title" className="text-lg font-semibold mb-4">
                            Delete Account
                        </h3>
                        <p id="delete-account-description" className="text-gray-600 mb-6">
                            Are you sure you want to delete your account? This action cannot be undone.
                        </p>
                        <div className="flex justify-end space-x-4">
                            <Button
                                variant="secondary"
                                onClick={() => setShowDeleteConfirm(false)}
                                disabled={loading}
                                aria-label="Cancel account deletion"
                            >
                                Cancel
                            </Button>
                            <Button
                                variant="danger"
                                onClick={handleDeleteAccount}
                                disabled={loading}
                                aria-label="Confirm account deletion"
                            >
                                {loading ? 'Deleting...' : 'Delete Account'}
                            </Button>
                        </div>
                    </div>
                </div>
            )}
        </div>
    );
}

export default UserSettings;
