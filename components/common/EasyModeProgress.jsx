import React, { useMemo, useState } from 'react'
import { useNouriGuide } from '../../utils/NouriGuideContext'

/**
 * Progress header for Easy Mode — one section at a time.
 */
export default function EasyModeProgress({ sectionIndex, sectionTotal, sectionTitle }) {
  const { settings } = useNouriGuide()
  if (!settings.easyMode || sectionTotal <= 1) return null

  const pct = Math.round(((sectionIndex + 1) / sectionTotal) * 100)

  return (
    <div
      className="mb-4 rounded-lg border border-[#2CABE3]/30 bg-[#2CABE3]/5 px-4 py-3"
      role="status"
      aria-live="polite"
    >
      <div className="flex items-center justify-between gap-2 mb-2">
        <p className="text-sm font-semibold text-gray-900">
          Easy mode — step {sectionIndex + 1} of {sectionTotal}
        </p>
        {sectionTitle && (
          <p className="text-xs text-gray-600 truncate">{sectionTitle}</p>
        )}
      </div>
      <div
        className="h-2 w-full rounded-full bg-gray-200 overflow-hidden"
        role="progressbar"
        aria-valuenow={pct}
        aria-valuemin={0}
        aria-valuemax={100}
        aria-label={`Form progress ${pct} percent`}
      >
        <div
          className="h-full bg-[#2CABE3] transition-all duration-300"
          style={{ width: `${pct}%` }}
        />
      </div>
    </div>
  )
}

/**
 * @param {{ easyMode: boolean, sectionIndex: number, activeSection: number, children: React.ReactNode }} props
 */
export function EasyModeSectionGate({ easyMode, sectionIndex, activeSection, children }) {
  if (!easyMode) return children
  if (sectionIndex !== activeSection) return null
  return children
}

/**
 * Hook for multi-section forms in Easy Mode.
 * @param {number} sectionCount
 */
export function useEasyModeSections(sectionCount) {
  const { settings } = useNouriGuide()
  const easyMode = settings.easyMode
  const [activeSection, setActiveSection] = useState(0)

  const navigation = useMemo(() => ({
    canPrev: activeSection > 0,
    canNext: activeSection < sectionCount - 1,
    goPrev: () => setActiveSection((s) => Math.max(0, s - 1)),
    goNext: () => setActiveSection((s) => Math.min(sectionCount - 1, s + 1)),
    goToSection: (index) => {
      const i = Math.max(0, Math.min(sectionCount - 1, Number(index) || 0))
      setActiveSection(i)
    },
    activeSection,
    sectionCount,
    easyMode,
  }), [activeSection, sectionCount, easyMode])

  return navigation
}
