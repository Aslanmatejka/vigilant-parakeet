import React from "react";
import Avatar from "./Avatar";
import Button from "./Button";
import { useAuthContext } from "../../utils/AuthContext";
import { useNavigate, useLocation, Link } from 'react-router-dom';
import { useTutorial } from '../../utils/TutorialContext';
import { useCommunityRole } from '../../utils/hooks/useCommunityRole.js';
import { browseCommunityIdsForUser } from '../../utils/communityScope';
import dataService from '../../utils/dataService';
import PropTypes from 'prop-types';

const SUPPORT_DROPDOWN = {
    label: 'Support Us',
    dropdown: [
        { label: 'Donate', path: '/donate' },
        { label: 'Volunteer', path: 'https://allgoodlivingfoundation.org/volunteer-form', external: true }
    ]
};
// Visitor nav keeps the marketing pages prominent.
const VISITOR_TAIL = [
    SUPPORT_DROPDOWN,
    { label: 'Impact Story', path: '/impact-story' },
    { label: 'Partners', path: '/sponsors' },
    { label: 'Contact', path: '/contact' }
];
// Authenticated roles get a slimmer tail — marketing pages live in the footer.
const AUTH_TAIL = [
    SUPPORT_DROPDOWN,
    { label: 'Contact', path: '/contact' }
];

function formatNavCount(n) {
    const count = Number(n) || 0;
    if (count <= 0) return null;
    if (count > 99) return '99+';
    return String(count);
}

function NavCountBadge({ count, label }) {
    const text = formatNavCount(count);
    if (!text) return null;
    return (
        <span
            className="ml-1.5 inline-flex min-w-[1.25rem] items-center justify-center rounded-full bg-[#2CABE3] px-1.5 py-0.5 text-[10px] font-semibold leading-none text-white"
            aria-label={`${text} ${label}`}
        >
            {text}
        </span>
    );
}

NavCountBadge.propTypes = {
    count: PropTypes.number,
    label: PropTypes.string.isRequired,
};

function Header({ menuItems: menuItemsProp }) {
    const { user: authUser, isAuthenticated, signOut } = useAuthContext();
    const communityRole = useCommunityRole();
    const isDonor = communityRole === 'donor';
    const isRecipient = communityRole === 'recipient';
    const isOrganizer = communityRole === 'organizer';
    const isAdmin = authUser?.is_admin === true || authUser?.role === 'admin';
    const showReceiptsAndActivity = isAuthenticated && !isDonor && !isOrganizer;

    const menuItems = React.useMemo(() => {
        if (menuItemsProp) return menuItemsProp;
        if (!isAuthenticated) {
            return [{ label: 'Find Food', path: '/find' }, ...VISITOR_TAIL];
        }
        if (isDonor) {
            return [
                { label: 'Share Food', path: '/share' },
                { label: 'Community Requests', path: '/community-requests' },
                { label: 'Partners', path: '/sponsors' },
                { label: 'Impact', path: '/impact-story' },
                SUPPORT_DROPDOWN,
                { label: 'Contact', path: '/contact' },
            ];
        }
        if (isRecipient) {
            return [
                { label: 'Find Food', path: '/find' },
                { label: 'Request Food', path: '/request' },
                { label: 'Receipts & Activity', path: '/receipts' },
                { label: 'Partners', path: '/sponsors' },
                { label: 'Impact', path: '/impact-story' },
                SUPPORT_DROPDOWN,
                { label: 'Contact', path: '/contact' },
            ];
        }
        if (isOrganizer) {
            return [
                { label: 'Share Food', path: '/share' },
                { label: 'Find Food', path: '/find' },
                { label: 'Request Food', path: '/request' },
                { label: 'Community Requests', path: '/community-requests' },
                { label: 'Partners', path: '/sponsors' },
                { label: 'Impact', path: '/impact-story' },
                SUPPORT_DROPDOWN,
                { label: 'Contact', path: '/contact' },
            ];
        }
        return [{ label: 'Find Food', path: '/find' }, ...AUTH_TAIL];
    }, [menuItemsProp, isAuthenticated, isDonor, isRecipient, isOrganizer]);

    const hasReceiptsInMainNav = menuItems.some((item) => item.label === 'Receipts & Activity');
    const showReceiptsNavLink = showReceiptsAndActivity && !hasReceiptsInMainNav;
    const showFindFoodBadge = menuItems.some((item) => item.path === '/find');
    const showRequestsBadge = menuItems.some((item) => item.path === '/community-requests');

    const navigate = useNavigate();
    const location = useLocation();
    const isAdminRoute = location.pathname.startsWith('/admin');
    const { startTutorial } = useTutorial();
    
    const [isMenuOpen, setIsMenuOpen] = React.useState(false);
    const [isDropdownOpen, setIsDropdownOpen] = React.useState(false);
    const [supportDropdownOpen, setSupportDropdownOpen] = React.useState(false);
    const [findFoodCount, setFindFoodCount] = React.useState(0);
    const [requestCount, setRequestCount] = React.useState(0);
    const dropdownRef = React.useRef(null);
    const supportDropdownRef = React.useRef(null);

    React.useEffect(() => {
        let cancelled = false;

        const loadCounts = async () => {
            if (!showFindFoodBadge && !showRequestsBadge) {
                if (!cancelled) {
                    setFindFoodCount(0);
                    setRequestCount(0);
                }
                return;
            }

            const allowedCommunityIds = browseCommunityIdsForUser(authUser, { isAdmin });
            const tasks = [];

            if (showFindFoodBadge) {
                tasks.push(
                    dataService.countLiveListings({
                        listing_type: 'donation',
                        community_ids: allowedCommunityIds,
                        exclude_user_id: isAuthenticated && authUser?.id ? authUser.id : null,
                    }).then((n) => {
                        if (!cancelled) setFindFoodCount(n);
                    })
                );
            } else if (!cancelled) {
                setFindFoodCount(0);
            }

            if (showRequestsBadge) {
                tasks.push(
                    dataService.countLiveListings({
                        listing_type: 'request',
                        community_ids: allowedCommunityIds,
                    }).then((n) => {
                        if (!cancelled) setRequestCount(n);
                    })
                );
            } else if (!cancelled) {
                setRequestCount(0);
            }

            await Promise.all(tasks);
        };

        loadCounts();

        const onFoodChanged = () => { loadCounts(); };
        window.addEventListener('foodShared', onFoodChanged);
        window.addEventListener('focus', onFoodChanged);
        const interval = window.setInterval(loadCounts, 60000);

        return () => {
            cancelled = true;
            window.removeEventListener('foodShared', onFoodChanged);
            window.removeEventListener('focus', onFoodChanged);
            window.clearInterval(interval);
        };
    }, [
        showFindFoodBadge,
        showRequestsBadge,
        isAuthenticated,
        isAdmin,
        authUser?.id,
        authUser?.community_id,
    ]);

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
        setIsDropdownOpen(false);
        setSupportDropdownOpen(false);
        setIsMenuOpen(false);
        navigate(path);
        window.scrollTo(0, 0);
    };

    const closeMenus = () => {
        setIsDropdownOpen(false);
        setSupportDropdownOpen(false);
        setIsMenuOpen(false);
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

    const renderNavLabel = (item) => {
        if (item.path === '/find') {
            return (
                <span className="inline-flex items-center">
                    {item.label}
                    <NavCountBadge count={findFoodCount} label="food listings available" />
                </span>
            );
        }
        if (item.path === '/community-requests') {
            return (
                <span className="inline-flex items-center">
                    {item.label}
                    <NavCountBadge count={requestCount} label="open food requests" />
                </span>
            );
        }
        return item.label;
    };

    return (
        <header data-name="header" className="header sticky top-0 z-50 bg-white shadow-sm">
            <div className="container mx-auto px-3 sm:px-4">
                <div className="flex items-center justify-between h-14 sm:h-16">
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
                        <Link to="/" className="flex items-center" onClick={closeMenus}>
                            <div className="h-10 w-10 bg-[#2CABE3] rounded-full flex items-center justify-center text-white">
                                <i className="fas fa-seedling text-xl"></i>
                            </div>
                            <span className="ml-2 text-xl font-semibold text-gray-900">DoGoods</span>
                        </Link>
                    </div>

                    <nav data-name="desktop-nav" className="hidden lg:flex flex-1 items-center justify-center gap-x-5 xl:gap-x-6 whitespace-nowrap text-sm xl:text-base">
                        {menuItems.map((item, index) => (
                            item.dropdown ? (
                                <div 
                                    key={index}
                                    className="relative"
                                    ref={supportDropdownRef}
                                >
                                    <button
                                        type="button"
                                        onClick={() => setSupportDropdownOpen(!supportDropdownOpen)}
                                        className="nav-link hover:text-[#2CABE3] transition-colors duration-75 flex items-center"
                                    >
                                        {item.label}
                                        <i className={`fas fa-chevron-down text-xs ml-1 transition-transform duration-75 ${supportDropdownOpen ? 'rotate-180' : ''}`}></i>
                                    </button>
                                    {supportDropdownOpen && (
                                        <div className="absolute left-0 mt-2 w-48 rounded-md shadow-lg bg-white ring-1 ring-black ring-opacity-5 z-50">
                                            <div className="py-1" role="menu">
                                                {item.dropdown.map((subItem, subIndex) => (
                                                    subItem.external ? (
                                                        <button
                                                            key={subIndex}
                                                            type="button"
                                                            className="nav-menu-item w-full text-left block px-4 py-2 text-sm text-gray-700 hover:text-[#2CABE3]"
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
                                                        <Link
                                                            key={subIndex}
                                                            to={subItem.path}
                                                            className="nav-menu-item block px-4 py-2 text-sm text-gray-700 hover:text-[#2CABE3]"
                                                            role="menuitem"
                                                            onClick={closeMenus}
                                                        >
                                                            {subItem.label}
                                                        </Link>
                                                    )
                                                ))}
                                            </div>
                                        </div>
                                    )}
                                </div>
                            ) : (
                                <Link 
                                    key={index}
                                    to={item.path}
                                    className="nav-link hover:text-[#2CABE3] transition-colors duration-75"
                                    onClick={closeMenus}
                                >
                                    {renderNavLabel(item)}
                                </Link>
                            )
                        ))}
                        {showReceiptsNavLink && (
                            <Link
                                to="/receipts"
                                className="nav-link hover:text-[#2CABE3] transition-colors duration-75"
                                onClick={closeMenus}
                            >
                                Receipts & Activity
                            </Link>
                        )}
                    </nav>

                    <div data-name="user-actions" className="hidden lg:flex items-center space-x-3 xl:space-x-4">
                        {/* Help / Tutorial button */}
                        <button
                            onClick={() => startTutorial()}
                            className="w-8 h-8 rounded-full border-2 border-[#2CABE3] text-[#2CABE3] hover:bg-[#2CABE3] hover:text-white flex items-center justify-center transition-colors duration-75 text-sm font-bold"
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
                                        <i className={`fas fa-chevron-down text-xs ml-2 text-gray-400 transition-transform duration-75 ${isDropdownOpen ? 'rotate-180' : ''}`}></i>
                                    </div>
                                </button>
                                
                                {isDropdownOpen && (
                                    <div 
                                        className="origin-top-right absolute right-0 mt-2 w-48 rounded-md shadow-lg bg-white ring-1 ring-black ring-opacity-5 divide-y divide-gray-100"
                                        role="menu"
                                    >
                                        <div className="py-1">
                                            {showReceiptsNavLink && (
                                                <Link
                                                    to="/receipts"
                                                    className="nav-menu-item block px-4 py-2 text-sm text-gray-700"
                                                    role="menuitem"
                                                    onClick={closeMenus}
                                                >
                                                    Receipts & Activity
                                                </Link>
                                            )}
                                            {!isAdminRoute && (
                                                <Link
                                                    to="/profile"
                                                    className="nav-menu-item block px-4 py-2 text-sm text-gray-700"
                                                    role="menuitem"
                                                    onClick={closeMenus}
                                                >
                                                    Your Profile
                                                </Link>
                                            )}
                                            {(authUser?.is_admin === true || authUser?.role === 'admin') && (
                                                <Link
                                                    to="/admin"
                                                    className="nav-menu-item block px-4 py-2 text-sm text-gray-700"
                                                    role="menuitem"
                                                    onClick={closeMenus}
                                                >
                                                    Admin Panel
                                                </Link>
                                            )}
                                            <Link
                                                to="/settings"
                                                className="nav-menu-item block px-4 py-2 text-sm text-gray-700"
                                                role="menuitem"
                                                onClick={closeMenus}
                                            >
                                                Settings
                                            </Link>
                                        </div>
                                        <div className="py-1">
                                            <button
                                                type="button"
                                                onClick={handleLogout}
                                                className="nav-menu-item block w-full text-left px-4 py-2 text-sm text-gray-700"
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
                                                                    type="button"
                                                                    className="nav-menu-item w-full text-left block px-4 py-2 text-gray-700 rounded-lg"
                                                                    onClick={() => {
                                                                        window.open(subItem.path, '_blank', 'noopener,noreferrer');
                                                                        setIsMenuOpen(false);
                                                                    }}
                                                                >
                                                                    {subItem.label}
                                                                    <i className="fas fa-external-link-alt ml-2 text-xs"></i>
                                                                </button>
                                                            ) : (
                                                                <Link
                                                                    to={subItem.path}
                                                                    className="nav-menu-item block px-4 py-2 text-gray-700 rounded-lg"
                                                                    onClick={closeMenus}
                                                                >
                                                                    {subItem.label}
                                                                </Link>
                                                            )}
                                                        </li>
                                                    ))}
                                                </ul>
                                            </li>
                                        ) : (
                                            <li key={index}>
                                                <Link
                                                    to={item.path}
                                                    className="nav-menu-item block px-4 py-2 text-gray-700 rounded-lg"
                                                    onClick={closeMenus}
                                                >
                                                    {renderNavLabel(item)}
                                                </Link>
                                            </li>
                                        )
                                    ))}
                                    {isAuthenticated && (
                                        <>
                                            {showReceiptsNavLink && (
                                                <li className="border-t border-gray-200 mt-2 pt-2">
                                                    <Link
                                                        to="/receipts"
                                                        className="nav-menu-item block px-4 py-2 text-gray-700 rounded-lg"
                                                        onClick={closeMenus}
                                                    >
                                                        Receipts & Activity
                                                    </Link>
                                                </li>
                                            )}
                                            {!isAdminRoute && (
                                                <li className={showReceiptsNavLink ? undefined : 'border-t border-gray-200 mt-2 pt-2'}>
                                                    <Link
                                                        to="/profile"
                                                        className="nav-menu-item block px-4 py-2 text-gray-700 rounded-lg"
                                                        onClick={closeMenus}
                                                    >
                                                        Your Profile
                                                    </Link>
                                                </li>
                                            )}
                                            {(authUser?.is_admin === true || authUser?.role === 'admin') && (
                                                <li>
                                                    <Link
                                                        to="/admin"
                                                        className="nav-menu-item block px-4 py-2 text-gray-700 rounded-lg"
                                                        onClick={closeMenus}
                                                    >
                                                        Admin Panel
                                                    </Link>
                                                </li>
                                            )}
                                            <li>
                                                <Link
                                                    to="/settings"
                                                    className="nav-menu-item block px-4 py-2 text-gray-700 rounded-lg"
                                                    onClick={closeMenus}
                                                >
                                                    Settings
                                                </Link>
                                            </li>
                                            <li>
                                                <button
                                                    type="button"
                                                    onClick={() => {
                                                        setIsMenuOpen(false);
                                                        startTutorial();
                                                    }}
                                                    className="nav-menu-item w-full block px-4 py-2 text-gray-700 rounded-lg text-left"
                                                >
                                                    <i className="fas fa-question-circle mr-2"></i>
                                                    Take a Tour
                                                </button>
                                            </li>
                                            <li className="border-t border-gray-200 mt-2 pt-2">
                                                <button
                                                    type="button"
                                                    onClick={() => {
                                                        setIsMenuOpen(false);
                                                        handleLogout();
                                                    }}
                                                    className="nav-menu-item block w-full text-left px-4 py-2 text-red-600 rounded-lg"
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
                                                    type="button"
                                                    onClick={() => {
                                                        setIsMenuOpen(false);
                                                        startTutorial();
                                                    }}
                                                    className="nav-menu-item w-full block px-4 py-2 text-gray-700 rounded-lg text-left"
                                                >
                                                    <i className="fas fa-question-circle mr-2"></i>
                                                    Take a Tour
                                                </button>
                                            </li>
                                            <li>
                                                <Link
                                                    to="/login"
                                                    className="nav-menu-item block px-4 py-2 text-gray-700 rounded-lg"
                                                    onClick={closeMenus}
                                                >
                                                    Sign In
                                                </Link>
                                            </li>
                                            <li>
                                                <Link
                                                    to="/signup"
                                                    className="block px-4 py-2 bg-[#2CABE3] text-white rounded-lg text-center"
                                                    onClick={closeMenus}
                                                >
                                                    Sign Up
                                                </Link>
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





