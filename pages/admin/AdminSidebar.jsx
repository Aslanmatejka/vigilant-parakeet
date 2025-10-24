import React from 'react';
import PropTypes from 'prop-types';
import { reportError } from '../../utils/helpers';

function AdminSidebar({ active, onNavigate }) {
    try {
        const menuItems = [
            { id: 'dashboard', label: 'Dashboard', icon: 'fa-tachometer-alt', path: '/admin' },
            { id: 'users', label: 'User Management', icon: 'fa-users', path: '/admin/users' },
            { id: 'content', label: 'Content Moderation', icon: 'fa-shield-alt', path: '/admin/content' },
            { id: 'posts', label: 'Posts & Blog', icon: 'fa-newspaper', path: '/admin/posts' },
            { id: 'distribution', label: 'Food Distribution', icon: 'fa-box-open', path: '/admin/distribution' },
            { id: 'attendees', label: 'Distribution Attendees', icon: 'fa-users-cog', path: '/admin/attendees' },
            { id: 'impact', label: 'Impact Data Entry', icon: 'fa-table', path: '/admin/impact' },
            { id: 'reports', label: 'Reports & Analytics', icon: 'fa-chart-bar', path: '/admin/reports' },
            { id: 'settings', label: 'Settings', icon: 'fa-cog', path: '/admin/settings' }
        ];

        const handleKeyPress = (event, path) => {
            if (event.key === 'Enter' || event.key === ' ') {
                event.preventDefault();
                onNavigate(path);
            }
        };

        return (
            <div 
                data-name="admin-sidebar" 
                className="h-full flex flex-col"
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
                            className={`
                                w-full flex items-center px-4 py-2 text-sm font-medium rounded-md
                                transition-colors duration-150 ease-in-out
                                ${active === item.id 
                                    ? 'bg-gray-900 text-white' 
                                    : 'text-gray-300 hover:bg-gray-700 hover:text-white'}
                            `}
                            role="menuitem"
                            aria-current={active === item.id ? 'page' : undefined}
                        >
                            <i className={`fas ${item.icon} w-6`} aria-hidden="true"></i>
                            <span className="ml-3">{item.label}</span>
                        </button>
                    ))}
                </nav>

                {/* Footer */}
                <div className="p-4 border-t border-gray-700">
                    <button 
                        onClick={() => onNavigate('/')}
                        onKeyDown={(e) => handleKeyPress(e, '/')}
                        className="flex items-center px-2 py-2 text-sm font-medium text-gray-300 rounded-md hover:bg-gray-700 hover:text-white w-full"
                        aria-label="Return to main site"
                    >
                        <i className="fas fa-arrow-left w-6" aria-hidden="true"></i>
                        <span className="ml-3">Back to Site</span>
                    </button>
                </div>
            </div>
        );
    } catch (error) {
        console.error('AdminSidebar error:', error);
        reportError(error);
        return null;
    }
}

AdminSidebar.propTypes = {
    active: PropTypes.string.isRequired,
    onNavigate: PropTypes.func.isRequired
};

export default AdminSidebar;
