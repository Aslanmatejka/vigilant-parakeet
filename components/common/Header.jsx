import React from "react";
import Avatar from "./Avatar";
import Button from "./Button";
import { useAuth } from "../../utils/hooks/useSupabase";
import PropTypes from 'prop-types';

function Header({ 
    menuItems = [
        { label: 'Home', path: '/' },
        { label: 'Share Food', path: '/share' },
        { label: 'Find Food', path: '/find' },

        { label: 'Community', path: '/community' }
    ]
}) {
    const { user: authUser, isAuthenticated, signOut } = useAuth();
    
    const [isMenuOpen, setIsMenuOpen] = React.useState(false);
    const [isDropdownOpen, setIsDropdownOpen] = React.useState(false);
    const dropdownRef = React.useRef(null);

    React.useEffect(() => {
        const handleClickOutside = (event) => {
            if (dropdownRef.current && !dropdownRef.current.contains(event.target)) {
                setIsDropdownOpen(false);
            }
        };

        document.addEventListener('mousedown', handleClickOutside);
        return () => {
            document.removeEventListener('mousedown', handleClickOutside);
        };
    }, []);

    const handleNavigation = (path) => {
        window.location.href = path;
    };

    const handleLogout = async () => {
        try {
            await signOut();
            window.location.href = '/';
        } catch (error) {
            console.error('Logout error:', error);
            window.location.href = '/';
        }
    };

    return (
        <header data-name="header" className="header sticky top-0 z-50 bg-white shadow-sm">
            <div className="container mx-auto px-4">
                <div className="flex items-center justify-between h-16">
                    {/* Mobile menu button */}
                    <div className="flex items-center lg:hidden">
                        <button
                            type="button"
                            className="inline-flex items-center justify-center p-2 rounded-md text-gray-600 hover:text-gray-900 hover:bg-gray-100"
                            onClick={() => setIsMenuOpen(true)}
                    >
                        <span className="sr-only">Open menu</span>
                        <i className="fas fa-bars text-xl"></i>
                    </button>
                    </div>

                    <div data-name="logo" className="flex items-center">
                        <a href="/" className="flex items-center">
                            <div className="h-10 w-10 bg-green-600 rounded-full flex items-center justify-center text-white">
                                <i className="fas fa-seedling text-xl"></i>
                            </div>
                            <span className="ml-2 text-xl font-semibold text-gray-900">DoGoods</span>
                        </a>
                    </div>

                    <nav data-name="desktop-nav" className="hidden md:flex space-x-6">
                        {menuItems.map((item, index) => (
                            <a 
                                key={index}
                                href={item.path}
                                className="nav-link hover:text-green-600 transition-colors duration-200"
                            >
                                {item.label}
                            </a>
                        ))}
                    </nav>

                    <div data-name="user-actions" className="hidden md:flex items-center space-x-4">
                        {isAuthenticated ? (
                            <div 
                                className="relative group"
                                ref={dropdownRef}
                            >
                                <button 
                                    className="flex items-center max-w-xs bg-white rounded-full focus:outline-none"
                                    onClick={() => setIsDropdownOpen(!isDropdownOpen)}
                                >
                                    <div className="flex items-center">
                                        <Avatar 
                                            size="sm" 
                                            src={authUser?.avatar_url} 
                                            alt={authUser?.name || authUser?.email || 'User'} 
                                        />
                                        <span className="ml-2 text-gray-700 text-sm">
                                            {authUser?.name || 'User'}
                                        </span>
                                        <i className={`fas fa-chevron-down text-xs ml-2 text-gray-400 transform transition-transform ${isDropdownOpen ? 'rotate-180' : ''}`}></i>
                                    </div>
                                </button>
                                
                                {isDropdownOpen && (
                                    <div 
                                        className="origin-top-right absolute right-0 mt-2 w-48 rounded-md shadow-lg bg-white ring-1 ring-black ring-opacity-5 divide-y divide-gray-100"
                                        role="menu"
                                    >
                                        <div className="py-1">
                                            <a 
                                                href="/profile" 
                                                className="block px-4 py-2 text-sm text-gray-700 hover:bg-gray-100"
                                                role="menuitem"
                                            >
                                                Your Profile
                                            </a>
                                            {authUser?.role === 'admin' && (
                                                <a 
                                                    href="/admin" 
                                                    className="block px-4 py-2 text-sm text-gray-700 hover:bg-gray-100"
                                                    role="menuitem"
                                                >
                                                    Admin Panel
                                                </a>
                                            )}
                                            <a 
                                                href="/settings" 
                                                className="block px-4 py-2 text-sm text-gray-700 hover:bg-gray-100"
                                                role="menuitem"
                                            >
                                                Settings
                                            </a>
                                        </div>
                                        <div className="py-1">
                                            <button
                                                onClick={handleLogout}
                                                className="block w-full text-left px-4 py-2 text-sm text-gray-700 hover:bg-gray-100"
                                                role="menuitem"
                                            >
                                                Sign out
                                            </button>
                                        </div>
                                    </div>
                                )}
                            </div>
                        ) : (
                            <div className="flex items-center space-x-2">
                                <Button
                                    variant="secondary"
                                    size="sm"
                                    onClick={() => handleNavigation('/login')}
                                >
                                    Sign In
                                </Button>
                                <Button
                                    variant="primary"
                                    size="sm"
                                    onClick={() => handleNavigation('/signup')}
                                >
                                    Sign Up
                                </Button>
                            </div>
                        )}
                    </div>
                </div>
            </div>

            {/* Mobile menu */}
            {isMenuOpen && (
                <div className="lg:hidden">
                    <div className="fixed inset-0 z-50">
                        <div className="fixed inset-0 bg-black bg-opacity-50" onClick={() => setIsMenuOpen(false)}></div>
                        <div className="fixed inset-y-0 left-0 w-64 bg-white shadow-lg">
                            <div className="flex items-center justify-between p-4 border-b">
                                <h2 className="text-xl font-semibold">Menu</h2>
                                <button
                                    onClick={() => setIsMenuOpen(false)}
                                    className="text-gray-500 hover:text-gray-700"
                                >
                                    <i className="fas fa-times"></i>
                                </button>
                            </div>
                            <nav className="p-4">
                                <ul className="space-y-2">
                                    {menuItems.map((item, index) => (
                                        <li key={index}>
                                            <a
                                                href={item.path}
                                                className="block px-4 py-2 text-gray-700 hover:bg-green-50 hover:text-green-600 rounded-lg"
                                                onClick={() => setIsMenuOpen(false)}
                                            >
                                                {item.label}
                                            </a>
                                        </li>
                                    ))}
                                </ul>
                            </nav>
                        </div>
                    </div>
                </div>
            )}
        </header>
    );
}

Header.propTypes = {
    menuItems: PropTypes.arrayOf(
        PropTypes.shape({
            label: PropTypes.string.isRequired,
            path: PropTypes.string.isRequired
        })
    )
};

export default Header;





