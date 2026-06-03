import React from "react";
import { Link } from "react-router-dom";
import Card from "../components/common/Card";
import Input from "../components/common/Input";
import Button from "../components/common/Button";
import { useAuth } from "../utils/hooks/useSupabase";
import DietaryPreferences from "../components/profile/DietaryPreferences";
import { useTutorial } from "../utils/TutorialContext";
import supabase from "../utils/supabaseClient";
import { geocodeAddress } from "../utils/geocoding";
import { clearCachedInsights } from "../utils/services/insightsFallback";

function UserSettings() {
    const { resetTutorial } = useTutorial();
    const { user: authUser, isAuthenticated, updateProfile } = useAuth();
    
    const [loading, setLoading] = React.useState(false);
    const [error, setError] = React.useState(null);
    const [showDeleteConfirm, setShowDeleteConfirm] = React.useState(false);
    const [originalAddress, setOriginalAddress] = React.useState('');
    const [addressCoords, setAddressCoords] = React.useState({ latitude: null, longitude: null });
    const [geocoding, setGeocoding] = React.useState(false);
    const [formData, setFormData] = React.useState({
        name: '',
        email: '',
        address: '',
        phone: '',
        community_role: '',
        sms_opt_in: false,
        sms_notifications_enabled: false,
        notifications: {
            email: false,
            push: false
        },
        privacy: {
            profileVisibility: false,
            locationSharing: false
        },
        dietary_restrictions: [],
        allergies: [],
        dietary_preferences: [],
        pickup_reminder_enabled: true,
        default_reminder_hours: 24
    });
    const [successMessage, setSuccessMessage] = React.useState('');

    React.useEffect(() => {
        const loadUserData = async () => {
            if (authUser) {
                // Fetch full user profile from database
                const { data: profile } = await supabase
                    .from('users')
                    .select('*')
                    .eq('id', authUser.id)
                    .single();

                setFormData({
                    name: authUser.name || profile?.name || '',
                    email: authUser.email || '',
                    address: profile?.address || authUser.address || '',
                    phone: profile?.phone || '',
                    community_role: profile?.community_role || '',
                    sms_opt_in: profile?.sms_opt_in || false,
                    sms_notifications_enabled: profile?.sms_notifications_enabled || false,
                    notifications: authUser.notifications || {
                        email: false,
                        push: false
                    },
                    privacy: authUser.privacy || {
                        profileVisibility: false,
                        locationSharing: false
                    },
                    dietary_restrictions: profile?.dietary_restrictions || [],
                    allergies: profile?.allergies || [],
                    dietary_preferences: profile?.dietary_preferences || [],
                    pickup_reminder_enabled: profile?.pickup_reminder_enabled !== false,
                    default_reminder_hours: profile?.default_reminder_hours || 24
                });
                setOriginalAddress(profile?.address || authUser.address || '');
                setAddressCoords({
                    latitude: profile?.latitude ?? null,
                    longitude: profile?.longitude ?? null,
                });
            }
        };
        loadUserData();
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

    const handleDietaryChange = React.useCallback((dietaryData) => {
        setFormData(prev => {
            const next = { ...prev, ...dietaryData };
            // Avoid unnecessary state updates that would re-trigger the child's effect
            const same = Object.keys(dietaryData).every(k => {
                const a = prev[k];
                const b = dietaryData[k];
                if (Array.isArray(a) && Array.isArray(b)) {
                    return a.length === b.length && a.every((v, i) => v === b[i]);
                }
                return a === b;
            });
            return same ? prev : next;
        });
    }, []);

    const handleSaveSettings = async (section) => {
        setLoading(true);
        setError(null);
        setSuccessMessage('');
        
        try {
            // Update user profile in Supabase
            if (section === 'SMS') {
                // Validate phone number if enabling SMS
                if (formData.sms_opt_in && !formData.phone?.trim()) {
                    throw new Error('Phone number is required to enable SMS notifications');
                }
                
                const updates = {
                    phone: formData.phone?.trim() || null,
                    sms_notifications_enabled: formData.sms_notifications_enabled
                };
                
                // Persist the consent flag to match the user's current choice.
                // Stamp the opt-in date when enabling so we have a consent record.
                updates.sms_opt_in = !!formData.sms_opt_in;
                if (formData.sms_opt_in) {
                    updates.sms_opt_in_date = new Date().toISOString();
                }
                
                const { error: updateError } = await supabase
                    .from('users')
                    .update(updates)
                    .eq('id', authUser.id);

                if (updateError) throw updateError;
            } else if (section === 'Dietary') {
                const { error: updateError } = await supabase
                    .from('users')
                    .update({
                        dietary_restrictions: formData.dietary_restrictions,
                        allergies: formData.allergies,
                        dietary_preferences: formData.dietary_preferences
                    })
                    .eq('id', authUser.id);

                if (updateError) throw updateError;
            } else if (section === 'Reminders') {
                const { error: updateError } = await supabase
                    .from('users')
                    .update({
                        pickup_reminder_enabled: formData.pickup_reminder_enabled,
                        default_reminder_hours: formData.default_reminder_hours
                    })
                    .eq('id', authUser.id);

                if (updateError) throw updateError;
            } else if (section === 'Account') {
                const nextAddress = formData.address?.trim() || null;
                const updates = {
                    name: formData.name,
                    address: nextAddress,
                    phone: formData.phone?.trim() || null,
                    community_role: formData.community_role?.trim() || null,
                };

                // Geocode whenever the address has changed (or coords are missing).
                const addressChanged = (nextAddress || '') !== (originalAddress || '');
                const coordsMissing = !addressCoords.latitude || !addressCoords.longitude;
                if (nextAddress && (addressChanged || coordsMissing)) {
                    try {
                        setGeocoding(true);
                        const geo = await geocodeAddress(nextAddress);
                        if (geo) {
                            updates.latitude = geo.latitude;
                            updates.longitude = geo.longitude;
                            updates.address_geocoded_at = new Date().toISOString();
                            setAddressCoords({ latitude: geo.latitude, longitude: geo.longitude });
                        } else {
                            // Clear stale coords if the address can't be resolved.
                            updates.latitude = null;
                            updates.longitude = null;
                            updates.address_geocoded_at = null;
                            setAddressCoords({ latitude: null, longitude: null });
                        }
                    } catch (geoErr) {
                        console.warn('Address geocoding failed:', geoErr);
                    } finally {
                        setGeocoding(false);
                    }
                } else if (!nextAddress) {
                    updates.latitude = null;
                    updates.longitude = null;
                    updates.address_geocoded_at = null;
                    setAddressCoords({ latitude: null, longitude: null });
                }

                const { error: updateError } = await supabase
                    .from('users')
                    .update(updates)
                    .eq('id', authUser.id);
                if (updateError) throw updateError;
                setOriginalAddress(nextAddress || '');
                if (updateProfile) {
                    try { await updateProfile(updates); } catch (_) {}
                }
                // Re-read the row we just wrote so the dropdown can't show a
                // stale value, and drop any cached AI insights so the role
                // badge on the Profile page refreshes immediately.
                try {
                    const { data: fresh } = await supabase
                        .from('users')
                        .select('community_role,name,address,phone,latitude,longitude')
                        .eq('id', authUser.id)
                        .single();
                    if (fresh) {
                        setFormData(prev => ({
                            ...prev,
                            community_role: fresh.community_role || '',
                            name: fresh.name ?? prev.name,
                            address: fresh.address ?? prev.address,
                            phone: fresh.phone ?? prev.phone,
                        }));
                    }
                } catch (_) { /* non-fatal */ }
                try { clearCachedInsights(authUser.id); } catch (_) {}
                // Notify every other mounted component (ProfilePage badge,
                // RoleInsightsPanel, AI chat) that the role just changed so
                // they can refetch instead of holding the old value.
                try {
                    window.dispatchEvent(new CustomEvent('dogoods:community-role-changed', {
                        detail: { userId: authUser.id, role: formData.community_role || null }
                    }));
                } catch (_) {}
            } else if (updateProfile) {
                await updateProfile(formData);
            }
            
            const roleChanged = section === 'Account' && formData.community_role;
            const roleLabel = roleChanged
                ? ` Your community role is now "${formData.community_role}". Refreshing so it applies everywhere…`
                : '';
            setSuccessMessage(`${section} settings saved successfully.${roleLabel}`);
            
            if (roleChanged) {
                // Hard reload is the only bulletproof way to flush stale role
                // state in components we don't own (AI chat conversation, any
                // open Profile tab, cached insights, etc.). Give the toast a
                // beat so the user sees confirmation first.
                setTimeout(() => {
                    try { window.location.reload(); } catch (_) {}
                }, 1200);
                return;
            }

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
                <div className="animate-spin rounded-full h-12 w-12 border-t-2 border-b-2 border-[#2CABE3] mx-auto"></div>
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
                    className="mb-6 bg-primary-50 border border-primary-200 text-primary-700 px-4 py-3 rounded relative"
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
                                onChange={() => {}}
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
                        <div className="mt-6 grid grid-cols-1 md:grid-cols-2 gap-6">
                            <div>
                                <Input
                                    label="Address"
                                    value={formData.address}
                                    onChange={(e) => handleInputChange('address', e.target.value)}
                                    placeholder="Street, City, State ZIP"
                                    aria-label="Address"
                                />
                                <p className="mt-1 text-xs text-gray-500" aria-live="polite">
                                    {geocoding && (
                                        <span><i className="fas fa-spinner fa-spin mr-1"></i>Locating address…</span>
                                    )}
                                    {!geocoding && addressCoords.latitude && addressCoords.longitude && (
                                        <span className="text-green-700">
                                            <i className="fas fa-map-marker-alt mr-1"></i>
                                            Used as fallback for map &amp; AI distance ({Number(addressCoords.latitude).toFixed(4)}, {Number(addressCoords.longitude).toFixed(4)})
                                        </span>
                                    )}
                                    {!geocoding && formData.address && !(addressCoords.latitude && addressCoords.longitude) && (
                                        <span className="text-amber-700">
                                            <i className="fas fa-exclamation-triangle mr-1"></i>
                                            Save to geocode this address so distance &amp; routing features can use it.
                                        </span>
                                    )}
                                </p>
                            </div>
                            <Input
                                label="Phone Number"
                                type="tel"
                                value={formData.phone}
                                onChange={(e) => handleInputChange('phone', e.target.value)}
                                placeholder="+1 (555) 123-4567"
                                aria-label="Phone number"
                            />
                        </div>
                        <div className="mt-6">
                            <label htmlFor="community-role" className="block text-sm font-medium text-gray-700 mb-1">
                                Community Role
                            </label>
                            <select
                                id="community-role"
                                value={formData.community_role || ''}
                                onChange={(e) => handleInputChange('community_role', e.target.value)}
                                className="w-full rounded-md border border-gray-300 px-3 py-2 focus:outline-none focus:ring-2 focus:ring-[#2CABE3] focus:border-transparent"
                                aria-label="Community role"
                            >
                                <option value="">Select your role…</option>
                                <option value="donor">Donor — I share food</option>
                                <option value="recipient">Recipient — I receive food</option>
                                <option value="volunteer">Volunteer — I help organize</option>
                                <option value="driver">Driver — I deliver food</option>
                                <option value="organizer">Organizer — I run distributions</option>
                                <option value="sponsor">Sponsor — I support the community</option>
                            </select>
                            <p className="mt-1 text-xs text-gray-500">
                                Helps the AI assistant tailor suggestions to how you participate.
                            </p>
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

                {/* SMS Notification Settings */}
                <Card>
                    <div className="p-6">
                        <h2 className="text-xl font-semibold mb-2">SMS Notifications</h2>
                        <p className="text-sm text-gray-600 mb-6">
                            Receive text messages about food claims, pickup reminders, and important updates.
                        </p>
                        
                        <div className="space-y-4">
                            {/* Phone Number */}
                            <div>
                                <label htmlFor="phone" className="block text-sm font-medium text-gray-700 mb-1">
                                    Phone Number
                                </label>
                                <Input
                                    id="phone"
                                    name="phone"
                                    type="tel"
                                    value={formData.phone}
                                    onChange={(e) => handleInputChange('phone', e.target.value)}
                                    placeholder="+1234567890 or (123) 456-7890"
                                    className="w-full"
                                    aria-describedby="phone-description"
                                />
                                <p id="phone-description" className="mt-1 text-xs text-gray-500">
                                    Format: +1234567890 or (123) 456-7890
                                </p>
                            </div>

                            {/* SMS Opt-in Status */}
                            {formData.sms_opt_in ? (
                                <div className="bg-primary-50 border border-primary-200 rounded-lg p-4">
                                    <div className="flex items-start">
                                        <i className="fas fa-check-circle text-primary-600 mt-0.5 mr-3"></i>
                                        <div className="flex-1">
                                            <h3 className="text-sm font-medium text-primary-900">SMS Notifications Enabled</h3>
                                            <p className="text-xs text-primary-700 mt-1">
                                                You've opted in to receive SMS notifications. You can disable notifications below at any time.
                                            </p>
                                        </div>
                                    </div>
                                </div>
                            ) : (
                                <div className="bg-blue-50 border border-blue-200 rounded-lg p-4">
                                    <div className="flex items-start">
                                        <i className="fas fa-info-circle text-blue-600 mt-0.5 mr-3"></i>
                                        <div className="flex-1">
                                            <h3 className="text-sm font-medium text-blue-900">SMS Notifications Not Enabled</h3>
                                            <p className="text-xs text-blue-700 mt-1">
                                                To receive SMS notifications, add your phone number above and check the box below to opt in.
                                            </p>
                                        </div>
                                    </div>
                                </div>
                            )}

                            {/* SMS Notifications Toggle */}
                            <div className="border-t border-gray-200 pt-4">
                                <div className="flex items-start">
                                    <input
                                        type="checkbox"
                                        id="smsNotifications"
                                        checked={formData.sms_notifications_enabled}
                                        onChange={(e) => {
                                            // If enabling and not opted in, also opt in
                                            if (e.target.checked && !formData.sms_opt_in) {
                                                setFormData(prev => ({
                                                    ...prev,
                                                    sms_opt_in: true,
                                                    sms_notifications_enabled: true
                                                }));
                                            } else {
                                                handleInputChange('sms_notifications_enabled', e.target.checked);
                                            }
                                        }}
                                        className="h-4 w-4 text-[#2CABE3] focus:ring-[#2CABE3] border-gray-300 rounded mt-0.5"
                                        aria-describedby="sms-notifications-description"
                                    />
                                    <div className="ml-3">
                                        <label htmlFor="smsNotifications" className="text-sm font-medium text-gray-700">
                                            Enable SMS Notifications
                                        </label>
                                        <p id="sms-notifications-description" className="text-xs text-gray-600 mt-1">
                                            {formData.sms_opt_in 
                                                ? 'Uncheck to stop receiving SMS messages. You can re-enable at any time.'
                                                : 'By enabling this, you consent to receive SMS notifications from DoGoods. Message and data rates may apply. You can opt out at any time.'
                                            }
                                        </p>
                                    </div>
                                </div>
                            </div>

                            {/* Legal Notice */}
                            <div className="text-xs text-gray-500 pt-2 border-t border-gray-200">
                                <p className="mb-1">
                                    <strong>SMS Terms:</strong> By opting in, you agree to receive automated text messages at the phone number provided. 
                                    Consent is not a condition of purchase. Message frequency varies. Message and data rates may apply.
                                </p>
                                <p>
                                    Reply STOP to cancel or HELP for help. View our <Link to="/terms" className="text-[#2CABE3] hover:underline">Terms of Service</Link> and <Link to="/privacy" className="text-[#2CABE3] hover:underline">Privacy Policy</Link>.
                                </p>
                            </div>
                        </div>

                        <div className="mt-6 flex justify-end">
                            <Button
                                variant="primary"
                                onClick={() => handleSaveSettings('SMS')}
                                disabled={loading || (formData.sms_notifications_enabled && !formData.phone?.trim())}
                                aria-label="Save SMS notification settings"
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
                                    className="h-4 w-4 text-primary-600 focus:ring-primary-500 border-gray-300 rounded"
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
                                    className="h-4 w-4 text-primary-600 focus:ring-primary-500 border-gray-300 rounded"
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

                {/* Pickup Reminders */}
                <Card>
                    <div className="p-6">
                        <h2 className="text-xl font-semibold mb-6">Pickup Reminders</h2>
                        <p className="text-sm text-gray-600 mb-4">
                            Get notified before your scheduled food pickups so you never miss a collection.
                        </p>
                        <div className="space-y-4">
                            <div className="flex items-center">
                                <input
                                    type="checkbox"
                                    id="pickupReminders"
                                    checked={formData.pickup_reminder_enabled}
                                    onChange={() => handleInputChange('pickup_reminder_enabled', !formData.pickup_reminder_enabled)}
                                    className="h-4 w-4 text-primary-600 focus:ring-primary-500 border-gray-300 rounded"
                                    aria-label="Enable pickup reminders"
                                />
                                <label htmlFor="pickupReminders" className="ml-2 block text-sm text-gray-900">
                                    Enable pickup reminders
                                </label>
                            </div>

                            {formData.pickup_reminder_enabled && (
                                <div className="ml-6 mt-4">
                                    <label className="block text-sm font-medium text-gray-700 mb-2">
                                        Remind me before pickup
                                    </label>
                                    <select
                                        value={formData.default_reminder_hours}
                                        onChange={(e) => handleInputChange('default_reminder_hours', parseInt(e.target.value))}
                                        className="mt-1 block w-full pl-3 pr-10 py-2 text-base border-gray-300 focus:outline-none focus:ring-primary-500 focus:border-[#2CABE3] sm:text-sm rounded-md"
                                        aria-label="Select reminder time"
                                    >
                                        <option value={1}>1 hour before</option>
                                        <option value={2}>2 hours before</option>
                                        <option value={4}>4 hours before</option>
                                        <option value={12}>12 hours before</option>
                                        <option value={24}>24 hours before (1 day)</option>
                                        <option value={48}>48 hours before (2 days)</option>
                                    </select>
                                </div>
                            )}
                        </div>
                        <div className="mt-6 flex justify-end">
                            <Button
                                variant="primary"
                                onClick={() => handleSaveSettings('Reminders')}
                                disabled={loading}
                                aria-label="Save reminder preferences"
                            >
                                {loading ? 'Saving...' : 'Save Reminder Preferences'}
                            </Button>
                        </div>
                    </div>
                </Card>

                {/* Dietary Preferences */}
                <Card>
                    <div className="p-6">
                        <h2 className="text-xl font-semibold mb-6">Dietary Preferences & Allergies</h2>
                        <p className="text-sm text-gray-600 mb-4">
                            Help us match you with suitable food by setting your dietary restrictions, allergies, and preferences.
                        </p>
                        <DietaryPreferences
                            initialRestrictions={formData.dietary_restrictions}
                            initialAllergies={formData.allergies}
                            initialPreferences={formData.dietary_preferences}
                            onChange={handleDietaryChange}
                        />
                        <div className="mt-6 flex justify-end">
                            <Button
                                variant="primary"
                                onClick={() => handleSaveSettings('Dietary')}
                                disabled={loading}
                                aria-label="Save dietary preferences"
                            >
                                {loading ? 'Saving...' : 'Save Dietary Preferences'}
                            </Button>
                        </div>
                    </div>
                </Card>

                {/* Tutorial Section */}
                <Card>
                    <div className="p-6">
                        <h2 className="text-xl font-semibold mb-4">Tutorial</h2>
                        <p className="text-gray-600 mb-6">
                            Need a refresher? Restart the interactive tutorial to learn how to use DoGoods.
                        </p>
                        <Button
                            variant="secondary"
                            onClick={resetTutorial}
                            className="flex items-center"
                        >
                            <i className="fas fa-graduation-cap mr-2"></i>
                            Start Tutorial
                        </Button>
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
                                    className="h-4 w-4 text-primary-600 focus:ring-primary-500 border-gray-300 rounded"
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
                                    className="h-4 w-4 text-primary-600 focus:ring-primary-500 border-gray-300 rounded"
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
