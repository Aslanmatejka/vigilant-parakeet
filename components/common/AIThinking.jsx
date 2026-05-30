import React, { useEffect, useState } from 'react';
import PropTypes from 'prop-types';

/**
 * Shared futuristic "AI is working" indicator.
 *
 * Used across every AI surface (chat, role insights, data query, etc.) so the
 * app speaks with one visual language whenever the model is thinking.
 *
 * Two visual variants:
 *   - "inline"  : compact avatar + status bubble (matches chat TypingIndicator)
 *   - "panel"   : full-width card with shimmer + scanning bar (replaces skeletons)
 *
 * Animations live in styles/components.css under the `.ai-typing-*` classes.
 */

const DEFAULT_STAGES = [
    { icon: 'brain', label: 'Analyzing your request' },
    { icon: 'database', label: 'Searching knowledge base' },
    { icon: 'satellite-dish', label: 'Consulting live activity' },
    { icon: 'wand-magic-sparkles', label: 'Generating response' },
];

function useCyclingStage(stages, intervalMs = 1400) {
    const [idx, setIdx] = useState(0);
    useEffect(() => {
        if (!stages || stages.length <= 1) return undefined;
        const t = setInterval(() => setIdx((i) => (i + 1) % stages.length), intervalMs);
        return () => clearInterval(t);
    }, [stages, intervalMs]);
    return stages?.[idx] || stages?.[0];
}

function OrbitingAvatar({ size = 40 }) {
    const px = `${size}px`;
    return (
        <div className="relative flex-shrink-0" style={{ width: px, height: px }}>
            {/* Outer fast-spinning gradient ring */}
            <div
                className="absolute inset-0 rounded-full ai-typing-orbit-fast"
                style={{
                    background:
                        'conic-gradient(from 0deg, transparent 0%, rgba(34,211,238,0.95) 28%, transparent 55%, rgba(168,85,247,0.85) 82%, transparent 100%)',
                    WebkitMask: 'radial-gradient(circle, transparent 56%, black 58%)',
                    mask: 'radial-gradient(circle, transparent 56%, black 58%)',
                }}
                aria-hidden="true"
            />
            {/* Inner counter-rotating ring */}
            <div
                className="absolute inset-1 rounded-full ai-typing-orbit-slow"
                style={{
                    background:
                        'conic-gradient(from 180deg, transparent 0%, rgba(165,243,252,0.7) 40%, transparent 80%)',
                    WebkitMask: 'radial-gradient(circle, transparent 62%, black 64%)',
                    mask: 'radial-gradient(circle, transparent 62%, black 64%)',
                }}
                aria-hidden="true"
            />
            {/* Pulsing core */}
            <div className="absolute inset-2 rounded-full bg-gradient-to-br from-cyan-400 via-blue-500 to-purple-600 flex items-center justify-center ai-typing-core">
                <i className="fas fa-sparkles text-[9px] text-white" aria-hidden="true" />
            </div>
            {/* Rising particles */}
            <span
                className="ai-typing-particle absolute top-0 left-1 w-1 h-1 rounded-full bg-cyan-300"
                style={{ animationDelay: '0ms' }}
                aria-hidden="true"
            />
            <span
                className="ai-typing-particle absolute top-0 right-1 w-1 h-1 rounded-full bg-fuchsia-300"
                style={{ animationDelay: '550ms' }}
                aria-hidden="true"
            />
            <span
                className="ai-typing-particle absolute top-1 left-4 w-0.5 h-0.5 rounded-full bg-white"
                style={{ animationDelay: '1100ms' }}
                aria-hidden="true"
            />
        </div>
    );
}

OrbitingAvatar.propTypes = { size: PropTypes.number };

function StageBubble({ stage, dark = true }) {
    const wrap = dark
        ? 'bg-slate-800/60 border-cyan-500/30 shadow-cyan-500/10'
        : 'bg-white/80 border-cyan-400/40 shadow-cyan-400/10';
    const labelColor = dark ? 'text-cyan-100' : 'text-cyan-900';
    const iconColor = dark ? 'text-cyan-300' : 'text-cyan-600';
    return (
        <div
            className={`ai-typing-shimmer relative backdrop-blur-md rounded-2xl px-3.5 py-2 border shadow-lg overflow-hidden ${wrap}`}
        >
            <div className="flex items-center gap-2 relative z-10">
                <i
                    key={`icon-${stage.icon}`}
                    className={`fas fa-${stage.icon} ${iconColor} text-[11px] ai-typing-status`}
                    aria-hidden="true"
                />
                <span
                    key={`label-${stage.label}`}
                    className={`text-[11px] ${labelColor} font-medium tracking-wide truncate ai-typing-status`}
                >
                    {stage.label}…
                </span>
            </div>
            <div className="flex items-center gap-1 mt-1 relative z-10">
                <span
                    className="ai-typing-dot w-1.5 h-1.5 rounded-full bg-cyan-300"
                    style={{ animationDelay: '0ms' }}
                />
                <span
                    className="ai-typing-dot w-1.5 h-1.5 rounded-full bg-blue-400"
                    style={{ animationDelay: '180ms' }}
                />
                <span
                    className="ai-typing-dot w-1.5 h-1.5 rounded-full bg-fuchsia-400"
                    style={{ animationDelay: '360ms' }}
                />
            </div>
        </div>
    );
}

StageBubble.propTypes = {
    stage: PropTypes.shape({
        icon: PropTypes.string.isRequired,
        label: PropTypes.string.isRequired,
    }).isRequired,
    dark: PropTypes.bool,
};

/**
 * Inline indicator: orbit avatar + cycling status bubble.
 * Drop-in for "AI is thinking" rows next to messages or buttons.
 */
export function AIThinkingInline({ stages = DEFAULT_STAGES, dark = true, size = 40, className = '' }) {
    const stage = useCyclingStage(stages);
    return (
        <div
            className={`flex items-center gap-3 ${className}`}
            role="status"
            aria-live="polite"
            aria-label={`AI: ${stage.label}`}
        >
            <OrbitingAvatar size={size} />
            <div className="relative flex-1 min-w-0 max-w-[280px]">
                <StageBubble stage={stage} dark={dark} />
            </div>
        </div>
    );
}

AIThinkingInline.propTypes = {
    stages: PropTypes.arrayOf(
        PropTypes.shape({ icon: PropTypes.string, label: PropTypes.string }),
    ),
    dark: PropTypes.bool,
    size: PropTypes.number,
    className: PropTypes.string,
};

/**
 * Panel indicator: futuristic card replacement for skeleton loaders.
 * Includes a horizontal "scanning" bar and a stacked status row.
 */
export function AIThinkingPanel({ stages = DEFAULT_STAGES, title = 'AI at work', className = '' }) {
    const stage = useCyclingStage(stages);
    return (
        <div
            className={`relative overflow-hidden rounded-xl border border-cyan-400/30 bg-gradient-to-br from-slate-50 via-cyan-50/40 to-indigo-50/40 p-4 ${className}`}
            role="status"
            aria-live="polite"
            aria-label={`${title}: ${stage.label}`}
        >
            {/* Scanning beam */}
            <div className="pointer-events-none absolute inset-0 ai-typing-shimmer" aria-hidden="true" />

            <div className="relative z-10 flex items-center gap-3">
                <OrbitingAvatar size={44} />
                <div className="min-w-0 flex-1">
                    <p className="text-[11px] font-semibold uppercase tracking-wider text-cyan-700/80">
                        {title}
                    </p>
                    <p
                        key={`panel-stage-${stage.label}`}
                        className="ai-typing-status mt-0.5 truncate text-sm font-medium text-slate-800"
                    >
                        <i className={`fas fa-${stage.icon} mr-2 text-cyan-600`} aria-hidden="true" />
                        {stage.label}…
                    </p>
                </div>
            </div>

            {/* Animated progress bar */}
            <div className="relative z-10 mt-3 h-1.5 w-full overflow-hidden rounded-full bg-cyan-100/70">
                <div
                    className="h-full w-1/3 rounded-full bg-gradient-to-r from-cyan-400 via-blue-500 to-fuchsia-500"
                    style={{
                        animation: 'ai-shimmer 1.8s linear infinite',
                    }}
                />
            </div>

            {/* Stacked status dots */}
            <div className="relative z-10 mt-3 flex items-center gap-1.5">
                <span className="ai-typing-dot w-1.5 h-1.5 rounded-full bg-cyan-500" style={{ animationDelay: '0ms' }} />
                <span className="ai-typing-dot w-1.5 h-1.5 rounded-full bg-blue-500" style={{ animationDelay: '180ms' }} />
                <span className="ai-typing-dot w-1.5 h-1.5 rounded-full bg-fuchsia-500" style={{ animationDelay: '360ms' }} />
                <span className="ml-2 text-[10px] uppercase tracking-wider text-slate-500">
                    Powered by GPT-4o
                </span>
            </div>
        </div>
    );
}

AIThinkingPanel.propTypes = {
    stages: PropTypes.arrayOf(
        PropTypes.shape({ icon: PropTypes.string, label: PropTypes.string }),
    ),
    title: PropTypes.string,
    className: PropTypes.string,
};

export default AIThinkingInline;
