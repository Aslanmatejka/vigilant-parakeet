import React from "react";
import Avatar from "./Avatar";
import Button from "./Button";
import { useAuthContext } from "../../utils/AuthContext";
import { useNavigate, useLocation } from 'react-router-dom';
import { useTutorial } from '../../utils/TutorialContext';
import { useCommunityRole } from '../../utils/hooks/useCommunityRole.js';
import PropTypes from 'prop-types';

const SUPPORT_DROPDOWN = {
    label: 'Support Us',
    dropdown: [
        { label: 'Donate', path: '/donate' },
        { label: 'Volunteer', path: 'https://allgoodlivingfoundation.org/volunteer-form', external: true }
    ]
};
const COMMON_TAIL = [
    SUPPORT_DROPDOWN,
    { label: 'Impact Story', path: '/impact-story' },
    { label: 'Recipes', path: '/recipes' },
    { label: 'Sponsors', path: '/sponsors' },
    { label: 'Contact', path: '/contact' }
];

function Header({ menuItems: menuItemsProp }) {
    const { user: authUser, isAuthenticated, signOut } = useAuthContext();
    const communityRole = useCommunityRole();
    const isDonor = communityRole === 'donor';
    const isRecipient = communityRole === 'recipient';
    const isVolunteer = ['volunteer', 'driver', 'dispatcher'].includes(communityRole);

    const menuItems = React.useMemo(() => {
        if (menuItemsProp) return menuItemsProp;
        if (!isAuthenticated) {
            return [{ label: 'Find Food', path: '/find' }, ...COMMON_TAIL];
        }
        if (isDonor) {
            return [
                { label: 'Share Food', path: '/share' },
                { label: 'My Listings', path: '/listings' },
                { label: 'Donation Schedules', path: '/donations' },
                ...COMMON_TAIL,
            ];
        }
        if (isRecipient) {
            return [
                { label: 'Find Food', path: '/find' },
                { label: 'Near Me', path: '/near-me' },
                { label: 'My Receipts', path: '/receipts' },
                ...COMMON_TAIL,
            ];
        }
        if (isVolunteer) {
            return [
                { label: 'Find Food', path: '/find' },
                { label: 'Pickup Routes', path: '/donations' },
                { label: 'Near Me', path: '/near-me' },
                ...COMMON_TAIL,
            ];
        }
        return [{ label: 'Find Food', path: '/find' }, ...COMMON_TAIL];
    }, [menuItemsProp, isAuthenticated, isDonor, isRecipient, isVolunteer]);

    const navigate = useNavigate();
    const location = useLocation();
    const isAdminRoute = location.pathname.startsWith('/admin');
    const { startTutorial } = useTutorial();
    
    const [isMenuOpen, setIsMenuOpen] = React.useState(false);
    const [isDropdownOpen, setIsDropdownOpen] = React.useState(false);
    const [supportDropdownOpen, setSupportDropdownOpen] = React.useState(false);
    const dropdownRef = React.useRef(null);
    const supportDropdownRef = React.useRef(null);

    React.useEffect(() => {
        const handleClickOutside = (event) => {
            if (dropdownRef.current && !dropdownRef.current.contains(event.target)) {
                setIsDropdownOpen(false);
            }
            if (supportDropdownRef.current && !supportDropdownRef.current.contains(event.target)) {
                setSupportDropdownOpen(false);
            }
        };

        document.addEventListener('mousedown', handleClickOutside);
        return () => {
            document.removeEventListener('mousedown', handleClickOutside);
        };
    }, []);

    const handleNavigation = (path) => {
        navigate(path);
        window.scrollTo(0, 0);
    };

    const handleLogout = async () => {
        try {
            // Close menus immediately so UI feels responsive
            setIsDropdownOpen(false);
            setIsMenuOpen(false);

            // Sign out from Supabase (this clears localStorage and notifies listeners)
            await signOut();

            // Navigate to home page after successful sign out
            navigate('/', { replace: true });
        } catch (error) {
            console.error('Logout error:', error);

            // Even if sign out fails, clear local state and navigate
            localStorage.removeItem('userAuthenticated');
            localStorage.removeItem('currentUser');
            localStorage.removeItem('adminAuthenticated');
            localStorage.removeItem('adminUser');

            navigate('/', { replace: true });
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
                            <div className="h-10 w-10 bg-[#2CABE3] rounded-full flex items-center justify-center text-white">
                                <i className="fas fa-seedling text-xl"></i>
                            </div>
                            <span className="ml-2 text-xl font-semibold text-gray-900">DoGoods</span>
                        </a>
                    </div>

                    <nav data-name="desktop-nav" className="hidden lg:flex items-center gap-x-5 xl:gap-x-6 whitespace-nowrap text-sm xl:text-base">
                        {menuItems.map((item, index) => (
                            item.dropdown ? (
                                <div 
                                    key={index}
                                    className="relative"
                                    ref={supportDropdownRef}
                                >
                                    <button
                                        onClick={() => setSupportDropdownOpen(!supportDropdownOpen)}
                                        className="nav-link hover:text-[#2CABE3] transition-colors duration-200 flex items-center"
                                    >
                                        {item.label}
                                        <i className={`fas fa-chevron-down text-xs ml-1 transform transition-transform ${supportDropdownOpen ? 'rotate-180' : ''}`}></i>
                                    </button>
                                    {supportDropdownOpen && (
                                        <div className="absolute left-0 mt-2 w-48 rounded-md shadow-lg bg-white ring-1 ring-black ring-opacity-5 z-50">
                                            <div className="py-1" role="menu">
                                                {item.dropdown.map((subItem, subIndex) => (
                                                    subItem.external ? (
                                                        <button
                                                            key={subIndex}
                                                            className="w-full text-left block px-4 py-2 text-sm text-gray-700 hover:bg-[#2CABE3]/10 hover:text-[#2CABE3]"
                                                            role="menuitem"
                                                            onClick={() => {
                                                                window.open(subItem.path, '_blank', 'noopener,noreferrer');
                                                                setSupportDropdownOpen(false);
                                                            }}
                                                        >
                                                            {subItem.label}
                                                            <i className="fas fa-external-link-alt ml-2 text-xs"></i>
                                                        </button>
                                                    ) : (
                                                        <a
                                                            key={subIndex}
                                                            href={subItem.path}
                                                            className="block px-4 py-2 text-sm text-gray-700 hover:bg-[#2CABE3]/10 hover:text-[#2CABE3]"
                                                            role="menuitem"
                                                            onClick={() => setSupportDropdownOpen(false)}
                                                        >
                                                            {subItem.label}
                                                        </a>
                                                    )
                                                ))}
                                            </div>
                                        </div>
                                    )}
                                </div>
                            ) : (
                                <a 
                                    key={index}
                                    href={item.path}
                                    className="nav-link hover:text-[#2CABE3] transition-colors duration-200"
                                >
                                    {item.label}
                                </a>
                            )
                        ))}
                        {isAuthenticated && (
                            <a
                                href="/dashboard"
                                className="nav-link hover:text-[#2CABE3] transition-colors duration-200"
                            >
                                Receipts & Activity
                            </a>
                        )}
                    </nav>

                    <div data-name="user-actions" className="hidden lg:flex items-center space-x-3 xl:space-x-4">
                        {/* Help / Tutorial button */}
                        <button
                            onClick={() => startTutorial()}
                            className="w-8 h-8 rounded-full border-2 border-[#2CABE3] text-[#2CABE3] hover:bg-[#2CABE3] hover:text-white flex items-center justify-center transition-all duration-200 text-sm font-bold"
                            title="Take a guided tour"
                            aria-label="Start tutorial"
                        >
                            ?
                        </button>
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
                                                href="/dashboard"
                                                className="block px-4 py-2 text-sm text-gray-700 hover:bg-gray-100"
                                                role="menuitem"
                                            >
                                                Receipts & Activity
                                            </a>
                                            {!isAdminRoute && (
                                                <a
                                                    href="/profile"
                                                    className="block px-4 py-2 text-sm text-gray-700 hover:bg-gray-100"
                                                    role="menuitem"
                                                >
                                                    Your Profile
                                                </a>
                                            )}
                                            {/* TEMPORARILY DISABLED
                                            <a
                                                href="/listings"
                                                className="block px-4 py-2 text-sm text-gray-700 hover:bg-gray-100"
                                                role="menuitem"
                                            >
                                                My Listings
                                            </a>
                                            */}
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
                                <span data-tutorial="signup-btn">
                                <Button
                                    variant="primary"
                                    size="sm"
                                    onClick={() => handleNavigation('/signup')}
                                >
                                    Sign Up
                                </Button>
                                </span>
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
                                        item.dropdown ? (
                                            <li key={index}>
                                                <div className="px-4 py-2 text-gray-900 font-semibold">
                                                    {item.label}
                                                </div>
                                                <ul className="ml-4 space-y-1 mt-1">
                                                    {item.dropdown.map((subItem, subIndex) => (
                                                        <li key={subIndex}>
                                                            {subItem.external ? (
                                                                <button
                                                                    className="w-full text-left block px-4 py-2 text-gray-700 hover:bg-[#2CABE3]/10 hover:text-[#2CABE3] rounded-lg"
                                                                    onClick={() => {
                                                                        window.open(subItem.path, '_blank', 'noopener,noreferrer');
                                                                        setIsMenuOpen(false);
                                                                    }}
                                                                >
                                                                    {subItem.label}
                                                                    <i className="fas fa-external-link-alt ml-2 text-xs"></i>
                                                                </button>
                                                            ) : (
                                                                <a
                                                                    href={subItem.path}
                                                                    className="block px-4 py-2 text-gray-700 hover:bg-[#2CABE3]/10 hover:text-[#2CABE3] rounded-lg"
                                                                    onClick={() => setIsMenuOpen(false)}
                                                                >
                                                                    {subItem.label}
                                                                </a>
                                                            )}
                                                        </li>
                                                    ))}
                                                </ul>
                                            </li>
                                        ) : (
                                            <li key={index}>
                                                <a
                                                    href={item.path}
                                                    className="block px-4 py-2 text-gray-700 hover:bg-[#2CABE3]/10 hover:text-[#2CABE3] rounded-lg"
                                                    onClick={() => setIsMenuOpen(false)}
                                                >
                                                    {item.label}
                                                </a>
                                            </li>
                                        )
                                    ))}
                                    {isAuthenticated && (
                                        <>
                                            <li className="border-t border-gray-200 mt-2 pt-2">
                                                <a
                                                    href="/dashboard"
                                                    className="block px-4 py-2 text-gray-700 hover:bg-[#2CABE3]/10 hover:text-[#2CABE3] rounded-lg"
                                                    onClick={() => setIsMenuOpen(false)}
                                                >
                                                    Receipts & Activity
                                                </a>
                                            </li>
                                            {!isAdminRoute && (
                                                <li>
                                                    <a
                                                        href="/profile"
                                                        className="block px-4 py-2 text-gray-700 hover:bg-[#2CABE3]/10 hover:text-[#2CABE3] rounded-lg"
                                                        onClick={() => setIsMenuOpen(false)}
                                                    >
                                                        Your Profile
                                                    </a>
                                                </li>
                                            )}
                                            {/* TEMPORARILY DISABLED
                                            <li>
                                                <a
                                                    href="/listings"
                                                    className="block px-4 py-2 text-gray-700 hover:bg-[#2CABE3]/10 hover:text-[#2CABE3] rounded-lg"
                                                    onClick={() => setIsMenuOpen(false)}
                                                >
                                                    My Listings
                                                </a>
                                            </li>
                                            */}
                                            {authUser?.role === 'admin' && (
                                                <li>
                                                    <a
                                                        href="/admin"
                                                        className="block px-4 py-2 text-gray-700 hover:bg-[#2CABE3]/10 hover:text-[#2CABE3] rounded-lg"
                                                        onClick={() => setIsMenuOpen(false)}
                                                    >
                                                        Admin Panel
                                                    </a>
                                                </li>
                                            )}
                                            <li>
                                                <a
                                                    href="/settings"
                                                    className="block px-4 py-2 text-gray-700 hover:bg-[#2CABE3]/10 hover:text-[#2CABE3] rounded-lg"
                                                    onClick={() => setIsMenuOpen(false)}
                                                >
                                                    Settings
                                                </a>
                                            </li>
                                            <li>
                                                <button
                                                    onClick={() => {
                                                        setIsMenuOpen(false);
                                                        startTutorial();
                                                    }}
                                                    className="w-full block px-4 py-2 text-gray-700 hover:bg-[#2CABE3]/10 hover:text-[#2CABE3] rounded-lg text-left"
                                                >
                                                    <i className="fas fa-question-circle mr-2"></i>
                                                    Take a Tour
                                                </button>
                                            </li>
                                            <li className="border-t border-gray-200 mt-2 pt-2">
                                                <button
                                                    onClick={() => {
                                                        setIsMenuOpen(false);
                                                        handleLogout();
                                                    }}
                                                    className="block w-full text-left px-4 py-2 text-red-600 hover:bg-red-50 rounded-lg"
                                                >
                                                    Sign out
                                                </button>
                                            </li>
                                        </>
                                    )}
                                    {!isAuthenticated && (
                                        <>
                                            <li className="border-t border-gray-200 mt-2 pt-2">
                                                <button
                                                    onClick={() => {
                                                        setIsMenuOpen(false);
                                                        startTutorial();
                                                    }}
                                                    className="w-full block px-4 py-2 text-gray-700 hover:bg-[#2CABE3]/10 hover:text-[#2CABE3] rounded-lg text-left"
                                                >
                                                    <i className="fas fa-question-circle mr-2"></i>
                                                    Take a Tour
                                                </button>
                                            </li>
                                            <li>
                                                <a
                                                    href="/login"
                                                    className="block px-4 py-2 text-gray-700 hover:bg-[#2CABE3]/10 hover:text-[#2CABE3] rounded-lg"
                                                    onClick={() => setIsMenuOpen(false)}
                                                >
                                                    Sign In
                                                </a>
                                            </li>
                                            <li>
                                                <a
                                                    href="/signup"
                                                    className="block px-4 py-2 bg-[#2CABE3] text-white hover:opacity-90 rounded-lg text-center"
                                                    onClick={() => setIsMenuOpen(false)}
                                                >
                                                    Sign Up
                                                </a>
                                            </li>
                                        </>
                                    )}
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





