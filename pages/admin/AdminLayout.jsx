import React from 'react';
import PropTypes from 'prop-types';
import { useNavigate } from 'react-router-dom';
import AdminSidebar, { ADMIN_MENU_FLAT } from './AdminSidebar';
import AIHealthBanner from '../../components/common/AIHealthBanner';
import { useAuthContext } from '../../utils/AuthContext';

const COLLAPSE_STORAGE_KEY = 'dogoods.admin.sidebarCollapsed';

/**
 * AdminLayout — the chrome surrounding every admin page.
 *
 * UX goals of this revision:
 *  • Persistent, discoverable desktop sidebar (no more hover-trigger strip)
 *  • Collapsible icon-rail mode that persists across sessions via localStorage
 *  • Real breadcrumb (Admin / <Section>) instead of an awkward single word
 *  • Lightweight admin "command-search" that filters and jumps to any page
 *  • Notification bell carries a live count of pending approvals via the badge prop
 *  • Skip-to-content link + ESC-to-close for keyboard users
 */
function AdminLayout({ children, active, pendingApprovals = 0 }) {
    const navigate = useNavigate();
    const { user, signOut } = useAuthContext();

    const [isMobileSidebarOpen, setIsMobileSidebarOpen] = React.useState(false);
    const [isCollapsed, setIsCollapsed] = React.useState(() => {
        if (typeof window === 'undefined') return false;
        try {
            return window.localStorage.getItem(COLLAPSE_STORAGE_KEY) === '1';
        } catch (_) { return false; }
    });

    const [showSearch, setShowSearch] = React.useState(false);
    const [searchQuery, setSearchQuery] = React.useState('');
    const [activeResultIdx, setActiveResultIdx] = React.useState(0);
    const [showUserMenu, setShowUserMenu] = React.useState(false);

    const searchInputRef = React.useRef(null);
    const userMenuRef = React.useRef(null);

    const handleNavigation = (path) => {
        navigate(path);
        window.scrollTo(0, 0);
        setIsMobileSidebarOpen(false);
        setShowSearch(false);
        setShowUserMenu(false);
    };

    const toggleCollapse = () => {
        setIsCollapsed((c) => {
            const next = !c;
            try { window.localStorage.setItem(COLLAPSE_STORAGE_KEY, next ? '1' : '0'); } catch (_) {}
            return next;
        });
    };

    // Active item lookup powers the breadcrumb label + user-menu context line.
    const activeItem = React.useMemo(
        () => ADMIN_MENU_FLAT.find((i) => i.id === active),
        [active]
    );

    // Filtered search results
    const searchResults = React.useMemo(() => {
        const q = searchQuery.trim().toLowerCase();
        if (!q) return ADMIN_MENU_FLAT.slice(0, 8);
        return ADMIN_MENU_FLAT
            .filter((i) => i.label.toLowerCase().includes(q) || i.id.toLowerCase().includes(q))
            .slice(0, 8);
    }, [searchQuery]);

    // Reset highlighted result when the list changes.
    React.useEffect(() => { setActiveResultIdx(0); }, [searchQuery, showSearch]);

    // Sidebar badges — only "approvals" wired today; structure is extensible.
    const sidebarBadges = React.useMemo(() => {
        const badges = {};
        if (pendingApprovals > 0) badges.dashboard = pendingApprovals;
        return badges;
    }, [pendingApprovals]);

    // ───── Keyboard shortcuts: Ctrl/Cmd+K opens search, Ctrl/Cmd+\ toggles sidebar
    React.useEffect(() => {
        const onKey = (e) => {
            const mod = e.metaKey || e.ctrlKey;
            if (mod && e.key.toLowerCase() === 'k') {
                e.preventDefault();
                setShowSearch(true);
                setTimeout(() => searchInputRef.current?.focus(), 30);
            }
            if (mod && e.key === '\\') {
                e.preventDefault();
                toggleCollapse();
            }
            if (e.key === 'Escape') {
                setShowSearch(false);
                setShowUserMenu(false);
                setIsMobileSidebarOpen(false);
            }
        };
        window.addEventListener('keydown', onKey);
        return () => window.removeEventListener('keydown', onKey);
    }, []);

    // Close user menu on outside click
    React.useEffect(() => {
        if (!showUserMenu) return;
        const onClick = (e) => {
            if (userMenuRef.current && !userMenuRef.current.contains(e.target)) {
                setShowUserMenu(false);
            }
        };
        window.addEventListener('mousedown', onClick);
        return () => window.removeEventListener('mousedown', onClick);
    }, [showUserMenu]);

    const adminName = user?.name || user?.email?.split('@')[0] || 'Admin';
    const adminInitials = adminName
        .split(/[\s@.]+/)
        .filter(Boolean)
        .slice(0, 2)
        .map((s) => s[0]?.toUpperCase())
        .join('');

    const handleSearchKey = (e) => {
        if (e.key === 'ArrowDown') {
            e.preventDefault();
            setActiveResultIdx((i) => Math.min(i + 1, searchResults.length - 1));
        } else if (e.key === 'ArrowUp') {
            e.preventDefault();
            setActiveResultIdx((i) => Math.max(i - 1, 0));
        } else if (e.key === 'Enter') {
            e.preventDefault();
            const target = searchResults[activeResultIdx];
            if (target) handleNavigation(target.path);
        }
    };

    return (
        <div data-name="admin-layout" className="min-h-screen bg-slate-100/70">
            {/* Skip link for keyboard users */}
            <a
                href="#admin-main"
                className="sr-only focus:not-sr-only focus:fixed focus:top-3 focus:left-3 focus:z-[60] focus:bg-white focus:text-[#2CABE3] focus:px-3 focus:py-1.5 focus:rounded-lg focus:shadow focus:ring-2 focus:ring-[#2CABE3]/40"
            >
                Skip to main content
            </a>

            {/* ───── Mobile sidebar overlay ───── */}
            {isMobileSidebarOpen && (
                <div
                    className="fixed inset-0 z-40 bg-slate-900/60 backdrop-blur-sm transition-opacity lg:hidden"
                    onClick={() => setIsMobileSidebarOpen(false)}
                    aria-hidden="true"
                />
            )}
            <div
                className={`fixed inset-y-0 left-0 z-50 w-72 transition-transform duration-300 lg:hidden shadow-2xl ${
                    isMobileSidebarOpen ? 'translate-x-0' : '-translate-x-full'
                }`}
            >
                <AdminSidebar active={active} onNavigate={handleNavigation} badges={sidebarBadges} />
            </div>

            {/* ───── Desktop persistent sidebar ───── */}
            <aside
                className={`hidden lg:block fixed inset-y-0 left-0 z-30 transition-[width] duration-300 shadow-xl
                    ${isCollapsed ? 'w-16' : 'w-64'}`}
            >
                <AdminSidebar
                    active={active}
                    onNavigate={handleNavigation}
                    collapsed={isCollapsed}
                    onToggleCollapse={toggleCollapse}
                    badges={sidebarBadges}
                />
            </aside>

            {/* ───── Main column (offset by sidebar width on desktop) ───── */}
            <div
                className={`flex flex-col min-h-screen transition-[padding] duration-300
                    ${isCollapsed ? 'lg:pl-16' : 'lg:pl-64'}`}
            >
                {/* ───── Top bar ───── */}
                <header className="sticky top-0 z-20 bg-white/85 backdrop-blur-md border-b border-slate-200/70 shadow-sm">
                    <div className="px-4 sm:px-6 lg:px-8">
                        <div className="flex items-center justify-between h-16 gap-3">
                            {/* Left: mobile menu + desktop collapse + breadcrumb */}
                            <div className="flex items-center min-w-0 gap-2">
                                <button
                                    type="button"
                                    className="lg:hidden inline-flex items-center justify-center h-9 w-9 rounded-lg text-slate-600 hover:text-slate-900 hover:bg-slate-100 transition"
                                    onClick={() => setIsMobileSidebarOpen(true)}
                                    aria-label="Open navigation"
                                >
                                    <i className="fas fa-bars text-lg" aria-hidden="true" />
                                </button>

                                {isCollapsed && (
                                    <button
                                        type="button"
                                        onClick={toggleCollapse}
                                        className="hidden lg:inline-flex items-center justify-center h-9 w-9 rounded-lg text-slate-600 hover:text-slate-900 hover:bg-slate-100 transition"
                                        aria-label="Expand sidebar"
                                        title="Expand sidebar (⌘\\)"
                                    >
                                        <i className="fas fa-angles-right text-sm" aria-hidden="true" />
                                    </button>
                                )}

                                {/* Breadcrumb */}
                                <nav aria-label="Breadcrumb" className="flex items-center gap-1.5 min-w-0">
                                    <button
                                        onClick={() => handleNavigation('/admin')}
                                        className="text-[13px] text-slate-500 hover:text-[#2CABE3] font-medium transition truncate"
                                    >
                                        Admin
                                    </button>
                                    {activeItem && active !== 'dashboard' && (
                                        <>
                                            <i className="fas fa-chevron-right text-[9px] text-slate-300" aria-hidden="true" />
                                            <span className="text-[14px] font-semibold text-slate-900 truncate" aria-current="page">
                                                {activeItem.label}
                                            </span>
                                        </>
                                    )}
                                    {active === 'dashboard' && (
                                        <>
                                            <i className="fas fa-chevron-right text-[9px] text-slate-300" aria-hidden="true" />
                                            <span className="text-[14px] font-semibold text-slate-900 truncate" aria-current="page">
                                                Dashboard
                                            </span>
                                        </>
                                    )}
                                </nav>
                            </div>

                            {/* Right: search trigger, notifications, user menu */}
                            <div className="flex items-center gap-1.5">
                                {/* Search trigger */}
                                <button
                                    type="button"
                                    onClick={() => {
                                        setShowSearch(true);
                                        setTimeout(() => searchInputRef.current?.focus(), 30);
                                    }}
                                    className="hidden sm:inline-flex items-center gap-2 pl-3 pr-2 h-9 rounded-lg border border-slate-200 bg-slate-50 text-slate-500 hover:text-slate-900 hover:bg-white hover:border-slate-300 text-[12px] transition"
                                    aria-label="Open admin search"
                                >
                                    <i className="fas fa-magnifying-glass text-[12px]" aria-hidden="true" />
                                    <span className="hidden md:inline">Jump to…</span>
                                    <kbd className="hidden md:inline ml-2 px-1.5 py-0.5 rounded bg-white border border-slate-200 text-[10px] font-sans text-slate-500">⌘K</kbd>
                                </button>
                                <button
                                    type="button"
                                    onClick={() => {
                                        setShowSearch(true);
                                        setTimeout(() => searchInputRef.current?.focus(), 30);
                                    }}
                                    className="sm:hidden inline-flex items-center justify-center h-9 w-9 rounded-lg text-slate-600 hover:text-slate-900 hover:bg-slate-100 transition"
                                    aria-label="Open admin search"
                                >
                                    <i className="fas fa-magnifying-glass" aria-hidden="true" />
                                </button>

                                {/* Notifications with badge */}
                                <button
                                    type="button"
                                    className="relative inline-flex items-center justify-center h-9 w-9 rounded-lg text-slate-600 hover:text-slate-900 hover:bg-slate-100 transition"
                                    aria-label={pendingApprovals > 0 ? `${pendingApprovals} pending approvals` : 'Notifications'}
                                    title={pendingApprovals > 0 ? `${pendingApprovals} pending approvals` : 'No new notifications'}
                                    onClick={() => active !== 'dashboard' && handleNavigation('/admin')}
                                >
                                    <i className="fas fa-bell" aria-hidden="true" />
                                    {pendingApprovals > 0 && (
                                        <>
                                            <span className="absolute top-1.5 right-1.5 h-2 w-2 rounded-full bg-rose-500 ring-2 ring-white animate-pulse" aria-hidden="true" />
                                            <span className="absolute -top-0.5 -right-0.5 min-w-[18px] h-[18px] px-1 rounded-full bg-rose-500 text-white text-[10px] font-semibold flex items-center justify-center">
                                                {pendingApprovals > 99 ? '99+' : pendingApprovals}
                                            </span>
                                        </>
                                    )}
                                </button>

                                <div className="hidden sm:block h-6 w-px bg-slate-200 mx-1" aria-hidden="true" />

                                {/* User menu — pt-2 bridges the hover gap so the menu
                                    doesn't disappear when moving the cursor down. */}
                                <div className="relative" ref={userMenuRef}>
                                    <button
                                        type="button"
                                        onClick={() => setShowUserMenu((v) => !v)}
                                        className="flex items-center gap-2 pl-1 pr-2 py-1 h-9 rounded-lg hover:bg-slate-100 transition"
                                        aria-haspopup="menu"
                                        aria-expanded={showUserMenu}
                                        aria-label="Account menu"
                                    >
                                        <div className="h-7 w-7 rounded-full bg-gradient-to-br from-[#2CABE3] to-emerald-500 text-white text-[11px] font-semibold flex items-center justify-center ring-1 ring-slate-200">
                                            {adminInitials || <i className="fas fa-user text-[10px]" aria-hidden="true" />}
                                        </div>
                                        <span className="hidden lg:inline text-[13px] font-medium text-slate-700 max-w-[120px] truncate">{adminName}</span>
                                        <i className="fas fa-chevron-down text-[9px] text-slate-400 hidden lg:inline" aria-hidden="true" />
                                    </button>

                                    {showUserMenu && (
                                        <div className="absolute right-0 top-full pt-2 z-50">
                                        <div
                                            role="menu"
                                            className="w-64 rounded-xl bg-white shadow-xl border border-slate-200 py-2 animate-[admin-fade-in_120ms_ease-out]"
                                        >
                                            <div className="px-4 py-2 border-b border-slate-100">
                                                <p className="text-[13px] font-semibold text-slate-900 truncate">{adminName}</p>
                                                <p className="text-[11px] text-slate-500 truncate">{user?.email || 'Administrator'}</p>
                                            </div>
                                            <button
                                                role="menuitem"
                                                onClick={() => handleNavigation('/admin/settings')}
                                                className="w-full text-left px-4 py-2 text-[13px] text-slate-700 hover:bg-slate-50 flex items-center gap-2.5"
                                            >
                                                <i className="fas fa-gear text-slate-400 w-4" aria-hidden="true" />
                                                Admin settings
                                            </button>
                                            <button
                                                role="menuitem"
                                                onClick={() => handleNavigation('/profile')}
                                                className="w-full text-left px-4 py-2 text-[13px] text-slate-700 hover:bg-slate-50 flex items-center gap-2.5"
                                            >
                                                <i className="fas fa-user text-slate-400 w-4" aria-hidden="true" />
                                                My profile
                                            </button>
                                            <button
                                                role="menuitem"
                                                onClick={() => handleNavigation('/')}
                                                className="w-full text-left px-4 py-2 text-[13px] text-slate-700 hover:bg-slate-50 flex items-center gap-2.5"
                                            >
                                                <i className="fas fa-house text-slate-400 w-4" aria-hidden="true" />
                                                Back to site
                                            </button>
                                            <div className="my-1 border-t border-slate-100" />
                                            <button
                                                role="menuitem"
                                                onClick={async () => {
                                                    try { await signOut?.(); } catch (_) { /* noop */ }
                                                    handleNavigation('/');
                                                }}
                                                className="w-full text-left px-4 py-2 text-[13px] text-rose-600 hover:bg-rose-50 flex items-center gap-2.5"
                                            >
                                                <i className="fas fa-right-from-bracket text-rose-500 w-4" aria-hidden="true" />
                                                Sign out
                                            </button>
                                        </div>
                                        </div>
                                    )}
                                </div>
                            </div>
                        </div>
                    </div>
                </header>

                {/* ───── Page content ───── */}
                <main id="admin-main" className="flex-1 px-2 sm:px-4 lg:px-6 py-2">
                    {children}
                </main>
            </div>

            {/* ───── Command-palette search overlay ───── */}
            {showSearch && (
                <div
                    className="fixed inset-0 z-[55] bg-slate-900/40 backdrop-blur-sm flex items-start justify-center p-4 pt-[10vh]"
                    role="dialog"
                    aria-modal="true"
                    aria-label="Quick navigation"
                    onClick={(e) => { if (e.target === e.currentTarget) setShowSearch(false); }}
                >
                    <div className="w-full max-w-xl bg-white rounded-2xl shadow-2xl ring-1 ring-slate-200 overflow-hidden animate-[admin-fade-in_140ms_ease-out]">
                        <div className="relative">
                            <i className="fas fa-magnifying-glass absolute left-4 top-1/2 -translate-y-1/2 text-slate-400" aria-hidden="true" />
                            <input
                                ref={searchInputRef}
                                type="search"
                                value={searchQuery}
                                onChange={(e) => setSearchQuery(e.target.value)}
                                onKeyDown={handleSearchKey}
                                placeholder="Jump to a page or run an action…"
                                className="w-full pl-11 pr-4 py-4 text-[15px] text-slate-900 placeholder-slate-400 bg-transparent border-0 border-b border-slate-100 focus:ring-0 focus:outline-none"
                                aria-label="Search admin pages"
                                aria-autocomplete="list"
                                aria-controls="admin-search-results"
                            />
                            <kbd className="absolute right-4 top-1/2 -translate-y-1/2 text-[10px] text-slate-400 border border-slate-200 rounded px-1.5 py-0.5">esc</kbd>
                        </div>

                        <ul id="admin-search-results" role="listbox" className="max-h-80 overflow-y-auto py-1">
                            {searchResults.length === 0 ? (
                                <li className="px-4 py-8 text-center text-[13px] text-slate-500">
                                    <i className="fas fa-inbox text-2xl text-slate-300 mb-2 block" aria-hidden="true" />
                                    No pages match &ldquo;{searchQuery}&rdquo;
                                </li>
                            ) : (
                                searchResults.map((item, idx) => {
                                    const isActive = idx === activeResultIdx;
                                    return (
                                        <li key={item.id} role="option" aria-selected={isActive}>
                                            <button
                                                type="button"
                                                onMouseEnter={() => setActiveResultIdx(idx)}
                                                onClick={() => handleNavigation(item.path)}
                                                className={`w-full flex items-center gap-3 px-4 py-2.5 text-left text-[13px] transition-colors
                                                    ${isActive ? 'bg-[#2CABE3]/10 text-slate-900' : 'text-slate-700 hover:bg-slate-50'}`}
                                            >
                                                <span className={`inline-flex h-7 w-7 items-center justify-center rounded-lg
                                                    ${isActive ? 'bg-[#2CABE3]/15 text-[#2CABE3]' : 'bg-slate-100 text-slate-500'}`}
                                                >
                                                    <i className={`fas ${item.icon} text-[12px]`} aria-hidden="true" />
                                                </span>
                                                <span className="font-medium flex-1 truncate">{item.label}</span>
                                                <span className="text-[10px] text-slate-400 truncate hidden sm:inline">{item.path}</span>
                                                {isActive && (
                                                    <i className="fas fa-arrow-turn-down-left text-[10px] text-[#2CABE3] rotate-90" aria-hidden="true" />
                                                )}
                                            </button>
                                        </li>
                                    );
                                })
                            )}
                        </ul>

                        <div className="px-4 py-2.5 border-t border-slate-100 flex items-center justify-between text-[10px] text-slate-400 bg-slate-50">
                            <div className="flex items-center gap-3">
                                <span className="flex items-center gap-1">
                                    <kbd className="border border-slate-200 bg-white rounded px-1">↑</kbd>
                                    <kbd className="border border-slate-200 bg-white rounded px-1">↓</kbd>
                                    to navigate
                                </span>
                                <span className="flex items-center gap-1">
                                    <kbd className="border border-slate-200 bg-white rounded px-1">⏎</kbd>
                                    to open
                                </span>
                            </div>
                            <span>{searchResults.length} results</span>
                        </div>
                    </div>
                </div>
            )}

            {/* Tiny global keyframe + scrollbar polish — colocated so AdminLayout
                is fully self-contained without bleeding into main.css. */}
            <style>{`
                @keyframes admin-fade-in {
                    from { opacity: 0; transform: translateY(-4px) scale(0.98); }
                    to { opacity: 1; transform: translateY(0) scale(1); }
                }
                .admin-sidebar-scroll::-webkit-scrollbar { width: 6px; }
                .admin-sidebar-scroll::-webkit-scrollbar-track { background: transparent; }
                .admin-sidebar-scroll::-webkit-scrollbar-thumb { background: rgba(255,255,255,0.06); border-radius: 9999px; }
                .admin-sidebar-scroll::-webkit-scrollbar-thumb:hover { background: rgba(255,255,255,0.12); }
                @media (prefers-reduced-motion: reduce) {
                    .animate-pulse { animation: none !important; }
                }
            `}</style>

            <AIHealthBanner />
        </div>
    );
}

AdminLayout.propTypes = {
    children: PropTypes.node.isRequired,
    active: PropTypes.string.isRequired,
    pendingApprovals: PropTypes.number,
};

export default AdminLayout;
