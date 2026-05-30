import React, { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import dataService from '../../utils/dataService';
import supabase from '../../utils/supabaseClient';
import { useAuthContext } from '../../utils/AuthContext';
import { debugAuthState } from '../../utils/authDebug';
import AdminLayout from '../../pages/admin/AdminLayout';
import RoleInsightsPanel from '../assistant/RoleInsightsPanel';
import AIQueryPanel from '../assistant/AIQueryPanel';

// ───────────────────────── Static config ─────────────────────────────────

/**
 * Section cards on the dashboard. Mirrors AdminSidebar groups so admins see the
 * same mental model in two surfaces. Color comes from a small token map so we
 * don't accumulate one-off Tailwind soup.
 */
const SECTION_TOKENS = {
    blue:    { chip: 'bg-blue-100 text-blue-700',       ring: 'group-hover:ring-blue-200' },
    amber:   { chip: 'bg-amber-100 text-amber-700',     ring: 'group-hover:ring-amber-200' },
    indigo:  { chip: 'bg-indigo-100 text-indigo-700',   ring: 'group-hover:ring-indigo-200' },
    pink:    { chip: 'bg-pink-100 text-pink-700',       ring: 'group-hover:ring-pink-200' },
    purple:  { chip: 'bg-purple-100 text-purple-700',   ring: 'group-hover:ring-purple-200' },
    emerald: { chip: 'bg-emerald-100 text-emerald-700', ring: 'group-hover:ring-emerald-200' },
    orange:  { chip: 'bg-orange-100 text-orange-700',   ring: 'group-hover:ring-orange-200' },
    teal:    { chip: 'bg-teal-100 text-teal-700',       ring: 'group-hover:ring-teal-200' },
    cyan:    { chip: 'bg-cyan-100 text-cyan-700',       ring: 'group-hover:ring-cyan-200' },
    lime:    { chip: 'bg-lime-100 text-lime-700',       ring: 'group-hover:ring-lime-200' },
    green:   { chip: 'bg-green-100 text-green-700',     ring: 'group-hover:ring-green-200' },
    rose:    { chip: 'bg-rose-100 text-rose-700',       ring: 'group-hover:ring-rose-200' },
    sky:     { chip: 'bg-sky-100 text-sky-700',         ring: 'group-hover:ring-sky-200' },
    slate:   { chip: 'bg-slate-100 text-slate-700',     ring: 'group-hover:ring-slate-200' },
};

const SECTION_GROUPS = [
    {
        label: 'Community',
        items: [
            { label: 'User Management',  description: 'Accounts, roles, and bans.',           icon: 'fa-users',           path: '/admin/users',           color: 'blue' },
            { label: 'Verifications',    description: 'Approve or reject ID checks.',         icon: 'fa-clipboard-check', path: '/admin/verifications',   color: 'emerald' },
            { label: 'Approval Codes',   description: 'Generate and revoke admin codes.',     icon: 'fa-key',             path: '/admin/approval-codes',  color: 'amber' },
            { label: 'Messages',         description: 'Reply to user conversations.',         icon: 'fa-comments',        path: '/admin/messages',        color: 'indigo' },
            { label: 'User Feedback',    description: 'Review submitted feedback.',           icon: 'fa-comment-dots',    path: '/admin/feedback',        color: 'purple' },
            { label: 'Broadcasts',       description: 'Send announcements platform-wide.',    icon: 'fa-bullhorn',        path: '/admin/broadcasts',      color: 'pink' },
        ],
    },
    {
        label: 'Operations',
        items: [
            { label: 'Food Distribution',     description: 'Plan and manage events.',                 icon: 'fa-box-open',          path: '/admin/distribution',  color: 'orange' },
            { label: 'Distribution Attendees', description: 'Who signed up where.',                    icon: 'fa-users-rectangle',   path: '/admin/attendees',     color: 'teal' },
            { label: 'Share Food',            description: 'Post listings on behalf of the org.',     icon: 'fa-utensils',          path: '/admin/share-food',    color: 'lime' },
            { label: 'Communities',           description: 'Manage community groups.',                icon: 'fa-city',              path: '/admin/communities',   color: 'cyan' },
        ],
    },
    {
        label: 'Insights & Content',
        items: [
            { label: 'Reports & Analytics', description: 'Platform-wide metrics and charts.', icon: 'fa-chart-line', path: '/admin/reports',         color: 'sky' },
            { label: 'Impact Data Entry',   description: 'Log impact metrics manually.',      icon: 'fa-table',      path: '/admin/impact',          color: 'green' },
            { label: 'Impact Content',      description: 'Edit impact stories and pages.',    icon: 'fa-heart',      path: '/admin/impact-content',  color: 'rose' },
        ],
    },
    {
        label: 'System',
        items: [
            { label: 'Settings', description: 'Platform configuration.', icon: 'fa-gear', path: '/admin/settings', color: 'slate' },
        ],
    },
];

const QUICK_ACTIONS = [
    { label: 'Send broadcast',   icon: 'fa-bullhorn',         path: '/admin/broadcasts',    color: 'from-pink-500 to-rose-500' },
    { label: 'Review users',     icon: 'fa-user-check',       path: '/admin/users',         color: 'from-blue-500 to-cyan-500' },
    { label: 'New distribution', icon: 'fa-box-open',         path: '/admin/distribution',  color: 'from-orange-500 to-amber-500' },
    { label: 'Open reports',     icon: 'fa-chart-line',       path: '/admin/reports',       color: 'from-emerald-500 to-teal-500' },
];

// ───────────────────────── Helpers ───────────────────────────────────────

function greetingFor(date = new Date()) {
    const h = date.getHours();
    if (h < 5) return 'Good evening';
    if (h < 12) return 'Good morning';
    if (h < 18) return 'Good afternoon';
    return 'Good evening';
}

function formatLongDate(date = new Date()) {
    try {
        return date.toLocaleDateString(undefined, {
            weekday: 'long', month: 'long', day: 'numeric',
        });
    } catch (_) {
        return date.toDateString();
    }
}

function relativeTime(iso) {
    if (!iso) return '';
    const then = new Date(iso).getTime();
    if (Number.isNaN(then)) return '';
    const diff = Date.now() - then;
    const s = Math.round(diff / 1000);
    if (s < 60) return 'just now';
    const m = Math.round(s / 60);
    if (m < 60) return `${m}m ago`;
    const h = Math.round(m / 60);
    if (h < 24) return `${h}h ago`;
    const d = Math.round(h / 24);
    if (d < 7) return `${d}d ago`;
    return new Date(iso).toLocaleDateString();
}

// ───────────────────────── Sub-components ────────────────────────────────

function KpiTile({ icon, accent, label, value, hint, loading, trend, onClick }) {
    const Wrap = onClick ? 'button' : 'div';
    return (
        <Wrap
            onClick={onClick}
            className={`group relative bg-white rounded-2xl border border-slate-200/80 hover:border-slate-300 shadow-sm hover:shadow-md transition-all p-5 text-left overflow-hidden
                ${onClick ? 'cursor-pointer focus:outline-none focus:ring-2 focus:ring-[#2CABE3]/40' : ''}`}
        >
            <div className={`absolute -top-10 -right-10 w-28 h-28 rounded-full blur-2xl opacity-30 ${accent.bg}`} aria-hidden="true" />
            <div className="flex items-start justify-between mb-3">
                <div className={`h-11 w-11 rounded-xl ${accent.bg} ${accent.fg} flex items-center justify-center ring-1 ring-inset ring-white/40`}>
                    <i className={`fas ${icon}`} aria-hidden="true" />
                </div>
                {trend != null && (
                    <span className={`inline-flex items-center gap-1 text-[11px] font-semibold px-2 py-0.5 rounded-full
                        ${trend >= 0 ? 'bg-emerald-50 text-emerald-700' : 'bg-rose-50 text-rose-700'}`}
                    >
                        <i className={`fas ${trend >= 0 ? 'fa-arrow-trend-up' : 'fa-arrow-trend-down'} text-[9px]`} aria-hidden="true" />
                        {Math.abs(trend)}%
                    </span>
                )}
            </div>
            <p className="text-[11px] font-medium uppercase tracking-wide text-slate-500">{label}</p>
            <p className="mt-1 text-2xl sm:text-[28px] font-bold text-slate-900 tabular-nums leading-none">
                {loading ? (
                    <span className="inline-block h-7 w-16 bg-slate-100 rounded animate-pulse align-middle" />
                ) : (
                    (value ?? 0).toLocaleString()
                )}
            </p>
            {hint && <p className="text-[11px] text-slate-500 mt-1.5">{hint}</p>}
        </Wrap>
    );
}

function SectionCard({ section, onClick }) {
    const tokens = SECTION_TOKENS[section.color] || SECTION_TOKENS.slate;
    return (
        <button
            onClick={onClick}
            className={`group text-left bg-white hover:bg-slate-50/80 rounded-xl p-4 border border-slate-200/80 hover:border-slate-300 transition-all hover:-translate-y-0.5 hover:shadow-md focus:outline-none focus:ring-2 focus:ring-[#2CABE3]/40 ring-0 ${tokens.ring}`}
        >
            <div className="flex items-start gap-3">
                <div className={`h-10 w-10 rounded-lg ${tokens.chip} flex items-center justify-center flex-shrink-0`}>
                    <i className={`fas ${section.icon}`} aria-hidden="true" />
                </div>
                <div className="min-w-0 flex-1">
                    <h3 className="font-semibold text-[14px] text-slate-900 group-hover:text-[#2CABE3] transition-colors leading-snug">
                        {section.label}
                    </h3>
                    <p className="text-[12px] text-slate-500 mt-0.5 line-clamp-2">{section.description}</p>
                </div>
                <i className="fas fa-arrow-right text-[10px] text-slate-300 group-hover:text-[#2CABE3] group-hover:translate-x-0.5 transition-all mt-2" aria-hidden="true" />
            </div>
        </button>
    );
}

function ActivityRow({ icon, accent, title, subtitle, time, onClick }) {
    return (
        <button
            onClick={onClick}
            className="w-full flex items-start gap-3 px-3 py-2.5 rounded-lg hover:bg-slate-50 text-left transition-colors focus:outline-none focus:ring-2 focus:ring-[#2CABE3]/30"
        >
            <div className={`h-8 w-8 rounded-lg ${accent} flex items-center justify-center flex-shrink-0 text-[12px]`}>
                <i className={`fas ${icon}`} aria-hidden="true" />
            </div>
            <div className="min-w-0 flex-1">
                <p className="text-[13px] font-medium text-slate-900 truncate">{title}</p>
                {subtitle && <p className="text-[11px] text-slate-500 truncate">{subtitle}</p>}
            </div>
            {time && <span className="text-[10px] text-slate-400 whitespace-nowrap pt-0.5">{time}</span>}
        </button>
    );
}

// ───────────────────────── Page ──────────────────────────────────────────

function AdminDashboard() {
    const navigate = useNavigate();
    const { user } = useAuthContext();

    const [foods, setFoods] = useState([]);
    const [loadingFoods, setLoadingFoods] = useState(false);
    const [actionStatus, setActionStatus] = useState({});

    const [stats, setStats] = useState(null);
    const [loadingStats, setLoadingStats] = useState(true);
    const [recentListings, setRecentListings] = useState([]);
    const [recentUsers, setRecentUsers] = useState([]);
    const [loadingActivity, setLoadingActivity] = useState(true);

    const [showInsights, setShowInsights] = useState(false);

    // Debug auth state on component mount (preserved from previous implementation)
    useEffect(() => {
        debugAuthState().then((state) => {
            console.log('Auth state in AdminDashboard:', state);
        });
    }, []);

    // Pending listings + real-time subscription (preserved behavior)
    useEffect(() => {
        fetchPendingFoods();
        const subscription = supabase
            .channel('admin-food-listings')
            .on(
                'postgres_changes',
                { event: '*', schema: 'public', table: 'food_listings' },
                (payload) => {
                    console.log('Food listing changed:', payload);
                    fetchPendingFoods();
                }
            )
            .subscribe();

        return () => { supabase.removeChannel(subscription); };
    }, []);

    // KPI stats + recent activity — both best-effort, dashboard still renders if they fail.
    useEffect(() => {
        let cancelled = false;
        (async () => {
            try {
                const s = await dataService.getAdminStats();
                if (!cancelled) setStats(s);
            } catch (err) {
                console.warn('getAdminStats failed:', err);
            } finally {
                if (!cancelled) setLoadingStats(false);
            }
        })();
        (async () => {
            try {
                const [listings, users] = await Promise.all([
                    dataService.getRecentListings(5).catch(() => []),
                    dataService.getRecentUsers(5).catch(() => []),
                ]);
                if (!cancelled) {
                    setRecentListings(listings || []);
                    setRecentUsers(users || []);
                }
            } catch (err) {
                console.warn('Recent activity failed:', err);
            } finally {
                if (!cancelled) setLoadingActivity(false);
            }
        })();
        return () => { cancelled = true; };
    }, []);

    async function fetchPendingFoods() {
        setLoadingFoods(true);
        try {
            const listings = await dataService.getFoodListings({ status: 'pending' });
            setFoods(listings || []);
        } catch (_) {
            setFoods([]);
        } finally {
            setLoadingFoods(false);
        }
    }

    async function handleAction(id, action) {
        setActionStatus((s) => ({ ...s, [id]: 'loading' }));
        try {
            await dataService.updateFoodListingStatus(id, action);
            setActionStatus((s) => ({ ...s, [id]: action }));
            fetchPendingFoods();
        } catch (_) {
            setActionStatus((s) => ({ ...s, [id]: 'error' }));
        }
    }

    const pendingCount = foods.length;
    const adminName = user?.name?.split(' ')?.[0] || 'there';

    return (
        <AdminLayout active="dashboard" pendingApprovals={pendingCount}>
            <div className="p-4 sm:p-6 lg:p-8 max-w-7xl mx-auto space-y-8">
                {/* ───────────── Welcome header ───────────── */}
                <header className="relative overflow-hidden rounded-2xl bg-gradient-to-br from-[#2CABE3] via-[#2196b8] to-emerald-500 text-white p-6 sm:p-8 shadow-lg">
                    <div className="absolute inset-0 opacity-25" aria-hidden="true" style={{
                        backgroundImage:
                            'radial-gradient(circle at 15% 20%, rgba(255,255,255,0.25) 0, transparent 40%), radial-gradient(circle at 80% 70%, rgba(255,255,255,0.18) 0, transparent 40%)',
                    }} />
                    <div className="relative flex flex-col lg:flex-row lg:items-end lg:justify-between gap-5">
                        <div>
                            <p className="text-[11px] font-semibold uppercase tracking-[0.2em] text-white/80 mb-2">
                                {formatLongDate()}
                            </p>
                            <h1 className="text-2xl sm:text-3xl lg:text-4xl font-bold tracking-tight">
                                {greetingFor()}, {adminName}.
                            </h1>
                            <p className="mt-2 text-white/85 text-[14px] sm:text-[15px] max-w-xl">
                                Here&apos;s what&apos;s happening on DoGoods today.{' '}
                                {pendingCount > 0
                                    ? <span className="font-semibold">{pendingCount} listing{pendingCount === 1 ? '' : 's'} need your review.</span>
                                    : 'No pending approvals — nice work staying ahead.'}
                            </p>
                        </div>
                        {/* Quick actions */}
                        <div className="flex flex-wrap gap-2">
                            {QUICK_ACTIONS.map((qa) => (
                                <button
                                    key={qa.path}
                                    onClick={() => navigate(qa.path)}
                                    className="inline-flex items-center gap-1.5 px-3 py-2 rounded-xl bg-white/15 hover:bg-white/25 active:scale-95 backdrop-blur-sm text-[12px] font-semibold text-white ring-1 ring-white/20 transition-all"
                                >
                                    <i className={`fas ${qa.icon} text-[11px]`} aria-hidden="true" />
                                    <span className="whitespace-nowrap">{qa.label}</span>
                                </button>
                            ))}
                        </div>
                    </div>
                </header>

                {/* ───────────── KPI tiles ───────────── */}
                <section aria-labelledby="kpi-heading">
                    <h2 id="kpi-heading" className="sr-only">Key metrics</h2>
                    <div className="grid grid-cols-2 lg:grid-cols-4 gap-3 sm:gap-4">
                        <KpiTile
                            icon="fa-users"
                            accent={{ bg: 'bg-blue-100', fg: 'text-blue-700' }}
                            label="Total users"
                            value={stats?.totalUsers}
                            loading={loadingStats}
                            onClick={() => navigate('/admin/users')}
                        />
                        <KpiTile
                            icon="fa-utensils"
                            accent={{ bg: 'bg-emerald-100', fg: 'text-emerald-700' }}
                            label="Food listings"
                            value={stats?.totalListings}
                            loading={loadingStats}
                            onClick={() => navigate('/admin/share-food')}
                        />
                        <KpiTile
                            icon="fa-hourglass-half"
                            accent={{ bg: 'bg-amber-100', fg: 'text-amber-700' }}
                            label="Pending approvals"
                            value={pendingCount}
                            hint={pendingCount > 0 ? 'Tap below to review now' : 'All clear'}
                            loading={loadingFoods}
                        />
                        <KpiTile
                            icon="fa-hand-holding-heart"
                            accent={{ bg: 'bg-rose-100', fg: 'text-rose-700' }}
                            label="Total donations"
                            value={stats?.totalDonations}
                            loading={loadingStats}
                            onClick={() => navigate('/admin/reports')}
                        />
                    </div>
                </section>

                {/* ───────────── Pending approvals (always visible when > 0) ───────────── */}
                {pendingCount > 0 && (
                    <section
                        aria-labelledby="pending-heading"
                        className="bg-white rounded-2xl border border-amber-200/80 shadow-sm overflow-hidden"
                    >
                        <header className="px-5 py-4 border-b border-amber-100 bg-gradient-to-r from-amber-50 to-white flex flex-wrap items-center justify-between gap-3">
                            <div className="flex items-center gap-3">
                                <div className="h-10 w-10 rounded-xl bg-amber-100 text-amber-700 flex items-center justify-center">
                                    <i className="fas fa-hourglass-half" aria-hidden="true" />
                                </div>
                                <div>
                                    <h2 id="pending-heading" className="text-base font-semibold text-slate-900">Pending approvals</h2>
                                    <p className="text-[12px] text-slate-500">
                                        <span className="font-semibold text-amber-700 tabular-nums">{pendingCount}</span> listing{pendingCount === 1 ? '' : 's'} waiting for review
                                    </p>
                                </div>
                            </div>
                            <button
                                onClick={fetchPendingFoods}
                                className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-[12px] font-medium text-slate-600 hover:text-slate-900 hover:bg-slate-100 transition"
                                aria-label="Refresh pending listings"
                            >
                                <i className={`fas fa-rotate text-[11px] ${loadingFoods ? 'animate-spin' : ''}`} aria-hidden="true" />
                                Refresh
                            </button>
                        </header>

                        <div className="p-5 grid gap-3 grid-cols-1 md:grid-cols-2 lg:grid-cols-3">
                            {foods.slice(0, 6).map((food) => {
                                const status = actionStatus[food.id];
                                const isLoadingAction = status === 'loading';
                                return (
                                    <article
                                        key={food.id}
                                        className="border border-slate-200 rounded-xl overflow-hidden flex flex-col bg-white hover:shadow-md transition-shadow"
                                    >
                                        {food.image_url ? (
                                            <img
                                                src={food.image_url}
                                                alt={food.title || food.name}
                                                loading="lazy"
                                                className="w-full h-32 object-cover"
                                            />
                                        ) : (
                                            <div className="w-full h-32 bg-gradient-to-br from-slate-100 to-slate-200 flex items-center justify-center text-slate-400">
                                                <i className="fas fa-image text-3xl" aria-hidden="true" />
                                            </div>
                                        )}
                                        <div className="p-3 flex flex-col flex-1">
                                            <h3 className="font-semibold text-[14px] text-slate-900 mb-1 line-clamp-1">{food.title || food.name}</h3>
                                            {food.description && (
                                                <p className="text-[12px] text-slate-500 mb-2 line-clamp-2">{food.description}</p>
                                            )}
                                            <div className="flex flex-wrap gap-1.5 mb-3 text-[10px]">
                                                {food.category && (
                                                    <span className="px-2 py-0.5 rounded-full bg-slate-100 text-slate-600 font-medium">{food.category}</span>
                                                )}
                                                {food.quantity && (
                                                    <span className="px-2 py-0.5 rounded-full bg-blue-50 text-blue-700 font-medium">
                                                        {food.quantity} {food.unit || ''}
                                                    </span>
                                                )}
                                                {food.expiry_date && (
                                                    <span className="px-2 py-0.5 rounded-full bg-amber-50 text-amber-700 font-medium">
                                                        Exp: {food.expiry_date}
                                                    </span>
                                                )}
                                            </div>
                                            <div className="mt-auto flex gap-2">
                                                <button
                                                    className="flex-1 inline-flex items-center justify-center gap-1.5 bg-emerald-500 hover:bg-emerald-600 text-white px-3 py-2 rounded-lg text-[12px] font-medium disabled:opacity-50 disabled:cursor-not-allowed transition"
                                                    onClick={() => handleAction(food.id, 'approved')}
                                                    disabled={food.status !== 'pending' || isLoadingAction}
                                                >
                                                    {isLoadingAction ? (
                                                        <i className="fas fa-spinner fa-spin text-[10px]" aria-hidden="true" />
                                                    ) : (
                                                        <i className="fas fa-check text-[10px]" aria-hidden="true" />
                                                    )}
                                                    Approve
                                                </button>
                                                <button
                                                    className="flex-1 inline-flex items-center justify-center gap-1.5 bg-white border border-rose-200 hover:bg-rose-50 text-rose-700 px-3 py-2 rounded-lg text-[12px] font-medium disabled:opacity-50 disabled:cursor-not-allowed transition"
                                                    onClick={() => handleAction(food.id, 'declined')}
                                                    disabled={food.status !== 'pending' || isLoadingAction}
                                                >
                                                    <i className="fas fa-xmark text-[10px]" aria-hidden="true" />
                                                    Decline
                                                </button>
                                            </div>
                                            {status === 'approved' && (
                                                <p className="text-emerald-600 text-[10px] mt-2 flex items-center gap-1">
                                                    <i className="fas fa-check-circle" aria-hidden="true" /> Approved
                                                </p>
                                            )}
                                            {status === 'declined' && (
                                                <p className="text-rose-600 text-[10px] mt-2 flex items-center gap-1">
                                                    <i className="fas fa-circle-xmark" aria-hidden="true" /> Declined
                                                </p>
                                            )}
                                            {status === 'error' && (
                                                <p className="text-rose-600 text-[10px] mt-2">Error — try again</p>
                                            )}
                                        </div>
                                    </article>
                                );
                            })}
                        </div>

                        {pendingCount > 6 && (
                            <div className="px-5 py-3 border-t border-slate-100 bg-slate-50/50 text-center">
                                <button
                                    onClick={() => navigate('/admin/share-food')}
                                    className="text-[13px] font-semibold text-[#2CABE3] hover:underline"
                                >
                                    View all {pendingCount} pending listings →
                                </button>
                            </div>
                        )}
                    </section>
                )}

                {/* ───────────── Main content + recent activity rail ───────────── */}
                <div className="grid gap-6 lg:grid-cols-3">
                    {/* LEFT — section navigation grouped */}
                    <div className="lg:col-span-2 space-y-7">
                        {SECTION_GROUPS.map((group) => (
                            <section key={group.label} aria-label={group.label}>
                                <div className="flex items-center gap-2 mb-3">
                                    <h2 className="text-[11px] font-semibold uppercase tracking-[0.16em] text-slate-500">
                                        {group.label}
                                    </h2>
                                    <span className="flex-1 h-px bg-slate-200" aria-hidden="true" />
                                </div>
                                <div className="grid gap-3 grid-cols-1 sm:grid-cols-2">
                                    {group.items.map((section) => (
                                        <SectionCard
                                            key={section.path}
                                            section={section}
                                            onClick={() => navigate(section.path)}
                                        />
                                    ))}
                                </div>
                            </section>
                        ))}

                        {/* AI insights collapsible */}
                        <section className="bg-white rounded-2xl border border-slate-200/80 shadow-sm overflow-hidden">
                            <button
                                onClick={() => setShowInsights((v) => !v)}
                                className="w-full flex items-center justify-between p-4 hover:bg-slate-50 transition"
                                aria-expanded={showInsights}
                                aria-controls="admin-ai-insights"
                            >
                                <div className="flex items-center gap-3">
                                    <div className="h-10 w-10 rounded-xl bg-violet-100 text-violet-600 flex items-center justify-center">
                                        <i className="fas fa-robot" aria-hidden="true" />
                                    </div>
                                    <div className="text-left">
                                        <p className="text-[14px] font-semibold text-slate-900">AI insights & queries</p>
                                        <p className="text-[11px] text-slate-500">Ask questions in natural language about your platform</p>
                                    </div>
                                </div>
                                <i className={`fas fa-chevron-down text-slate-400 transition-transform ${showInsights ? 'rotate-180' : ''}`} aria-hidden="true" />
                            </button>
                            {showInsights && (
                                <div id="admin-ai-insights" className="p-4 border-t border-slate-100 space-y-4 bg-slate-50/50">
                                    <RoleInsightsPanel roleHint="admin" />
                                    <AIQueryPanel />
                                </div>
                            )}
                        </section>
                    </div>

                    {/* RIGHT — recent activity rail */}
                    <aside className="space-y-5 lg:sticky lg:top-24 lg:self-start">
                        {/* Recent listings */}
                        <div className="bg-white rounded-2xl border border-slate-200/80 shadow-sm overflow-hidden">
                            <header className="flex items-center justify-between px-4 py-3 border-b border-slate-100">
                                <h3 className="text-[13px] font-semibold text-slate-900 flex items-center gap-2">
                                    <i className="fas fa-clock text-[#2CABE3] text-[12px]" aria-hidden="true" />
                                    Recent listings
                                </h3>
                                <button
                                    onClick={() => navigate('/admin/share-food')}
                                    className="text-[11px] font-medium text-[#2CABE3] hover:underline"
                                >
                                    View all
                                </button>
                            </header>
                            <div className="p-2">
                                {loadingActivity ? (
                                    Array.from({ length: 3 }).map((_, i) => (
                                        <div key={i} className="flex items-center gap-3 px-3 py-2.5">
                                            <div className="h-8 w-8 rounded-lg bg-slate-100 animate-pulse" />
                                            <div className="flex-1 space-y-1.5">
                                                <div className="h-3 w-3/4 bg-slate-100 rounded animate-pulse" />
                                                <div className="h-2.5 w-1/2 bg-slate-100 rounded animate-pulse" />
                                            </div>
                                        </div>
                                    ))
                                ) : recentListings.length === 0 ? (
                                    <p className="px-3 py-6 text-center text-[12px] text-slate-500">No recent listings.</p>
                                ) : (
                                    recentListings.map((l) => (
                                        <ActivityRow
                                            key={l.id}
                                            icon="fa-utensils"
                                            accent="bg-emerald-50 text-emerald-700"
                                            title={l.title || l.name || 'Untitled listing'}
                                            subtitle={l.users?.name ? `by ${l.users.name}` : (l.location || '')}
                                            time={relativeTime(l.created_at)}
                                            onClick={() => navigate('/admin/share-food')}
                                        />
                                    ))
                                )}
                            </div>
                        </div>

                        {/* Recent signups */}
                        <div className="bg-white rounded-2xl border border-slate-200/80 shadow-sm overflow-hidden">
                            <header className="flex items-center justify-between px-4 py-3 border-b border-slate-100">
                                <h3 className="text-[13px] font-semibold text-slate-900 flex items-center gap-2">
                                    <i className="fas fa-user-plus text-emerald-500 text-[12px]" aria-hidden="true" />
                                    New members
                                </h3>
                                <button
                                    onClick={() => navigate('/admin/users')}
                                    className="text-[11px] font-medium text-[#2CABE3] hover:underline"
                                >
                                    View all
                                </button>
                            </header>
                            <div className="p-2">
                                {loadingActivity ? (
                                    Array.from({ length: 3 }).map((_, i) => (
                                        <div key={i} className="flex items-center gap-3 px-3 py-2.5">
                                            <div className="h-8 w-8 rounded-full bg-slate-100 animate-pulse" />
                                            <div className="flex-1 space-y-1.5">
                                                <div className="h-3 w-1/2 bg-slate-100 rounded animate-pulse" />
                                                <div className="h-2.5 w-2/3 bg-slate-100 rounded animate-pulse" />
                                            </div>
                                        </div>
                                    ))
                                ) : recentUsers.length === 0 ? (
                                    <p className="px-3 py-6 text-center text-[12px] text-slate-500">No new members.</p>
                                ) : (
                                    recentUsers.map((u) => (
                                        <ActivityRow
                                            key={u.id}
                                            icon="fa-user"
                                            accent="bg-blue-50 text-blue-700"
                                            title={u.name || u.email || 'Unknown user'}
                                            subtitle={u.organization || u.email}
                                            time={relativeTime(u.created_at)}
                                            onClick={() => navigate('/admin/users')}
                                        />
                                    ))
                                )}
                            </div>
                        </div>
                    </aside>
                </div>
            </div>
        </AdminLayout>
    );
}

export default AdminDashboard;
