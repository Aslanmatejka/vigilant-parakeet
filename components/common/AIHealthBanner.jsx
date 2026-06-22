import React, { useEffect, useState } from 'react'
import { aiHealth, AI_STATUS } from '../../utils/services/aiSelfHealing.js'

/**
 * AIHealthBanner
 * --------------
 * Futuristic "self-healing in progress" overlay.
 *
 * - Subscribes to the AI self-healing health monitor
 * - Renders an animated neural orb + scan sweep + reassuring copy
 *   while the AI backend is degraded or down
 * - Disappears automatically once health is restored
 */
function AIHealthBanner() {
    const [status, setStatus] = useState(aiHealth.getStatus())

    useEffect(() => {
        const unsub = aiHealth.subscribe(setStatus)
        return unsub
    }, [])

    if (!status || status.status === AI_STATUS.HEALTHY) return null

    const isDown = status.status === AI_STATUS.DOWN
    const title = isDown ? 'Repairing AI link' : 'Healing AI link'
    const subtitle = isDown
        ? 'Reconnecting circuits to the neural backbone'
        : 'Patching the connection in the background'
    const accent = isDown
        ? 'from-rose-400 via-fuchsia-400 to-cyan-400'
        : 'from-amber-300 via-cyan-300 to-violet-400'

    return (
        <div
            role="status"
            aria-live="polite"
            aria-label={`${title}. ${subtitle}`}
            className="fixed top-4 right-4 z-[9999] w-[300px] max-w-[calc(100vw-2rem)] pointer-events-none"
        >
            <div className="ai-heal-card relative px-4 py-3 text-white pointer-events-auto">
                {/* Animated diagonal scan sweep */}
                <span className="ai-heal-scan" aria-hidden="true" />

                <div className="relative z-10 flex items-center gap-3">
                    {/* Circuit-repair scene: broken wire being welded, sparks, orbiting wrench */}
                    <div className="relative w-14 h-14 flex-shrink-0" aria-hidden="true">
                        <svg
                            viewBox="0 0 56 56"
                            className="absolute inset-0 w-full h-full"
                        >
                            <defs>
                                <linearGradient id="aiHealWire" x1="0" y1="0" x2="1" y2="0">
                                    <stop offset="0%"   stopColor="#22d3ee" />
                                    <stop offset="50%"  stopColor="#a78bfa" />
                                    <stop offset="100%" stopColor="#ec4899" />
                                </linearGradient>
                                <radialGradient id="aiHealNode" cx="0.5" cy="0.5" r="0.5">
                                    <stop offset="0%" stopColor="#fff"     stopOpacity="1" />
                                    <stop offset="60%" stopColor="#22d3ee" stopOpacity="0.9" />
                                    <stop offset="100%" stopColor="#22d3ee" stopOpacity="0" />
                                </radialGradient>
                            </defs>

                            {/* Existing solid wire segments */}
                            <path d="M4 28 L18 28" stroke="url(#aiHealWire)" strokeWidth="2.5" strokeLinecap="round" opacity="0.85" />
                            <path d="M38 28 L52 28" stroke="url(#aiHealWire)" strokeWidth="2.5" strokeLinecap="round" opacity="0.85" />

                            {/* The "broken" gap being welded back together */}
                            <path
                                d="M18 28 L38 28"
                                stroke="url(#aiHealWire)"
                                strokeWidth="2.5"
                                strokeLinecap="round"
                                fill="none"
                                className="ai-heal-weld"
                            />

                            {/* End-cap nodes */}
                            <circle cx="4"  cy="28" r="2.5" fill="#22d3ee" className="ai-heal-node" />
                            <circle cx="52" cy="28" r="2.5" fill="#ec4899" className="ai-heal-node" />

                            {/* Repair point — bright flash where the weld happens */}
                            <circle
                                cx="28"
                                cy="28"
                                r="6"
                                fill="url(#aiHealNode)"
                                style={{ transformOrigin: '28px 28px' }}
                                className="ai-heal-flash"
                            />
                        </svg>

                        {/* Sparks flying outward from the weld point */}
                        <div className="absolute top-1/2 left-1/2 w-0 h-0" aria-hidden="true">
                            <span className="ai-heal-spark absolute top-0 left-0 w-1 h-1 rounded-full bg-cyan-300 shadow-[0_0_6px_rgba(34,211,238,1)]" />
                            <span className="ai-heal-spark absolute top-0 left-0 w-1 h-1 rounded-full bg-amber-300 shadow-[0_0_6px_rgba(252,211,77,1)]" />
                            <span className="ai-heal-spark absolute top-0 left-0 w-1 h-1 rounded-full bg-fuchsia-300 shadow-[0_0_6px_rgba(232,121,249,1)]" />
                            <span className="ai-heal-spark absolute top-0 left-0 w-1 h-1 rounded-full bg-white shadow-[0_0_6px_rgba(255,255,255,1)]" />
                        </div>

                        {/* Tiny wrench orbiting the repair point */}
                        <div className="absolute inset-0 flex items-center justify-center pointer-events-none">
                            <div className="ai-heal-tool-orbit">
                                <i className="fas fa-wrench text-[10px] text-cyan-200 ai-heal-tool-shake drop-shadow-[0_0_4px_rgba(34,211,238,0.9)]" />
                            </div>
                        </div>
                    </div>

                    {/* Text block */}
                    <div className="flex-1 min-w-0">
                        <div className="flex items-center gap-1.5">
                            <span className={`text-[13px] font-semibold tracking-wide bg-gradient-to-r ${accent} bg-clip-text text-transparent`}>
                                {title}
                            </span>
                        </div>
                        <div className="mt-0.5 flex items-center gap-1.5 text-[11px] text-slate-300/90">
                            <span className="truncate">{subtitle}</span>
                            <span className="inline-flex items-end gap-[2px] ml-0.5">
                                <span className="ai-heal-dot w-1 h-1 rounded-full bg-cyan-300" />
                                <span className="ai-heal-dot w-1 h-1 rounded-full bg-fuchsia-300" />
                                <span className="ai-heal-dot w-1 h-1 rounded-full bg-violet-300" />
                            </span>
                        </div>
                    </div>
                </div>

                {/* Bottom data stream */}
                <div className="relative z-10 mt-2 h-[3px] rounded-full bg-slate-700/60 overflow-hidden">
                    <div
                        className={`h-full w-1/3 rounded-full bg-gradient-to-r ${accent}`}
                        style={{ animation: 'ai-scan-sweep 1.6s linear infinite' }}
                    />
                </div>
            </div>
        </div>
    )
}

export default AIHealthBanner
