import React from 'react';
import PropTypes from 'prop-types';
import { Link } from 'react-router-dom';

function AdminSidebar({ active }) {
    const menuItems = [
        { id: 'dashboard', label: 'Dashboard', icon: 'fa-tachometer-alt', path: '/admin' },
        { id: 'users', label: 'User Management', icon: 'fa-users', path: '/admin/users' },
        { id: 'moderation', label: 'Content Moderation', icon: 'fa-shield-alt', path: '/admin/moderation' },
        { id: 'distributions', label: 'Food Distribution', icon: 'fa-box-open', path: '/admin/distributions' },
        { id: 'reports', label: 'Reports & Analytics', icon: 'fa-chart-bar', path: '/admin/reports' },
        { id: 'settings', label: 'Settings', icon: 'fa-cog', path: '/admin/settings' },
        { id: 'profile', label: 'Profile', icon: 'fa-user', path: '/admin/profile' }
    ];

    return (
        <div className="h-full flex flex-col bg-gray-800">
            {/* Logo */}
            <div className="p-4 border-b border-gray-700">
                <Link to="/admin" className="flex items-center space-x-2 text-white">
                    <div className="h-8 w-8 bg-green-600 rounded-full flex items-center justify-center">
                        <i className="fas fa-seedling"></i>
                    </div>
                    <span className="text-lg font-semibold">DoGoods Admin</span>
                </Link>
            </div>

            {/* Navigation */}
            <nav className="flex-1 px-2 py-4 space-y-1">
                {menuItems.map(item => (
                    <Link
                        key={item.id}
                        to={item.path}
                        className={`flex items-center px-3 py-2 text-sm font-medium rounded-md ${
                            active === item.id
                                ? 'text-white bg-gray-900'
                                : 'text-gray-300 hover:text-white hover:bg-gray-700'
                        }`}
                    >
                        <i className={`fas ${item.icon} w-6`}></i>
                        <span className="ml-3">{item.label}</span>
                    </Link>
                ))}
            </nav>

            {/* Bottom section */}
            <div className="p-4 border-t border-gray-700">
                <Link
                    to="/"
                    className="flex items-center px-3 py-2 text-sm font-medium text-gray-300 hover:text-white hover:bg-gray-700 rounded-md"
                >
                    <i className="fas fa-arrow-left w-6"></i>
                    <span className="ml-3">Back to Site</span>
                </Link>
            </div>
        </div>
    );
}

AdminSidebar.propTypes = {
    active: PropTypes.string.isRequired
};

export default AdminSidebar;
