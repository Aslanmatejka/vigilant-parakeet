import React from 'react';
import PropTypes from 'prop-types';
import { useNavigate } from 'react-router-dom';
import aiChatService from '../../utils/services/aiChatService.js';
import { reportError } from '../../utils/helpers.js';
import { useAuthContext } from '../../utils/AuthContext.jsx';
import { AIThinkingPanel } from '../common/AIThinking.jsx';

const ROLE_LABELS = {
    admin: 'Admin coach',
    donor: 'Donor coach',
    recipient: 'Recipient guide',
    organizer: 'Organizer copilot',
};

const PRIORITY_BADGE = {
    high: 'bg-red-100 text-red-700',
    medium: 'bg-amber-100 text-amber-700',
    low: 'bg-emerald-100 text-emerald-700',
};

function formatTimestamp(value) {
    if (!value) return '';
    try {
        return new Date(value).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
    } catch (_) {
        return '';
    }
}

function RoleInsightsPanel({ roleHint = null, className = '' }) {
    const navigate = useNavigate();
    const { user, isAdmin } = useAuthContext();
    const [state, setState] = React.useState({
        loading: true,
        refreshing: false,
        error: null,
        degraded: false,
        role: roleHint || (isAdmin ? 'admin' : 'recipient'),
        headline: '',
        insights: [],
        profileCompletion: null,
        profileGaps: [],
        generatedAt: null,
    });

    const load = React.useCallback(async (isInitial = false) => {
        if (!user?.id) return;
        setState((prev) => ({
            ...prev,
            // Only show the full skeleton when we have nothing to display yet.
            loading: isInitial && prev.insights.length === 0,
            refreshing: !isInitial || prev.insights.length > 0,
            error: null,
        }));
        try {
            const data = await aiChatService.getInsights(user.id, {
                roleHint: roleHint || (isAdmin ? 'admin' : null),
            });
            setState((prev) => ({
                loading: false,
                refreshing: false,
                error: null,
                degraded: !!data.degraded,
                role: data.role,
                // If the self-healing fallback fired, prefer the last good
                // insights/headline we already had instead of going blank.
                headline: data.degraded && prev.insights.length > 0 ? prev.headline : data.headline,
                insights: data.degraded && prev.insights.length > 0 ? prev.insights : data.insights,
                profileCompletion: data.degraded && prev.insights.length > 0 ? prev.profileCompletion : data.profileCompletion,
                profileGaps: data.degraded && prev.insights.length > 0 ? prev.profileGaps : (data.profileGaps || []),
                generatedAt: data.degraded && prev.insights.length > 0 ? prev.generatedAt : data.generatedAt,
            }));
        } catch (error) {
            reportError(error);
            setState((prev) => ({
                ...prev,
                loading: false,
                refreshing: false,
                // Only surface the error UI when we have no cached insights to fall back to.
                error: prev.insights.length === 0 ? 'Unable to load AI insights right now.' : null,
                degraded: prev.insights.length > 0,
            }));
        }
    }, [user?.id, roleHint, isAdmin]);

    React.useEffect(() => {
        load(true);
    }, [load]);

    const handleAction = (action) => {
        if (!action?.href) return;
        if (/^https?:\/\//i.test(action.href)) {
            window.open(action.href, '_blank', 'noopener,noreferrer');
            return;
        }
        navigate(action.href);
    };

    const roleLabel = ROLE_LABELS[state.role] || 'AI assistant';

    return (
        <section
            className={`rounded-lg border border-gray-200 bg-white shadow-sm ${className}`}
            aria-label="AI dashboard insights"
        >
            <header className="flex items-center justify-between border-b border-gray-100 px-5 py-3">
                <div className="flex items-center gap-3">
                    <span className="inline-flex h-9 w-9 items-center justify-center rounded-full bg-[#2CABE3]/10 text-[#2CABE3]">
                        <i className="fas fa-sparkles" aria-hidden="true" />
                    </span>
                    <div>
                        <h2 className="text-sm font-semibold text-gray-900 flex items-center gap-1.5">
                            AI Insights · {roleLabel}
                            {state.degraded && (
                                <span
                                    title="AI link recovering — showing best-effort data"
                                    className="inline-flex items-center gap-1 rounded-full bg-amber-50 px-1.5 py-0.5 text-[10px] font-medium text-amber-700 border border-amber-200"
                                >
                                    <i className="fas fa-bolt text-[8px]" aria-hidden="true" />
                                    recovering
                                </span>
                            )}
                        </h2>
                        {state.generatedAt && (
                            <p className="text-xs text-gray-500">
                                Updated {formatTimestamp(state.generatedAt)}
                                {state.refreshing && (
                                    <span className="ml-2 inline-flex items-center gap-1 text-[#2CABE3]">
                                        <i className="fas fa-circle-notch fa-spin text-[10px]" aria-hidden="true" />
                                        refreshing
                                    </span>
                                )}
                            </p>
                        )}
                    </div>
                </div>
                <button
                    type="button"
                    onClick={() => load(false)}
                    disabled={state.loading || state.refreshing}
                    className="rounded-md border border-gray-200 px-3 py-1 text-xs font-medium text-gray-700 hover:bg-gray-50 disabled:opacity-50"
                >
                    {state.refreshing ? 'Refreshing...' : 'Refresh'}
                </button>
            </header>

            <div className="px-5 py-4">
                {state.role !== 'admin' && typeof state.profileCompletion === 'number' && !state.loading && (
                    <div className="mb-4 rounded-md border border-gray-100 bg-gray-50 p-3">
                        <div className="flex items-center justify-between text-xs text-gray-600">
                            <span className="font-medium">Profile completion</span>
                            <span>{state.profileCompletion}%</span>
                        </div>
                        <div className="mt-2 h-2 w-full overflow-hidden rounded-full bg-gray-200">
                            <div
                                className="h-full rounded-full bg-[#2CABE3] transition-all"
                                style={{ width: `${Math.max(0, Math.min(100, state.profileCompletion))}%` }}
                            />
                        </div>
                        {state.profileGaps.length > 0 && (
                            <p className="mt-2 text-[11px] text-gray-500">
                                {state.profileGaps.length} profile item{state.profileGaps.length === 1 ? '' : 's'} missing — see suggestions below.
                            </p>
                        )}
                    </div>
                )}

                {state.headline && !state.loading && (
                    <p className="mb-3 text-sm font-medium text-gray-800">{state.headline}</p>
                )}

                {state.loading ? (
                    <AIThinkingPanel
                        title="Generating insights"
                        stages={[
                            { icon: 'user-shield', label: 'Reading your profile' },
                            { icon: 'chart-line', label: 'Reviewing recent activity' },
                            { icon: 'brain', label: 'Spotting opportunities' },
                            { icon: 'wand-magic-sparkles', label: 'Drafting recommendations' },
                        ]}
                    />
                ) : state.error ? (
                    <div className="rounded-md border border-amber-200 bg-amber-50 p-4 text-center">
                        <i className="fas fa-exclamation-triangle text-amber-500 mb-2"></i>
                        <p className="text-sm text-amber-800 mb-3">{state.error}</p>
                        <button
                            type="button"
                            onClick={() => load(false)}
                            disabled={state.refreshing}
                            className="inline-flex items-center gap-1 rounded-md bg-amber-600 px-3 py-1.5 text-xs font-medium text-white hover:bg-amber-700 disabled:opacity-50"
                        >
                            <i className={`fas fa-${state.refreshing ? 'spinner fa-spin' : 'redo'} text-[10px]`}></i>
                            {state.refreshing ? 'Retrying…' : 'Try again'}
                        </button>
                    </div>
                ) : state.insights.length === 0 ? (
                    <p className="text-sm text-gray-500">
                        No personalized insights yet — check back after some activity.
                    </p>
                ) : (
                    <ul className="space-y-3">
                        {state.insights
                            .filter((insight) => state.role !== 'admin' || insight.source !== 'profile_gap')
                            .map((insight, idx) => {
                            const priorityClass = PRIORITY_BADGE[insight.priority] || PRIORITY_BADGE.low;
                            const iconClass = insight.icon ? `fas fa-${insight.icon}` : 'fas fa-lightbulb';
                            const isProfileGap = insight.source === 'profile_gap';
                            return (
                                <li
                                    key={insight.id || `insight-${idx}`}
                                    className={`flex items-start gap-3 rounded-md border p-3 hover:border-[#2CABE3]/40 ${isProfileGap ? 'border-[#2CABE3]/30 bg-[#2CABE3]/5' : 'border-gray-100'}`}
                                >
                                    <span className={`mt-0.5 inline-flex h-8 w-8 flex-shrink-0 items-center justify-center rounded-md ${isProfileGap ? 'bg-[#2CABE3]/15 text-[#2CABE3]' : 'bg-gray-50 text-gray-700'}`}>
                                        <i className={iconClass} aria-hidden="true" />
                                    </span>
                                    <div className="flex-1">
                                        <div className="flex items-start justify-between gap-2">
                                            <h3 className="text-sm font-semibold text-gray-900">
                                                {insight.title}
                                            </h3>
                                            {isProfileGap ? (
                                                <span className="rounded-full bg-[#2CABE3]/15 px-2 py-0.5 text-[10px] font-medium uppercase tracking-wide text-[#2CABE3]">
                                                    Profile
                                                </span>
                                            ) : insight.priority && (
                                                <span className={`rounded-full px-2 py-0.5 text-[10px] font-medium uppercase tracking-wide ${priorityClass}`}>
                                                    {insight.priority}
                                                </span>
                                            )}
                                        </div>
                                        {insight.message && (
                                            <p className="mt-1 text-sm text-gray-600">{insight.message}</p>
                                        )}
                                        {insight.action?.label && (
                                            <button
                                                type="button"
                                                onClick={() => handleAction(insight.action)}
                                                className="mt-2 inline-flex items-center gap-1 rounded-md bg-[#2CABE3] px-3 py-1 text-xs font-medium text-white hover:opacity-90"
                                            >
                                                {insight.action.label}
                                                <i className="fas fa-arrow-right text-[10px]" aria-hidden="true" />
                                            </button>
                                        )}
                                    </div>
                                </li>
                            );
                        })}
                    </ul>
                )}
            </div>
        </section>
    );
}

RoleInsightsPanel.propTypes = {
    roleHint: PropTypes.string,
    className: PropTypes.string,
};

export default RoleInsightsPanel;
