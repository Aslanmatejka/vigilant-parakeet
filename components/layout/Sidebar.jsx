import React from 'react';
import PropTypes from 'prop-types';
import Avatar from '../common/Avatar';

function Sidebar({ 
    isOpen, 
    onClose,
    menuItems = [
        { icon: 'fa-home', label: 'Home', path: '/' },
        { icon: 'fa-share-alt', label: 'Share Food', path: '/share' },
        { icon: 'fa-search', label: 'Find Food', path: '/find' },
        { icon: 'fa-users', label: 'Community', path: '/community' },
        { icon: 'fa-user', label: 'Profile', path: '/profile' }
    ]
}) {
    return (
        <div data-name="sidebar">
            {/* Overlay */}
            {isOpen && (
                <div
                    className="fixed inset-0 bg-black bg-opacity-50 z-40 lg:hidden"
                    onClick={onClose}
                />
            )}

            {/* Sidebar */}
            <div
                className={`
                    fixed top-0 left-0 bottom-0
                    w-64 bg-white shadow-lg z-50
                    transform transition-transform duration-300 ease-in-out
                    ${isOpen ? 'translate-x-0' : '-translate-x-full'}
                    lg:translate-x-0 lg:static
                `}
            >
                <div className="p-4 border-b">
                    <div className="flex items-center justify-between">
                        <h2 className="text-xl font-semibold text-gray-800">ShareFoods</h2>
                        <button
                            onClick={onClose}
                            className="lg:hidden text-gray-500 hover:text-gray-700"
                        >
                            <i className="fas fa-times"></i>
                        </button>
                    </div>
                </div>

                <nav className="p-4">
                    <ul className="space-y-2">
                        {menuItems.map((item, index) => (
                            <li key={index}>
                                <a
                                    href={item.path}
                                    className="
                                        flex items-center px-4 py-2 rounded-lg
                                        text-gray-700 hover:bg-green-50 hover:text-green-600
                                        transition-colors duration-200
                                    "
                                >
                                    <i className={`fas ${item.icon} w-5`}></i>
                                    <span className="ml-3">{item.label}</span>
                                </a>
                            </li>
                        ))}
                    </ul>
                </nav>

                <div className="absolute bottom-0 left-0 right-0 p-4 border-t">
                    <div className="flex items-center space-x-3">
                        <Avatar size="sm" />
                        <div>
                            <p className="text-sm font-medium text-gray-700">John Doe</p>
                            <p className="text-xs text-gray-500">View Profile</p>
                        </div>
                    </div>
                </div>
            </div>
        </div>
    );
}

Sidebar.propTypes = {
    isOpen: PropTypes.bool.isRequired,
    onClose: PropTypes.func.isRequired,
    menuItems: PropTypes.arrayOf(
        PropTypes.shape({
            icon: PropTypes.string.isRequired,
            label: PropTypes.string.isRequired,
            path: PropTypes.string.isRequired
        })
    )
};

export default Sidebar;
