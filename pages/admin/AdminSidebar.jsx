import React from 'react';
import PropTypes from 'prop-types';
import { useAuthContext } from '../../utils/AuthContext';
import { reportError } from '../../utils/helpers';

/**
 * Menu structure for the admin sidebar.
 * Grouped into logical clusters so 16 items scan in seconds instead of a flat
 * wall of links. Exported so AdminLayout can derive breadcrumb labels and the
 * global admin command-search from the same source of truth.
 */
export const ADMIN_MENU_GROUPS = [
    {
        id: 'overview',
        label: 'Overview',
        items: [
            { id: 'dashboard', label: 'Dashboard', icon: 'fa-gauge-high', path: '/admin' },
        ],
    },
    {
        id: 'community',
        label: 'Community',
        items: [
            { id: 'users', label: 'User Management', icon: 'fa-users', path: '/admin/users' },
            { id: 'verifications', label: 'Verifications', icon: 'fa-clipboard-check', path: '/admin/verifications' },
            { id: 'approval-codes', label: 'Approval Codes', icon: 'fa-key', path: '/admin/approval-codes' },
            { id: 'messages', label: 'Messages', icon: 'fa-comments', path: '/admin/messages' },
            { id: 'feedback', label: 'User Feedback', icon: 'fa-comment-dots', path: '/admin/feedback' },
            { id: 'broadcasts', label: 'Broadcasts', icon: 'fa-bullhorn', path: '/admin/broadcasts' },
        ],
    },
    {
        id: 'operations',
        label: 'Operations',
        items: [
            { id: 'distribution', label: 'Food Distribution', icon: 'fa-box-open', path: '/admin/distribution' },
            { id: 'attendees', label: 'Distribution Attendees', icon: 'fa-users-rectangle', path: '/admin/attendees' },
            { id: 'share-food', label: 'Share Food', icon: 'fa-utensils', path: '/admin/share-food' },
            { id: 'communities', label: 'Communities', icon: 'fa-city', path: '/admin/communities' },
            { id: 'safety', label: 'Safety & Trust', icon: 'fa-shield-halved', path: '/admin/safety' },
        ],
    },
    {
        id: 'insights',
        label: 'Insights',
        items: [
            { id: 'reports', label: 'Reports & Analytics', icon: 'fa-chart-line', path: '/admin/reports' },
            { id: 'impact', label: 'Impact Data Entry', icon: 'fa-table', path: '/admin/impact' },
            { id: 'impact-content', label: 'Impact Content', icon: 'fa-heart', path: '/admin/impact-content' },
        ],
    },
    {
        id: 'system',
        label: 'System',
        items: [
            { id: 'settings', label: 'Settings', icon: 'fa-gear', path: '/admin/settings' },
        ],
    },
];

/** Flat list — handy for breadcrumbs, search, and any "find by id" lookup. */
export const ADMIN_MENU_FLAT = ADMIN_MENU_GROUPS.flatMap((g) => g.items);

function AdminSidebar({ active, onNavigate, collapsed = false, onToggleCollapse, badges = {} }) {
    try {
        const [query, setQuery] = React.useState('');
        const { user, signOut } = useAuthContext();
        const searchInputRef = React.useRef(null);

        // Local search across menu items — admins can fly straight to a page.
        const filteredGroups = React.useMemo(() => {
            const q = query.trim().toLowerCase();
            if (!q) return ADMIN_MENU_GROUPS;
            return ADMIN_MENU_GROUPS
                .map((g) => ({ ...g, items: g.items.filter((i) => i.label.toLowerCase().includes(q)) }))
                .filter((g) => g.items.length > 0);
        }, [query]);

        const handleKeyPress = (event, path) => {
            if (event.key === 'Enter' || event.key === ' ') {
                event.preventDefault();
                onNavigate(path);
            }
        };

        const handleSignOut = async () => {
            try {
                await signOut?.();
                onNavigate('/');
            } catch (err) {
                console.error('Sign-out failed:', err);
                reportError(err);
            }
        };

        const adminName = user?.name || user?.email?.split('@')[0] || 'Admin';
        const adminInitials = adminName
            .split(/[\s@.]+/)
            .filter(Boolean)
            .slice(0, 2)
            .map((s) => s[0]?.toUpperCase())
            .join('');

        return (
            <div
                data-name="admin-sidebar"
                className="h-full flex flex-col bg-gradient-to-b from-slate-900 via-slate-900 to-slate-950 text-slate-200"
                role="navigation"
                aria-label="Admin navigation"
            >
                {/* ───────────── Brand / collapse ───────────── */}
                <div className={`flex items-center border-b border-white/5 ${collapsed ? 'justify-center py-4 px-2' : 'justify-between p-4'}`}>
                    <button
                        onClick={() => onNavigate('/admin')}
                        className="flex items-center gap-2.5 text-white group"
                        aria-label="Go to admin dashboard"
                    >
                        <div className="relative h-9 w-9 rounded-xl bg-gradient-to-br from-[#2CABE3] to-emerald-500 flex items-center justify-center shadow-lg shadow-[#2CABE3]/20 ring-1 ring-white/10">
                            <i className="fas fa-seedling text-white" aria-hidden="true" />
                            <span className="absolute -top-0.5 -right-0.5 h-2.5 w-2.5 rounded-full bg-emerald-400 ring-2 ring-slate-900" />
                        </div>
                        {!collapsed && (
                            <div className="flex flex-col items-start leading-tight">
                                <span className="text-[15px] font-semibold tracking-tight">DoGoods</span>
                                <span className="text-[10px] font-medium uppercase tracking-[0.18em] text-[#2CABE3]">Admin Console</span>
                            </div>
                        )}
                    </button>

                    {/* Desktop collapse toggle */}
                    {!collapsed && onToggleCollapse && (
                        <button
                            type="button"
                            onClick={onToggleCollapse}
                            className="hidden lg:inline-flex h-8 w-8 items-center justify-center rounded-lg text-slate-400 hover:text-white hover:bg-white/5 transition"
                            aria-label="Collapse sidebar"
                            title="Collapse (⌘\\)"
                        >
                            <i className="fas fa-angles-left text-xs" aria-hidden="true" />
                        </button>
                    )}
                </div>

                {/* ───────────── Search (expanded only) ───────────── */}
                {!collapsed && (
                    <div className="px-3 pt-3 pb-1">
                        <div className="relative">
                            <i className="fas fa-magnifying-glass absolute left-3 top-1/2 -translate-y-1/2 text-slate-500 text-xs" aria-hidden="true" />
                            <input
                                ref={searchInputRef}
                                type="search"
                                value={query}
                                onChange={(e) => setQuery(e.target.value)}
                                placeholder="Search admin…"
                                className="w-full pl-8 pr-3 py-1.5 text-[13px] rounded-lg bg-white/5 text-slate-100 placeholder-slate-500 border border-white/10 focus:bg-white/10 focus:border-[#2CABE3]/50 focus:ring-2 focus:ring-[#2CABE3]/20 outline-none transition"
                                aria-label="Search admin pages"
                            />
                        </div>
                    </div>
                )}

                {/* ───────────── Nav groups ───────────── */}
                <nav
                    className={`flex-1 overflow-y-auto py-3 ${collapsed ? 'px-2' : 'px-2'} space-y-4 admin-sidebar-scroll`}
                    role="menu"
                >
                    {filteredGroups.length === 0 ? (
                        <p className="px-3 py-4 text-center text-[12px] text-slate-500">
                            No matches for &ldquo;{query}&rdquo;
                        </p>
                    ) : (
                        filteredGroups.map((group, gIdx) => (
                            <div key={group.id} className="space-y-0.5">
                                {!collapsed ? (
                                    <h3 className="px-3 pb-1 text-[10px] font-semibold uppercase tracking-[0.16em] text-slate-500">
                                        {group.label}
                                    </h3>
                                ) : (
                                    gIdx > 0 && <div className="my-2 mx-3 h-px bg-white/5" aria-hidden="true" />
                                )}

                                {group.items.map((item) => {
                                    const isActive = active === item.id;
                                    const badge = badges[item.id];
                                    return (
                                        <button
                                            key={item.id}
                                            onClick={() => onNavigate(item.path)}
                                            onKeyDown={(e) => handleKeyPress(e, item.path)}
                                            className={`relative w-full flex items-center rounded-lg text-[13px] font-medium transition-all
                                                ${collapsed ? 'h-10 justify-center' : 'px-3 py-2'}
                                                ${isActive
                                                    ? 'bg-[#2CABE3]/15 text-white shadow-inner ring-1 ring-[#2CABE3]/30'
                                                    : 'text-slate-300 hover:bg-white/5 hover:text-white'}
                                            `}
                                            role="menuitem"
                                            aria-current={isActive ? 'page' : undefined}
                                            aria-label={collapsed ? item.label : undefined}
                                            title={collapsed ? item.label : undefined}
                                        >
                                            {/* Active accent bar */}
                                            {isActive && (
                                                <span className="absolute left-0 top-1/2 -translate-y-1/2 h-5 w-0.5 rounded-r bg-gradient-to-b from-[#2CABE3] to-emerald-400" aria-hidden="true" />
                                            )}
                                            <i
                                                className={`fas ${item.icon} ${collapsed ? 'text-[15px]' : 'w-5 text-[14px]'} ${isActive ? 'text-[#2CABE3]' : ''}`}
                                                aria-hidden="true"
                                            />
                                            {!collapsed && (
                                                <>
                                                    <span className="ml-3 truncate">{item.label}</span>
                                                    {badge ? (
                                                        <span className="ml-auto inline-flex items-center justify-center min-w-[20px] h-5 px-1.5 rounded-full text-[10px] font-semibold bg-amber-400 text-amber-950">
                                                            {badge}
                                                        </span>
                                                    ) : null}
                                                </>
                                            )}
                                            {/* Collapsed-mode badge dot */}
                                            {collapsed && badge ? (
                                                <span className="absolute top-1 right-1 h-2 w-2 rounded-full bg-amber-400 ring-2 ring-slate-900" />
                                            ) : null}
                                        </button>
                                    );
                                })}
                            </div>
                        ))
                    )}
                </nav>

                {/* ───────────── Footer ───────────── */}
                <div className={`border-t border-white/5 ${collapsed ? 'p-2' : 'p-3'} space-y-1`}>
                    {!collapsed ? (
                        <div className="flex items-center gap-2.5 px-2 py-2 rounded-lg bg-white/5">
                            <div className="h-9 w-9 rounded-full bg-gradient-to-br from-[#2CABE3] to-emerald-500 flex items-center justify-center text-white text-xs font-semibold ring-1 ring-white/10">
                                {adminInitials || <i className="fas fa-user" aria-hidden="true" />}
                            </div>
                            <div className="min-w-0 flex-1">
                                <p className="text-[12px] font-semibold text-white truncate">{adminName}</p>
                                <p className="text-[10px] text-slate-400 truncate">
                                    {user?.email || 'Administrator'}
                                </p>
                            </div>
                        </div>
                    ) : (
                        <div className="flex justify-center py-1" title={adminName}>
                            <div className="h-8 w-8 rounded-full bg-gradient-to-br from-[#2CABE3] to-emerald-500 flex items-center justify-center text-white text-[10px] font-semibold ring-1 ring-white/10">
                                {adminInitials || <i className="fas fa-user" aria-hidden="true" />}
                            </div>
                        </div>
                    )}

                    <button
                        onClick={() => onNavigate('/')}
                        onKeyDown={(e) => handleKeyPress(e, '/')}
                        className={`w-full flex items-center text-[12px] font-medium text-slate-300 rounded-lg hover:bg-white/5 hover:text-white transition
                            ${collapsed ? 'h-9 justify-center' : 'px-3 py-2'}`}
                        aria-label="Return to main site"
                        title={collapsed ? 'Back to site' : undefined}
                    >
                        <i className={`fas fa-arrow-left ${collapsed ? '' : 'w-5'}`} aria-hidden="true" />
                        {!collapsed && <span className="ml-2">Back to site</span>}
                    </button>

                    <button
                        onClick={handleSignOut}
                        className={`w-full flex items-center text-[12px] font-medium text-slate-300 rounded-lg hover:bg-rose-500/10 hover:text-rose-300 transition
                            ${collapsed ? 'h-9 justify-center' : 'px-3 py-2'}`}
                        aria-label="Sign out"
                        title={collapsed ? 'Sign out' : undefined}
                    >
                        <i className={`fas fa-right-from-bracket ${collapsed ? '' : 'w-5'}`} aria-hidden="true" />
                        {!collapsed && <span className="ml-2">Sign out</span>}
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
    onNavigate: PropTypes.func.isRequired,
    collapsed: PropTypes.bool,
    onToggleCollapse: PropTypes.func,
    badges: PropTypes.object,
};

export default AdminSidebar;
