import React from 'react';
import AdminLayout from './AdminLayout';
import Button from '../../components/common/Button';
import Input from '../../components/common/Input';
import Avatar from '../../components/common/Avatar';
import { useAuth } from '../../utils/hooks/useSupabase';
import { reportError } from '../../utils/helpers';
import { toast } from 'react-toastify';

// Utility function for formatting dates
const formatDate = (dateString) => {
    if (!dateString) return 'N/A';
    return new Date(dateString).toLocaleDateString('en-US', {
        year: 'numeric',
        month: 'long',
        day: 'numeric'
    });
};

function AdminProfile() {
    const { user: authUser, isAdmin } = useAuth();
    
    try {
        const [loading, setLoading] = React.useState(false);
        const [error, setError] = React.useState(null);
        const [isEditing, setIsEditing] = React.useState(false);
        const [editForm, setEditForm] = React.useState({
            name: '',
            email: '',
            phone: '',
            bio: ''
        });

        React.useEffect(() => {
            if (authUser) {
                setEditForm({
                    name: authUser.name || '',
                    email: authUser.email || '',
                    phone: authUser.phone || '',
                    bio: authUser.bio || ''
                });
            }
        }, [authUser]);

        const handleEditSubmit = async (e) => {
            e.preventDefault();
            if (!validateForm()) {
                return;
            }
            setLoading(true);
            try {
                // In a real app, you would update the user profile in Supabase
                // For now, just show success
                toast.success('Profile updated successfully!');
                setIsEditing(false);
            } catch (error) {
                console.error('Update profile error:', error);
                toast.error('Failed to update profile. Please try again.');
            } finally {
                setLoading(false);
            }
        };

        const handleChangePassword = () => {
            // Implement password change logic here
            toast.info('Password change functionality coming soon!');
        };

        const handleEnable2FA = () => {
            // Implement 2FA logic here
            toast.info('Two-factor authentication coming soon!');
        };

        const validateForm = () => {
            let isValid = true;
            const newErrors = {};

            if (!editForm.name) {
                newErrors.name = 'Name is required';
                isValid = false;
            }
            if (!editForm.email) {
                newErrors.email = 'Email is required';
                isValid = false;
            } else if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(editForm.email)) {
                newErrors.email = 'Invalid email address';
                isValid = false;
            }
            setErrors(newErrors);
            return isValid;
        };

        if (loading) {
            return (
                <AdminLayout active="profile">
                    <div className="max-w-4xl mx-auto py-8">
                        <div className="animate-pulse space-y-6">
                            <div className="h-32 bg-gray-200 rounded-lg"></div>
                            <div className="h-64 bg-gray-200 rounded-lg"></div>
                        </div>
                    </div>
                </AdminLayout>
            );
        }

        if (error) {
            return (
                <AdminLayout active="profile">
                    <div className="max-w-4xl mx-auto py-8 text-center">
                        <i className="fas fa-exclamation-circle text-red-500 text-4xl mb-4"></i>
                        <p className="text-gray-600 mb-4">{error}</p>
                        <Button
                            variant="secondary"
                            onClick={loadProfile}
                        >
                            Try Again
                        </Button>
                    </div>
                </AdminLayout>
            );
        }

        return (
            <AdminLayout active="profile">
                <div className="max-w-4xl mx-auto py-8">
                    <div className="bg-white rounded-lg shadow overflow-hidden">
                        <div className="p-6">
                            <div className="flex items-center justify-between mb-8">
                                <h1 className="text-2xl font-bold text-gray-900">Admin Profile</h1>
                                {!isEditing && (
                                    <Button
                                        variant="secondary"
                                        icon={<i className="fas fa-edit"></i>}
                                        onClick={() => setIsEditing(true)}
                                    >
                                        Edit Profile
                                    </Button>
                                )}
                            </div>

                            {isEditing ? (
                                <form onSubmit={handleEditSubmit} className="space-y-6">
                                    <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                                        <Input
                                            label="Name"
                                            name="name"
                                            value={editForm.name}
                                            onChange={(e) => setEditForm(prev => ({
                                                ...prev,
                                                name: e.target.value
                                            }))}
                                            required
                                        />
                                        <Input
                                            label="Email"
                                            name="email"
                                            type="email"
                                            value={editForm.email}
                                            onChange={(e) => setEditForm(prev => ({
                                                ...prev,
                                                email: e.target.value
                                            }))}
                                            required
                                        />
                                        <Input
                                            label="Phone"
                                            name="phone"
                                            value={editForm.phone}
                                            onChange={(e) => setEditForm(prev => ({
                                                ...prev,
                                                phone: e.target.value
                                            }))}
                                        />
                                        <div className="md:col-span-2">
                                            <Input
                                                label="Bio"
                                                name="bio"
                                                type="textarea"
                                                value={editForm.bio}
                                                onChange={(e) => setEditForm(prev => ({
                                                    ...prev,
                                                    bio: e.target.value
                                                }))}
                                            />
                                        </div>
                                    </div>
                                    <div className="flex justify-end space-x-4">
                                        <Button
                                            variant="secondary"
                                            onClick={() => setIsEditing(false)}
                                        >
                                            Cancel
                                        </Button>
                                        <Button
                                            variant="primary"
                                            type="submit"
                                            disabled={loading}
                                        >
                                            {loading ? 'Saving...' : 'Save Changes'}
                                        </Button>
                                    </div>
                                </form>
                            ) : (
                                <div>
                                    <div className="flex items-center mb-8">
                                        <div className="mr-6">
                                            <Avatar
                                                src={profile?.avatar}
                                                size="xl"
                                            />
                                        </div>
                                        <div>
                                            <h2 className="text-xl font-semibold">{profile?.name}</h2>
                                            <p className="text-gray-600">{profile?.email}</p>
                                            <p className="text-sm text-gray-500 mt-1">
                                                Role: {profile?.role?.charAt(0).toUpperCase() + profile?.role?.slice(1)}
                                            </p>
                                        </div>
                                    </div>

                                    <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                                        <div>
                                            <h3 className="text-lg font-semibold mb-4">Account Information</h3>
                                            <div className="space-y-4">
                                                <div>
                                                    <label className="block text-sm font-medium text-gray-500">Account ID</label>
                                                    <p className="mt-1">{profile?.id}</p>
                                                </div>
                                                <div>
                                                    <label className="block text-sm font-medium text-gray-500">Join Date</label>
                                                    <p className="mt-1">{formatDate(profile?.joinDate)}</p>
                                                </div>
                                                <div>
                                                    <label className="block text-sm font-medium text-gray-500">Last Login</label>
                                                    <p className="mt-1">Today at {new Date().toLocaleTimeString()}</p>
                                                </div>
                                                {profile?.phone && (
                                                    <div>
                                                        <label className="block text-sm font-medium text-gray-500">Phone</label>
                                                        <p className="mt-1">{profile.phone}</p>
                                                    </div>
                                                )}
                                                {profile?.bio && (
                                                    <div>
                                                        <label className="block text-sm font-medium text-gray-500">Bio</label>
                                                        <p className="mt-1">{profile.bio}</p>
                                                    </div>
                                                )}
                                            </div>
                                        </div>

                                        <div>
                                            <h3 className="text-lg font-semibold mb-4">Security</h3>
                                            <div className="space-y-4">
                                                <Button
                                                    variant="secondary"
                                                    icon={<i className="fas fa-key"></i>}
                                                    onClick={handleChangePassword}
                                                >
                                                    Change Password
                                                </Button>
                                                <Button
                                                    variant="secondary"
                                                    icon={<i className="fas fa-shield-alt"></i>}
                                                    onClick={handleEnable2FA}
                                                >
                                                    Enable Two-Factor Auth
                                                </Button>
                                            </div>
                                        </div>
                                    </div>

                                    <div className="mt-8 pt-8 border-t">
                                        <h3 className="text-lg font-semibold mb-4">Recent Activity</h3>
                                        <div className="space-y-4">
                                            {profile?.recentActivity?.length > 0 ? (
                                                profile.recentActivity.map((activity, index) => (
                                                    <div key={index} className="flex items-start">
                                                        <div className={`mt-1 ${activity.iconColor || 'text-gray-500'}`}>
                                                            <i className={`fas ${activity.icon || 'fa-circle'}`}></i>
                                                        </div>
                                                        <div className="ml-3">
                                                            <p className="text-gray-900">{activity.action}</p>
                                                            <p className="text-sm text-gray-500">
                                                                {formatDate(activity.timestamp)}
                                                            </p>
                                                        </div>
                                                    </div>
                                                ))
                                            ) : (
                                                <p className="text-gray-500 text-sm">No recent activity</p>
                                            )}
                                        </div>
                                    </div>
                                </div>
                            )}
                        </div>
                    </div>
                </div>
            </AdminLayout>
        );
    } catch (error) {
        console.error('AdminProfile error:', error);
        reportError(error);
        return null;
    }
}

export default AdminProfile;
