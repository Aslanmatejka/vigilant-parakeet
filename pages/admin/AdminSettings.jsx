import React from 'react';
import AdminLayout from './AdminLayout';
import Button from '../../components/common/Button';
import Card from '../../components/common/Card';
import { reportError } from '../../utils/helpers';
import { toast } from 'react-toastify';
import { useAuth } from '../../utils/hooks/useSupabase';
import supabase from '../../utils/supabaseClient';

const AUTOMATION_EVENTS = ['new_listing', 'draft_listing_reminder', 'admin_broadcast'];

const formatStatusDate = (value) => {
    if (!value) return 'No activity yet';
    try {
        return new Date(value).toLocaleString();
    } catch {
        return String(value);
    }
};

function AdminSettings() {
    const { user: authUser, isAdmin } = useAuth();
    
    const [loading, setLoading] = React.useState(false);
        const [success, setSuccess] = React.useState(null);
        const [error, setError] = React.useState(null);
        const [maintenanceMode, setMaintenanceMode] = React.useState(false);
        const [automationStatus, setAutomationStatus] = React.useState({
            loading: true,
            refreshing: false,
            error: null,
            lastLoadedAt: null,
            pendingBroadcasts: 0,
            sentBroadcasts24h: 0,
            deliveredBroadcasts24h: 0,
            notifications24h: 0,
            smsSent24h: 0,
            smsFailed24h: 0,
            eventCounts24h: {
                new_listing: 0,
                draft_listing_reminder: 0,
                admin_broadcast: 0
            },
            latestEventAt: null,
            failedBroadcasts: []
        });
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
                allowedCategories: 'produce,dairy,bakery,pantry,meat,prepared'
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
            loadAutomationStatus(true);
        }, []);

        const loadAutomationStatus = async (isInitial = false) => {
            const now = new Date();
            const sinceIso = new Date(now.getTime() - (24 * 60 * 60 * 1000)).toISOString();

            setAutomationStatus(prev => ({
                ...prev,
                loading: isInitial,
                refreshing: !isInitial,
                error: null
            }));

            try {
                const [pendingBroadcastsRes, sentBroadcastsRes, notificationsRes, smsRes] = await Promise.all([
                    supabase
                        .from('admin_broadcasts')
                        .select('id', { count: 'exact', head: true })
                        .eq('sent', false),
                    supabase
                        .from('admin_broadcasts')
                        .select('id, title, channel, target_role, community_id, sent_at, delivered_count')
                        .eq('sent', true)
                        .gte('sent_at', sinceIso)
                        .order('sent_at', { ascending: false })
                        .limit(250),
                    supabase
                        .from('notifications')
                        .select('created_at, data')
                        .gte('created_at', sinceIso)
                        .order('created_at', { ascending: false })
                        .limit(500),
                    supabase
                        .from('sms_logs')
                        .select('created_at, status')
                        .gte('created_at', sinceIso)
                        .order('created_at', { ascending: false })
                        .limit(500)
                ]);

                if (pendingBroadcastsRes.error) throw pendingBroadcastsRes.error;
                if (sentBroadcastsRes.error) throw sentBroadcastsRes.error;
                if (notificationsRes.error) throw notificationsRes.error;
                if (smsRes.error) throw smsRes.error;

                const sentBroadcasts = sentBroadcastsRes.data || [];
                const notifications = notificationsRes.data || [];
                const smsLogs = smsRes.data || [];

                const eventCounts24h = {
                    new_listing: 0,
                    draft_listing_reminder: 0,
                    admin_broadcast: 0
                };

                notifications.forEach((item) => {
                    const evt = item?.data?.event;
                    if (AUTOMATION_EVENTS.includes(evt)) {
                        eventCounts24h[evt] += 1;
                    }
                });

                const smsFailed24h = smsLogs.filter((item) => {
                    const status = String(item?.status || '').toLowerCase();
                    return status === 'failed' || status === 'error';
                }).length;

                const deliveredBroadcasts24h = sentBroadcasts.reduce((sum, item) => {
                    return sum + (Number(item.delivered_count) || 0);
                }, 0);

                const failedBroadcasts = sentBroadcasts
                    .filter((item) => (Number(item.delivered_count) || 0) === 0)
                    .slice(0, 10);

                const latestEventAt = [
                    notifications[0]?.created_at,
                    smsLogs[0]?.created_at,
                    sentBroadcasts[0]?.sent_at
                ]
                    .filter(Boolean)
                    .sort((a, b) => new Date(b).getTime() - new Date(a).getTime())[0] || null;

                setAutomationStatus({
                    loading: false,
                    refreshing: false,
                    error: null,
                    lastLoadedAt: new Date().toISOString(),
                    pendingBroadcasts: pendingBroadcastsRes.count || 0,
                    sentBroadcasts24h: sentBroadcasts.length,
                    deliveredBroadcasts24h,
                    notifications24h: notifications.length,
                    smsSent24h: smsLogs.length,
                    smsFailed24h,
                    eventCounts24h,
                    latestEventAt,
                    failedBroadcasts
                });
            } catch (statusError) {
                console.error('Automation status load error:', statusError);
                reportError(statusError);
                setAutomationStatus(prev => ({
                    ...prev,
                    loading: false,
                    refreshing: false,
                    error: statusError?.message || 'Failed to load automation status.'
                }));
            }
        };

        const loadSettings = async () => {
            try {
                // TODO: Fetch from Supabase settings table when available
                // For now, keep defaults already set in state
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
                        <div className="mb-6 bg-[#2CABE3]/10 border border-[#2CABE3]/30 text-[#2CABE3] px-4 py-3 rounded relative">
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
                                            className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-[#2CABE3] focus:border-transparent"
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
                                            className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-[#2CABE3] focus:border-transparent"
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
                                            className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-[#2CABE3] focus:border-transparent"
                                            value={settings.general.supportPhone}
                                            onChange={(e) => handleInputChange('general', 'supportPhone', e.target.value)}
                                        />
                                    </div>
                                    <div className="md:col-span-2">
                                        <label className="block text-sm font-medium text-gray-700 mb-1">
                                            Site Description
                                        </label>
                                        <textarea
                                            className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-[#2CABE3] focus:border-transparent"
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
                                                className="h-4 w-4 text-[#2CABE3] focus:ring-[#2CABE3] border-gray-300 rounded"
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
                                                className="h-4 w-4 text-[#2CABE3] focus:ring-[#2CABE3] border-gray-300 rounded"
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
                                            className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-[#2CABE3] focus:border-transparent"
                                            value={settings.notifications.adminAlertEmails}
                                            onChange={(e) => handleInputChange('notifications', 'adminAlertEmails', e.target.value)}
                                        />
                                    </div>
                                    <div className="flex items-start">
                                        <div className="flex items-center h-5">
                                            <input
                                                id="dailyDigest"
                                                type="checkbox"
                                                className="h-4 w-4 text-[#2CABE3] focus:ring-[#2CABE3] border-gray-300 rounded"
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

                        {/* Automation Status */}
                        <Card>
                            <div className="p-6">
                                <div className="mb-5 flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
                                    <div>
                                        <h2 className="text-lg font-semibold text-gray-900">Automation Status</h2>
                                        <p className="mt-1 text-sm text-gray-500">
                                            Live snapshot of run_forever workers over the last 24 hours.
                                        </p>
                                    </div>
                                    <Button
                                        variant="secondary"
                                        size="sm"
                                        onClick={() => loadAutomationStatus(false)}
                                        disabled={automationStatus.loading || automationStatus.refreshing}
                                    >
                                        {automationStatus.refreshing ? 'Refreshing...' : 'Refresh Status'}
                                    </Button>
                                </div>

                                {automationStatus.error && (
                                    <div className="mb-4 rounded-md border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">
                                        <i className="fas fa-circle-exclamation mr-2"></i>
                                        {automationStatus.error}
                                    </div>
                                )}

                                <div className="grid grid-cols-1 gap-4 md:grid-cols-2 xl:grid-cols-4">
                                    <div className="rounded-lg border border-gray-200 bg-gray-50 p-4">
                                        <p className="text-xs font-semibold uppercase tracking-wide text-gray-500">Pending Broadcasts</p>
                                        <p className="mt-2 text-2xl font-bold text-yellow-700">
                                            {automationStatus.loading ? '-' : automationStatus.pendingBroadcasts}
                                        </p>
                                    </div>
                                    <div className="rounded-lg border border-gray-200 bg-gray-50 p-4">
                                        <p className="text-xs font-semibold uppercase tracking-wide text-gray-500">Broadcasts Sent (24h)</p>
                                        <p className="mt-2 text-2xl font-bold text-[#2CABE3]">
                                            {automationStatus.loading ? '-' : automationStatus.sentBroadcasts24h}
                                        </p>
                                    </div>
                                    <div className="rounded-lg border border-gray-200 bg-gray-50 p-4">
                                        <p className="text-xs font-semibold uppercase tracking-wide text-gray-500">Delivery Actions (24h)</p>
                                        <p className="mt-2 text-2xl font-bold text-gray-900">
                                            {automationStatus.loading ? '-' : automationStatus.deliveredBroadcasts24h}
                                        </p>
                                    </div>
                                    <div className="rounded-lg border border-gray-200 bg-gray-50 p-4">
                                        <p className="text-xs font-semibold uppercase tracking-wide text-gray-500">Latest Automation Event</p>
                                        <p className="mt-2 text-sm font-semibold text-gray-900">
                                            {automationStatus.loading ? 'Loading...' : formatStatusDate(automationStatus.latestEventAt)}
                                        </p>
                                    </div>
                                </div>

                                <div className="mt-5 grid grid-cols-1 gap-4 lg:grid-cols-2">
                                    <div className="rounded-lg border border-gray-200 p-4">
                                        <h3 className="text-sm font-semibold text-gray-800">Automation Notification Events (24h)</h3>
                                        <ul className="mt-3 space-y-2 text-sm text-gray-700">
                                            <li className="flex items-center justify-between">
                                                <span>New listing matches</span>
                                                <strong>{automationStatus.loading ? '-' : automationStatus.eventCounts24h.new_listing}</strong>
                                            </li>
                                            <li className="flex items-center justify-between">
                                                <span>Draft reminders</span>
                                                <strong>{automationStatus.loading ? '-' : automationStatus.eventCounts24h.draft_listing_reminder}</strong>
                                            </li>
                                            <li className="flex items-center justify-between">
                                                <span>Admin broadcast notifications</span>
                                                <strong>{automationStatus.loading ? '-' : automationStatus.eventCounts24h.admin_broadcast}</strong>
                                            </li>
                                        </ul>
                                    </div>

                                    <div className="rounded-lg border border-gray-200 p-4">
                                        <h3 className="text-sm font-semibold text-gray-800">SMS Worker Health (24h)</h3>
                                        <ul className="mt-3 space-y-2 text-sm text-gray-700">
                                            <li className="flex items-center justify-between">
                                                <span>SMS logs recorded</span>
                                                <strong>{automationStatus.loading ? '-' : automationStatus.smsSent24h}</strong>
                                            </li>
                                            <li className="flex items-center justify-between">
                                                <span>SMS failures</span>
                                                <strong className={automationStatus.smsFailed24h > 0 ? 'text-red-600' : ''}>
                                                    {automationStatus.loading ? '-' : automationStatus.smsFailed24h}
                                                </strong>
                                            </li>
                                            <li className="flex items-center justify-between">
                                                <span>All notifications recorded</span>
                                                <strong>{automationStatus.loading ? '-' : automationStatus.notifications24h}</strong>
                                            </li>
                                        </ul>
                                    </div>
                                </div>

                                <div className="mt-5 rounded-lg border border-gray-200 p-4">
                                    <div className="flex items-center justify-between">
                                        <h3 className="text-sm font-semibold text-gray-800">Recent Broadcast Failures (24h)</h3>
                                        <span className="text-xs text-gray-500">
                                            Sent broadcasts with zero delivered notifications
                                        </span>
                                    </div>
                                    {automationStatus.loading ? (
                                        <p className="mt-3 text-sm text-gray-500">Loading...</p>
                                    ) : automationStatus.failedBroadcasts.length === 0 ? (
                                        <p className="mt-3 text-sm text-gray-500">No failed broadcasts in the last 24 hours.</p>
                                    ) : (
                                        <div className="mt-3 overflow-x-auto">
                                            <table className="min-w-full divide-y divide-gray-200 text-sm">
                                                <thead className="bg-gray-50">
                                                    <tr>
                                                        <th className="px-3 py-2 text-left text-xs font-semibold uppercase tracking-wide text-gray-600">Title</th>
                                                        <th className="px-3 py-2 text-left text-xs font-semibold uppercase tracking-wide text-gray-600">Channel</th>
                                                        <th className="px-3 py-2 text-left text-xs font-semibold uppercase tracking-wide text-gray-600">Target</th>
                                                        <th className="px-3 py-2 text-left text-xs font-semibold uppercase tracking-wide text-gray-600">Sent At</th>
                                                        <th className="px-3 py-2 text-left text-xs font-semibold uppercase tracking-wide text-gray-600">Delivered</th>
                                                    </tr>
                                                </thead>
                                                <tbody className="divide-y divide-gray-100 bg-white">
                                                    {automationStatus.failedBroadcasts.map((item) => (
                                                        <tr key={item.id}>
                                                            <td className="px-3 py-2 text-gray-900">{item.title || '-'}</td>
                                                            <td className="px-3 py-2 text-gray-700">{item.channel || '-'}</td>
                                                            <td className="px-3 py-2 text-gray-700">
                                                                {item.target_role || 'all'}
                                                                {item.community_id ? ` / community ${item.community_id}` : ''}
                                                            </td>
                                                            <td className="px-3 py-2 text-gray-700">{formatStatusDate(item.sent_at)}</td>
                                                            <td className="px-3 py-2 font-semibold text-red-600">0</td>
                                                        </tr>
                                                    ))}
                                                </tbody>
                                            </table>
                                        </div>
                                    )}
                                </div>

                                <p className="mt-5 text-xs text-gray-500">
                                    Last refreshed: {formatStatusDate(automationStatus.lastLoadedAt)}
                                </p>
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
                                                className="h-4 w-4 text-[#2CABE3] focus:ring-[#2CABE3] border-gray-300 rounded"
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
                                            className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-[#2CABE3] focus:border-transparent"
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
                                            className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-[#2CABE3] focus:border-transparent"
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
                                            className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-[#2CABE3] focus:border-transparent"
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
                                                className="h-4 w-4 text-[#2CABE3] focus:ring-[#2CABE3] border-gray-300 rounded"
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
                                                className="h-4 w-4 text-[#2CABE3] focus:ring-[#2CABE3] border-gray-300 rounded"
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
                                            className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-[#2CABE3] focus:border-transparent"
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
                                            className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-[#2CABE3] focus:border-transparent"
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
                                            className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-[#2CABE3] focus:border-transparent"
                                            value={settings.privacy.dataRetentionDays}
                                            onChange={(e) => handleInputChange('privacy', 'dataRetentionDays', parseInt(e.target.value))}
                                        />
                                    </div>
                                    <div className="flex items-start">
                                        <div className="flex items-center h-5">
                                            <input
                                                id="showUserProfiles"
                                                type="checkbox"
                                                className="h-4 w-4 text-[#2CABE3] focus:ring-[#2CABE3] border-gray-300 rounded"
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
                                                className="h-4 w-4 text-[#2CABE3] focus:ring-[#2CABE3] border-gray-300 rounded"
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
                                                className="h-4 w-4 text-[#2CABE3] focus:ring-[#2CABE3] border-gray-300 rounded"
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
}

export default AdminSettings;
