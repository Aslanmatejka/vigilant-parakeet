import React, { useState, useEffect } from 'react';
import PropTypes from 'prop-types';
import { Button } from '../common/Button';
import { Avatar } from '../common/Avatar';
import { Input } from '../common/Input';
import { reportError } from '../../utils/helpers';

// File size limit in bytes (5MB)
const MAX_FILE_SIZE = 5 * 1024 * 1024;

function UserProfile({
    user,
    onUpdate,
    loading = false
}) {
    const [isEditing, setIsEditing] = useState(false);
    const [formData, setFormData] = useState({
        name: '',
        email: '',
        phone: '',
        organization: '',
        bio: '',
        location: '',
        avatar: null,
        ...user
    });
    const [avatarPreviewUrl, setAvatarPreviewUrl] = useState(null);
    const [error, setError] = useState(null);

    useEffect(() => {
        // Cleanup avatar preview URL when component unmounts or when avatar changes
        return () => {
            if (avatarPreviewUrl) {
                URL.revokeObjectURL(avatarPreviewUrl);
            }
        };
    }, [avatarPreviewUrl]);

    const handleChange = (e) => {
        const { name, value } = e.target;
        setFormData(prev => ({
            ...prev,
            [name]: value
        }));
        setError(null);
    };

    const handleAvatarChange = (e) => {
        const file = e.target.files[0];
        if (!file) return;

        if (!file.type.startsWith('image/')) {
            setError('Please upload an image file');
            return;
        }

        if (file.size > MAX_FILE_SIZE) {
            setError('File size should be less than 5MB');
            return;
        }

        // Cleanup previous preview URL
        if (avatarPreviewUrl) {
            URL.revokeObjectURL(avatarPreviewUrl);
        }

        const previewUrl = URL.createObjectURL(file);
        setAvatarPreviewUrl(previewUrl);
        setFormData(prev => ({
            ...prev,
            avatar: file
        }));
        setError(null);
    };

    const handleSubmit = async (e) => {
        e.preventDefault();
        try {
            await onUpdate(formData);
            setIsEditing(false);
            setError(null);
        } catch (error) {
            console.error('Profile update error:', error);
            setError('Failed to update profile. Please try again.');
        }
    };

    return (
        <div 
            data-name="user-profile" 
            className="bg-white rounded-lg shadow-sm"
            role="region"
            aria-label="User Profile"
        >
            <div className="p-6">
                <div className="flex items-center justify-between mb-6">
                    <h2 className="text-2xl font-bold text-gray-900">Profile</h2>
                    <Button
                        variant={isEditing ? 'secondary' : 'primary'}
                        onClick={() => setIsEditing(!isEditing)}
                        aria-label={isEditing ? 'Cancel editing' : 'Edit profile'}
                    >
                        {isEditing ? 'Cancel' : 'Edit Profile'}
                    </Button>
                </div>

                {error && (
                    <div 
                        className="mb-4 p-3 bg-red-100 text-red-700 rounded-lg"
                        role="alert"
                    >
                        {error}
                    </div>
                )}

                {isEditing ? (
                    <form onSubmit={handleSubmit} className="space-y-6">
                        <div className="flex items-center space-x-4 mb-6">
                            <Avatar
                                src={avatarPreviewUrl || formData.avatar}
                                size="xl"
                                alt={`${formData.name}'s avatar`}
                            />
                            <Input
                                type="file"
                                name="avatar"
                                onChange={handleAvatarChange}
                                accept="image/*"
                                aria-label="Upload profile picture"
                            />
                        </div>

                        <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                            <Input
                                label="Name"
                                name="name"
                                value={formData.name}
                                onChange={handleChange}
                                required
                                aria-required="true"
                            />

                            <Input
                                label="Email"
                                name="email"
                                type="email"
                                value={formData.email}
                                onChange={handleChange}
                                required
                                aria-required="true"
                            />

                            <Input
                                label="Phone"
                                name="phone"
                                type="tel"
                                value={formData.phone}
                                onChange={handleChange}
                                pattern="[0-9\-\+\s\(\)]+"
                                aria-label="Phone number"
                            />

                            <Input
                                label="Organization"
                                name="organization"
                                value={formData.organization}
                                onChange={handleChange}
                            />

                            <Input
                                label="Location"
                                name="location"
                                value={formData.location}
                                onChange={handleChange}
                                icon={<i className="fas fa-map-marker-alt" aria-hidden="true"></i>}
                            />

                            <div className="md:col-span-2">
                                <Input
                                    label="Bio"
                                    name="bio"
                                    type="textarea"
                                    value={formData.bio}
                                    onChange={handleChange}
                                    maxLength={500}
                                />
                            </div>
                        </div>

                        <div className="flex justify-end space-x-4">
                            <Button
                                type="submit"
                                disabled={loading}
                                aria-busy={loading}
                            >
                                {loading ? 'Saving...' : 'Save Changes'}
                            </Button>
                        </div>
                    </form>
                ) : (
                    <div className="space-y-6">
                        <div className="flex items-center space-x-4">
                            <Avatar 
                                src={user.avatar} 
                                size="xl" 
                                alt={`${user.name}'s avatar`}
                            />
                            <div>
                                <h3 className="text-xl font-semibold text-gray-900">
                                    {user.name}
                                </h3>
                                {user.organization && (
                                    <p className="text-gray-500">{user.organization}</p>
                                )}
                            </div>
                        </div>

                        <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                            <div>
                                <h4 className="text-sm font-medium text-gray-500">Email</h4>
                                <p className="mt-1">{user.email}</p>
                            </div>

                            {user.phone && (
                                <div>
                                    <h4 className="text-sm font-medium text-gray-500">Phone</h4>
                                    <p className="mt-1">{user.phone}</p>
                                </div>
                            )}

                            {user.location && (
                                <div>
                                    <h4 className="text-sm font-medium text-gray-500">Location</h4>
                                    <p className="mt-1">
                                        <i className="fas fa-map-marker-alt text-gray-400 mr-2" aria-hidden="true"></i>
                                        {user.location}
                                    </p>
                                </div>
                            )}

                            {user.bio && (
                                <div className="md:col-span-2">
                                    <h4 className="text-sm font-medium text-gray-500">Bio</h4>
                                    <p className="mt-1">{user.bio}</p>
                                </div>
                            )}
                        </div>
                    </div>
                )}
            </div>
        </div>
    );
}

UserProfile.propTypes = {
    user: PropTypes.shape({
        name: PropTypes.string.isRequired,
        email: PropTypes.string.isRequired,
        phone: PropTypes.string,
        organization: PropTypes.string,
        bio: PropTypes.string,
        location: PropTypes.string,
        avatar: PropTypes.string
    }).isRequired,
    onUpdate: PropTypes.func.isRequired,
    loading: PropTypes.bool
};

export default UserProfile;
