import React from 'react';
import PropTypes from 'prop-types';
import { Link } from 'react-router-dom';

function AdminSidebar({ active, onNavigate }) {
    const menuItems = [
        { id: 'dashboard', label: 'Dashboard', icon: 'fa-tachometer-alt', path: '/admin' },
        { id: 'users', label: 'User Management', icon: 'fa-users', path: '/admin/users' },
        { id: 'moderation', label: 'Content Moderation', icon: 'fa-shield-alt', path: '/admin/moderation' },
        { id: 'distributions', label: 'Food Distribution', icon: 'fa-box-open', path: '/admin/distributions' },
        { id: 'reports', label: 'Reports & Analytics', icon: 'fa-chart-bar', path: '/admin/reports' },
        { id: 'settings', label: 'Settings', icon: 'fa-cog', path: '/admin/settings' },
        { id: 'profile', label: 'Profile', icon: 'fa-user', path: '/admin/profile' }
    ];

    const handleKeyPress = (event, path) => {
        if (event.key === 'Enter' || event.key === ' ') {
            event.preventDefault();
            onNavigate(path);
        }
    };

    try {
        return (
            <div 
                data-name="admin-sidebar" 
                className="h-full flex flex-col bg-gray-800"
                role="navigation"
                aria-label="Admin navigation"
            >
                {/* Logo */}
                <div className="p-4 border-b border-gray-700">
                    <button 
                        onClick={() => onNavigate('/admin')}
                        className="flex items-center space-x-2 text-white"
                        aria-label="Go to admin dashboard"
                    >
                        <div className="h-8 w-8 bg-green-600 rounded-full flex items-center justify-center">
                            <i className="fas fa-seedling" aria-hidden="true"></i>
                        </div>
                        <span className="text-lg font-semibold">DoGoods Admin</span>
                    </button>
                </div>

                {/* Navigation */}
                <nav className="flex-1 px-2 py-4 space-y-1">
                    {menuItems.map(item => (
                        <button
                            key={item.id}
                            onClick={() => onNavigate(item.path)}
                            onKeyDown={(e) => handleKeyPress(e, item.path)}
                            className={`w-full flex items-center px-3 py-2 text-sm font-medium rounded-md transition-colors duration-150 ${
                                active === item.id
                                    ? 'text-white bg-gray-900'
                                    : 'text-gray-300 hover:text-white hover:bg-gray-700'
                            }`}
                            role="menuitem"
                            aria-current={active === item.id ? 'page' : undefined}
                        >
                            <i className={`fas ${item.icon} w-6`} aria-hidden="true"></i>
                            <span className="ml-3">{item.label}</span>
                        </button>
                    ))}
                </nav>

                {/* Bottom section */}
                <div className="p-4 border-t border-gray-700">
                    <button
                        onClick={() => onNavigate('/')}
                        className="w-full flex items-center px-3 py-2 text-sm font-medium text-gray-300 hover:text-white hover:bg-gray-700 rounded-md"
                        aria-label="Return to main site"
                    >
                        <i className="fas fa-arrow-left w-6" aria-hidden="true"></i>
                        <span className="ml-3">Back to Site</span>
                    </button>
                </div>
            </div>
        );
    } catch (error) {
        reportError(error);
        return null;
    }
}

AdminSidebar.propTypes = {
    active: PropTypes.string.isRequired,
    onNavigate: PropTypes.func.isRequired
};

export default AdminSidebar;
