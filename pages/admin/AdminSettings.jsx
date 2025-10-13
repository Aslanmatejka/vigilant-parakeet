import React from 'react';
import AdminLayout from './AdminLayout';
import Button from '../../components/common/Button';
import Card from '../../components/common/Card';
import { reportError } from '../../utils/helpers';
import { toast } from 'react-toastify';
import { useAuth } from '../../utils/hooks/useSupabase';

function AdminSettings() {
    const { user: authUser, isAdmin } = useAuth();
    
    try {
        const [loading, setLoading] = React.useState(false);
        const [success, setSuccess] = React.useState(null);
        const [error, setError] = React.useState(null);
        const [maintenanceMode, setMaintenanceMode] = React.useState(false);
        const [settings, setSettings] = React.useState({
            general: {
                siteName: 'ShareFoods',
                siteDescription: 'A community-driven platform designed to reduce food waste and combat hunger by connecting individuals, businesses, and organizations.',
                contactEmail: 'contact@sharefoods.com',
                supportPhone: '(123) 456-7890'
            },
            notifications: {
                enableEmailNotifications: true,
                enablePushNotifications: false,
                adminAlertEmails: 'admin@sharefoods.com,alerts@sharefoods.com',
                dailyDigest: true,
                weeklyReport: true
            },
            listings: {
                requireApproval: false,
                maxImagesPerListing: 5,
                maxActiveDaysDefault: 7,
                allowedCategories: 'produce,dairy,bakery,pantry,meat,prepared',
                enableFoodSafetyGuidelines: true
            },
            users: {
                requireEmailVerification: true,
                allowGuestBrowsing: true,
                defaultUserRole: 'user',
                accountDeletionPolicy: 'soft-delete'
            },
            privacy: {
                dataRetentionDays: 180,
                showUserProfiles: true,
                maskUserContact: true,
                allowLocationSharing: true
            }
        });

        // Load initial settings
        React.useEffect(() => {
            loadSettings();
        }, []);

        const loadSettings = async () => {
            try {
                // For now, use default settings since we don't have a settings table
                // In a real app, you would fetch from Supabase settings table
                setSettings(settings);
                setMaintenanceMode(false);
            } catch (error) {
                console.error('Load settings error:', error);
                toast.error('Failed to load settings');
            }
        };

        const validateSettings = (section) => {
            const errors = [];
            
            switch (section) {
                case 'general':
                    if (!settings.general.siteName.trim()) {
                        errors.push('Site name is required');
                    }
                    if (!settings.general.contactEmail.trim() || 
                        !/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(settings.general.contactEmail)) {
                        errors.push('Valid contact email is required');
                    }
                    break;
                    
                case 'notifications':
                    if (settings.notifications.adminAlertEmails) {
                        const emails = settings.notifications.adminAlertEmails.split(',');
                        const invalidEmails = emails.filter(email => 
                            !/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email.trim())
                        );
                        if (invalidEmails.length > 0) {
                            errors.push('Invalid admin alert email(s)');
                        }
                    }
                    break;
                    
                case 'listings':
                    if (settings.listings.maxImagesPerListing < 1 || 
                        settings.listings.maxImagesPerListing > 10) {
                        errors.push('Max images must be between 1 and 10');
                    }
                    if (settings.listings.maxActiveDaysDefault < 1 || 
                        settings.listings.maxActiveDaysDefault > 30) {
                        errors.push('Max active days must be between 1 and 30');
                    }
                    break;
                    
                case 'privacy':
                    if (settings.privacy.dataRetentionDays < 30) {
                        errors.push('Data retention period must be at least 30 days');
                    }
                    break;
            }
            
            return errors;
        };

        const handleSaveSettings = async (section) => {
            const errors = validateSettings(section);
            if (errors.length > 0) {
                errors.forEach(error => toast.error(error));
                return;
            }

            setLoading(true);
            setSuccess(null);
            setError(null);
            
            try {
                // For now, just show success since we don't have a settings table
                // In a real app, you would save to Supabase settings table
                toast.success(`${section.charAt(0).toUpperCase() + section.slice(1)} settings saved successfully`);
            } catch (err) {
                console.error('Save settings error:', err);
                toast.error('Failed to save settings. Please try again.');
            } finally {
                setLoading(false);
            }
        };

        // System maintenance functions
        const handleBackupDatabase = async () => {
            try {
                setLoading(true);
                // In a real app, you would trigger Supabase backup
                toast.success('Database backup initiated successfully');
            } catch (error) {
                console.error('Database backup error:', error);
                toast.error('Failed to initiate database backup');
            } finally {
                setLoading(false);
            }
        };

        const handleCleanupListings = async () => {
            try {
                setLoading(true);
                // In a real app, you would cleanup expired listings in Supabase
                toast.success('Expired listings cleanup completed');
            } catch (error) {
                console.error('Cleanup error:', error);
                toast.error('Failed to cleanup expired listings');
            } finally {
                setLoading(false);
            }
        };

        const handleClearCache = async () => {
            try {
                setLoading(true);
                // In a real app, you would clear application cache
                toast.success('Cache cleared successfully');
            } catch (error) {
                console.error('Cache clear error:', error);
                toast.error('Failed to clear cache');
            } finally {
                setLoading(false);
            }
        };

        const handleMaintenanceMode = async () => {
            try {
                setLoading(true);
                // In a real app, you would update maintenance mode in Supabase
                setMaintenanceMode(!maintenanceMode);
                toast.success(`Maintenance mode ${!maintenanceMode ? 'enabled' : 'disabled'}`);
            } catch (error) {
                console.error('Maintenance mode error:', error);
                toast.error('Failed to update maintenance mode');
            } finally {
                setLoading(false);
            }
        };

        const handleInputChange = (section, field, value) => {
            setSettings(prev => ({
                ...prev,
                [section]: {
                    ...prev[section],
                    [field]: value
                }
            }));
        };

        const handleCheckboxChange = (section, field) => {
            setSettings(prev => ({
                ...prev,
                [section]: {
                    ...prev[section],
                    [field]: !prev[section][field]
                }
            }));
        };

        return (
            <AdminLayout active="settings">
                <div data-name="admin-settings" className="max-w-7xl mx-auto py-8 px-4 sm:px-6 lg:px-8">
                    <div className="mb-8">
                        <h1 className="text-3xl font-bold text-gray-900">Settings</h1>
                        <p className="mt-2 text-gray-600">
                            Configure platform settings and preferences
                        </p>
                    </div>

                    {maintenanceMode && (
                        <div className="mb-6 bg-yellow-50 border border-yellow-200 text-yellow-700 px-4 py-3 rounded relative">
                            <span className="block sm:inline">
                                <i className="fas fa-exclamation-triangle mr-2"></i>
                                Site is currently in maintenance mode
                            </span>
                        </div>
                    )}

                    {success && (
                        <div className="mb-6 bg-green-50 border border-green-200 text-green-700 px-4 py-3 rounded relative">
                            <span className="block sm:inline">{success}</span>
                        </div>
                    )}
                    
                    {error && (
                        <div className="mb-6 bg-red-50 border border-red-200 text-red-700 px-4 py-3 rounded relative">
                            <span className="block sm:inline">{error}</span>
                        </div>
                    )}

                    <div className="space-y-6">
                        {/* General Settings */}
                        <Card>
                            <div className="p-6">
                                <h2 className="text-lg font-semibold mb-6">General Settings</h2>
                                <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                                    <div>
                                        <label className="block text-sm font-medium text-gray-700 mb-1">
                                            Site Name
                                        </label>
                                        <input
                                            type="text"
                                            className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-green-500 focus:border-transparent"
                                            value={settings.general.siteName}
                                            onChange={(e) => handleInputChange('general', 'siteName', e.target.value)}
                                        />
                                    </div>
                                    <div>
                                        <label className="block text-sm font-medium text-gray-700 mb-1">
                                            Contact Email
                                        </label>
                                        <input
                                            type="email"
                                            className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-green-500 focus:border-transparent"
                                            value={settings.general.contactEmail}
                                            onChange={(e) => handleInputChange('general', 'contactEmail', e.target.value)}
                                        />
                                    </div>
                                    <div>
                                        <label className="block text-sm font-medium text-gray-700 mb-1">
                                            Support Phone
                                        </label>
                                        <input
                                            type="text"
                                            className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-green-500 focus:border-transparent"
                                            value={settings.general.supportPhone}
                                            onChange={(e) => handleInputChange('general', 'supportPhone', e.target.value)}
                                        />
                                    </div>
                                    <div className="md:col-span-2">
                                        <label className="block text-sm font-medium text-gray-700 mb-1">
                                            Site Description
                                        </label>
                                        <textarea
                                            className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-green-500 focus:border-transparent"
                                            rows="3"
                                            value={settings.general.siteDescription}
                                            onChange={(e) => handleInputChange('general', 'siteDescription', e.target.value)}
                                        ></textarea>
                                    </div>
                                </div>
                                <div className="mt-6 flex justify-end">
                                    <Button
                                        variant="primary"
                                        onClick={() => handleSaveSettings('general')}
                                        disabled={loading}
                                    >
                                        {loading ? 'Saving...' : 'Save Settings'}
                                    </Button>
                                </div>
                            </div>
                        </Card>

                        {/* Notification Settings */}
                        <Card>
                            <div className="p-6">
                                <h2 className="text-lg font-semibold mb-6">Notification Settings</h2>
                                <div className="space-y-4">
                                    <div className="flex items-start">
                                        <div className="flex items-center h-5">
                                            <input
                                                id="enableEmailNotifications"
                                                type="checkbox"
                                                className="h-4 w-4 text-green-600 focus:ring-green-500 border-gray-300 rounded"
                                                checked={settings.notifications.enableEmailNotifications}
                                                onChange={() => handleCheckboxChange('notifications', 'enableEmailNotifications')}
                                            />
                                        </div>
                                        <div className="ml-3 text-sm">
                                            <label htmlFor="enableEmailNotifications" className="font-medium text-gray-700">Enable Email Notifications</label>
                                            <p className="text-gray-500">Send email notifications to users for important updates</p>
                                        </div>
                                    </div>
                                    <div className="flex items-start">
                                        <div className="flex items-center h-5">
                                            <input
                                                id="enablePushNotifications"
                                                type="checkbox"
                                                className="h-4 w-4 text-green-600 focus:ring-green-500 border-gray-300 rounded"
                                                checked={settings.notifications.enablePushNotifications}
                                                onChange={() => handleCheckboxChange('notifications', 'enablePushNotifications')}
                                            />
                                        </div>
                                        <div className="ml-3 text-sm">
                                            <label htmlFor="enablePushNotifications" className="font-medium text-gray-700">Enable Push Notifications</label>
                                            <p className="text-gray-500">Send push notifications to users with the mobile app</p>
                                        </div>
                                    </div>
                                    <div>
                                        <label className="block text-sm font-medium text-gray-700 mb-1">
                                            Admin Alert Emails (comma separated)
                                        </label>
                                        <input
                                            type="text"
                                            className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-green-500 focus:border-transparent"
                                            value={settings.notifications.adminAlertEmails}
                                            onChange={(e) => handleInputChange('notifications', 'adminAlertEmails', e.target.value)}
                                        />
                                    </div>
                                    <div className="flex items-start">
                                        <div className="flex items-center h-5">
                                            <input
                                                id="dailyDigest"
                                                type="checkbox"
                                                className="h-4 w-4 text-green-600 focus:ring-green-500 border-gray-300 rounded"
                                                checked={settings.notifications.dailyDigest}
                                                onChange={() => handleCheckboxChange('notifications', 'dailyDigest')}
                                            />
                                        </div>
                                        <div className="ml-3 text-sm">
                                            <label htmlFor="dailyDigest" className="font-medium text-gray-700">Send Daily Digest</label>
                                            <p className="text-gray-500">Send a daily summary of platform activity to admins</p>
                                        </div>
                                    </div>
                                </div>
                                <div className="mt-6 flex justify-end">
                                    <Button
                                        variant="primary"
                                        onClick={() => handleSaveSettings('notifications')}
                                        disabled={loading}
                                    >
                                        {loading ? 'Saving...' : 'Save Settings'}
                                    </Button>
                                </div>
                            </div>
                        </Card>

                        {/* Listing Settings */}
                        <Card>
                            <div className="p-6">
                                <h2 className="text-lg font-semibold mb-6">Listing Settings</h2>
                                <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                                    <div className="flex items-start">
                                        <div className="flex items-center h-5">
                                            <input
                                                id="requireApproval"
                                                type="checkbox"
                                                className="h-4 w-4 text-green-600 focus:ring-green-500 border-gray-300 rounded"
                                                checked={settings.listings.requireApproval}
                                                onChange={() => handleCheckboxChange('listings', 'requireApproval')}
                                            />
                                        </div>
                                        <div className="ml-3 text-sm">
                                            <label htmlFor="requireApproval" className="font-medium text-gray-700">Require Approval</label>
                                            <p className="text-gray-500">Require admin approval before listings go live</p>
                                        </div>
                                    </div>
                                    <div>
                                        <label className="block text-sm font-medium text-gray-700 mb-1">
                                            Max Images Per Listing
                                        </label>
                                        <input
                                            type="number"
                                            min="1"
                                            max="10"
                                            className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-green-500 focus:border-transparent"
                                            value={settings.listings.maxImagesPerListing}
                                            onChange={(e) => handleInputChange('listings', 'maxImagesPerListing', parseInt(e.target.value))}
                                        />
                                    </div>
                                    <div>
                                        <label className="block text-sm font-medium text-gray-700 mb-1">
                                            Default Active Days
                                        </label>
                                        <input
                                            type="number"
                                            min="1"
                                            max="30"
                                            className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-green-500 focus:border-transparent"
                                            value={settings.listings.maxActiveDaysDefault}
                                            onChange={(e) => handleInputChange('listings', 'maxActiveDaysDefault', parseInt(e.target.value))}
                                        />
                                    </div>
                                    <div>
                                        <label className="block text-sm font-medium text-gray-700 mb-1">
                                            Allowed Categories (comma separated)
                                        </label>
                                        <input
                                            type="text"
                                            className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-green-500 focus:border-transparent"
                                            value={settings.listings.allowedCategories}
                                            onChange={(e) => handleInputChange('listings', 'allowedCategories', e.target.value)}
                                        />
                                    </div>
                                </div>
                                <div className="mt-6 flex justify-end">
                                    <Button
                                        variant="primary"
                                        onClick={() => handleSaveSettings('listings')}
                                        disabled={loading}
                                    >
                                        {loading ? 'Saving...' : 'Save Settings'}
                                    </Button>
                                </div>
                            </div>
                        </Card>

                        {/* User Settings */}
                        <Card>
                            <div className="p-6">
                                <h2 className="text-lg font-semibold mb-6">User Settings</h2>
                                <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                                    <div className="flex items-start">
                                        <div className="flex items-center h-5">
                                            <input
                                                id="requireEmailVerification"
                                                type="checkbox"
                                                className="h-4 w-4 text-green-600 focus:ring-green-500 border-gray-300 rounded"
                                                checked={settings.users.requireEmailVerification}
                                                onChange={() => handleCheckboxChange('users', 'requireEmailVerification')}
                                            />
                                        </div>
                                        <div className="ml-3 text-sm">
                                            <label htmlFor="requireEmailVerification" className="font-medium text-gray-700">Require Email Verification</label>
                                            <p className="text-gray-500">Users must verify their email before using the platform</p>
                                        </div>
                                    </div>
                                    <div className="flex items-start">
                                        <div className="flex items-center h-5">
                                            <input
                                                id="allowGuestBrowsing"
                                                type="checkbox"
                                                className="h-4 w-4 text-green-600 focus:ring-green-500 border-gray-300 rounded"
                                                checked={settings.users.allowGuestBrowsing}
                                                onChange={() => handleCheckboxChange('users', 'allowGuestBrowsing')}
                                            />
                                        </div>
                                        <div className="ml-3 text-sm">
                                            <label htmlFor="allowGuestBrowsing" className="font-medium text-gray-700">Allow Guest Browsing</label>
                                            <p className="text-gray-500">Allow non-registered users to browse available listings</p>
                                        </div>
                                    </div>
                                    <div>
                                        <label className="block text-sm font-medium text-gray-700 mb-1">
                                            Default User Role
                                        </label>
                                        <select
                                            className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-green-500 focus:border-transparent"
                                            value={settings.users.defaultUserRole}
                                            onChange={(e) => handleInputChange('users', 'defaultUserRole', e.target.value)}
                                        >
                                            <option value="user">User</option>
                                            <option value="contributor">Contributor</option>
                                            <option value="moderator">Moderator</option>
                                        </select>
                                    </div>
                                    <div>
                                        <label className="block text-sm font-medium text-gray-700 mb-1">
                                            Account Deletion Policy
                                        </label>
                                        <select
                                            className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-green-500 focus:border-transparent"
                                            value={settings.users.accountDeletionPolicy}
                                            onChange={(e) => handleInputChange('users', 'accountDeletionPolicy', e.target.value)}
                                        >
                                            <option value="soft-delete">Soft Delete (Anonymize)</option>
                                            <option value="hard-delete">Hard Delete (Complete Removal)</option>
                                            <option value="archive">Archive (Preserve Data)</option>
                                        </select>
                                    </div>
                                </div>
                                <div className="mt-6 flex justify-end">
                                    <Button
                                        variant="primary"
                                        onClick={() => handleSaveSettings('users')}
                                        disabled={loading}
                                    >
                                        {loading ? 'Saving...' : 'Save Settings'}
                                    </Button>
                                </div>
                            </div>
                        </Card>

                        {/* Privacy Settings */}
                        <Card>
                            <div className="p-6">
                                <h2 className="text-lg font-semibold mb-6">Privacy Settings</h2>
                                <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                                    <div>
                                        <label className="block text-sm font-medium text-gray-700 mb-1">
                                            Data Retention Period (days)
                                        </label>
                                        <input
                                            type="number"
                                            min="30"
                                            className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-green-500 focus:border-transparent"
                                            value={settings.privacy.dataRetentionDays}
                                            onChange={(e) => handleInputChange('privacy', 'dataRetentionDays', parseInt(e.target.value))}
                                        />
                                    </div>
                                    <div className="flex items-start">
                                        <div className="flex items-center h-5">
                                            <input
                                                id="showUserProfiles"
                                                type="checkbox"
                                                className="h-4 w-4 text-green-600 focus:ring-green-500 border-gray-300 rounded"
                                                checked={settings.privacy.showUserProfiles}
                                                onChange={() => handleCheckboxChange('privacy', 'showUserProfiles')}
                                            />
                                        </div>
                                        <div className="ml-3 text-sm">
                                            <label htmlFor="showUserProfiles" className="font-medium text-gray-700">Show User Profiles</label>
                                            <p className="text-gray-500">Allow users to view other users' profiles</p>
                                        </div>
                                    </div>
                                    <div className="flex items-start">
                                        <div className="flex items-center h-5">
                                            <input
                                                id="maskUserContact"
                                                type="checkbox"
                                                className="h-4 w-4 text-green-600 focus:ring-green-500 border-gray-300 rounded"
                                                checked={settings.privacy.maskUserContact}
                                                onChange={() => handleCheckboxChange('privacy', 'maskUserContact')}
                                            />
                                        </div>
                                        <div className="ml-3 text-sm">
                                            <label htmlFor="maskUserContact" className="font-medium text-gray-700">Mask User Contact Info</label>
                                            <p className="text-gray-500">Hide user contact information until explicitly shared</p>
                                        </div>
                                    </div>
                                    <div className="flex items-start">
                                        <div className="flex items-center h-5">
                                            <input
                                                id="allowLocationSharing"
                                                type="checkbox"
                                                className="h-4 w-4 text-green-600 focus:ring-green-500 border-gray-300 rounded"
                                                checked={settings.privacy.allowLocationSharing}
                                                onChange={() => handleCheckboxChange('privacy', 'allowLocationSharing')}
                                            />
                                        </div>
                                        <div className="ml-3 text-sm">
                                            <label htmlFor="allowLocationSharing" className="font-medium text-gray-700">Allow Location Sharing</label>
                                            <p className="text-gray-500">Allow users to share their precise location for listings</p>
                                        </div>
                                    </div>
                                </div>
                                <div className="mt-6 flex justify-end">
                                    <Button
                                        variant="primary"
                                        onClick={() => handleSaveSettings('privacy')}
                                        disabled={loading}
                                    >
                                        {loading ? 'Saving...' : 'Save Settings'}
                                    </Button>
                                </div>
                            </div>
                        </Card>

                        {/* System Maintenance */}
                        <Card>
                            <div className="p-6">
                                <h2 className="text-lg font-semibold mb-6">System Maintenance</h2>
                                <div className="space-y-4">
                                    <div>
                                        <Button
                                            variant="secondary"
                                            icon={<i className="fas fa-database"></i>}
                                            onClick={handleBackupDatabase}
                                            disabled={loading}
                                        >
                                            {loading ? 'Backing Up...' : 'Backup Database'}
                                        </Button>
                                    </div>
                                    <div>
                                        <Button
                                            variant="secondary"
                                            icon={<i className="fas fa-trash-alt"></i>}
                                            onClick={handleCleanupListings}
                                            disabled={loading}
                                        >
                                            {loading ? 'Cleaning Up...' : 'Clean Up Expired Listings'}
                                        </Button>
                                    </div>
                                    <div>
                                        <Button
                                            variant="secondary"
                                            icon={<i className="fas fa-broom"></i>}
                                            onClick={handleClearCache}
                                            disabled={loading}
                                        >
                                            {loading ? 'Clearing Cache...' : 'Clear Cache'}
                                        </Button>
                                    </div>
                                    <div className="pt-4 border-t">
                                        <Button
                                            variant="danger"
                                            icon={<i className="fas fa-exclamation-triangle"></i>}
                                            onClick={handleMaintenanceMode}
                                            disabled={loading}
                                        >
                                            {loading ? 'Updating...' : `Enable ${maintenanceMode ? 'Normal Mode' : 'Maintenance Mode'}`}
                                        </Button>
                                    </div>
                                </div>
                            </div>
                        </Card>
                    </div>
                </div>
            </AdminLayout>
        );
    } catch (error) {
        console.error('AdminSettings error:', error);
        reportError(error);
        return null;
    }
}

export default AdminSettings;
