import React, { useState, useEffect, useRef, useCallback, useMemo } from 'react'
import { useAIChat, AI_TONE_OPTIONS, AI_TONE_LABELS } from '../../utils/hooks/useAIChat.js'
import { useAuthContext } from '../../utils/AuthContext.jsx'
import { useCommunityRole } from '../../utils/hooks/useCommunityRole.js'
import { useMapContext } from '../../utils/MapContext.jsx'
import { useUIControl } from '../../utils/UIControlContext.jsx'
import VoiceOutput from './VoiceOutput.jsx'
import { useNouriGuide } from '../../utils/NouriGuideContext.jsx'
import aiChatService from '../../utils/services/aiChatService.js'
import { parseListingsCsv, downloadCsvTemplate, sanitizeListingExpiry, visionDraftToRow, matchCommunityByName } from '../../utils/csvListings.js'
import { assignImagestoRows, assignFoodImage } from '../../utils/foodImages.js'
import dataService from '../../utils/dataService.js'
import supabase from '../../utils/supabaseClient.js'
import { resolveInputChips } from '../../utils/suggestionChips.js'
import { toast } from 'react-toastify'
import {
  browseCommunityIdsForUser,
  listingVisibleToCommunityScope,
} from '../../utils/communityScope.js'
import {
  getWelcomeCategories,
  getSuggestions,
  welcomeGreeting,
  t as chatT,
  dateLocale,
  dateLabel,
  languageSwitchPrompt,
  CHAT_UI_LANGUAGES,
  CHAT_LANGUAGE_LABELS,
  getToneLabels,
  chatLang,
  onlineToneLabel,
} from '../../utils/chatI18n.js'

// Map accent → tailwind classes so the welcome cards stay on-brand
// while still being visually distinct from each other.
const ACCENT_MAP = {
  emerald: {
    iconBg: 'bg-emerald-500/15 text-emerald-700 ring-emerald-400/30',
    border: 'border-emerald-500/20 hover:border-emerald-400/40',
    glow: 'hover:shadow-emerald-500/10',
    promptHover: 'hover:bg-emerald-500/10 hover:text-emerald-800',
  },
  fuchsia: {
    iconBg: 'bg-fuchsia-500/15 text-fuchsia-700 ring-fuchsia-400/30',
    border: 'border-fuchsia-500/20 hover:border-fuchsia-400/40',
    glow: 'hover:shadow-fuchsia-500/10',
    promptHover: 'hover:bg-fuchsia-500/10 hover:text-fuchsia-800',
  },
  cyan: {
    iconBg: 'bg-[#2CABE3]/15 text-[#2CABE3] ring-[#2CABE3]/30',
    border: 'border-[#2CABE3]/20 hover:border-[#2CABE3]/40',
    glow: 'hover:shadow-[#2CABE3]/10',
    promptHover: 'hover:bg-[#2CABE3]/10 hover:text-[#2299c7]',
  },
  sky: {
    iconBg: 'bg-sky-500/15 text-sky-600 ring-sky-400/30',
    border: 'border-sky-500/20 hover:border-sky-400/40',
    glow: 'hover:shadow-sky-500/10',
    promptHover: 'hover:bg-sky-500/10 hover:text-sky-700',
  },
  amber: {
    iconBg: 'bg-amber-500/15 text-amber-600 ring-amber-400/30',
    border: 'border-amber-500/20 hover:border-amber-400/40',
    glow: 'hover:shadow-amber-500/10',
    promptHover: 'hover:bg-amber-500/10 hover:text-amber-800',
  },
}

// ─── WelcomeHero — empty-state onboarding surface ──────────────────
function WelcomeHero({ language, userName, onPromptClick, communityRole }) {
  const all = getWelcomeCategories(language)
  const role = String(communityRole || '').toLowerCase()
  const categories = all.filter((cat) => {
    if (role === 'donor') return cat.key !== 'find' && cat.key !== 'request'
    if (role === 'recipient') return cat.key !== 'share'
    return true
  })
  const greeting = welcomeGreeting(language, userName)
  const subtitle = chatT(language, 'welcomeSubtitle')

  return (
    <div className="px-4 pt-3 pb-2">
      <div className="mb-3">
        <h2 className="text-base font-semibold text-gray-900 tracking-tight">{greeting}</h2>
        <p className="text-xs text-gray-600 mt-0.5">{subtitle}</p>
      </div>

      <div className="grid grid-cols-2 gap-2">
        {categories.map((cat) => {
          const accent = ACCENT_MAP[cat.accent] || ACCENT_MAP.cyan
          return (
            <div
              key={cat.key}
              className={`rounded-xl p-3 bg-white/70 backdrop-blur-sm border transition-all ${accent.border} hover:bg-white/90 hover:shadow-md shadow-sm ${accent.glow}`}
            >
              <div className="flex items-center gap-2 mb-1.5">
                <span className={`w-7 h-7 rounded-lg ring-1 flex items-center justify-center ${accent.iconBg}`}>
                  <i className={`fas ${cat.icon} text-xs`} aria-hidden="true" />
                </span>
                <div className="min-w-0">
                  <div className="text-xs font-semibold text-gray-900 truncate">{cat.title}</div>
                  <div className="text-[10px] text-gray-500 truncate">{cat.blurb}</div>
                </div>
              </div>
              <ul className="space-y-1">
                {cat.prompts.map((p) => (
                  <li key={p}>
                    <button
                      type="button"
                      onClick={() => onPromptClick?.(p)}
                      className={`w-full text-left text-[11px] leading-snug text-gray-600 px-2 py-1 rounded-md transition-colors ${accent.promptHover}`}
                    >
                      {p}
                    </button>
                  </li>
                ))}
              </ul>
            </div>
          )
        })}
      </div>
    </div>
  )
}

// ─── Date separator — "Today" / "Yesterday" / "Mon, May 22" ────────
function formatSeparator(iso, language) {
  if (!iso) return null
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return null
  const now = new Date()
  const startOfDay = (x) => new Date(x.getFullYear(), x.getMonth(), x.getDate()).getTime()
  const diffDays = Math.round((startOfDay(now) - startOfDay(d)) / 86400000)
  const loc = dateLocale(language)
  if (diffDays === 0) return dateLabel(language, 'today')
  if (diffDays === 1) return dateLabel(language, 'yesterday')
  if (diffDays < 7) {
    return d.toLocaleDateString(loc, { weekday: 'long' })
  }
  return d.toLocaleDateString(loc, { month: 'short', day: 'numeric' })
}

function DateSeparator({ label }) {
  return (
    <div className="relative my-3 flex items-center gap-2" aria-hidden="true">
      <span className="flex-1 h-px bg-gradient-to-r from-transparent via-[#2CABE3]/25 to-transparent" />
      <span className="text-[10px] uppercase tracking-wider text-gray-500 px-2 py-0.5 rounded-full bg-white/80 border border-[#2CABE3]/15">
        {label}
      </span>
      <span className="flex-1 h-px bg-gradient-to-l from-transparent via-[#2CABE3]/25 to-transparent" />
    </div>
  )
}

// ─── ScrollToBottomPill — appears when user scrolls up ─────────────
function ScrollToBottomPill({ visible, onClick, language }) {
  if (!visible) return null
  return (
    <button
      type="button"
      onClick={onClick}
      className="absolute bottom-3 right-3 z-10 flex items-center gap-1.5 px-3 py-1.5 rounded-full bg-white/90 backdrop-blur-md border border-[#2CABE3]/20 text-[#2CABE3] text-xs shadow-lg shadow-[#2CABE3]/10 hover:bg-white hover:border-[#2CABE3]/40 hover:scale-105 active:scale-95 transition-all animate-fade-in"
      aria-label={chatT(language, 'jumpLatest')}
    >
      <i className="fas fa-arrow-down text-[10px]" aria-hidden="true" />
      {chatT(language, 'latest')}
    </button>
  )
}

// ─── Autocomplete suggestion pool (see utils/chatI18n.js) ─────────

function TypingIndicator() {
  return (
    <div className="flex px-4 py-1.5" aria-live="polite" aria-label="Nouri is typing">
      <div className="inline-flex items-center gap-1 rounded-2xl bg-white/80 border border-[#2CABE3]/15 px-3 py-2 backdrop-blur-sm shadow-sm">
        {[0, 180, 360].map((delay) => (
          <span
            key={delay}
            className="ai-typing-dot w-1.5 h-1.5 rounded-full bg-[#2CABE3]/70"
            style={{ animationDelay: `${delay}ms` }}
            aria-hidden="true"
          />
        ))}
      </div>
    </div>
  )
}

// ─── Tool result card ──────────────────────────────────
// Unified visual language: every kind of tool result becomes a card with
// a colored icon chip, a strong title, optional meta line, and an
// optional details footer. Color tokens are picked per intent so users
// can scan the conversation and instantly tell apart "you claimed",
// "you posted", "you cancelled", and "search results".
const TOOL_CARD_TOKENS = {
  search: {
    title: { en: 'Nearby food', es: 'Comida cerca' },
    icon: 'fa-utensils',
    ring: 'ring-emerald-400/50',
    bg: 'bg-emerald-950 border-emerald-500/40',
    accent: 'text-white',
    sub: 'text-emerald-50',
    tag: 'bg-emerald-500/30 text-white border-emerald-400/50',
  },
  mylistings: {
    title: { en: 'Your listings', es: 'Tus publicaciones' },
    icon: 'fa-clipboard-list',
    ring: 'ring-emerald-400/50',
    bg: 'bg-emerald-950 border-emerald-500/40',
    accent: 'text-white',
    sub: 'text-emerald-50',
    tag: 'bg-emerald-500/30 text-white border-emerald-400/50',
  },
  myclaims: {
    title: { en: 'Your claims', es: 'Tus reclamos' },
    icon: 'fa-hand-holding-heart',
    ring: 'ring-emerald-400/50',
    bg: 'bg-emerald-950 border-emerald-500/40',
    accent: 'text-white',
    sub: 'text-emerald-50',
    tag: 'bg-emerald-500/30 text-white border-emerald-400/50',
  },
  community: {
    title: { en: 'Community listings', es: 'Publicaciones de la comunidad' },
    icon: 'fa-school',
    ring: 'ring-emerald-400/50',
    bg: 'bg-emerald-950 border-emerald-500/40',
    accent: 'text-white',
    sub: 'text-emerald-50',
    tag: 'bg-emerald-500/30 text-white border-emerald-400/50',
  },
  claim: {
    title: { en: 'Claim confirmed', es: 'Reclamo confirmado' },
    icon: 'fa-circle-check',
    ring: 'ring-emerald-400/50',
    bg: 'bg-emerald-950 border-emerald-500/40',
    accent: 'text-white',
    sub: 'text-emerald-50',
  },
  error: {
    title: { en: 'Something went wrong', es: 'Algo salió mal' },
    icon: 'fa-triangle-exclamation',
    ring: 'ring-rose-400/50',
    bg: 'bg-rose-950 border-rose-500/40',
    accent: 'text-white',
    sub: 'text-rose-50',
  },
  cancel: {
    title: { en: 'Claim released', es: 'Reclamo liberado' },
    icon: 'fa-arrow-rotate-left',
    ring: 'ring-amber-400/50',
    bg: 'bg-amber-950 border-amber-500/40',
    accent: 'text-white',
    sub: 'text-amber-50',
  },
  updated: {
    title: { en: 'Listing updated', es: 'Listado actualizado' },
    icon: 'fa-pen-to-square',
    ring: 'ring-violet-400/50',
    bg: 'bg-violet-950 border-violet-500/40',
    accent: 'text-white',
    sub: 'text-violet-50',
  },
  deleted: {
    title: { en: 'Listing deleted', es: 'Listado eliminado' },
    icon: 'fa-trash-can',
    ring: 'ring-slate-400/50',
    bg: 'bg-slate-900 border-slate-500/40',
    accent: 'text-white',
    sub: 'text-slate-100',
  },
  post: {
    title: { en: 'Listing posted', es: 'Donación publicada' },
    icon: 'fa-bullhorn',
    ring: 'ring-fuchsia-400/50',
    bg: 'bg-fuchsia-950 border-fuchsia-500/40',
    accent: 'text-white',
    sub: 'text-fuchsia-50',
  },
  pickup: {
    title: { en: 'Pickup confirmed', es: 'Recogida confirmada' },
    icon: 'fa-check-double',
    ring: 'ring-sky-400/50',
    bg: 'bg-sky-950 border-sky-500/40',
    accent: 'text-white',
    sub: 'text-sky-50',
  },
  reminder: {
    title: { en: 'Reminder set', es: 'Recordatorio creado' },
    icon: 'fa-bell',
    ring: 'ring-blue-400/50',
    bg: 'bg-blue-950 border-blue-500/40',
    accent: 'text-white',
    sub: 'text-blue-50',
  },
  generic: {
    title: { en: 'Done', es: 'Hecho' },
    icon: 'fa-circle-check',
    ring: 'ring-slate-400/40',
    bg: 'bg-slate-900 border-slate-500/40',
    accent: 'text-white',
    sub: 'text-slate-100',
  },
  claimfail: {
    title: { en: 'Could not claim', es: 'No se pudo reclamar' },
    icon: 'fa-circle-xmark',
    ring: 'ring-red-400/50',
    bg: 'bg-red-950 border-red-500/40',
    accent: 'text-white',
    sub: 'text-red-50',
  },
}

function ToolCardShell({ kind, language = 'en', titleOverride, children }) {
  const t = TOOL_CARD_TOKENS[kind] || TOOL_CARD_TOKENS.claim
  const title = titleOverride || t.title[language] || t.title.en
  return (
    <div
      role="status"
      className={`mt-2 ${t.bg} border rounded-xl p-3 text-sm shadow-md`}
    >
      <div className="flex items-center gap-2 mb-1.5">
        <span className={`inline-flex w-6 h-6 rounded-full bg-black/30 ring-1 ${t.ring} items-center justify-center`}>
          <i className={`fas ${t.icon} text-[11px] ${t.accent}`} aria-hidden="true" />
        </span>
        <div className={`font-semibold text-xs uppercase tracking-wide ${t.accent}`}>{title}</div>
      </div>
      <div className={`text-xs leading-relaxed ${t.sub}`}>{children}</div>
    </div>
  )
}


function SearchResultsClaimList({
  searchItems,
  tool,
  language,
  t,
  cardKind,
  onSuggestionClick,
}) {
  const isEs = language === 'es'
  const claimable = tool === 'search_food_near_user'
    || tool === 'search_food_nearby'
    || tool === 'get_recent_listings'
    || tool === 'get_community_listings'
  const [selected, setSelected] = useState(() => new Set())

  const toggle = (displayNum) => {
    setSelected((prev) => {
      const next = new Set(prev)
      if (next.has(displayNum)) next.delete(displayNum)
      else next.add(displayNum)
      return next
    })
  }

  const selectAllVisible = () => {
    const nums = searchItems.slice(0, 25).map((item, idx) => item.display_index ?? (idx + 1))
    setSelected(new Set(nums))
  }

  const clearSelection = () => setSelected(new Set())

  const claimSelected = () => {
    if (!onSuggestionClick || selected.size === 0) return
    const nums = Array.from(selected).sort((a, b) => a - b)
    if (nums.length === 1) {
      onSuggestionClick(
        isEs ? `Quiero reclamar el #${nums[0]}` : `I'd like to claim #${nums[0]}`,
      )
      return
    }
    const list = nums.map((n) => `#${n}`).join(', ')
    onSuggestionClick(
      isEs
        ? `Quiero reclamar ${list} — varios a la vez`
        : `I'd like to claim ${list} — multiple items at once`,
    )
  }

  const fmtDate = (iso) => {
    if (!iso) return null
    try {
      const [y, m, d] = String(iso).slice(0, 10).split('-').map(Number)
      return new Date(y, m - 1, d).toLocaleDateString(undefined, { month: 'short', day: 'numeric' })
    } catch {
      return iso
    }
  }

  const titleOverride = claimable && searchItems.length >= 2
    ? (isEs
      ? `Comida cerca · ${searchItems.length} · puedes reclamar varios`
      : `Food nearby · ${searchItems.length} · claim several at once`)
    : `${t.title[language] || t.title.en} · ${searchItems.length}`

  return (
    <ToolCardShell kind={cardKind} language={language} titleOverride={titleOverride}>
      {claimable && searchItems.length >= 2 && onSuggestionClick && (
        <div className="mb-2 rounded-lg border border-emerald-500/25 bg-emerald-500/10 px-2.5 py-2 space-y-1.5">
          <p className={`text-[11px] ${t.accent} font-medium`}>
            {isEs
              ? 'Marca varios y reclámalos juntos — o usa Reclamar en uno solo.'
              : 'Select several items and claim them together — or Claim one at a time.'}
          </p>
          <div className="flex flex-wrap items-center gap-1.5">
            <button
              type="button"
              onClick={selectAllVisible}
              className="text-[11px] px-2 py-0.5 rounded-md border border-emerald-400/40 text-emerald-50 hover:bg-emerald-500/30"
            >
              {isEs ? 'Seleccionar visibles' : 'Select visible'}
            </button>
            {selected.size > 0 && (
              <button
                type="button"
                onClick={clearSelection}
                className="text-[11px] px-2 py-0.5 rounded-md border border-slate-500 text-slate-100 hover:bg-slate-800/60"
              >
                {isEs ? 'Limpiar' : 'Clear'}
              </button>
            )}
            <button
              type="button"
              onClick={claimSelected}
              disabled={selected.size === 0}
              className="ml-auto inline-flex items-center gap-1 px-2.5 py-1 rounded-md bg-emerald-500/40 border border-emerald-300/60 text-white text-[11px] font-semibold hover:bg-emerald-500/55 disabled:opacity-40 disabled:cursor-not-allowed"
            >
              <i className="fas fa-hand-holding-heart text-[10px]" aria-hidden="true" />
              {selected.size === 0
                ? (isEs ? 'Reclamar seleccionados' : 'Claim selected')
                : (isEs
                  ? `Reclamar ${selected.size} seleccionados`
                  : `Claim ${selected.size} selected`)}
            </button>
          </div>
        </div>
      )}
      <ul className="space-y-1.5">
        {searchItems.slice(0, 25).map((item, idx) => {
          const displayNum = item.display_index ?? (idx + 1)
          const miles = item.distance_miles != null
            ? Number(item.distance_miles)
            : (item.distance_km != null ? Number(item.distance_km) * 0.621371 : null)
          const distance = miles != null && Number.isFinite(miles)
            ? `${miles.toFixed(miles < 10 ? 1 : 0)} mi`
            : null
          const qtyLabel = item.quantity != null
            ? `${item.quantity}${item.unit ? ` ${item.unit}` : ''} available`
            : null
          const expiryRaw = item.expiry_date || item.pickup_by || null
          const expiryLabel = fmtDate(expiryRaw)
          const meta = [distance, qtyLabel, item.category, expiryLabel ? `Exp ${expiryLabel}` : null].filter(Boolean).join(' · ')
          const address = item.address || item.full_address || item.pickup_location || null
          const photoUrl = typeof item.image_url === 'string' && /^https?:\/\//i.test(item.image_url)
            ? item.image_url
            : null
          const isSelected = selected.has(displayNum)

          return (
            <li
              key={item.id || displayNum}
              className={`rounded-lg px-2.5 py-2 border ${
                isSelected
                  ? 'bg-emerald-500/15 border-emerald-400/40'
                  : 'bg-slate-900/40 border-emerald-500/15'
              }`}
            >
              <div className="flex gap-2.5">
                {claimable && onSuggestionClick && (
                  <label className="flex-shrink-0 mt-0.5 cursor-pointer">
                    <input
                      type="checkbox"
                      checked={isSelected}
                      onChange={() => toggle(displayNum)}
                      className="rounded border-slate-600 bg-slate-900 text-emerald-500 focus:ring-emerald-500/40"
                      aria-label={isEs ? `Seleccionar #${displayNum}` : `Select #${displayNum}`}
                    />
                  </label>
                )}
                <span
                  className={`flex-shrink-0 w-7 h-7 rounded-full bg-emerald-500/20 border border-emerald-400/30 flex items-center justify-center text-[12px] font-bold ${t.accent}`}
                  aria-hidden="true"
                >
                  {displayNum}
                </span>
                {photoUrl && (
                  <img
                    src={photoUrl}
                    alt={item.title || ''}
                    loading="lazy"
                    className="h-14 w-14 flex-shrink-0 rounded-md object-cover border border-emerald-500/15 bg-slate-800"
                    onError={(e) => { e.currentTarget.style.display = 'none' }}
                  />
                )}
                <div className="min-w-0 flex-1">
                  <div className={`font-medium ${t.accent}`}>{item.title}</div>
                  {meta && <div className={`${t.sub} text-[11px] mt-0.5`}>{meta}</div>}
                  {address && (
                    <div className={`${t.sub} text-[11px] mt-0.5 flex items-start gap-1`}>
                      <i className="fas fa-map-marker-alt mt-[2px] text-[10px] opacity-70" aria-hidden="true" />
                      <span className="break-words">{address}</span>
                    </div>
                  )}
                  {item.community_name && (
                    <div className={`${t.sub} text-[11px] mt-0.5 flex items-center gap-1`}>
                      <i className="fas fa-people-group text-[10px] opacity-70" aria-hidden="true" />
                      <span>{item.community_name}</span>
                    </div>
                  )}
                  {item.dietary_tags?.length > 0 && (
                    <div className="flex gap-1 mt-1.5 flex-wrap">
                      {item.dietary_tags.map((tag) => (
                        <span key={tag} className={`${t.tag} text-[10px] px-1.5 py-0.5 rounded border`}>{tag}</span>
                      ))}
                    </div>
                  )}
                  {onSuggestionClick && item.id && claimable && (
                    <button
                      type="button"
                      onClick={() => onSuggestionClick(
                        isEs
                          ? `Quiero reclamar el #${displayNum}`
                          : `I'd like to claim #${displayNum}`,
                      )}
                      className="mt-1.5 inline-flex items-center gap-1 px-2 py-0.5 rounded-md bg-emerald-500/20 border border-emerald-400/30 text-emerald-50 text-[11px] font-semibold hover:bg-emerald-500/40 transition-colors"
                    >
                      <i className="fas fa-hand-holding-heart text-[10px]" aria-hidden="true" />
                      {isEs ? 'Reclamar solo este' : 'Claim this one'}
                    </button>
                  )}
                </div>
              </div>
            </li>
          )
        })}
        {searchItems.length > 25 && (
          <li className={`text-[11px] ${t.sub} text-center pt-0.5`}>
            {isEs ? `+${searchItems.length - 25} más` : `+${searchItems.length - 25} more`}
          </li>
        )}
      </ul>
    </ToolCardShell>
  )
}

function ToolResultCard({ toolResult, language = 'en', onSuggestionClick, allowedCommunityIds = null }) {
  if (!toolResult) return null

  const { tool } = toolResult
  const result = toolResult.result ?? toolResult
  const ok = (result?.success === true || toolResult.ok === true) && !result?.error

  const rawSearchItems = result.listings ?? result.results ?? []
  const searchBrowseTools = [
    'search_food_near_user',
    'search_food_nearby',
    'get_recent_listings',
    'get_community_listings',
  ]
  const searchItems = searchBrowseTools.includes(tool)
    ? rawSearchItems.filter((item) => {
        // If community_id was stripped by an older polish path, trust the
        // backend (already community-scoped). Only hide when we know the id
        // and it is outside the viewer's own community.
        if (item?.community_id == null || item?.community_id === '') return true
        return listingVisibleToCommunityScope(item, allowedCommunityIds)
      })
    : rawSearchItems
  if ((tool === 'search_food_near_user' || tool === 'search_food_nearby' || tool === 'get_recent_listings' || tool === 'get_my_claims' || tool === 'get_community_listings' || tool === 'get_user_listings') && searchItems.length > 0) {
    const cardKind = tool === 'get_user_listings'
      ? 'mylistings'
      : tool === 'get_my_claims'
        ? 'myclaims'
        : tool === 'get_community_listings'
          ? 'community'
          : 'search'
    const t = TOOL_CARD_TOKENS[cardKind] || TOOL_CARD_TOKENS.search

    // Claimable browse results: multi-select + claim several at once.
    if (['search_food_near_user', 'search_food_nearby', 'get_recent_listings', 'get_community_listings'].includes(tool)) {
      return (
        <SearchResultsClaimList
          searchItems={searchItems}
          tool={tool}
          language={language}
          t={t}
          cardKind={cardKind}
          onSuggestionClick={onSuggestionClick}
        />
      )
    }

    /** Format an ISO date string (YYYY-MM-DD) as a short human-readable label. */
    const fmtDate = (iso) => {
      if (!iso) return null
      try {
        const [y, m, d] = String(iso).slice(0, 10).split('-').map(Number)
        return new Date(y, m - 1, d).toLocaleDateString(undefined, { month: 'short', day: 'numeric' })
      } catch {
        return iso
      }
    }

    return (
      <ToolCardShell kind={cardKind} language={language} titleOverride={`${t.title[language] || t.title.en} · ${searchItems.length}`}>
        <ul className="space-y-1.5">
          {searchItems.slice(0, 25).map((item, idx) => {
            const displayNum = item.display_index ?? (idx + 1)
            const miles = item.distance_miles != null
              ? Number(item.distance_miles)
              : (item.distance_km != null ? Number(item.distance_km) * 0.621371 : null)
            const distance = miles != null && Number.isFinite(miles)
              ? `${miles.toFixed(miles < 10 ? 1 : 0)} mi`
              : null
            const qtyLabel = item.quantity != null
              ? `${item.quantity}${item.unit ? ` ${item.unit}` : ''} available`
              : null
            const expiryRaw = item.expiry_date || item.pickup_by || null
            const expiryLabel = fmtDate(expiryRaw)
            const meta = [distance, qtyLabel, item.category, expiryLabel ? `Exp ${expiryLabel}` : null].filter(Boolean).join(' · ')
            const address = item.address || item.full_address || item.pickup_location || null
            const photoUrl = typeof item.image_url === 'string' && /^https?:\/\//i.test(item.image_url)
              ? item.image_url
              : null
            return (
              <li key={item.id || displayNum} className="rounded-lg bg-slate-900/40 px-2.5 py-2 border border-emerald-500/15">
                <div className="flex gap-2.5">
                  <span
                    className={`flex-shrink-0 w-7 h-7 rounded-full bg-emerald-500/20 border border-emerald-400/30 flex items-center justify-center text-[12px] font-bold ${t.accent}`}
                    aria-hidden="true"
                  >
                    {displayNum}
                  </span>
                  {photoUrl && (
                    <img
                      src={photoUrl}
                      alt={item.title || ''}
                      loading="lazy"
                      className="h-14 w-14 flex-shrink-0 rounded-md object-cover border border-emerald-500/15 bg-slate-800"
                      onError={(e) => { e.currentTarget.style.display = 'none' }}
                    />
                  )}
                  <div className="min-w-0 flex-1">
                    <div className={`font-medium ${t.accent}`}>{item.title}</div>
                    {meta && <div className={`${t.sub} text-[11px] mt-0.5`}>{meta}</div>}
                    {address && (
                      <div className={`${t.sub} text-[11px] mt-0.5 flex items-start gap-1`}>
                        <i className="fas fa-map-marker-alt mt-[2px] text-[10px] opacity-70" aria-hidden="true" />
                        <span className="break-words">{address}</span>
                      </div>
                    )}
                  </div>
                </div>
              </li>
            )
          })}
        </ul>
      </ToolCardShell>
    )
  }

  if (tool === 'claim_listings') {
    const claimed = Array.isArray(result.claimed) ? result.claimed : []
    const failed = Array.isArray(result.failed) ? result.failed : []
    if (claimed.length === 0 && failed.length === 0 && !result.summary) return null
    return (
      <ToolCardShell
        kind={failed.length && !claimed.length ? 'claimfail' : 'claim'}
        language={language}
        titleOverride={
          language === 'es'
            ? `Reclamos · ${claimed.length} ok${failed.length ? `, ${failed.length} fallaron` : ''}`
            : `Multi-claim · ${claimed.length} ok${failed.length ? `, ${failed.length} failed` : ''}`
        }
      >
        {claimed.length > 0 && (
          <ul className="space-y-1.5 mb-2">
            {claimed.map((c, i) => (
              <li key={c.listing_id || c.claim_id || i} className="text-white text-[12px]">
                <span className="font-semibold">{c.title || c.listing_id || 'Listing'}</span>
                {c.quantity != null && (
                  <span className="text-emerald-50"> · {c.quantity} {c.unit || ''}</span>
                )}
              </li>
            ))}
          </ul>
        )}
        {failed.length > 0 && (
          <ul className="space-y-1 text-red-100 text-[11px]">
            {failed.map((f, i) => (
              <li key={f.listing_id || i}>
                {f.title || f.listing_id || `#${f.index ?? i + 1}`}: {f.error || 'failed'}
              </li>
            ))}
          </ul>
        )}
        {(result.summary || result.message) && (
          <div className="text-white text-[12px] mt-1">{result.summary || result.message}</div>
        )}
      </ToolCardShell>
    )
  }

  if ((tool === 'claim_listing' || tool === 'claim_food') && !ok && (result?.error || toolResult.summary)) {
    const errText = result?.error || toolResult.summary
    return (
      <ToolCardShell kind="claimfail" language={language}>
        <div className="text-white">{errText}</div>
        {result?.next_step && (
          <div className={`${TOOL_CARD_TOKENS.claimfail.sub} text-[11px] mt-1.5`}>{result.next_step}</div>
        )}
      </ToolCardShell>
    )
  }

  if ((tool === 'claim_listing' || tool === 'claim_food') && ok) {
    // Only show the real listing photo (no category placeholder fallback)
    // so the thumbnail always matches the photo the donor attached.
    const photoUrl = typeof result.image_url === 'string' && /^https?:\/\//i.test(result.image_url)
      ? result.image_url
      : null
    return (
      <ToolCardShell kind="claim" language={language}>
        <div className="flex gap-2.5">
          {photoUrl && (
            <img
              src={photoUrl}
              alt={result.title || ''}
              loading="lazy"
              className="h-14 w-14 flex-shrink-0 rounded-md object-cover border border-emerald-500/15 bg-slate-800"
              onError={(e) => { e.currentTarget.style.display = 'none' }}
            />
          )}
          <div className="min-w-0 flex-1">
            {result.title && (
              <div className="text-white">
                {result.quantity ? <span className="font-medium">{result.quantity} {result.unit || ''} </span> : null}
                {result.quantity ? (language === 'es' ? 'de ' : 'of ') : null}
                <span className="font-semibold">{result.title}</span>
                {result.category && <span className="text-emerald-50"> · {result.category}</span>}
              </div>
            )}
            {result.pickup_location && (
              <div className="text-white text-[11px] mt-1 flex items-start gap-1">
                <i className="fas fa-location-dot text-[10px] mt-[2px] opacity-70" aria-hidden="true" />
                <span className="break-words">{result.pickup_location}</span>
              </div>
            )}
            {result.community_name && (
              <div className="text-white text-[11px] mt-0.5 flex items-center gap-1">
                <i className="fas fa-people-group text-[10px] opacity-70" aria-hidden="true" />
                <span>{result.community_name}</span>
              </div>
            )}
            {(result.summary || result.message) && (
              <div className="text-white text-[12px] mt-1">{result.summary || result.message}</div>
            )}
          </div>
        </div>
      </ToolCardShell>
    )
  }

  if (tool === 'create_reminder' && (result?.success || result?.created)) {
    return (
      <ToolCardShell kind="reminder" language={language}>
        <span className="text-white">{result.summary || (language === 'es' ? 'Te avisaré.' : "I'll ping you.")}</span>
      </ToolCardShell>
    )
  }

  if ((tool === 'post_food_listings' || tool === 'bulk_post_food_listings' || tool === 'bulk_import_listings') && ok) {
    const posted = Array.isArray(result.posted) ? result.posted : (Array.isArray(result.listings) ? result.listings : [])
    const failed = Array.isArray(result.failed) ? result.failed : []
    const count = result.count_posted ?? posted.length
    return (
      <ToolCardShell
        kind="post"
        language={language}
        titleOverride={
          language === 'es'
            ? `Publicado · ${count} listado${count === 1 ? '' : 's'}`
            : `Posted · ${count} listing${count === 1 ? '' : 's'}`
        }
      >
        {posted.length > 0 && (
          <ul className="space-y-1.5 mb-2">
            {posted.slice(0, 12).map((row, i) => (
              <li key={row.listing_id || row.id || i} className="text-white text-[12px]">
                <span className="font-semibold">{row.title || row.listing_id || `Item ${i + 1}`}</span>
                {row.quantity != null && (
                  <span className="text-fuchsia-50"> · {row.quantity} {row.unit || ''}</span>
                )}
              </li>
            ))}
          </ul>
        )}
        {failed.length > 0 && (
          <ul className="space-y-1 text-red-100 text-[11px] mb-1">
            {failed.slice(0, 8).map((f, i) => (
              <li key={f.listing_id || i}>
                {f.title || f.listing_id || `#${i + 1}`}: {f.error || 'failed'}
              </li>
            ))}
          </ul>
        )}
        {(result.summary || result.message) && (
          <div className="text-white text-[12px] mt-1">{result.summary || result.message}</div>
        )}
      </ToolCardShell>
    )
  }

  if ((tool === 'create_food_listing' || tool === 'post_food_listing') && !ok && (result?.error || toolResult.summary)) {
    const errText = result?.error || toolResult.summary
    return (
      <ToolCardShell kind="claimfail" language={language} titleOverride={language === 'es' ? 'No se pudo publicar' : 'Could not post'}>
        <div className="text-white">{errText}</div>
        {result?.next_step && (
          <div className={`${TOOL_CARD_TOKENS.claimfail.sub} text-[11px] mt-1.5`}>{result.next_step}</div>
        )}
      </ToolCardShell>
    )
  }

  if ((tool === 'create_food_listing' || tool === 'post_food_listing') && ok) {
    return (
      <ToolCardShell kind="post" language={language}>
        {result.title && (
          <div className="text-white">
            <span className="font-semibold">{result.title}</span>
            {result.quantity != null && <span className="text-white"> · {result.quantity} {result.unit || ''}</span>}
            {result.category && <span className="text-white"> · {result.category}</span>}
          </div>
        )}
        {result.address && (
          <div className="text-white text-[11px] mt-1 flex items-start gap-1">
            <i className="fas fa-map-marker-alt mt-[2px] text-[10px] opacity-70" aria-hidden="true" />
            <span className="break-words">{result.address}</span>
          </div>
        )}
        {result.community_name && (
          <div className="text-white text-[11px] mt-0.5 flex items-center gap-1">
            <i className="fas fa-people-group text-[10px] opacity-70" aria-hidden="true" />
            <span>{result.community_name}</span>
          </div>
        )}
        {result.on_map === false && (
          <div className="text-amber-50 text-[11px] mt-1 flex items-center gap-1">
            <i className="fas fa-triangle-exclamation text-[10px]" aria-hidden="true" />
            <span>{language === 'es' ? 'Sin coordenadas — no aparecerá en el mapa' : 'No coordinates — listing will not appear on the map'}</span>
          </div>
        )}
        {(result.summary || result.message) && (
          <div className="text-white mt-1">{result.summary || result.message}</div>
        )}
      </ToolCardShell>
    )
  }

  if ((tool === 'update_food_listing' || tool === 'update_listing' || tool === 'edit_listing') && ok) {
    const item = result.listing || result
    const fmtDate = (iso) => {
      if (!iso) return null
      try {
        const [y, m, d] = String(iso).slice(0, 10).split('-').map(Number)
        return new Date(y, m - 1, d).toLocaleDateString(undefined, { month: 'short', day: 'numeric' })
      } catch {
        return iso
      }
    }
    const qtyLabel = item.quantity != null
      ? `${item.quantity}${item.unit ? ` ${item.unit}` : ''}`
      : null
    const expiryLabel = fmtDate(item.expiry_date || item.pickup_by)
    const address = item.address || item.full_address || item.location || null
    const photoUrl = typeof item.image_url === 'string' && /^https?:\/\//i.test(item.image_url)
      ? item.image_url
      : null
    return (
      <ToolCardShell kind="updated" language={language}>
        <div className="flex gap-2.5">
          {photoUrl && (
            <img
              src={photoUrl}
              alt={item.title || ''}
              loading="lazy"
              className="h-14 w-14 flex-shrink-0 rounded-md object-cover border border-violet-500/15 bg-slate-800"
              onError={(e) => { e.currentTarget.style.display = 'none' }}
            />
          )}
          <div className="min-w-0 flex-1">
            {item.title && (
              <div className="text-white font-semibold">{item.title}</div>
            )}
            <div className={`${TOOL_CARD_TOKENS.updated.sub} text-[11px] mt-0.5 space-y-0.5`}>
              {qtyLabel && (
                <div>{language === 'es' ? 'Cantidad: ' : 'Quantity: '}{qtyLabel}</div>
              )}
              {expiryLabel && (
                <div>{language === 'es' ? 'Vence: ' : 'Expires: '}{expiryLabel}</div>
              )}
              {item.community_name && (
                <div className="flex items-center gap-1">
                  <i className="fas fa-people-group text-[10px] opacity-70" aria-hidden="true" />
                  <span>{item.community_name}</span>
                </div>
              )}
              {address && (
                <div className="flex items-start gap-1">
                  <i className="fas fa-map-marker-alt mt-[2px] text-[10px] opacity-70" aria-hidden="true" />
                  <span className="break-words">{address}</span>
                </div>
              )}
              {item.description && (
                <div className="italic opacity-90">{item.description}</div>
              )}
            </div>
            {(result.summary || result.message) && (
              <div className="text-white text-[11px] mt-1">{result.summary || result.message}</div>
            )}
          </div>
        </div>
      </ToolCardShell>
    )
  }

  if ((tool === 'update_food_listing' || tool === 'update_listing' || tool === 'edit_listing') && !ok) {
    return (
      <ToolCardShell kind="claimfail" language={language} titleOverride={language === 'es' ? 'No se pudo actualizar' : 'Could not update'}>
        <div className="text-white">{result?.error || result?.message || result?.summary}</div>
      </ToolCardShell>
    )
  }

  if (tool === 'delete_listing' && ok) {
    const count = result.deleted_count || 1
    const titles = result.titles || (result.title ? [result.title] : [])
    return (
      <ToolCardShell kind="deleted" language={language}>
        <div className="text-white">
          {count > 1 ? (
            language === 'es'
              ? `Eliminados ${count} listados duplicados.`
              : `Removed ${count} duplicate listings.`
          ) : (
            <>
              {language === 'es' ? 'Eliminado: ' : 'Removed: '}
              <span className="font-semibold">{result.title || titles[0] || 'listing'}</span>
            </>
          )}
        </div>
        {(result.summary || result.message) && (
          <div className="text-white mt-1">{result.summary || result.message}</div>
        )}
      </ToolCardShell>
    )
  }

  if (tool === 'delete_listing' && !ok) {
    return (
      <ToolCardShell kind="error" language={language}>
        <div className="text-white font-medium">
          {language === 'es' ? 'No se pudo eliminar' : 'Could not delete listing'}
        </div>
        {(result.error || result.message || result.summary) && (
          <div className="text-white mt-1">{result.error || result.message || result.summary}</div>
        )}
      </ToolCardShell>
    )
  }

  if (tool === 'cancel_claim' && ok) {
    return (
      <ToolCardShell kind="cancel" language={language}>
        {result.title && (
          <div className="text-amber-100">
            {language === 'es' ? 'Liberado: ' : 'Released: '}
            <span className="font-semibold">{result.title}</span>
          </div>
        )}
        {result.summary && <div className="text-amber-50 mt-1">{result.summary}</div>}
      </ToolCardShell>
    )
  }

  if (tool === 'confirm_claim' && ok) {
    return (
      <ToolCardShell kind="pickup" language={language}>
        {result.title && (
          <div className="text-sky-100">
            {language === 'es' ? 'Completado: ' : 'Completed: '}
            <span className="font-semibold">{result.title}</span>
          </div>
        )}
        {result.summary && <div className="text-white mt-1">{result.summary}</div>}
      </ToolCardShell>
    )
  }

  // Generic fallback: any other tool that succeeded with a summary string.
  // Keeps users informed instead of silently swallowing the result for tools
  // we haven't designed a custom card for (e.g. update_user_profile,
  // attach_photos_to_listing, post_food_request, bulk_import_listings,
  // query_distribution_centers, get_user_dashboard, get_mapbox_route).
  // Skip pure UI-control tools: their effect is the navigation itself, so a
  // "Done" card would be redundant noise next to the assistant's reply.
  const SILENT_UI_TOOLS = new Set(['ui_action', 'navigate_ui', 'mark_notifications_read'])
  if (ok && !SILENT_UI_TOOLS.has(tool) && (result?.summary || result?.message)) {
    return (
      <ToolCardShell kind="generic" language={language} titleOverride={tool?.replace(/_/g, ' ') || (language === 'es' ? 'Acción' : 'Action')}>
        <div className="text-white text-[12px]">{result.summary || result.message}</div>
      </ToolCardShell>
    )
  }

  return null
}

// ─── Message bubble ────────────────────────────────────
/**
 * Human-readable copy for backend error_code values. Kept in-component (not
 * a separate file) so we can ship i18n improvements alongside the panel
 * without a cross-file diff. Returns { eyebrow, hint } where eyebrow goes
 * into the small chip and hint is one short explanatory sentence.
 */
function describeErrorCode(code, language = 'en') {
  const isEs = language === 'es'
  switch (code) {
    case 'timeout':
      return {
        eyebrow: isEs ? 'Tiempo agotado' : 'Timed out',
        hint: isEs ? 'La respuesta tardó demasiado.' : 'The response took too long.',
      }
    case 'rate_limit':
      return {
        eyebrow: isEs ? 'Límite de uso' : 'Rate limited',
        hint: isEs ? 'Demasiadas solicitudes. Espera unos segundos.' : 'Too many requests. Wait a few seconds.',
      }
    case 'model_unavailable':
      return {
        eyebrow: isEs ? 'IA no disponible' : 'AI unavailable',
        hint: isEs ? 'El modelo está temporalmente caído.' : 'The model is temporarily down.',
      }
    case 'circuit_open':
      return {
        eyebrow: isEs ? 'Recuperando' : 'Recovering',
        hint: isEs ? 'Estoy recuperándome de un problema.' : "I'm bouncing back from an issue.",
      }
    case 'auth':
      return {
        eyebrow: isEs ? 'Autenticación' : 'Auth error',
        hint: isEs ? 'Hay un problema con las credenciales del servicio.' : "There's an issue with service credentials.",
      }
    case 'invalid_input':
      return {
        eyebrow: isEs ? 'Entrada inválida' : 'Invalid request',
        hint: isEs ? 'No pude procesar esa entrada.' : "I couldn't process that input.",
      }
    default:
      return {
        eyebrow: isEs ? 'Error' : 'Error',
        hint: isEs ? 'Algo salió mal.' : 'Something went wrong.',
      }
  }
}

function ConfirmationBar({ language, pendingAction, onConfirm, onCancel, onEdit, disabled }) {
  const summary = pendingAction?.summary || ''
  const isEs = language === 'es'
  return (
    <div className="mt-2 p-3 rounded-xl bg-amber-50 border border-amber-200 ring-1 ring-amber-200/60">
      {summary && (
        <div className="text-amber-950 text-xs mb-2.5 leading-snug font-medium">
          {isEs ? 'Acción pendiente: ' : 'Pending: '}
          <span className="font-medium">{summary}</span>
        </div>
      )}
      <div className="flex flex-wrap gap-2">
        <button
          type="button"
          onClick={onConfirm}
          disabled={disabled}
          className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-full text-xs font-semibold bg-emerald-600 hover:bg-emerald-500 text-white disabled:opacity-40"
        >
          <i className="fas fa-check text-[10px]" aria-hidden="true" />
          {isEs ? 'Confirmar' : 'Confirm'}
        </button>
        <button
          type="button"
          onClick={onEdit}
          disabled={disabled}
          className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-full text-xs font-medium bg-white hover:bg-gray-50 text-gray-900 border border-gray-400 disabled:opacity-40"
        >
          <i className="fas fa-pen text-[10px]" aria-hidden="true" />
          {isEs ? 'Editar' : 'Edit'}
        </button>
        <button
          type="button"
          onClick={onCancel}
          disabled={disabled}
          className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-full text-xs font-medium bg-white hover:bg-gray-50 text-gray-800 border border-gray-400 disabled:opacity-40"
        >
          <i className="fas fa-xmark text-[10px]" aria-hidden="true" />
          {isEs ? 'Cancelar' : 'Cancel'}
        </button>
      </div>
    </div>
  )
}

function MessageBubble({
  msg,
  onFeedback,
  language,
  onSuggestionClick,
  onAttachPhoto,
  onConfirmAction,
  isLoading,
  currentUser,
  allowedCommunityIds = null,
  onRetry,
  onRegenerate,
  showRegenerate = false,
  showSuggestionChips = false,
}) {
  const [feedbackGiven, setFeedbackGiven] = useState(null)
  const [avatarBroken, setAvatarBroken] = useState(false)
  const [copied, setCopied] = useState(false)
  const isUser = msg.role === 'user'
  const suggestionItems = useMemo(() => {
    const raw = msg.suggestions || msg.suggestedActions || []
    const responseText = msg.message || msg.text || ''
    return resolveInputChips(raw, language, null, {
      allowLazy: false,
      responseText,
    })
  }, [msg.suggestions, msg.suggestedActions, msg.message, msg.text, language])
  const isVoiceMessage = msg.source === 'voice'

  const handleFeedback = (rating) => {
    setFeedbackGiven(rating)
    onFeedback?.(msg.id, rating)
  }

  const handleCopy = useCallback(() => {
    if (!msg.message) return
    try {
      const copy = navigator?.clipboard?.writeText?.bind(navigator.clipboard)
      if (copy) {
        copy(msg.message).then(
          () => {
            setCopied(true)
            setTimeout(() => setCopied(false), 1600)
          },
          () => { /* clipboard denied — silent */ },
        )
      }
    } catch {
      /* clipboard unavailable */
    }
  }, [msg.message])

  // Compute user initials for the avatar fallback
  const userInitials = useMemo(() => {
    const src = (currentUser?.name || currentUser?.email || '').trim()
    if (!src) return '🙋'
    const parts = src.split(/[\s@._-]+/).filter(Boolean)
    if (parts.length === 0) return src.charAt(0).toUpperCase()
    if (parts.length === 1) return parts[0].slice(0, 2).toUpperCase()
    return (parts[0].charAt(0) + parts[parts.length - 1].charAt(0)).toUpperCase()
  }, [currentUser?.name, currentUser?.email])

  const userAvatarUrl = !avatarBroken ? currentUser?.avatar_url : null

  return (
    <div className={`flex ${isUser ? 'justify-end' : 'justify-start'} mb-3`}>
      <div className={`max-w-[85%] flex items-start gap-2 ${isUser ? 'flex-row-reverse' : ''}`}>
        {/* Nouri avatar (assistant) */}
        {!isUser && (
          <div className="flex-shrink-0 w-7 h-7 rounded-full bg-gradient-to-br from-[#2CABE3] to-emerald-500 flex items-center justify-center mt-1 shadow-sm shadow-[#2CABE3]/25">
            <svg viewBox="0 0 100 100" className="w-5 h-5">
              <circle cx="50" cy="52" r="36" fill="#f0f4f8" />
              <rect x="26" y="38" rx="12" ry="12" width="48" height="24" fill="#1e293b" opacity="0.85" />
              <path d="M35 53 Q38 46 41 53" stroke="#67e8f9" strokeWidth="4" strokeLinecap="round" fill="none" />
              <path d="M59 53 Q62 46 65 53" stroke="#67e8f9" strokeWidth="4" strokeLinecap="round" fill="none" />
            </svg>
          </div>
        )}

        {/* User avatar bubble */}
        {isUser && (
          <div
            className="flex-shrink-0 w-7 h-7 rounded-full overflow-hidden mt-1 shadow-sm shadow-[#2CABE3]/20 ring-1 ring-[#2CABE3]/30 bg-gradient-to-br from-[#2CABE3] to-emerald-500 flex items-center justify-center"
            title={currentUser?.name || currentUser?.email || 'You'}
            aria-label={`Message from ${currentUser?.name || 'you'}`}
          >
            {userAvatarUrl ? (
              <img
                src={userAvatarUrl}
                alt={currentUser?.name || 'You'}
                className="w-full h-full object-cover"
                onError={() => setAvatarBroken(true)}
              />
            ) : (
              <span className="text-[10px] font-semibold text-white tracking-wide">{userInitials}</span>
            )}
          </div>
        )}

        <div className="group/msg min-w-0 flex-1">
          <div
            className={`px-4 py-2.5 rounded-2xl text-[13px] leading-relaxed ${
              isUser
                ? 'bg-gradient-to-br from-[#2CABE3] to-emerald-500 text-white rounded-br-md shadow-md shadow-[#2CABE3]/20 ring-1 ring-[#2CABE3]/20'
                : msg.isError
                  ? 'bg-red-50 text-red-800 border border-red-200 rounded-bl-md backdrop-blur-sm'
                  : 'bg-white text-gray-900 rounded-bl-md border border-[#2CABE3]/15 shadow-sm'
            }`}
          >
            {/* Inline photo message: show thumbnail instead of raw URL */}
            {/^image:\s*https?:\/\//i.test(msg.message) ? (
              <div className="flex items-center gap-2">
                <img
                  src={msg.message.replace(/^image:\s*/i, '')}
                  alt="uploaded"
                  className="max-h-32 max-w-[200px] rounded-lg object-cover ring-1 ring-white/20"
                  onError={(e) => { e.currentTarget.style.display = 'none' }}
                />
                <span className="text-[11px] opacity-70">📷</span>
              </div>
            ) : (
              // Defensive: if the model emits markdown image syntax
              // (`![alt](url)`) — typically a hallucinated photo URL — strip
              // it before rendering. Real listing photos are shown in the
              // search tool card from `item.image_url`, never in prose.
              <p className="whitespace-pre-wrap">
                {String(msg.message || '').replace(/!\[[^\]]*\]\([^)]*\)/g, '').trim()}
              </p>
            )}

            {/* Typed error metadata: small chip + retry button. Only renders
                when the bubble carries an errorCode from the backend. The
                Retry button re-sends the original user text (stashed on the
                error bubble as retryText) and removes this bubble. */}
            {msg.isError && msg.errorCode && (
              <div className="mt-2.5 pt-2.5 border-t border-red-200 flex flex-wrap items-center gap-2">
                <span className="inline-flex items-center gap-1.5 px-2 py-0.5 rounded-full bg-red-100 text-red-800 text-[10px] font-semibold tracking-wide ring-1 ring-red-200">
                  <i className="fas fa-circle-exclamation text-[9px]" aria-hidden="true" />
                  {describeErrorCode(msg.errorCode, language).eyebrow}
                </span>
                {msg.errorRetryable && onRetry && msg.retryText && (
                  <button
                    type="button"
                    onClick={() => onRetry(msg.id)}
                    disabled={isLoading}
                    className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-md bg-red-600 hover:bg-red-700 text-white text-[11px] font-semibold transition-colors disabled:opacity-40 disabled:cursor-not-allowed focus:outline-none focus-visible:ring-2 focus-visible:ring-red-300"
                    aria-label={language === 'es' ? 'Reintentar mensaje' : 'Retry message'}
                  >
                    <i className={`fas ${isLoading ? 'fa-spinner fa-spin' : 'fa-rotate-right'} text-[10px]`} aria-hidden="true" />
                    {language === 'es' ? 'Reintentar' : 'Retry'}
                    {msg.errorRetryAfter ? (
                      <span className="text-white/80 font-normal">· {msg.errorRetryAfter}s</span>
                    ) : null}
                  </button>
                )}
                {msg.requestId && (
                  <span
                    className="ml-auto text-[9px] font-mono text-red-400 tracking-wider truncate max-w-[120px]"
                    title={`Request ID: ${msg.requestId}`}
                  >
                    {msg.requestId.slice(0, 8)}
                  </span>
                )}
              </div>
            )}
          </div>

          {/* Confirmation bar for destructive actions (post, delete, etc.) */}
          {!isUser && msg.requiresConfirmation && showSuggestionChips && onConfirmAction && (
            <ConfirmationBar
              language={language}
              pendingAction={msg.pendingAction}
              disabled={isLoading}
              onConfirm={() => onConfirmAction(true)}
              onCancel={() => onConfirmAction(false)}
              onEdit={() => onSuggestionClick?.(language === 'es' ? 'Espera, edítalo' : 'Wait, edit it')}
            />
          )}

          {/* Tool result cards */}
          {msg.toolResults?.map((tr, i) => (
            <ToolResultCard
              key={i}
              toolResult={tr}
              language={language}
              onSuggestionClick={onSuggestionClick}
              allowedCommunityIds={allowedCommunityIds}
            />
          ))}

          {/* Suggested actions — only on the latest assistant turn so stale
              chips from earlier questions don't linger in the scrollback. */}
          {showSuggestionChips && suggestionItems.length > 0 && !isUser && (
            <div className={`flex flex-wrap gap-1 mt-2 ${suggestionItems.length > 4 ? 'max-h-36 overflow-y-auto pr-1' : ''}`}>
              {suggestionItems.map((action, i) => (
                <SuggestedActionButton
                  key={i}
                  action={action}
                  onSuggestionClick={onSuggestionClick}
                  onAttachPhoto={onAttachPhoto}
                  disabled={isLoading}
                  compact={suggestionItems.length > 4}
                />
              ))}
            </div>
          )}

          {/* Hover-revealed action row for assistant replies */}
          {!isUser && !msg.isError && msg.id !== 'welcome' && (
            <div
              className="flex items-center gap-1 mt-1.5 opacity-80 md:opacity-70 md:group-hover/msg:opacity-100 transition-opacity"
              role="toolbar"
              aria-label={language === 'es' ? 'Acciones del mensaje' : 'Message actions'}
            >
              <VoiceOutput text={msg.message} language={language} />
              <button
                type="button"
                onClick={handleCopy}
                className="inline-flex items-center justify-center w-6 h-6 rounded-md text-gray-500 hover:text-[#2CABE3] hover:bg-[#2CABE3]/10 transition-colors"
                title={copied ? (language === 'es' ? 'Copiado' : 'Copied') : (language === 'es' ? 'Copiar' : 'Copy')}
                aria-label={language === 'es' ? 'Copiar mensaje' : 'Copy message'}
              >
                <i className={`fas ${copied ? 'fa-check text-[#2CABE3]' : 'fa-copy'} text-[11px]`} aria-hidden="true" />
              </button>
              {!feedbackGiven && (
                <>
                  <button
                    type="button"
                    onClick={() => handleFeedback('helpful')}
                    className="inline-flex items-center justify-center w-6 h-6 rounded-md text-gray-500 hover:text-emerald-600 hover:bg-emerald-50 transition-colors"
                    title={language === 'es' ? 'Útil' : 'Helpful'}
                    aria-label={language === 'es' ? 'Marcar como útil' : 'Mark as helpful'}
                  >
                    <i className="fas fa-thumbs-up text-[11px]" aria-hidden="true" />
                  </button>
                  <button
                    type="button"
                    onClick={() => handleFeedback('not_helpful')}
                    className="inline-flex items-center justify-center w-6 h-6 rounded-md text-gray-500 hover:text-rose-600 hover:bg-rose-50 transition-colors"
                    title={language === 'es' ? 'No útil' : 'Not helpful'}
                    aria-label={language === 'es' ? 'Marcar como no útil' : 'Mark as not helpful'}
                  >
                    <i className="fas fa-thumbs-down text-[11px]" aria-hidden="true" />
                  </button>
                </>
              )}
              {feedbackGiven && (
                <span className="text-[10px] text-[#2299c7] px-1.5 py-0.5 rounded-md bg-[#2CABE3]/10 border border-[#2CABE3]/20">
                  {feedbackGiven === 'helpful'
                    ? (language === 'es' ? 'Gracias 👍' : 'Thanks 👍')
                    : (language === 'es' ? 'Anotado 👎' : 'Noted 👎')}
                </span>
              )}
              {/* Regenerate — only on the last assistant message. Reuses the
                  previous user turn to ask the model for a fresh answer. */}
              {showRegenerate && onRegenerate && (
                <button
                  type="button"
                  onClick={onRegenerate}
                  disabled={isLoading}
                  className="ml-1 inline-flex items-center gap-1 px-1.5 h-6 rounded-md text-gray-500 hover:text-[#2CABE3] hover:bg-[#2CABE3]/10 transition-colors disabled:opacity-40 disabled:cursor-not-allowed text-[10px] font-medium"
                  title={language === 'es' ? 'Regenerar respuesta' : 'Regenerate response'}
                  aria-label={language === 'es' ? 'Regenerar respuesta' : 'Regenerate response'}
                >
                  <i className={`fas ${isLoading ? 'fa-spinner fa-spin' : 'fa-arrows-rotate'} text-[10px]`} aria-hidden="true" />
                  <span className="hidden sm:inline">{language === 'es' ? 'Regenerar' : 'Regenerate'}</span>
                </button>
              )}
            </div>
          )}

          {/* Timestamp */}
          <div className={`text-[10px] mt-1 flex items-center gap-1 ${isUser ? 'justify-end text-white/75' : 'text-gray-500'}`}>
            {isVoiceMessage && (
              <span className="px-1.5 py-0.5 rounded-full border border-white/30 bg-white/15 text-white/90 text-[9px] uppercase tracking-wide inline-flex items-center gap-1">
                <i className="fas fa-microphone text-[8px]" aria-hidden="true" />
                {language === 'es' ? 'Voz' : 'Voice'}
              </span>
            )}
            <span>{new Date(msg.timestamp).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}</span>
          </div>
        </div>
      </div>
    </div>
  )
}

// ─── Suggested action button ───────────────────────────
function SuggestedActionButton({ action, onSuggestionClick, onAttachPhoto, disabled = false, compact = false }) {
  const { executeUIAction } = useUIControl()

  const asObject = action && typeof action === 'object'
  const label = asObject
    ? action.label || action.message || action.text || ''
    : String(action || '')
  const actionType = asObject
    ? (action.action || (action.href ? 'navigate' : 'send'))
    : 'send'
  const sendText = asObject
    ? action.message || action.text || action.query || action.prompt || action.label || ''
    : String(action || '')

  const handleClick = () => {
    if (disabled) return

    const isOpenForm = /^(open the form|abrir el formulario)$/i.test(String(sendText || label || '').trim())
    const isAttachPhoto = actionType === 'attach_photo' || /^(attach a photo|adjuntar foto)$/i.test(String(label || sendText || '').trim())
    if (isAttachPhoto && onAttachPhoto) {
      onAttachPhoto()
      return
    }

    if (actionType === 'navigate' && asObject && (action.target || action.href || action.path)) {
      const target = action.target || action.href || action.path
      const path = action.path || (typeof target === 'string' && target.startsWith('/') ? target : undefined)
      executeUIAction({
        ok: true,
        action: 'navigate',
        path: path || (isOpenForm ? '/share' : undefined),
        target: typeof target === 'string' && !String(target).startsWith('/') ? target : undefined,
      })
      // Still send the chat message so Nouri enters guided mode.
      if (sendText && onSuggestionClick) {
        onSuggestionClick(sendText)
      }
      return
    }

    if (sendText && onSuggestionClick) {
      onSuggestionClick(sendText)
    }
  }

  if (!label) return null

  const styleClass = actionType === 'navigate'
    ? 'bg-blue-50 text-blue-800 hover:bg-blue-100 border-blue-300 font-medium'
    : 'bg-[#2CABE3]/15 text-[#1a7a9e] hover:bg-[#2CABE3]/25 border-[#2CABE3]/30 font-medium'

  return (
    <button
      onClick={handleClick}
      disabled={disabled}
      className={`${compact ? 'text-[10px] px-2 py-0.5' : 'text-xs px-2.5 py-1'} rounded-full transition-colors border ${styleClass} disabled:opacity-60 disabled:cursor-not-allowed`}
    >
      {label}
    </button>
  )
}

// ─── Bulk upload preview (photo + CSV → bulk listings) ───────
function BulkUploadPreview({
  pending,
  busy,
  language,
  preferredCommunityId,
  preferredLocation,
  onCancel,
  onConfirm,
  onUpdateRow,
  onUpdateRows,
  onRemoveRow,
}) {
  const isEs = language === 'es'
  const kindLabel = pending.kind === 'photo'
    ? (isEs ? 'Borrador desde foto' : 'Draft from photo')
    : (isEs ? 'Importación CSV' : 'CSV import')
  const icon = pending.kind === 'photo' ? 'fa-camera' : 'fa-file-csv'
  const tint = pending.kind === 'photo' ? 'fuchsia' : 'emerald'
  const ringClass = pending.kind === 'photo'
    ? 'border-fuchsia-500/40 shadow-fuchsia-500/10'
    : 'border-emerald-500/40 shadow-emerald-500/10'
  const headerClass = pending.kind === 'photo' ? 'text-fuchsia-200' : 'text-emerald-200'

  // Lazy-load active communities once so the preview can offer a selector.
  const [communities, setCommunities] = useState([])
  const [communitiesError, setCommunitiesError] = useState(null)
  const [communitiesLoading, setCommunitiesLoading] = useState(true)
  // CSV: select rows and apply shared values (location, community, …).
  const [selectedRowIndexes, setSelectedRowIndexes] = useState(() => new Set())
  const [bulkLocation, setBulkLocation] = useState(() => String(preferredLocation || '').trim())
  const [bulkCommunityId, setBulkCommunityId] = useState(() =>
    preferredCommunityId != null && preferredCommunityId !== ''
      ? String(preferredCommunityId)
      : ''
  )
  const [bulkCategory, setBulkCategory] = useState('')
  const [bulkExpiry, setBulkExpiry] = useState('')
  // When true, Apply only fills rows that are still missing that field.
  const [fillEmptyOnly, setFillEmptyOnly] = useState(true)
  const loadCommunities = useCallback(async () => {
    setCommunitiesLoading(true)
    setCommunitiesError(null)
    try {
      const { data, error } = await supabase
        .from('communities')
        .select('id, name')
        .eq('is_active', true)
        .order('name', { ascending: true })
      if (error) throw error
      setCommunities(data || [])
    } catch (err) {
      setCommunities([])
      setCommunitiesError(err?.message || (isEs ? 'No se pudieron cargar las comunidades' : 'Could not load communities'))
    } finally {
      setCommunitiesLoading(false)
    }
  }, [isEs])
  useEffect(() => {
    loadCommunities()
  }, [loadCommunities])

  // Default CSV selection to all rows when the batch arrives / row count changes.
  useEffect(() => {
    if (pending?.kind !== 'csv') return
    const n = pending?.rows?.length || 0
    setSelectedRowIndexes(new Set(Array.from({ length: n }, (_, i) => i)))
    setBulkLocation((prev) => {
      if (String(prev || '').trim()) return prev
      return String(preferredLocation || '').trim()
    })
    setBulkCommunityId((prev) => {
      if (String(prev || '').trim()) return prev
      return preferredCommunityId != null && preferredCommunityId !== ''
        ? String(preferredCommunityId)
        : ''
    })
  }, [pending?.kind, pending?.rows?.length, preferredLocation, preferredCommunityId])

  // Resolve per-row community from CSV (name → id) and only prefill the
  // importer's community when a row has neither id nor name. Never overwrite
  // a CSV / picker community with the donor profile default (warehouse leak).
  useEffect(() => {
    if (!communities.length) return
    const currentRows = pending?.rows || []
    if (!currentRows.length) return
    const preferred = preferredCommunityId
      ? communities.find((c) => String(c.id) === String(preferredCommunityId))
      : null
    currentRows.forEach((row, idx) => {
      if (row?.community_id) {
        if (!row.community_name) {
          const byId = communities.find((c) => String(c.id) === String(row.community_id))
          if (byId) onUpdateRow(idx, { community_name: byId.name })
        }
        return
      }
      if (row?.community_name) {
        const match = matchCommunityByName(row.community_name, communities)
        if (match) {
          onUpdateRow(idx, {
            community_id: String(match.id),
            community_name: match.name,
          })
        }
        return
      }
      if (preferred) {
        onUpdateRow(idx, {
          community_id: String(preferred.id),
          community_name: preferred.name,
        })
      }
    })
    // Intentionally omit onUpdateRow / pending.rows identity to avoid loops —
    // re-run when communities arrive or row count / kind changes.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [communities, preferredCommunityId, pending?.rows?.length, pending?.kind])

  // ALL hooks must be declared before any early return (Rules of Hooks).
  const filledLog = Array.isArray(pending.filledLog) ? pending.filledLog : []
  const filledByIndex = useMemo(() => {
    const m = new Map()
    for (const f of filledLog) {
      if (f && typeof f.index === 'number') m.set(f.index, f.fields || [])
    }
    return m
  }, [filledLog])

  const rows = pending?.rows || []
  const missingCommunity = rows.some((r) => !r?.community_id && !String(r?.community_name || '').trim())
  const isCsv = pending.kind === 'csv'
  const allSelected = isCsv && rows.length > 0 && selectedRowIndexes.size === rows.length
  const someSelected = isCsv && selectedRowIndexes.size > 0 && selectedRowIndexes.size < rows.length

  const toggleSelectAll = () => {
    if (allSelected) {
      setSelectedRowIndexes(new Set())
    } else {
      setSelectedRowIndexes(new Set(rows.map((_, i) => i)))
    }
  }

  const toggleRowSelected = (idx) => {
    setSelectedRowIndexes((prev) => {
      const next = new Set(prev)
      if (next.has(idx)) next.delete(idx)
      else next.add(idx)
      return next
    })
  }

  const applyPatchToSelected = (patch, isEmptyRow) => {
    if (!patch || typeof onUpdateRows !== 'function' || !selectedRowIndexes.size) return
    const indexes = Array.from(selectedRowIndexes).filter((idx) => {
      if (!fillEmptyOnly) return true
      if (typeof isEmptyRow !== 'function') return true
      return isEmptyRow(rows[idx])
    })
    if (!indexes.length) return
    onUpdateRows(indexes, patch)
  }

  const applyLocationToSelected = () => {
    const location = String(bulkLocation || '').trim()
    if (!location) return
    applyPatchToSelected(
      { location },
      (r) => !String(r?.location || '').trim(),
    )
  }

  const applyCommunityToSelected = () => {
    const id = String(bulkCommunityId || '').trim()
    if (!id) return
    const match = communities.find((c) => String(c.id) === id)
    if (!match) return
    applyPatchToSelected(
      {
        community_id: String(match.id),
        community_name: match.name,
      },
      (r) => !r?.community_id && !String(r?.community_name || '').trim(),
    )
  }

  const applyCategoryToSelected = () => {
    const category = String(bulkCategory || '').trim()
    if (!category) return
    applyPatchToSelected(
      { category },
      (r) => !String(r?.category || '').trim() || String(r?.category).toLowerCase() === 'other',
    )
  }

  const applyExpiryToSelected = () => {
    const expiry = String(bulkExpiry || '').trim()
    if (!expiry) return
    applyPatchToSelected(
      { expiry_date: expiry },
      (r) => !String(r?.expiry_date || '').trim(),
    )
  }

  const applyAllMissingToSelected = () => {
    // One-click: push every filled bulk field onto empty cells of selected rows.
    if (String(bulkLocation || '').trim()) applyLocationToSelected()
    if (String(bulkCommunityId || '').trim()) applyCommunityToSelected()
    if (String(bulkCategory || '').trim()) applyCategoryToSelected()
    if (String(bulkExpiry || '').trim()) applyExpiryToSelected()
  }

  if (pending.error) {
    const allErrors = [pending.error, ...(pending.parseErrors || []).slice(1)].filter(Boolean)
    return (
      <div className={`mx-3 mb-2 rounded-xl border ${ringClass} bg-slate-900/80 backdrop-blur-sm p-3 shadow-sm`}>
        <div className="flex items-start gap-3">
          <i className={`fas ${icon} ${headerClass} mt-0.5`} aria-hidden="true" />
          <div className="flex-1 min-w-0">
            <div className="text-xs font-semibold text-slate-100">{kindLabel}</div>
            <div className="text-xs text-slate-300 truncate mb-1">{pending.filename}</div>
            {allErrors.map((e, i) => (
              <div key={i} className="text-sm text-rose-300">{e}</div>
            ))}
          </div>
          <button
            type="button"
            onClick={onCancel}
            className="text-xs text-slate-300 hover:text-white px-2 py-1 rounded-md hover:bg-slate-800/60 flex-shrink-0"
          >
            {isEs ? 'Cerrar' : 'Dismiss'}
          </button>
        </div>
        {pending.kind === 'csv' && (
          <button
            type="button"
            onClick={downloadCsvTemplate}
            className="mt-2 w-full flex items-center justify-center gap-1.5 text-xs px-3 py-1.5 rounded-lg bg-emerald-500/25 text-emerald-50 hover:bg-emerald-500/35 border border-emerald-400/40 transition-colors"
          >
            <i className="fas fa-download text-[10px]" aria-hidden="true" />
            {isEs ? 'Descargar plantilla CSV' : 'Download CSV template'}
          </button>
        )}
      </div>
    )
  }

  if (pending.analyzing || pending.enriching) {
    return (
      <div className={`mx-3 mb-2 rounded-xl border ${ringClass} bg-slate-900/80 backdrop-blur-sm p-3 flex items-center gap-3 shadow-sm`}>
        <i className={`fas ${icon} ${headerClass}`} aria-hidden="true" />
        <div className="flex-1 min-w-0">
          <div className="text-xs font-semibold text-slate-100">{kindLabel}</div>
          <div className="text-xs text-slate-300 truncate">{pending.filename}</div>
          <div className="mt-1 text-sm text-slate-200">
            <i className="fas fa-wand-magic-sparkles mr-1.5 text-cyan-300 animate-pulse" aria-hidden="true" />
            {pending.enriching
              ? (isEs ? 'Rellenando huecos con IA…' : 'Filling gaps with AI…')
              : (isEs ? 'Analizando con IA...' : 'Analyzing with AI…')}
          </div>
        </div>
      </div>
    )
  }

  if (rows.length === 0) return null
  // CSV: show all rows (scrollable) so select-all + one location works.
  // Photo drafts stay capped at 5 for compactness.
  const previewRows = isCsv ? rows : rows.slice(0, 5)
  const extra = isCsv ? 0 : rows.length - previewRows.length
  const totalFilled = filledLog.length
  const selectAllRef = (el) => {
    if (el) el.indeterminate = someSelected
  }

  return (
    <div className={`mx-3 mb-2 rounded-xl border ${ringClass} bg-slate-900/80 backdrop-blur-sm p-3 shadow-sm`}>
      <div className="flex items-center gap-2 mb-2">
        <i className={`fas ${icon} ${headerClass}`} aria-hidden="true" />
        <div className="text-xs font-semibold text-slate-200">
          {kindLabel} · {rows.length} {rows.length === 1 ? (isEs ? 'fila' : 'row') : (isEs ? 'filas' : 'rows')}
        </div>
        {typeof pending.confidence === 'number' && pending.kind === 'photo' && (
          <span className="text-[10px] text-slate-300 ml-auto">
            {isEs ? 'Confianza' : 'Confidence'}: {Math.round(pending.confidence * 100)}%
          </span>
        )}
      </div>
      <div className="text-[11px] text-slate-300 mb-2 truncate" title={pending.filename}>{pending.filename}</div>

      {pending.enriched && (
        <div className="mb-2 flex items-start gap-1.5 rounded-lg border border-cyan-500/30 bg-cyan-500/15 px-2 py-1.5 text-[11px] text-cyan-50">
          <i className="fas fa-wand-magic-sparkles mt-0.5" aria-hidden="true" />
          <span className="flex-1">
            {pending.enrichSummary
              || (totalFilled
                ? (isEs
                    ? `IA rellenó huecos en ${totalFilled} fila(s). Revisa y confirma.`
                    : `AI filled gaps on ${totalFilled} row(s). Review and confirm.`)
                : (isEs
                    ? 'IA revisó tus filas — no había huecos que rellenar.'
                    : 'AI reviewed your rows — no gaps to fill.'))}
          </span>
        </div>
      )}

      {isCsv && (
        <div className="mb-2 rounded-lg border border-emerald-500/25 bg-emerald-500/5 p-2 space-y-1.5">
          <div className="flex flex-wrap items-center gap-x-3 gap-y-1.5">
            <label className="flex items-center gap-2 text-[11px] text-slate-200 cursor-pointer select-none">
              <input
                ref={selectAllRef}
                type="checkbox"
                checked={allSelected}
                onChange={toggleSelectAll}
                disabled={busy || rows.length === 0}
                className="rounded border-slate-600 bg-slate-900 text-emerald-500 focus:ring-emerald-500/40"
                aria-label={isEs ? 'Seleccionar todas las filas' : 'Select all rows'}
              />
              <span className="font-medium">
                {isEs ? 'Seleccionar todas' : 'Select all'}
              </span>
              <span className="text-slate-300">
                ({selectedRowIndexes.size}/{rows.length})
              </span>
            </label>
            <label className="flex items-center gap-1.5 text-[11px] text-slate-200 cursor-pointer select-none">
              <input
                type="checkbox"
                checked={fillEmptyOnly}
                onChange={(e) => setFillEmptyOnly(e.target.checked)}
                disabled={busy}
                className="rounded border-slate-600 bg-slate-900 text-emerald-500 focus:ring-emerald-500/40"
              />
              <span>
                {isEs ? 'Solo rellenar vacíos' : 'Only fill empty'}
              </span>
            </label>
          </div>

          <div className="flex flex-col sm:flex-row gap-1.5 items-stretch sm:items-center">
            <label className="flex-1 flex items-center gap-1.5 min-w-0 text-[11px]">
              <i className="fas fa-people-group text-emerald-300 flex-shrink-0" aria-hidden="true" />
              <select
                value={bulkCommunityId}
                onChange={(e) => setBulkCommunityId(e.target.value)}
                disabled={busy || communitiesLoading || communities.length === 0}
                className="flex-1 min-w-0 bg-slate-900 border border-slate-600 rounded px-2 py-1 text-slate-100 outline-none focus:border-emerald-500/50"
                aria-label={isEs ? 'Comunidad compartida' : 'Shared community'}
              >
                <option value="">
                  {communitiesLoading
                    ? (isEs ? 'Cargando comunidades…' : 'Loading communities…')
                    : (isEs ? 'Una comunidad para las seleccionadas…' : 'One community for selected rows…')}
                </option>
                {communities.map((c) => (
                  <option key={c.id} value={c.id}>{c.name}</option>
                ))}
              </select>
            </label>
            <button
              type="button"
              onClick={applyCommunityToSelected}
              disabled={busy || !String(bulkCommunityId || '').trim() || selectedRowIndexes.size === 0}
              className="flex-shrink-0 text-[11px] px-2.5 py-1 rounded-md bg-emerald-500/35 text-emerald-50 border border-emerald-400/50 hover:bg-emerald-500/45 disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
            >
              {isEs
                ? `Aplicar comunidad (${selectedRowIndexes.size})`
                : `Apply community (${selectedRowIndexes.size})`}
            </button>
          </div>

          <div className="flex flex-col sm:flex-row gap-1.5 items-stretch sm:items-center">
            <label className="flex-1 flex items-center gap-1.5 min-w-0 text-[11px]">
              <i className="fas fa-location-dot text-emerald-300 flex-shrink-0" aria-hidden="true" />
              <input
                type="text"
                value={bulkLocation}
                onChange={(e) => setBulkLocation(e.target.value)}
                disabled={busy}
                placeholder={isEs ? 'Una dirección de recogida para las seleccionadas…' : 'One pickup address for selected rows…'}
                className="flex-1 min-w-0 bg-slate-900 border border-slate-600 rounded px-2 py-1 text-slate-100 placeholder:text-slate-400 outline-none focus:border-emerald-500/50"
                aria-label={isEs ? 'Dirección compartida' : 'Shared pickup address'}
              />
            </label>
            <button
              type="button"
              onClick={applyLocationToSelected}
              disabled={busy || !String(bulkLocation || '').trim() || selectedRowIndexes.size === 0}
              className="flex-shrink-0 text-[11px] px-2.5 py-1 rounded-md bg-emerald-500/35 text-emerald-50 border border-emerald-400/50 hover:bg-emerald-500/45 disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
            >
              {isEs
                ? `Aplicar dirección (${selectedRowIndexes.size})`
                : `Apply address (${selectedRowIndexes.size})`}
            </button>
          </div>

          <div className="flex flex-col sm:flex-row gap-1.5 items-stretch sm:items-center">
            <label className="flex-1 flex items-center gap-1.5 min-w-0 text-[11px]">
              <i className="fas fa-tag text-emerald-300 flex-shrink-0" aria-hidden="true" />
              <select
                value={bulkCategory}
                onChange={(e) => setBulkCategory(e.target.value)}
                disabled={busy}
                className="flex-1 min-w-0 bg-slate-900 border border-slate-600 rounded px-2 py-1 text-slate-100 outline-none focus:border-emerald-500/50"
                aria-label={isEs ? 'Categoría compartida' : 'Shared category'}
              >
                <option value="">{isEs ? 'Categoría (opcional)…' : 'Category (optional)…'}</option>
                {['produce', 'bakery', 'dairy', 'pantry', 'meat', 'prepared', 'other'].map((c) => (
                  <option key={c} value={c}>{c}</option>
                ))}
              </select>
            </label>
            <label className="flex-1 flex items-center gap-1.5 min-w-0 text-[11px]">
              <i className="fas fa-calendar-day text-emerald-300 flex-shrink-0" aria-hidden="true" />
              <input
                type="date"
                value={bulkExpiry}
                onChange={(e) => setBulkExpiry(e.target.value)}
                disabled={busy}
                className="flex-1 min-w-0 bg-slate-900 border border-slate-600 rounded px-2 py-1 text-slate-100 outline-none focus:border-emerald-500/50"
                aria-label={isEs ? 'Caducidad compartida' : 'Shared expiry'}
              />
            </label>
            <button
              type="button"
              onClick={() => {
                if (String(bulkCategory || '').trim()) applyCategoryToSelected()
                if (String(bulkExpiry || '').trim()) applyExpiryToSelected()
              }}
              disabled={
                busy
                || selectedRowIndexes.size === 0
                || (!String(bulkCategory || '').trim() && !String(bulkExpiry || '').trim())
              }
              className="flex-shrink-0 text-[11px] px-2.5 py-1 rounded-md bg-emerald-500/35 text-emerald-50 border border-emerald-400/50 hover:bg-emerald-500/45 disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
            >
              {isEs ? 'Aplicar' : 'Apply'}
            </button>
          </div>

          <button
            type="button"
            onClick={applyAllMissingToSelected}
            disabled={
              busy
              || selectedRowIndexes.size === 0
              || (
                !String(bulkLocation || '').trim()
                && !String(bulkCommunityId || '').trim()
                && !String(bulkCategory || '').trim()
                && !String(bulkExpiry || '').trim()
              )
            }
            className="w-full text-[11px] px-2.5 py-1.5 rounded-md bg-cyan-500/25 text-cyan-50 border border-cyan-400/40 hover:bg-cyan-500/35 disabled:opacity-40 disabled:cursor-not-allowed transition-colors font-medium"
          >
            {fillEmptyOnly
              ? (isEs
                  ? `Aplicar todo a campos vacíos (${selectedRowIndexes.size} filas)`
                  : `Apply all to empty fields (${selectedRowIndexes.size} rows)`)
              : (isEs
                  ? `Aplicar todo a seleccionadas (${selectedRowIndexes.size})`
                  : `Apply all to selected (${selectedRowIndexes.size})`)}
          </button>
        </div>
      )}

      <div className={`space-y-1.5 overflow-y-auto nourish-scrollbar pr-1 ${isCsv ? 'max-h-64' : 'max-h-44'}`}>
        {previewRows.map((row, idx) => (
          <div key={idx} className="rounded-lg border border-slate-700/60 bg-slate-800/40 p-2 flex items-start gap-2">
            {isCsv && (
              <input
                type="checkbox"
                checked={selectedRowIndexes.has(idx)}
                onChange={() => toggleRowSelected(idx)}
                disabled={busy}
                className="mt-1 rounded border-slate-600 bg-slate-900 text-emerald-500 focus:ring-emerald-500/40 flex-shrink-0"
                aria-label={isEs ? `Seleccionar fila ${idx + 1}` : `Select row ${idx + 1}`}
              />
            )}
            {/* Auto-assigned image thumbnail */}
            {row.image_url && (
              <img
                src={row.image_url}
                alt={row.title || 'food'}
                className="w-12 h-12 rounded-lg object-cover flex-shrink-0 border border-slate-600/50"
                onError={(e) => { e.target.style.display = 'none' }}
              />
            )}
            <div className="flex-1 min-w-0">
              <div className="flex items-center gap-1.5">
                <input
                  type="text"
                  value={row.title || ''}
                  onChange={(e) => onUpdateRow(idx, { title: e.target.value })}
                  disabled={busy}
                  className="flex-1 min-w-0 bg-transparent text-sm text-slate-100 font-medium outline-none focus:bg-slate-900/60 px-1.5 py-0.5 rounded"
                  aria-label={`Row ${idx + 1} title`}
                />
                {filledByIndex.has(idx) && (
                  <span
                    className="text-[9px] uppercase tracking-wide px-1.5 py-0.5 rounded-full bg-cyan-500/25 text-cyan-50 border border-cyan-400/40 whitespace-nowrap"
                    title={`${isEs ? 'IA rellenó' : 'AI filled'}: ${filledByIndex.get(idx).join(', ')}`}
                  >
                    <i className="fas fa-wand-magic-sparkles mr-0.5" aria-hidden="true" />
                    AI +{filledByIndex.get(idx).length}
                  </span>
                )}
              </div>
              <div className="flex items-center gap-1.5 mt-0.5 text-[11px] text-slate-300">
                <input
                  type="number"
                  step="0.1"
                  min="0"
                  value={row.quantity ?? ''}
                  onChange={(e) => onUpdateRow(idx, { quantity: Number(e.target.value) })}
                  disabled={busy}
                  className="w-16 bg-transparent outline-none focus:bg-slate-900/60 px-1 py-0.5 rounded text-slate-100"
                  aria-label="Quantity"
                />
                <input
                  type="text"
                  value={row.unit || ''}
                  onChange={(e) => onUpdateRow(idx, { unit: e.target.value })}
                  disabled={busy}
                  className="w-16 bg-transparent outline-none focus:bg-slate-900/60 px-1 py-0.5 rounded text-slate-100"
                  aria-label="Unit"
                />
                <span className="text-slate-300">·</span>
                <select
                  value={row.category || 'other'}
                  onChange={(e) => onUpdateRow(idx, { category: e.target.value })}
                  disabled={busy}
                  className="bg-slate-900 border border-slate-600 rounded px-1 py-0.5 text-slate-100"
                  aria-label="Category"
                >
                  {['produce','bakery','dairy','pantry','meat','prepared','other'].map(c => (
                    <option key={c} value={c}>{c}</option>
                  ))}
                </select>
              </div>
              {/* Pickup address / expiry / community — without these the
                  listing publishes without a map pin, freshness hint, or
                  community attribution. Pre-filled from the donor profile
                  and a category-based expiry suggestion by the backend. */}
              <div className="mt-1 grid grid-cols-1 sm:grid-cols-3 gap-1 text-[11px]">
                <label className="flex items-center gap-1 min-w-0">
                  <i className="fas fa-location-dot text-slate-400 flex-shrink-0" aria-hidden="true" />
                  <input
                    type="text"
                    value={row.location || ''}
                    onChange={(e) => onUpdateRow(idx, { location: e.target.value })}
                    disabled={busy}
                    placeholder={isEs ? 'Dirección de recogida' : 'Pickup address'}
                    className="flex-1 min-w-0 bg-transparent outline-none focus:bg-slate-900/60 px-1 py-0.5 rounded text-slate-100 placeholder:text-slate-400"
                    aria-label={isEs ? 'Dirección de recogida' : 'Pickup address'}
                  />
                </label>
                <label className="flex items-center gap-1 min-w-0">
                  <i className="fas fa-calendar-day text-slate-400 flex-shrink-0" aria-hidden="true" />
                  <input
                    type="date"
                    value={row.expiry_date || ''}
                    onChange={(e) => onUpdateRow(idx, { expiry_date: e.target.value })}
                    disabled={busy}
                    className="flex-1 min-w-0 bg-transparent outline-none focus:bg-slate-900/60 px-1 py-0.5 rounded text-slate-100"
                    aria-label={isEs ? 'Fecha de caducidad' : 'Expiry date'}
                  />
                </label>
                <label className="flex items-center gap-1 min-w-0">
                  <i className="fas fa-people-group text-slate-400 flex-shrink-0" aria-hidden="true" />
                  {communities.length > 0 ? (
                    <select
                      value={row.community_id || ''}
                      onChange={(e) => {
                        const id = e.target.value || ''
                        const match = communities.find((c) => String(c.id) === String(id))
                        onUpdateRow(idx, {
                          community_id: id || undefined,
                          community_name: match?.name,
                        })
                      }}
                      disabled={busy}
                      className={`flex-1 min-w-0 bg-slate-900 border rounded px-1 py-0.5 text-slate-100 ${
                        row.community_id ? 'border-slate-600' : 'border-amber-400'
                      }`}
                      aria-label={isEs ? 'Comunidad / escuela' : 'Community / school'}
                      required
                    >
                      <option value="">
                        {isEs ? 'Elige escuela o comunidad…' : 'Choose school or community…'}
                      </option>
                      {communities.map(c => (
                        <option key={c.id} value={c.id}>{c.name}</option>
                      ))}
                    </select>
                  ) : (
                    <input
                      type="text"
                      value={row.community_name || ''}
                      onChange={(e) => onUpdateRow(idx, {
                        community_name: e.target.value || undefined,
                        community_id: undefined,
                      })}
                      disabled={busy || communitiesLoading}
                      placeholder={
                        communitiesLoading
                          ? (isEs ? 'Cargando comunidades…' : 'Loading communities…')
                          : (isEs ? 'Nombre de escuela o comunidad' : 'School or community name')
                      }
                      className={`flex-1 min-w-0 bg-transparent outline-none focus:bg-slate-900/60 px-1 py-0.5 rounded text-slate-100 placeholder:text-slate-400 ${
                        row.community_name ? '' : 'ring-1 ring-amber-400 rounded'
                      }`}
                      aria-label={isEs ? 'Comunidad / escuela' : 'Community / school'}
                    />
                  )}
                </label>
              </div>
              {communitiesError && (
                <div className="mt-1 flex items-center gap-2 text-[10px] text-amber-200">
                  <span>{communitiesError}</span>
                  <button
                    type="button"
                    onClick={loadCommunities}
                    disabled={busy || communitiesLoading}
                    className="underline hover:text-amber-100 disabled:opacity-40"
                  >
                    {isEs ? 'Reintentar' : 'Retry'}
                  </button>
                </div>
              )}
            </div>
            <button
              type="button"
              onClick={() => onRemoveRow(idx)}
              disabled={busy}
              className="text-slate-400 hover:text-rose-300 text-xs p-1 disabled:opacity-40"
              aria-label={`Remove row ${idx + 1}`}
              title={isEs ? 'Quitar' : 'Remove'}
            >
              <i className="fas fa-times" aria-hidden="true" />
            </button>
          </div>
        ))}
        {extra > 0 && (
          <div className="text-[11px] text-slate-300 italic px-1">
            {isEs ? `…y ${extra} más` : `…and ${extra} more`}
          </div>
        )}
      </div>

      {pending.parseErrors && pending.parseErrors.length > 0 && (
        <div className="mt-2 text-[11px] text-amber-200">
          <i className="fas fa-triangle-exclamation mr-1" aria-hidden="true" />
          {pending.parseErrors.length} {isEs ? 'fila(s) omitida(s)' : 'row(s) skipped'}
        </div>
      )}

      {missingCommunity && (
        <div className="mt-2 text-[11px] text-amber-200">
          <i className="fas fa-triangle-exclamation mr-1" aria-hidden="true" />
          {isEs
            ? 'Elige una escuela o comunidad para cada fila (usa “Aplicar comunidad” arriba para todas a la vez).'
            : 'Choose a school or community for each row (use “Apply community” above to set them all at once).'}
        </div>
      )}

      <div className="flex items-center gap-2 mt-3">
        <button
          type="button"
          onClick={onCancel}
          disabled={busy}
          className="text-xs px-3 py-1.5 rounded-full bg-slate-700 text-slate-50 hover:bg-slate-600 border border-slate-700/60 disabled:opacity-40"
        >
          {isEs ? 'Cancelar' : 'Cancel'}
        </button>
        <button
          type="button"
          onClick={onConfirm}
          disabled={busy || rows.length === 0 || missingCommunity}
          className={`text-xs px-3 py-1.5 rounded-full text-white font-semibold disabled:opacity-50 disabled:cursor-not-allowed transition-all ml-auto bg-gradient-to-r ${
            tint === 'fuchsia'
              ? 'from-fuchsia-500 to-purple-500 hover:from-fuchsia-400 hover:to-purple-400 shadow-md shadow-fuchsia-500/20'
              : 'from-emerald-500 to-cyan-500 hover:from-emerald-400 hover:to-cyan-400 shadow-md shadow-emerald-500/20'
          }`}
        >
          {busy
            ? (isEs ? 'Creando…' : 'Creating…')
            : (isEs
                ? `Crear ${rows.length} publicación${rows.length === 1 ? '' : 'es'}`
                : `Create ${rows.length} listing${rows.length === 1 ? '' : 's'}`)}
        </button>
      </div>
    </div>
  )
}

// ─── Main Chat Panel ───────────────────────────────────
function AIChatPanel() {
  const {
    messages,
    sendMessage,
    sendVoice,
    isLoading,
    error,
    language,
    clearHistory,
    submitFeedback,
    appendLocalMessage,
    sendSilentMessage,
    isAuthenticated,
    setLanguage,
    // Error recovery actions surfaced via Retry / Regenerate buttons in the bubble UI.
    retryMessage,
    regenerateLast,
    historyLoaded,
    tone,
    setTone,
    confirmPendingAction,
  } = useAIChat()

  const { applyToolResults, clearAIOverlays } = useMapContext()
  const { registerHandler, executeUIActionsFromToolResults, executeUIAction } = useUIControl()
  const { user: authUser, isAdmin } = useAuthContext() || {}
  const allowedCommunityIds = useMemo(
    () => browseCommunityIdsForUser(authUser, { isAdmin }),
    [authUser?.community_id, isAdmin],
  )
  const communityRole = useCommunityRole()
  const { settings: a11ySettings, guide, syncFromChat, cancelVoice, updateSetting } = useNouriGuide()
  // Photo / CSV attach is donor-only (list food, attach listing photos, bulk CSV).
  const canAttachFiles = communityRole !== 'recipient'
  // Staged photos for the composer (attach + optional text, then send together).
  const [pendingChatPhotos, setPendingChatPhotos] = useState([])
  const prevCommunityRoleRef = useRef(null)
  const lastAppliedToolMsgRef = useRef(null)
  const lastSurfacedErrorRef = useRef(null)

  // Surface backend AI errors as a toast so the user sees what went wrong,
  // not just an error bubble inside the chat (which can be missed when scrolled).
  useEffect(() => {
    if (!error || error === lastSurfacedErrorRef.current) return
    lastSurfacedErrorRef.current = error
    toast.error(
      language === 'es'
        ? `Problema con el asistente: ${error}`
        : `Assistant error: ${error}`,
      { autoClose: 4000, position: 'top-center' }
    )
  }, [error, language])

  // Fire a toast when the AI successfully claims or cancels a food listing.
  // Only fires for LIVE turns — never on history reload, otherwise a user
  // refreshing the page would get a stale "Claim confirmed!" popup.
  const lastToastedClaimRef = useRef(null)
  useEffect(() => {
    if (!messages?.length) return
    const last = messages[messages.length - 1]
    if (!last || last.role !== 'assistant' || !last.toolResults?.length) return
    if (last.fromHistory) return
    for (const tr of last.toolResults) {
      const key = `${last.id}-${tr.tool}`
      if (lastToastedClaimRef.current === key) continue
      const result = tr.result ?? tr
      const ok = result?.success || tr.ok
      if ((tr.tool === 'claim_listing' || tr.tool === 'claim_food') && ok) {
        lastToastedClaimRef.current = key
        // Claim success is shown in the chat card — skip duplicate toast.
        window.dispatchEvent(new CustomEvent('foodShared'))
      }
      if (tr.tool === 'claim_listings' && ok) {
        lastToastedClaimRef.current = key
        window.dispatchEvent(new CustomEvent('foodShared'))
      }
      if (tr.tool === 'cancel_claim' && ok) {
        lastToastedClaimRef.current = key
        toast.info(
          language === 'es' ? 'Reclamo cancelado.' : 'Claim released — item returned to inventory.',
          { autoClose: 4000, position: 'top-center' }
        )
      }
      // Notify FoodMap and FindFoodPage to refresh so the new listing pin
      // appears immediately without requiring a page reload.
      if ((tr.tool === 'create_food_listing' || tr.tool === 'post_food_listing') && ok) {
        window.dispatchEvent(new CustomEvent('foodShared'))
      }
      if (ok && ['update_food_listing', 'update_listing', 'edit_listing', 'deactivate_listing', 'delete_listing'].includes(tr.tool)) {
        window.dispatchEvent(new CustomEvent('foodShared'))
      }
    }
  }, [messages, language])

  // Whenever a new assistant message arrives with tool_results, push them
  // to the MapContext so any mounted FoodMap can render markers / route.
  // On history reload, scan BACKWARDS for the most recent assistant turn
  // with map-relevant tools, so closing the chat with "claim it" / "thanks"
  // as the last message doesn't leave the map blank.
  const MAP_TOOLS = useMemo(() => new Set([
    'search_food_near_user', 'search_food_nearby', 'get_recent_listings',
    'get_community_listings', 'get_user_listings', 'get_my_claims',
    'get_mapbox_route', 'show_route_to_listing', 'query_distribution_centers',
    'optimize_pickup_route',
  ]), [])
  useEffect(() => {
    if (!messages || messages.length === 0) return
    const last = messages[messages.length - 1]
    if (!last || last.role !== 'assistant') return

    // Live turn → apply immediately and run UI actions.
    if (!last.fromHistory) {
      if (Array.isArray(last.toolResults) && last.toolResults.length > 0
          && lastAppliedToolMsgRef.current !== last.id) {
        lastAppliedToolMsgRef.current = last.id
        applyToolResults(last.toolResults)
        // GUIDED tutorial: never auto-open pages — Nouri only tells the user how.
        const guidedTutorial = /^guided\b|^guiado\b/i.test(String(last.message || '').trim())
        const navCount = guidedTutorial
          ? 0
          : executeUIActionsFromToolResults(last.toolResults)
        if (!guidedTutorial && navCount === 0 && last.action && !last.fromHistory) {
          executeUIAction({ ok: true, ...last.action })
        }
        // Route optimizer hint → open dashboard so PickupRouteOptimizer can render stops.
        const wantsRouteUi = !guidedTutorial && last.toolResults.some((tr) => {
          const r = tr.result ?? tr
          const hint = r?.frontend_hint || tr.frontend_hint
          return tr.tool === 'optimize_pickup_route'
            || hint?.component === 'RouteOptimizer'
        })
        if (wantsRouteUi) {
          executeUIAction({ ok: true, action: 'navigate', path: '/dashboard' })
        }
      }
      return
    }

    // History reload → find the most recent message that has map tools,
    // and apply ONLY its results so the map can re-render its state.
    // UI actions are NOT replayed (we don't want navigation/modals to
    // re-fire just because the user refreshed the page).
    for (let i = messages.length - 1; i >= 0; i--) {
      const m = messages[i]
      if (m.role !== 'assistant' || !Array.isArray(m.toolResults)) continue
      const hasMapTool = m.toolResults.some(tr => MAP_TOOLS.has(tr?.tool))
      if (hasMapTool) {
        if (lastAppliedToolMsgRef.current !== m.id) {
          lastAppliedToolMsgRef.current = m.id
          applyToolResults(m.toolResults)
        }
        break
      }
    }
  }, [messages, applyToolResults, executeUIActionsFromToolResults, executeUIAction, MAP_TOOLS])

  const [isOpen, setIsOpen] = useState(false)
  const [isExpanded, setIsExpanded] = useState(false)
  const [inputText, setInputText] = useState('')
  const [showMenu, setShowMenu] = useState(false)
  const [suggestionIndex, setSuggestionIndex] = useState(-1)
  const [suggestionsOpen, setSuggestionsOpen] = useState(false)
  const [voiceMode, setVoiceMode] = useState(false)
  // Live mic input level (0..1) — sampled from the existing AnalyserNode in
  // the VAD loop and used to drive the orb's scale + the live audio meter.
  const [audioLevel, setAudioLevel] = useState(0)
  const [isVoiceListening, setIsVoiceListening] = useState(false)
  const [isVoiceSpeaking, setIsVoiceSpeaking] = useState(false)
  // iOS Safari blocks autoplay outside a user gesture. When that happens we
  // stash a replay() callback here and surface a "Tap to hear" button; tapping
  // it replays the audio from inside a real tap, which the browser allows.
  const [tapToHear, setTapToHear] = useState(null)
  const [voiceError, setVoiceError] = useState(null)
  const [voiceTranscript, setVoiceTranscript] = useState('')
  // ─── Wake word ("Nouri") hands-free state ───────
  // wakeWordEnabled: user opted in to always-listening wake activation.
  // wakeActive: a SpeechRecognition session is currently listening for the
  // wake word in the background (used to drive the standby indicator).
  const [wakeWordEnabled, setWakeWordEnabled] = useState(false)
  const [wakeActive, setWakeActive] = useState(false)
  // ─── Upload (photo + CSV → bulk-listings) state ───────
  // pendingUpload shape: { kind:'photo'|'csv', rows:[], filename, confidence?, error?, parseErrors? }
  const [pendingUpload, setPendingUpload] = useState(null)
  const [uploadBusy, setUploadBusy] = useState(false)
  // Monotonic counter that lets us cancel in-flight async work (enrichment,
  // vision, storage upload) when the user dismisses the preview or starts
  // a new upload. Each upload session captures the current value and bails
  // out early if it no longer matches.
  const uploadSessionRef = useRef(0)
  const photoInputRef = useRef(null)
  const csvInputRef = useRef(null)
  const inlinePhotoInputRef = useRef(null)
  const messagesEndRef = useRef(null)
  // Container ref + state for the scroll-to-bottom pill. We show the pill
  // only when the user has scrolled away from the latest message so it
  // doesn't compete with the normal autoscroll behavior.
  const messagesContainerRef = useRef(null)
  const [showScrollPill, setShowScrollPill] = useState(false)
  const wasOpenRef = useRef(false)
  const historyScrollDoneRef = useRef(false)

  const scrollMessagesToEnd = useCallback(() => {
    const run = () => {
      const el = messagesContainerRef.current
      if (el) {
        el.scrollTop = el.scrollHeight
      } else {
        messagesEndRef.current?.scrollIntoView({ behavior: 'auto' })
      }
      setShowScrollPill(false)
    }
    requestAnimationFrame(() => requestAnimationFrame(run))
  }, [])
  const [showAttachMenu, setShowAttachMenu] = useState(false)
  const attachMenuRef = useRef(null)

  useEffect(() => {
    if (!canAttachFiles) setShowAttachMenu(false)
  }, [canAttachFiles])

  // When the user switches donor ↔ recipient, drop prior chat so Nouri
  // doesn't keep acting under the old role from history.
  useEffect(() => {
    const role = String(communityRole || '').toLowerCase()
    const prev = prevCommunityRoleRef.current
    prevCommunityRoleRef.current = role || null
    if (!prev || !role || prev === role) return
    if (!['donor', 'recipient'].includes(prev) || !['donor', 'recipient'].includes(role)) {
      return
    }
    ;(async () => {
      // Bump upload session so in-flight photo/CSV work cannot reinstate stale drafts.
      uploadSessionRef.current += 1
      setPendingUpload(null)
      setPendingChatPhotos((photos) => {
        photos.forEach((p) => {
          if (p.previewUrl) URL.revokeObjectURL(p.previewUrl)
        })
        return []
      })
      await clearHistory()
      toast.info(
        language === 'es'
          ? `Rol actualizado a ${role}. Empezamos un chat limpio.`
          : `Role updated to ${role}. Starting a fresh chat.`,
        { autoClose: 3500, position: 'top-center' },
      )
    })()
  }, [communityRole, clearHistory, language])

  const inputRef = useRef(null)
  const panelRef = useRef(null)
  const previousFocusRef = useRef(null)
  const currentAudioRef = useRef(null)
  const lastSpokenIdRef = useRef(null)
  const voiceModeRef = useRef(false)
  const sendVoiceRef = useRef(sendVoice)
  const mediaStreamRef = useRef(null)
  const mediaRecorderRef = useRef(null)
  const audioChunksRef = useRef([])
  const analyserRef = useRef(null)
  const silenceTimerRef = useRef(null)
  const vadFrameRef = useRef(null)
  // ─── Wake word ("Nouri") refs ───────
  // Browser SpeechRecognition is event-driven and set up once, so the handlers
  // read the latest values through refs instead of stale closures.
  const wakeRecognitionRef = useRef(null)      // active SpeechRecognition instance
  const wakeWordEnabledRef = useRef(false)     // mirror of wakeWordEnabled state
  const handsFreeRef = useRef(false)           // a wake-triggered conversation turn is live
  const wakeCooldownRef = useRef(0)            // debounce repeated wake detections
  const isVoiceSpeakingRef = useRef(false)     // mirror of isVoiceSpeaking
  const startWakeListeningRef = useRef(null)   // late-bound startWakeListening
  const triggerWakeRef = useRef(null)          // late-bound triggerWake
  const endHandsFreeTurnRef = useRef(null)     // late-bound endHandsFreeTurn
  const prevSpeakingRef = useRef(false)        // edge-detect speaking → idle

  // Wake word relies on the Web Speech API, which Safari/Firefox expose
  // inconsistently. Detect support once so we can hide the toggle when the
  // browser can't deliver continuous recognition.
  const wakeWordSupported = typeof window !== 'undefined'
    && !!(window.SpeechRecognition || window.webkitSpeechRecognition)

  useEffect(() => { sendVoiceRef.current = sendVoice }, [sendVoice])

  const closeAssistant = useCallback(() => {
    setIsOpen(false)
    setIsExpanded(false)
    setShowMenu(false)
    setShowAttachMenu(false)
    setSuggestionsOpen(false)
    setSuggestionIndex(-1)
  }, [])

  // Register imperative handlers so the AI's ui_action tool can drive this panel.
  useEffect(() => {
    const u1 = registerHandler('setAssistantOpen', (open) => {
      if (open) setIsOpen(true)
      else closeAssistant()
    })
    const u2 = registerHandler('setAssistantExpanded', (exp) => setIsExpanded(!!exp))
    const u3 = registerHandler('clearMapOverlays', () => clearAIOverlays())
    const u4 = registerHandler('setLanguage', (lang) => {
      if (CHAT_UI_LANGUAGES.includes(chatLang(lang))) setLanguage(chatLang(lang))
    })
    return () => { u1(); u2(); u3(); u4() }
  }, [registerHandler, clearAIOverlays, setLanguage, closeAssistant])

  // Hold focus like the main menu: backdrop dim + scroll lock.
  useEffect(() => {
    if (!isOpen) return undefined

    previousFocusRef.current = document.activeElement
    const prevOverflow = document.body.style.overflow
    document.body.style.overflow = 'hidden'

    return () => {
      document.body.style.overflow = prevOverflow
      const prev = previousFocusRef.current
      if (prev && typeof prev.focus === 'function') {
        requestAnimationFrame(() => {
          try { prev.focus() } catch { /* element may have unmounted */ }
        })
      }
      previousFocusRef.current = null
    }
  }, [isOpen])

  // Focus trap + Escape while the assistant is open.
  useEffect(() => {
    if (!isOpen) return undefined

    const getFocusable = () => {
      if (!panelRef.current) return []
      return Array.from(panelRef.current.querySelectorAll(
        'button:not([disabled]), [href], input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])',
      ))
    }

    const onKeyDown = (e) => {
      if (e.key === 'Escape') {
        e.preventDefault()
        if (showMenu) {
          setShowMenu(false)
          return
        }
        if (showAttachMenu) {
          setShowAttachMenu(false)
          return
        }
        if (suggestionsOpen) {
          setSuggestionsOpen(false)
          setSuggestionIndex(-1)
          return
        }
        closeAssistant()
        return
      }
      if (e.key !== 'Tab') return
      const focusable = getFocusable()
      if (focusable.length === 0) return
      const first = focusable[0]
      const last = focusable[focusable.length - 1]
      if (e.shiftKey) {
        if (document.activeElement === first || !panelRef.current?.contains(document.activeElement)) {
          e.preventDefault()
          last.focus()
        }
      } else if (document.activeElement === last || !panelRef.current?.contains(document.activeElement)) {
        e.preventDefault()
        first.focus()
      }
    }

    document.addEventListener('keydown', onKeyDown)
    return () => document.removeEventListener('keydown', onKeyDown)
  }, [isOpen, closeAssistant, showMenu, showAttachMenu, suggestionsOpen])

  // Last assistant message for voice mode auto-speak
  const lastAssistantMessage = useMemo(() => {
    for (let i = messages.length - 1; i >= 0; i--) {
      if (messages[i].role === 'assistant' && !messages[i].isError) return messages[i]
    }
    return null
  }, [messages])

  // Autocomplete always follows the sticky conversation language — never
  // flip pools mid-typing from accent marks in English loan-words.
  const suggestionPool = getSuggestions(language)
  const filteredSuggestions = useMemo(() => {
    const q = inputText.trim().toLowerCase()
    if (!q) return []
    const scored = []
    for (const s of suggestionPool) {
      const lower = s.toLowerCase()
      if (lower === q) continue
      const idx = lower.indexOf(q)
      if (idx !== -1) scored.push({ s, idx })
    }
    scored.sort((a, b) => a.idx - b.idx || a.s.length - b.s.length)
    return scored.slice(0, 6).map((x) => x.s)
  }, [inputText, suggestionPool])

  const showSuggestions = suggestionsOpen && filteredSuggestions.length > 0 && !isLoading

  // Reset highlighted index whenever the filtered list changes
  useEffect(() => {
    setSuggestionIndex(-1)
  }, [inputText])

  const acceptSuggestion = useCallback((value) => {
    if (!value) return
    setInputText(value)
    setSuggestionsOpen(false)
    setSuggestionIndex(-1)
    // Refocus textarea so the user can press Enter to send
    setTimeout(() => inputRef.current?.focus(), 0)
  }, [])

  // Auto-scroll to bottom on new messages — but ONLY when the user is
  // already near the bottom. If they're reading older history (scroll pill
  // visible), we don't yank them away from their place.
  useEffect(() => {
    if (!isOpen) return
    const el = messagesContainerRef.current
    if (!el) {
      messagesEndRef.current?.scrollIntoView({ behavior: 'auto', block: 'end' })
      return
    }
    const nearBottom = el.scrollHeight - el.scrollTop - el.clientHeight < 200
    if (nearBottom) {
      messagesEndRef.current?.scrollIntoView({ behavior: 'auto', block: 'end' })
    }
  }, [messages, isOpen, isLoading])

  // Opening the panel should always land on the latest messages, not the
  // top of a long history thread.
  useEffect(() => {
    if (isOpen && !wasOpenRef.current) {
      scrollMessagesToEnd()
    }
    wasOpenRef.current = isOpen
  }, [isOpen, scrollMessagesToEnd])

  // When async history hydrates after login, jump to the newest turn once.
  useEffect(() => {
    historyScrollDoneRef.current = false
  }, [authUser?.id])

  useEffect(() => {
    if (!historyLoaded || historyScrollDoneRef.current) return
    historyScrollDoneRef.current = true
    if (isOpen) {
      scrollMessagesToEnd()
    }
  }, [historyLoaded, isOpen, scrollMessagesToEnd])

  // Track scroll position to toggle the "jump to latest" pill.
  useEffect(() => {
    const el = messagesContainerRef.current
    if (!el) return
    const onScroll = () => {
      const distance = el.scrollHeight - el.scrollTop - el.clientHeight
      setShowScrollPill(distance > 240)
    }
    onScroll()
    el.addEventListener('scroll', onScroll, { passive: true })
    return () => el.removeEventListener('scroll', onScroll)
  }, [isOpen, voiceMode])

  const jumpToLatest = useCallback(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'auto', block: 'end' })
  }, [])

  // Focus input when panel opens
  useEffect(() => {
    if (isOpen && inputRef.current) {
      setTimeout(() => inputRef.current?.focus(), 200)
    }
  }, [isOpen])

  // Keep the textarea ready for the next message after each AI turn.
  // `disabled` yanks focus; `readOnly` preserves it while blocking edits.
  const prevLoadingRef = useRef(isLoading)
  useEffect(() => {
    const wasLoading = prevLoadingRef.current
    prevLoadingRef.current = isLoading
    if (wasLoading && !isLoading && isOpen && !voiceMode) {
      requestAnimationFrame(() => inputRef.current?.focus())
    }
  }, [isLoading, isOpen, voiceMode])

  // Close menu on outside click
  useEffect(() => {
    const handleClickOutside = (e) => {
      if (showMenu && panelRef.current && !panelRef.current.contains(e.target)) {
        setShowMenu(false)
      }
      if (showAttachMenu && attachMenuRef.current && !attachMenuRef.current.contains(e.target)) {
        setShowAttachMenu(false)
      }
    }
    document.addEventListener('mousedown', handleClickOutside)
    return () => document.removeEventListener('mousedown', handleClickOutside)
  }, [showMenu, showAttachMenu])

  const handleSend = useCallback(async (e) => {
    e?.preventDefault()
    if (isLoading || uploadBusy) return
    const text = inputText.trim()
    const photos = pendingChatPhotos
    if (!text && photos.length === 0) return

    setSuggestionsOpen(false)
    setSuggestionIndex(-1)

    if (photos.length === 0) {
      sendMessage(text)
      setInputText('')
      requestAnimationFrame(() => inputRef.current?.focus())
      return
    }

    setUploadBusy(true)
    try {
      const urls = []
      for (const photo of photos) {
        if (photo.url) {
          urls.push(photo.url)
          continue
        }
        if (!photo.file || !authUser?.id) continue
        try {
          const res = await dataService.uploadFile(photo.file, 'food-images')
          if (res?.url) urls.push(res.url)
        } catch (err) {
          console.warn('Chat photo upload failed:', err?.message || err)
        }
      }
      if (urls.length === 0) {
        appendLocalMessage({
          role: 'assistant',
          message: language === 'es'
            ? 'No pude subir esas fotos. ¿Puedes intentar de nuevo?'
            : "I couldn't upload those photos. Please try again.",
          isError: true,
        })
        return
      }
      const imageBlock = urls.map((u) => `image: ${u}`).join('\n')
      const payload = text ? `${text}\n\n${imageBlock}` : imageBlock
      sendMessage(payload)
      setInputText('')
      setPendingChatPhotos((prev) => {
        prev.forEach((p) => {
          if (p.previewUrl) URL.revokeObjectURL(p.previewUrl)
        })
        return []
      })
    } finally {
      setUploadBusy(false)
      requestAnimationFrame(() => inputRef.current?.focus())
    }
  }, [
    inputText,
    isLoading,
    uploadBusy,
    pendingChatPhotos,
    sendMessage,
    authUser?.id,
    appendLocalMessage,
    language,
  ])

  const removePendingChatPhoto = useCallback((id) => {
    setPendingChatPhotos((prev) => {
      const next = []
      for (const p of prev) {
        if (p.id === id) {
          if (p.previewUrl) URL.revokeObjectURL(p.previewUrl)
        } else {
          next.push(p)
        }
      }
      return next
    })
  }, [])

  const handleQuickAction = useCallback((msg) => {
    if (isLoading) return
    const text = String(msg || '').trim()
    if (!text) return
    // Open Share / Find / Request — page-aware labels.
    const openForm = /^(open the form|abrir el formulario|open find food|abrir buscar comida|open request food|abrir solicitar comida)$/i.test(text)
    if (openForm) {
      let path = '/share'
      const lower = text.toLowerCase()
      try {
        const lastAsst = [...messages].reverse().find(
          (m) => m.role === 'assistant' && !m.isError && m.id !== 'welcome',
        )
        const locPath = typeof window !== 'undefined' ? (window.location.pathname || '') : ''
        const ctx = `${lastAsst?.message || ''} ${text} ${locPath}`.toLowerCase()
        if (/open find food|abrir buscar|find food|buscar comida|\/find|near-me/.test(lower + ctx)
          && !/open the form|abrir el formulario|share food|\/share/.test(lower)) {
          path = locPath.includes('near-me') ? '/near-me' : '/find'
        } else if (/open request food|abrir solicitar|request food|\/request/.test(lower + ctx)
          && !/open the form|share food|\/share/.test(lower)) {
          path = '/request'
        } else if (/(find food|buscar comida|search nearby|near you)/.test(ctx)
          && !/(share food|\/share|compartir|donate|posting)/.test(ctx)) {
          path = locPath.includes('near-me') ? '/near-me' : '/find'
        } else if (/(request food|solicitar)/.test(ctx)
          && !/(share food|\/share|compartir|donate|posting)/.test(ctx)) {
          path = '/request'
        }
      } catch { /* keep /share */ }
      try {
        executeUIAction?.({ ok: true, action: 'navigate', path })
      } catch { /* UI control optional */ }
    }
    sendMessage(text)
    requestAnimationFrame(() => inputRef.current?.focus())
  }, [isLoading, sendMessage, executeUIAction, messages])

  // Quick-suggestion chip rail above the input.
  // Conversation start: role-aware starter chips.
  // Mid-conversation: mirror the same backend chips as the bubble (no lazy
  // fallbacks — empty rail is better than mismatched "Find food" chips).
  const railChips = useMemo(() => {
    if (isLoading || pendingUpload || voiceMode || pendingChatPhotos.length > 0) return []
    if (messages.length <= 1) {
      return resolveInputChips([], language, communityRole, { allowLazy: true })
    }
    let lastAssistant = null
    for (let i = messages.length - 1; i >= 0; i--) {
      const m = messages[i]
      if (m.role === 'assistant' && !m.isError && m.id !== 'welcome') {
        lastAssistant = m
        break
      }
    }
    if (!lastAssistant || lastAssistant.requiresConfirmation) return []
    const backendSuggestions = Array.isArray(lastAssistant.suggestions) ? lastAssistant.suggestions : []
    const responseText = String(lastAssistant.message || lastAssistant.text || '')
    return resolveInputChips(backendSuggestions, language, communityRole, {
      allowLazy: false,
      responseText,
    })
  }, [messages, isLoading, pendingUpload, voiceMode, language, communityRole, pendingChatPhotos.length])

  // ─── File uploads (photo + CSV → bulk-listings) ───────
  // All three uploads require an authenticated user: the vision/enrichment
  // backend rejects anonymous calls, and the storage bucket policy needs a
  // user id. Gate the trigger so guests get a clear "sign in" message
  // instead of a generic "Failed to analyze image" downstream.
  const requireAuthForUpload = useCallback(() => {
    if (authUser?.id) return true
    appendLocalMessage({
      role: 'assistant',
      message: language === 'es'
        ? 'Inicia sesión para subir fotos o CSV — necesito identificarte para crear publicaciones a tu nombre.'
        : 'Sign in to upload photos or CSVs — I need to identify you to post listings on your behalf.',
      isError: true,
    })
    return false
  }, [appendLocalMessage, authUser?.id, language])

  const triggerPhotoUpload = useCallback(() => {
    if (uploadBusy || isLoading) return
    if (!requireAuthForUpload()) return
    photoInputRef.current?.click()
  }, [uploadBusy, isLoading, requireAuthForUpload])

  const triggerCsvUpload = useCallback(() => {
    if (uploadBusy || isLoading) return
    if (!requireAuthForUpload()) return
    csvInputRef.current?.click()
  }, [uploadBusy, isLoading, requireAuthForUpload])

  const triggerInlinePhotoUpload = useCallback(() => {
    if (uploadBusy || isLoading) return
    if (!requireAuthForUpload()) return
    inlinePhotoInputRef.current?.click()
  }, [uploadBusy, isLoading, requireAuthForUpload])

  // Inline photo attach: stage one or more photos in the composer so the
  // donor can add a caption and send text + photos together.
  const handleInlinePhotoSelected = useCallback(async (e) => {
    const files = Array.from(e.target.files || [])
    e.target.value = ''
    if (!files.length) return
    const ALLOWED_IMAGE_TYPES = new Set(['image/jpeg', 'image/png', 'image/webp', 'image/gif'])
    const accepted = []
    let rejectedType = false
    let rejectedSize = false
    for (const file of files) {
      if (!ALLOWED_IMAGE_TYPES.has(file.type)) {
        rejectedType = true
        continue
      }
      if (file.size > 8 * 1024 * 1024) {
        rejectedSize = true
        continue
      }
      accepted.push({
        id: `chat-photo-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`,
        file,
        previewUrl: URL.createObjectURL(file),
        name: file.name,
      })
    }
    if (rejectedType) {
      appendLocalMessage({
        role: 'assistant',
        message: language === 'es'
          ? 'Solo se admiten imágenes JPG, PNG, WEBP o GIF.'
          : 'Only JPG, PNG, WEBP, or GIF images are supported.',
        isError: true,
      })
    }
    if (rejectedSize) {
      appendLocalMessage({
        role: 'assistant',
        message: language === 'es' ? 'Una o más imágenes son demasiado grandes (máx 8 MB).' : 'One or more images are too large (max 8 MB).',
        isError: true,
      })
    }
    if (!accepted.length) return
    setPendingChatPhotos((prev) => [...prev, ...accepted].slice(0, 8))
  }, [appendLocalMessage, language])

  const cancelPendingUpload = useCallback(() => {
    if (uploadBusy) return
    // Bump session id so any still-running async callback (enrichment, vision,
    // storage upload) sees a stale id and bails out before touching state.
    uploadSessionRef.current += 1
    setPendingUpload(null)
  }, [uploadBusy])

  const handleClearConversation = useCallback(async () => {
    setShowMenu(false)
    cancelPendingUpload()
    setPendingChatPhotos((prev) => {
      prev.forEach((p) => {
        if (p.previewUrl) URL.revokeObjectURL(p.previewUrl)
      })
      return []
    })
    clearAIOverlays()
    historyScrollDoneRef.current = false
    setShowScrollPill(false)
    setInputText('')
    setSuggestionsOpen(false)
    setSuggestionIndex(-1)
    await clearHistory()
    scrollMessagesToEnd()
  }, [cancelPendingUpload, clearAIOverlays, clearHistory, scrollMessagesToEnd])

  const handlePhotoSelected = useCallback(async (e) => {
    const file = e.target.files?.[0]
    e.target.value = ''
    if (!file) return
    // Whitelist concrete raster MIME types only. `image/*` would let SVGs
    // through, which can carry inline scripts — even if the chat UI only
    // ever renders the result via <img src>, the URL also ends up in
    // food_listings.image_url and could be embedded as <object> elsewhere.
    const ALLOWED_IMAGE_TYPES = new Set(['image/jpeg', 'image/png', 'image/webp', 'image/gif'])
    if (!ALLOWED_IMAGE_TYPES.has(file.type)) {
      const msg = language === 'es'
        ? 'Solo se admiten imágenes JPG, PNG, WEBP o GIF.'
        : 'Only JPG, PNG, WEBP, or GIF images are supported.'
      setPendingUpload({ kind: 'photo', error: msg, filename: file.name })
      appendLocalMessage({ role: 'assistant', message: msg, isError: true })
      return
    }
    if (file.size > 8 * 1024 * 1024) {
      const msg = language === 'es' ? 'La imagen es demasiado grande (máx 8 MB).' : 'Image too large (max 8 MB).'
      setPendingUpload({ kind: 'photo', error: msg, filename: file.name })
      appendLocalMessage({ role: 'assistant', message: msg, isError: true })
      return
    }
    appendLocalMessage({
      role: 'user',
      message: `📷 ${language === 'es' ? 'Foto subida' : 'Photo uploaded'}: ${file.name}`,
    })
    // Open a new upload session and stash its id so async callbacks can detect
    // cancellation / superseded uploads.
    uploadSessionRef.current += 1
    const sessionId = uploadSessionRef.current
    setUploadBusy(true)
    setPendingUpload({ kind: 'photo', rows: [], filename: file.name, analyzing: true })
    try {
      // Shrink large phone photos once for both vision + storage upload.
      let uploadFile = file
      try {
        const { compressImage } = await import('../../utils/compressImage.js')
        uploadFile = await compressImage(file)
      } catch (err) {
        console.warn('Photo compress skipped:', err?.message || err)
      }

      // Kick off the storage upload and the vision call in parallel so the
      // user sees the preview faster. Storage upload is optional; if it fails
      // (no auth, bucket missing) we fall back to a category-based image.
      const uploadPromise = (async () => {
        if (!authUser?.id) return null
        try {
          const res = await dataService.uploadFile(uploadFile, 'food-images')
          return res?.url || null
        } catch (err) {
          console.warn('Photo storage upload failed; falling back to stock image:', err?.message || err)
          return null
        }
      })()

      const { draft, confidence } = await aiChatService.visionListing(uploadFile, { userId: authUser?.id })
      if (sessionId !== uploadSessionRef.current) return  // user cancelled / new upload

      if (!draft?.title) {
        setPendingUpload({
          kind: 'photo',
          error: language === 'es' ? 'No detecté un alimento en la foto. Prueba con otra imagen.' : "I couldn't detect a food item in that photo. Try another image.",
          filename: file.name,
        })
        appendLocalMessage({
          role: 'assistant',
          message: language === 'es' ? 'No pude identificar comida en esa foto. ¿Quieres intentar con otra?' : "I couldn't identify a food item in that photo. Want to try another?",
        })
        return
      }

      // Wait for the storage upload to settle, then attach the resulting URL
      // (or a deterministic stock photo) to the draft.
      const uploadedUrl = await uploadPromise
      if (sessionId !== uploadSessionRef.current) return

      const enrichedDraft = {
        ...draft,
        image_url: uploadedUrl || assignFoodImage(draft),
        // Carry profile community when vision did not set one so the
        // school selector is not stuck on Do Good Warehouse by accident.
        community_id: draft.community_id || authUser?.community_id || undefined,
        location: draft.location || authUser?.address || undefined,
      }
      const row = visionDraftToRow(enrichedDraft) || enrichedDraft

      setPendingUpload({ kind: 'photo', rows: [row], filename: file.name, confidence })
      appendLocalMessage({
        role: 'assistant',
        message: language === 'es'
          ? `Detecté: ${draft.title} (${draft.quantity} ${draft.unit}, ${draft.category}). Elige la escuela/comunidad abajo, revisa el borrador y confirma para publicar.`
          : `I detected: ${draft.title} (${draft.quantity} ${draft.unit}, ${draft.category}). Pick the school/community below, review the draft, and confirm to publish.`,
      })
    } catch (err) {
      if (sessionId !== uploadSessionRef.current) return
      const msg = err?.message || (language === 'es' ? 'Falló el análisis de la imagen.' : 'Vision request failed.')
      setPendingUpload({ kind: 'photo', error: msg, filename: file.name })
      appendLocalMessage({
        role: 'assistant',
        message: language === 'es' ? `No pude analizar la foto: ${msg}` : `I couldn't analyze that photo: ${msg}`,
        isError: true,
      })
    } finally {
      if (sessionId === uploadSessionRef.current) setUploadBusy(false)
    }
  }, [appendLocalMessage, authUser?.id, authUser?.community_id, authUser?.address, language])

  const handleCsvSelected = useCallback(async (e) => {
    const file = e.target.files?.[0]
    e.target.value = ''
    if (!file) return
    if (file.size > 2 * 1024 * 1024) {
      setPendingUpload({ kind: 'csv', error: language === 'es' ? 'El archivo CSV es demasiado grande (máx 2 MB).' : 'CSV too large (max 2 MB).', filename: file.name })
      appendLocalMessage({
        role: 'assistant',
        message: language === 'es' ? 'El archivo CSV es demasiado grande (máx 2 MB).' : 'CSV file is too large (max 2 MB).',
        isError: true,
      })
      return
    }
    appendLocalMessage({
      role: 'user',
      message: `📊 ${language === 'es' ? 'CSV subido' : 'CSV uploaded'}: ${file.name}`,
    })
    // Open a new upload session and stash its id so async callbacks can detect
    // cancellation / superseded uploads.
    uploadSessionRef.current += 1
    const sessionId = uploadSessionRef.current
    const isStale = () => sessionId !== uploadSessionRef.current
    setUploadBusy(true)
    try {
      const text = await new Promise((resolve, reject) => {
        const reader = new FileReader()
        reader.onload = (ev) => resolve(ev.target.result)
        reader.onerror = () => reject(new Error('Failed to read file'))
        reader.readAsText(file)
      })
      if (isStale()) return
      const { rows, errors } = parseListingsCsv(text)
      if (rows.length === 0) {
        const errMsg = errors[0] || (language === 'es' ? 'El CSV no tiene filas válidas.' : 'CSV had no valid rows.')
        setPendingUpload({ kind: 'csv', error: errMsg, filename: file.name, parseErrors: errors })
        appendLocalMessage({
          role: 'assistant',
          message: language === 'es' ? `No pude analizar ese CSV: ${errMsg}` : `I couldn't parse that CSV: ${errMsg}`,
          isError: true,
        })
        return
      }
      const rowsWithImages = assignImagestoRows(rows.slice(0, 100))
      setPendingUpload({ kind: 'csv', rows: rowsWithImages, filename: file.name, parseErrors: errors })
      appendLocalMessage({
        role: 'assistant',
        message: language === 'es'
          ? `Leí **${rows.length}** publicaciones del CSV${errors.length ? ` (${errors.length} filas omitidas)` : ''}. Dame un momento — la IA está rellenando huecos…`
          : `I parsed **${rows.length}** listings from your CSV${errors.length ? ` (${errors.length} rows skipped)` : ''}. Give me a sec — the AI is filling in gaps…`,
      })

      if (authUser?.id) {
        setPendingUpload(prev => prev ? { ...prev, enriching: true } : prev)
        try {
          const enrichment = await aiChatService.enrichListings(rowsWithImages.slice(0, 100), {
            userId: authUser.id,
            language,
          })
          if (isStale()) return
          if (enrichment?.rows?.length) {
            const enrichedWithImages = assignImagestoRows(enrichment.rows)
            setPendingUpload(prev => {
              if (!prev || prev.kind !== 'csv') return prev
              return {
                ...prev,
                rows: enrichedWithImages,
                enriching: false,
                enriched: true,
                filledLog: enrichment.filled || [],
                enrichSummary: enrichment.summary || '',
              }
            })
            const filledCount = (enrichment.filled || []).length
            const summary = enrichment.summary
              || (language === 'es'
                ? (filledCount
                    ? `Rellené huecos en ${filledCount} fila(s).`
                    : 'Tus filas se ven completas — sin huecos que rellenar.')
                : (filledCount
                    ? `Filled gaps on ${filledCount} row(s).`
                    : 'Your rows look complete — no gaps to fill.'))
            appendLocalMessage({
              role: 'assistant',
              message: language === 'es'
                ? `🪄 ${summary} **Revisa la vista previa y confirma** para crear las publicaciones, o cancela.`
                : `🪄 ${summary} **Review the preview and confirm** to create the listings, or cancel.`,
            })
          } else {
            setPendingUpload(prev => prev ? { ...prev, enriching: false } : prev)
            appendLocalMessage({
              role: 'assistant',
              message: language === 'es'
                ? 'Revisa la vista previa abajo y confirma para crear las publicaciones.'
                : 'Review the preview below and confirm to create the listings.',
            })
          }
        } catch {
          if (isStale()) return
          setPendingUpload(prev => prev ? { ...prev, enriching: false } : prev)
          appendLocalMessage({
            role: 'assistant',
            message: language === 'es'
              ? 'No pude rellenar huecos automáticamente, pero puedes confirmar como están.'
              : "I couldn't auto-fill gaps, but you can confirm as-is.",
          })
        }
      } else {
        appendLocalMessage({
          role: 'assistant',
          message: language === 'es'
            ? 'Revisa la vista previa abajo y confirma para crear las publicaciones.'
            : 'Review the preview below and confirm to create the listings.',
        })
      }
    } catch (err) {
      if (isStale()) return
      const msg = err?.message || (language === 'es' ? 'No pude leer el archivo.' : 'Could not read CSV file.')
      setPendingUpload({ kind: 'csv', error: msg, filename: file.name })
      appendLocalMessage({
        role: 'assistant',
        message: language === 'es' ? `Error leyendo CSV: ${msg}` : `Error reading CSV: ${msg}`,
        isError: true,
      })
    } finally {
      if (!isStale()) setUploadBusy(false)
    }
  }, [appendLocalMessage, language, authUser?.id])

  const confirmBulkCreate = useCallback(async () => {
    if (!pendingUpload?.rows?.length || uploadBusy) return
    if (!authUser?.id) {
      appendLocalMessage({
        role: 'assistant',
        message: language === 'es' ? 'Necesitas iniciar sesión para publicar.' : 'You need to sign in to publish listings.',
        isError: true,
      })
      return
    }
    const missingSchool = pendingUpload.rows.some(
      (r) => !r?.community_id && !String(r?.community_name || '').trim(),
    )
    if (missingSchool) {
      toast.error(
        language === 'es'
          ? 'Elige una escuela o comunidad para cada publicación.'
          : 'Choose a school or community for each listing.',
        { position: 'top-center' },
      )
      return
    }
    setUploadBusy(true)
    try {
      const rowsToCreate = pendingUpload.rows.map((r) => {
        const cleaned = sanitizeListingExpiry(r)
        return {
          ...cleaned,
          community_id: cleaned.community_id != null
            ? String(cleaned.community_id)
            : undefined,
          community_name: cleaned.community_name || undefined,
        }
      })
      const result = await aiChatService.bulkCreateListings(rowsToCreate, { userId: authUser.id })
      const { created, failed, ids, awaitingApproval } = result
      toast.success(
        language === 'es'
          ? awaitingApproval
            ? `✅ ${created} publicación${created === 1 ? '' : 'es'} enviada${created === 1 ? '' : 's'} para aprobación del admin${failed ? ` (${failed} fallaron)` : ''}`
            : `✅ ${created} publicación${created === 1 ? '' : 'es'} creada${created === 1 ? '' : 's'} correctamente${failed ? ` (${failed} fallaron)` : ''}`
          : awaitingApproval
            ? `✅ ${created} listing${created === 1 ? '' : 's'} submitted for admin approval${failed ? ` — ${failed} failed` : ''}`
            : `✅ ${created} listing${created === 1 ? '' : 's'} created successfully${failed ? ` — ${failed} failed` : ''}`,
        { autoClose: 5000, position: 'top-center' }
      )
      setPendingUpload(null)

      // Notify Find Food / map views to refresh immediately.
      window.dispatchEvent(new CustomEvent('foodShared'))

      // Build a rich context prompt so Nouri responds naturally to what just happened.
      const isEs = language === 'es'
      const itemNames = rowsToCreate
        .slice(0, 5)
        .map((r) => {
          const school = r.community_name || `community #${r.community_id}`
          return `${r.title} (${r.quantity} ${r.unit}, ${r.category}, under ${school})`
        })
        .join('; ')
      const moreItemsCount = rowsToCreate.length - 5
      const moreItems = moreItemsCount > 0
        ? (isEs ? ` y ${moreItemsCount} más` : ` and ${moreItemsCount} more`)
        : ''
      const failNote = failed
        ? (isEs ? ` (${failed} no se pudieron guardar)` : ` (${failed} could not be saved)`)
        : ''
      const kindLabel = pendingUpload.kind === 'photo'
        ? (isEs ? 'foto' : 'photo upload')
        : (isEs ? 'importación CSV' : 'bulk CSV upload')
      const idList = Array.isArray(ids) && ids.length
        ? ids.slice(0, 8).join(', ')
        : ''
      const approvalNote = awaitingApproval
        ? (isEs
          ? ' Estado: pendiente de aprobación del admin — NO digas que ya están en Find Food hasta que un admin apruebe.'
          : ' Status: pending admin approval — do NOT say they are live on Find Food until an admin approves.')
        : ''
      const prompt = isEs
        ? `[Acción ya completada por el sistema] El sistema acaba de guardar ${created} publicación${created === 1 ? '' : 'es'} de comida en la base de datos mediante ${kindLabel}${failNote}. Artículos: ${itemNames}${moreItems}.${idList ? ` IDs: ${idList}.` : ''}${approvalNote} NO llames a post_food_listing / create_food_listing / bulk_post_food_listings / bulk_import_listings — YA están guardadas. Si el usuario pide cambiar la comunidad/escuela, cantidad, título o dirección, usa update_food_listing con listing_id. Si pregunta por SUS publicaciones, usa get_user_listings (search_food_near_user oculta las propias). Solo responde en español: felicítame brevemente y ofrece 2-3 próximos pasos (cambiar comunidad, ver mis publicaciones pendientes, compartir más).`
        : `[Action already completed by the system] The system just saved ${created} food listing${created === 1 ? '' : 's'} to the database via ${kindLabel}${failNote}. Items: ${itemNames}${moreItems}.${idList ? ` Listing IDs: ${idList}.` : ''}${approvalNote} DO NOT call post_food_listing, create_food_listing, bulk_post_food_listings, or bulk_import_listings — they are ALREADY saved. If the user wants to change community/school, quantity, title, or address, call update_food_listing with listing_id. If they ask about THEIR listings, call get_user_listings (search_food_near_user hides the donor's own posts). Reply with a brief congratulations and 2–3 next steps (change community, review my pending listings, share more).`
      sendSilentMessage(prompt)
    } catch (err) {
      const msg = err?.message || (language === 'es' ? 'Falló la creación.' : 'Bulk create failed.')
      appendLocalMessage({
        role: 'assistant',
        message: language === 'es' ? `No pude crear las publicaciones: ${msg}` : `I couldn't create those listings: ${msg}`,
        isError: true,
      })
    } finally {
      setUploadBusy(false)
    }
  }, [pendingUpload, uploadBusy, authUser?.id, appendLocalMessage, sendSilentMessage, language])

  const updatePendingRow = useCallback((idx, patch) => {
    setPendingUpload(prev => {
      if (!prev?.rows) return prev
      const rows = prev.rows.map((r, i) => (i === idx ? { ...r, ...patch } : r))
      return { ...prev, rows }
    })
  }, [])

  const updatePendingRows = useCallback((indices, patch) => {
    const indexSet = new Set(Array.isArray(indices) ? indices : [])
    if (!indexSet.size || !patch || typeof patch !== 'object') return
    setPendingUpload(prev => {
      if (!prev?.rows) return prev
      const rows = prev.rows.map((r, i) => (indexSet.has(i) ? { ...r, ...patch } : r))
      return { ...prev, rows }
    })
  }, [])

  const removePendingRow = useCallback((idx) => {
    setPendingUpload(prev => {
      if (!prev?.rows) return prev
      const rows = prev.rows.filter((_, i) => i !== idx)
      if (rows.length === 0) return null
      return { ...prev, rows }
    })
  }, [])

  // ─── Voice recording via MediaRecorder + Whisper STT ───────
  const stopRecording = useCallback(() => {
    if (vadFrameRef.current) { cancelAnimationFrame(vadFrameRef.current); vadFrameRef.current = null }
    if (silenceTimerRef.current) { clearTimeout(silenceTimerRef.current); silenceTimerRef.current = null }
    if (mediaRecorderRef.current && mediaRecorderRef.current.state === 'recording') {
      mediaRecorderRef.current.stop()
    }
  }, [])

  const startVoiceListening = useCallback(async () => {
    setVoiceError(null)
    setVoiceTranscript('')
    audioChunksRef.current = []

    try {
      // Get mic stream (reuse existing or request new)
      if (!mediaStreamRef.current || !mediaStreamRef.current.active) {
        mediaStreamRef.current = await navigator.mediaDevices.getUserMedia({ audio: true })
      }
      const stream = mediaStreamRef.current

      // Set up audio analyser for VAD (voice activity detection)
      const audioCtx = new (window.AudioContext || window.webkitAudioContext)()
      const source = audioCtx.createMediaStreamSource(stream)
      const analyser = audioCtx.createAnalyser()
      analyser.fftSize = 512
      analyser.smoothingTimeConstant = 0.3
      source.connect(analyser)
      analyserRef.current = analyser

      // Prefer formats Whisper accepts reliably. Safari often lacks webm;
      // fall back to mp4 so we don't upload a mystery container labelled .webm.
      const mimeType = MediaRecorder.isTypeSupported('audio/webm;codecs=opus')
        ? 'audio/webm;codecs=opus'
        : MediaRecorder.isTypeSupported('audio/webm')
          ? 'audio/webm'
          : MediaRecorder.isTypeSupported('audio/mp4')
            ? 'audio/mp4'
            : MediaRecorder.isTypeSupported('audio/ogg;codecs=opus')
              ? 'audio/ogg;codecs=opus'
              : ''
      const recorder = mimeType
        ? new MediaRecorder(stream, { mimeType })
        : new MediaRecorder(stream)

      audioChunksRef.current = []

      recorder.ondataavailable = (e) => {
        if (e.data.size > 0) audioChunksRef.current.push(e.data)
      }

      recorder.onstop = async () => {
        // Clean up analyser
        if (vadFrameRef.current) { cancelAnimationFrame(vadFrameRef.current); vadFrameRef.current = null }
        source.disconnect()
        audioCtx.close().catch(() => {})
        setAudioLevel(0)

        const chunks = audioChunksRef.current
        if (!chunks.length) {
          setIsVoiceListening(false)
          // Hands-free re-arm produced no audio → the user is done talking.
          // Stand down to wake-word standby instead of looping.
          if (handsFreeRef.current) endHandsFreeTurnRef.current?.()
          return
        }

        const audioBlob = new Blob(chunks, { type: recorder.mimeType || 'audio/webm' })
        // Skip tiny recordings (empty breath / click). ~2KB is enough for a
        // short "yes"/"hi" in opus; the old 5KB floor dropped real speech.
        if (audioBlob.size < 1500) {
          setIsVoiceListening(false)
          if (handsFreeRef.current) endHandsFreeTurnRef.current?.()
          return
        }

        setIsVoiceListening(false)
        setVoiceTranscript(language === 'es' ? 'Procesando audio...' : 'Processing audio...')

        try {
          // Send raw audio to backend so Whisper + AI chat run through the
          // same server-side system (history, tool-calling, safeguards).
          await sendVoiceRef.current(audioBlob)
          setVoiceTranscript('')
        } catch (err) {
          console.error('[Voice] Backend voice processing failed:', err)
          setVoiceError(language === 'es' ? 'Error de voz' : 'Voice processing failed')
          setVoiceTranscript('')
          if (handsFreeRef.current) endHandsFreeTurnRef.current?.()
        }
      }

      recorder.start(250) // collect data every 250ms
      mediaRecorderRef.current = recorder
      setIsVoiceListening(true)

      // Voice Activity Detection — stop recording after silence
      let speechDetected = false
      let silenceStart = 0
      const SILENCE_THRESHOLD = 12  // RMS level below which = silence
      const SILENCE_DURATION = 2200 // ms of silence before auto-stop
      const MAX_DURATION = 30000    // max recording duration
      // If the user never starts speaking (e.g. a hands-free re-arm where they
      // had nothing to add), don't hold the mic for the full MAX_DURATION —
      // give up after a short grace window so we can stand down to standby.
      const NO_SPEECH_TIMEOUT = 9000
      const dataArray = new Uint8Array(analyser.frequencyBinCount)
      const startTime = Date.now()

      const checkAudio = () => {
        if (!mediaRecorderRef.current || mediaRecorderRef.current.state !== 'recording') return

        // Auto-stop at max duration
        if (Date.now() - startTime > MAX_DURATION) {
          stopRecording()
          return
        }

        // Auto-stop if no speech ever started within the grace window.
        if (!speechDetected && Date.now() - startTime > NO_SPEECH_TIMEOUT) {
          stopRecording()
          return
        }

        analyser.getByteFrequencyData(dataArray)
        let sum = 0
        for (let i = 0; i < dataArray.length; i++) sum += dataArray[i]
        const avg = sum / dataArray.length

        // Publish a normalized 0..1 level for the UI. The VAD threshold sits
        // around 15 and most speech peaks well under 80, so /80 keeps the
        // meter responsive without clipping immediately on loud sounds.
        setAudioLevel(Math.min(1, avg / 80))

        if (avg > SILENCE_THRESHOLD) {
          speechDetected = true
          silenceStart = 0
        } else if (speechDetected) {
          if (!silenceStart) silenceStart = Date.now()
          if (Date.now() - silenceStart > SILENCE_DURATION) {
            stopRecording()
            return
          }
        }

        vadFrameRef.current = requestAnimationFrame(checkAudio)
      }
      vadFrameRef.current = requestAnimationFrame(checkAudio)

    } catch (err) {
      console.error('[Voice] Mic access failed:', err)
      setIsVoiceListening(false)
      setVoiceError(
        err.name === 'NotAllowedError'
          ? (language === 'es' ? 'Permiso de micrófono denegado' : 'Microphone permission denied')
          : (language === 'es' ? 'No se pudo acceder al micrófono' : 'Could not access microphone')
      )
    }
  }, [language, stopRecording])

  const enterVoiceMode = useCallback(() => {
    setVoiceMode(true)
    voiceModeRef.current = true
  }, [])

  const exitVoiceMode = useCallback(() => {
    setVoiceMode(false)
    voiceModeRef.current = false
    setIsVoiceSpeaking(false)
    setIsVoiceListening(false)
    setVoiceError(null)
    setVoiceTranscript('')
    setTapToHear(null)
    setAudioLevel(0)
    stopRecording()
    // Release mic stream
    if (mediaStreamRef.current) {
      mediaStreamRef.current.getTracks().forEach(t => t.stop())
      mediaStreamRef.current = null
    }
    if (currentAudioRef.current) {
      currentAudioRef.current()
      currentAudioRef.current = null
    }
    if (typeof window !== 'undefined' && window.speechSynthesis) {
      window.speechSynthesis.cancel()
    }
  }, [stopRecording])

  // Interrupt AI speech (barge-in) — user must tap orb again to start listening
  const interruptSpeaking = useCallback(() => {
    if (currentAudioRef.current) {
      currentAudioRef.current()
      currentAudioRef.current = null
    }
    if (typeof window !== 'undefined' && window.speechSynthesis) {
      window.speechSynthesis.cancel()
    }
    setIsVoiceSpeaking(false)
    setTapToHear(null)
  }, [])

  // Orb tap: interrupt when speaking, start listening when idle
  const handleOrbTap = useCallback(() => {
    if (isVoiceSpeaking) {
      interruptSpeaking()
    } else if (isVoiceListening) {
      // User taps while listening → stop recording early (send what we have)
      stopRecording()
    } else if (!isLoading) {
      startVoiceListening()
    }
  }, [isVoiceSpeaking, isVoiceListening, isLoading, interruptSpeaking, stopRecording, startVoiceListening])

  // ─── Wake word ("Nouri") — hands-free activation ──────────────────────
  // Keep isVoiceSpeaking mirrored in a ref so the wake handlers (set up once)
  // can read the live value without re-binding.
  useEffect(() => { isVoiceSpeakingRef.current = isVoiceSpeaking }, [isVoiceSpeaking])

  // Stop the background wake-word recognizer and release its mic grab.
  const stopWakeListening = useCallback(() => {
    setWakeActive(false)
    const rec = wakeRecognitionRef.current
    wakeRecognitionRef.current = null
    if (rec) {
      try { rec.onend = null; rec.onerror = null; rec.onresult = null; rec.stop() } catch { /* already stopped */ }
    }
  }, [])

  // Start a continuous SpeechRecognition session that listens only for the
  // wake word. On a hit it hands off to the full Whisper voice pipeline.
  const startWakeListening = useCallback(() => {
    if (!wakeWordEnabledRef.current) return
    if (wakeRecognitionRef.current) return            // already running
    // Never contend with an active recording / voice turn for the mic.
    if (voiceModeRef.current || handsFreeRef.current) return
    if (mediaRecorderRef.current && mediaRecorderRef.current.state === 'recording') return
    const SR = window.SpeechRecognition || window.webkitSpeechRecognition
    if (!SR) return

    let rec
    try {
      rec = new SR()
    } catch {
      return
    }
    rec.continuous = true
    // Final results only — interim results flicker and re-fire on partial
    // ambient speech, which woke the assistant on words the user never said.
    rec.interimResults = false
    rec.lang = language === 'es' ? 'es-ES' : 'en-US'

    rec.onresult = (event) => {
      for (let i = event.resultIndex; i < event.results.length; i++) {
        const res = event.results[i]
        // Only act on a finalized phrase — never on an interim guess.
        if (!res.isFinal) continue
        const transcript = (res[0]?.transcript || '').toLowerCase()
        // Match only the distinctive "Nouri" spellings Whisper/STT produce.
        // Deliberately NOT matching bare "nour" / "nori" / "noor": those are
        // common words/names (e.g. "nori" seaweed on a food app) and caused
        // the assistant to wake — and then act — on unrelated conversation.
        if (/\b(nouri|nourie|nouree|noori|noury|nuri)\b/.test(transcript)) {
          try { rec.onend = null; rec.stop() } catch { /* noop */ }
          wakeRecognitionRef.current = null
          setWakeActive(false)
          triggerWakeRef.current?.()
          return
        }
      }
    }

    rec.onerror = (event) => {
      // Permission problems are terminal — turn the feature off so we don't
      // busy-loop restarting a recognizer the browser will keep rejecting.
      if (event.error === 'not-allowed' || event.error === 'service-not-allowed') {
        wakeWordEnabledRef.current = false
        setWakeWordEnabled(false)
        setWakeActive(false)
        wakeRecognitionRef.current = null
      }
      // 'no-speech' / 'aborted' / 'network' just end the session; onend
      // handles the restart.
    }

    rec.onend = () => {
      wakeRecognitionRef.current = null
      setWakeActive(false)
      // Auto-restart so "continuous" survives the browser's periodic resets,
      // but only while enabled and idle (not mid-conversation).
      if (
        wakeWordEnabledRef.current
        && !handsFreeRef.current
        && !voiceModeRef.current
        && (!mediaRecorderRef.current || mediaRecorderRef.current.state !== 'recording')
      ) {
        setTimeout(() => startWakeListeningRef.current?.(), 400)
      }
    }

    try {
      rec.start()
      wakeRecognitionRef.current = rec
      setWakeActive(true)
    } catch {
      // start() throws if a session is already live — ignore.
      wakeRecognitionRef.current = null
    }
  }, [language])

  // Wake detected → open the assistant, enter voice mode, and start listening
  // for the user's command. Debounced so a stray double-match can't double-fire.
  const triggerWake = useCallback(() => {
    const now = Date.now()
    if (now - wakeCooldownRef.current < 3000) return
    wakeCooldownRef.current = now
    handsFreeRef.current = true
    stopWakeListening()
    setIsOpen(true)
    if (!voiceModeRef.current) enterVoiceMode()
    // Let the voice overlay mount + the wake recognizer fully release the mic
    // before we grab it for recording.
    setTimeout(() => {
      if (!isVoiceSpeakingRef.current
          && (!mediaRecorderRef.current || mediaRecorderRef.current.state !== 'recording')) {
        startVoiceListening()
      }
    }, 450)
  }, [stopWakeListening, enterVoiceMode, startVoiceListening])

  // A hands-free turn ended (user fell silent). Stand down: leave voice mode,
  // release the mic, and resume background wake-word listening if still on.
  const endHandsFreeTurn = useCallback(() => {
    handsFreeRef.current = false
    if (voiceModeRef.current) exitVoiceMode()
    if (wakeWordEnabledRef.current) {
      setTimeout(() => startWakeListeningRef.current?.(), 700)
    }
  }, [exitVoiceMode])

  // Late-bind refs so the once-registered recognition handlers always call
  // the current callbacks.
  useEffect(() => { startWakeListeningRef.current = startWakeListening }, [startWakeListening])
  useEffect(() => { triggerWakeRef.current = triggerWake }, [triggerWake])
  useEffect(() => { endHandsFreeTurnRef.current = endHandsFreeTurn }, [endHandsFreeTurn])

  // Toggle handler — flips the feature and starts/stops the recognizer.
  const toggleWakeWord = useCallback(() => {
    setWakeWordEnabled((prev) => {
      const next = !prev
      wakeWordEnabledRef.current = next
      try { localStorage.setItem('dg.ai.wakeword', next ? '1' : '0') } catch { /* private mode */ }
      if (next) {
        if (!voiceModeRef.current
            && (!mediaRecorderRef.current || mediaRecorderRef.current.state !== 'recording')) {
          setTimeout(() => startWakeListeningRef.current?.(), 100)
        }
      } else {
        handsFreeRef.current = false
        stopWakeListening()
      }
      return next
    })
  }, [stopWakeListening])

  // Restore the saved preference on mount and arm the recognizer.
  useEffect(() => {
    let saved = '0'
    try { saved = localStorage.getItem('dg.ai.wakeword') || '0' } catch { /* noop */ }
    if (saved === '1' && wakeWordSupported) {
      setWakeWordEnabled(true)
      wakeWordEnabledRef.current = true
      setTimeout(() => startWakeListeningRef.current?.(), 300)
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  // Re-arm the mic for the user's follow-up after Nouri finishes speaking,
  // so a wake-triggered conversation flows turn-by-turn without any taps.
  useEffect(() => {
    const was = prevSpeakingRef.current
    prevSpeakingRef.current = isVoiceSpeaking
    if (was && !isVoiceSpeaking && voiceMode && handsFreeRef.current && !isLoading) {
      const t = setTimeout(() => {
        if (voiceModeRef.current
            && handsFreeRef.current
            && !isVoiceSpeakingRef.current
            && (!mediaRecorderRef.current || mediaRecorderRef.current.state !== 'recording')) {
          startVoiceListening()
        }
      }, 700)
      return () => clearTimeout(t)
    }
  }, [isVoiceSpeaking, voiceMode, isLoading, startVoiceListening])

  // Tear down the wake recognizer on unmount.
  useEffect(() => {
    return () => {
      wakeWordEnabledRef.current = false
      const rec = wakeRecognitionRef.current
      wakeRecognitionRef.current = null
      if (rec) { try { rec.onend = null; rec.stop() } catch { /* noop */ } }
    }
  }, [])

  // Voice mode and the wake recognizer both need the mic. Pause wake listening
  // whenever voice mode is open; resume it once the user returns to chat (and
  // wake word is still enabled and no hands-free turn is mid-flight).
  useEffect(() => {
    if (voiceMode) {
      stopWakeListening()
    } else if (wakeWordEnabledRef.current && !handsFreeRef.current) {
      const t = setTimeout(() => startWakeListeningRef.current?.(), 500)
      return () => clearTimeout(t)
    }
  }, [voiceMode, stopWakeListening])

  // Voice mode is manual — user taps the orb to start each recording

  // Unified guide sync + voice for every assistant reply
  const lastGuideMsgRef = useRef(null)
  useEffect(() => {
    if (!lastAssistantMessage || isLoading) return
    if (lastAssistantMessage.id === 'welcome') return
    if (lastAssistantMessage.id === lastGuideMsgRef.current) return
    lastGuideMsgRef.current = lastAssistantMessage.id

    const lang = language === 'es' ? 'es' : (a11ySettings.preferredLanguage || language || 'en')
    const shouldSpeak =
      voiceMode
      && !a11ySettings.preferTextOverVoice
      && lastAssistantMessage.id !== lastSpokenIdRef.current

    if (shouldSpeak) {
      lastSpokenIdRef.current = lastAssistantMessage.id
      if (mediaStreamRef.current) {
        mediaStreamRef.current.getAudioTracks().forEach((t) => { t.enabled = false })
      }
    }

    syncFromChat(lastAssistantMessage.message, { lang, speak: shouldSpeak })

    if (shouldSpeak) {
      const micTimer = setTimeout(() => {
        if (voiceModeRef.current && mediaStreamRef.current) {
          mediaStreamRef.current.getAudioTracks().forEach((t) => { t.enabled = true })
        }
      }, 3500)
      return () => clearTimeout(micTimer)
    }
  }, [voiceMode, lastAssistantMessage, isLoading, language, a11ySettings.preferTextOverVoice, syncFromChat])

  useEffect(() => {
    if (voiceMode) setIsVoiceSpeaking(guide.isSpeaking)
  }, [guide.isSpeaking, voiceMode])

  // Cleanup on unmount
  useEffect(() => {
    return () => {
      voiceModeRef.current = false
      if (vadFrameRef.current) cancelAnimationFrame(vadFrameRef.current)
      if (silenceTimerRef.current) clearTimeout(silenceTimerRef.current)
      if (mediaRecorderRef.current && mediaRecorderRef.current.state === 'recording') {
        try { mediaRecorderRef.current.stop() } catch {}
      }
      if (mediaStreamRef.current) {
        mediaStreamRef.current.getTracks().forEach(t => t.stop())
      }
      if (currentAudioRef.current) {
        currentAudioRef.current()
        currentAudioRef.current = null
      }
      cancelVoice()
    }
  }, [])

  const handleKeyDown = useCallback((e) => {
    // Autocomplete navigation takes priority when the dropdown is visible
    if (suggestionsOpen && filteredSuggestions.length > 0) {
      if (e.key === 'ArrowDown') {
        e.preventDefault()
        setSuggestionIndex((i) => (i + 1) % filteredSuggestions.length)
        return
      }
      if (e.key === 'ArrowUp') {
        e.preventDefault()
        setSuggestionIndex((i) => (i <= 0 ? filteredSuggestions.length - 1 : i - 1))
        return
      }
      if (e.key === 'Escape') {
        e.preventDefault()
        setSuggestionsOpen(false)
        setSuggestionIndex(-1)
        return
      }
      if (e.key === 'Tab' && suggestionIndex >= 0) {
        e.preventDefault()
        acceptSuggestion(filteredSuggestions[suggestionIndex])
        return
      }
      if (e.key === 'Enter' && !e.shiftKey && suggestionIndex >= 0) {
        e.preventDefault()
        acceptSuggestion(filteredSuggestions[suggestionIndex])
        return
      }
    }
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      if (!isLoading) handleSend()
    }
  }, [handleSend, isLoading, suggestionsOpen, filteredSuggestions, suggestionIndex, acceptSuggestion])

  // ─── Floating bubble (closed state) ──────
  if (!isOpen) {
    return (
      <div className="fixed right-4 sm:right-5 z-40 group fab-base" style={{ perspective: '600px' }}>
        {/* Speech bubble with "?" */}
        <div className="absolute -top-14 -left-12 animate-float-slow opacity-0 group-hover:opacity-100 transition-opacity duration-500 pointer-events-none">
          <div className="relative bg-white rounded-2xl px-3 py-2 shadow-lg border border-cyan-200/50">
            <span className="text-cyan-500 font-bold text-lg">?</span>
            {/* Speech tail */}
            <div className="absolute -bottom-2 right-4 w-4 h-4 bg-white border-r border-b border-cyan-200/50 transform rotate-45" />
          </div>
        </div>

        {/* Glow ring behind robot */}
        <div className="absolute inset-0 m-auto w-16 h-16 rounded-full bg-cyan-400/20 blur-xl animate-pulse-glow" />

        <button
          onClick={() => setIsOpen(true)}
          className="relative w-[68px] h-[68px] rounded-full focus:outline-none focus:ring-2 focus:ring-cyan-400 focus:ring-offset-2 animate-bob"
          aria-label="Open Nouri AI Assistant"
          style={{ transformStyle: 'preserve-3d' }}
        >
          {/* Robot SVG body */}
          <svg viewBox="0 0 100 100" className="w-full h-full drop-shadow-2xl" style={{ filter: 'drop-shadow(0 8px 16px rgba(0,200,255,0.3))' }}>
            {/* Body circle — glossy white */}
            <defs>
              <radialGradient id="bodyGrad" cx="40%" cy="35%" r="60%">
                <stop offset="0%" stopColor="#ffffff" />
                <stop offset="60%" stopColor="#f0f4f8" />
                <stop offset="100%" stopColor="#d1dbe6" />
              </radialGradient>
              <radialGradient id="eyeGrad" cx="50%" cy="40%" r="50%">
                <stop offset="0%" stopColor="#67e8f9" />
                <stop offset="100%" stopColor="#06b6d4" />
              </radialGradient>
              <radialGradient id="cheekGrad" cx="50%" cy="50%" r="50%">
                <stop offset="0%" stopColor="#22d3ee" stopOpacity="0.6" />
                <stop offset="100%" stopColor="#22d3ee" stopOpacity="0" />
              </radialGradient>
              <filter id="glow">
                <feGaussianBlur stdDeviation="2" result="coloredBlur" />
                <feMerge>
                  <feMergeNode in="coloredBlur" />
                  <feMergeNode in="SourceGraphic" />
                </feMerge>
              </filter>
            </defs>

            {/* Left antenna */}
            <line x1="30" y1="22" x2="22" y2="6" stroke="#b0bec5" strokeWidth="2.5" strokeLinecap="round" />
            <circle cx="22" cy="5" r="3.5" fill="url(#eyeGrad)" filter="url(#glow)" className="animate-antenna-glow" />

            {/* Right antenna */}
            <line x1="70" y1="22" x2="78" y2="6" stroke="#b0bec5" strokeWidth="2.5" strokeLinecap="round" />
            <circle cx="78" cy="5" r="3.5" fill="url(#eyeGrad)" filter="url(#glow)" className="animate-antenna-glow" />

            {/* Main body */}
            <circle cx="50" cy="52" r="36" fill="url(#bodyGrad)" stroke="#cfd8dc" strokeWidth="1" />

            {/* Screen / face visor */}
            <rect x="26" y="38" rx="12" ry="12" width="48" height="24" fill="#1e293b" opacity="0.85" />

            {/* Left eye — happy arc */}
            <path d="M35 53 Q38 46 41 53" stroke="url(#eyeGrad)" strokeWidth="3" strokeLinecap="round" fill="none" filter="url(#glow)" />
            {/* Right eye — happy arc */}
            <path d="M59 53 Q62 46 65 53" stroke="url(#eyeGrad)" strokeWidth="3" strokeLinecap="round" fill="none" filter="url(#glow)" />

            {/* Mouth — small smile */}
            <path d="M44 57 Q50 61 56 57" stroke="#67e8f9" strokeWidth="1.5" strokeLinecap="round" fill="none" opacity="0.7" />

            {/* Left ear / side detail */}
            <ellipse cx="14" cy="52" rx="5" ry="8" fill="#e2e8f0" stroke="#b0bec5" strokeWidth="0.8" />
            <ellipse cx="14" cy="52" rx="3" ry="5" fill="url(#eyeGrad)" opacity="0.4" />

            {/* Right ear / side detail */}
            <ellipse cx="86" cy="52" rx="5" ry="8" fill="#e2e8f0" stroke="#b0bec5" strokeWidth="0.8" />
            <ellipse cx="86" cy="52" rx="3" ry="5" fill="url(#eyeGrad)" opacity="0.4" />

            {/* Shine highlight */}
            <ellipse cx="38" cy="36" rx="10" ry="5" fill="white" opacity="0.5" />
          </svg>

          {/* Hover 3D tilt effect handled by CSS */}
          <div className="absolute inset-0 rounded-full ring-2 ring-cyan-300/0 group-hover:ring-cyan-300/40 transition-all duration-300" />
        </button>

        {/* Inline keyframes */}
        <style>{`
          @keyframes bob {
            0%, 100% { transform: translateY(0) rotateY(0deg); }
            25% { transform: translateY(-6px) rotateY(3deg); }
            50% { transform: translateY(-2px) rotateY(0deg); }
            75% { transform: translateY(-8px) rotateY(-3deg); }
          }
          @keyframes float-slow {
            0%, 100% { transform: translateY(0) scale(1); }
            50% { transform: translateY(-4px) scale(1.03); }
          }
          @keyframes pulse-glow {
            0%, 100% { opacity: 0.3; transform: scale(1); }
            50% { opacity: 0.6; transform: scale(1.3); }
          }
          @keyframes antenna-glow {
            0%, 100% { opacity: 0.7; }
            50% { opacity: 1; }
          }
          .animate-bob { animation: bob 3s ease-in-out infinite; }
          .animate-float-slow { animation: float-slow 2.5s ease-in-out infinite; }
          .animate-pulse-glow { animation: pulse-glow 2s ease-in-out infinite; }
          .animate-antenna-glow { animation: antenna-glow 1.5s ease-in-out infinite; }

          .group:hover .animate-bob {
            animation: bob 2s ease-in-out infinite;
            filter: drop-shadow(0 12px 24px rgba(0,200,255,0.45));
          }
        `}</style>
      </div>
    )
  }

  // ─── Chat panel (open state) ─────────────
  const panelClasses = isExpanded
    ? 'fixed inset-2 z-[1] sm:inset-4 md:inset-8'
    : 'fixed z-[1] inset-x-2 top-2 bottom-2 sm:inset-x-auto sm:left-auto sm:top-auto sm:bottom-20 sm:right-4 sm:w-[540px] sm:max-w-[calc(100vw-2rem)] sm:h-[820px] sm:max-h-[calc(100vh-6rem)]'

  return (
    <div className="fixed inset-0 z-[60]">
      {/* Backdrop — same focus pattern as the mobile main menu */}
      <div
        className="fixed inset-0 bg-black/50"
        onClick={closeAssistant}
        aria-hidden="true"
      />
      <div
        ref={panelRef}
        role="dialog"
        aria-modal="true"
        aria-label={language === 'es' ? 'Asistente Nouri' : 'Nouri AI Assistant'}
        className={`${panelClasses} flex flex-col rounded-2xl shadow-2xl shadow-[#2CABE3]/10 overflow-hidden transition-all duration-300 border border-[#2CABE3]/15 bg-white/75 backdrop-blur-xl`}
      >
      {/* Ambient orbs — matches Find Food / Share Food hero pages */}
      <div className="pointer-events-none absolute inset-0 overflow-hidden" aria-hidden="true">
        <div className="absolute -top-24 -left-24 w-72 h-72 rounded-full bg-[#2CABE3]/15 blur-3xl" />
        <div className="absolute top-1/4 -right-20 w-64 h-64 rounded-full bg-emerald-300/20 blur-3xl" />
        <div className="absolute bottom-0 left-1/4 w-48 h-48 rounded-full bg-[#2CABE3]/8 blur-2xl" />
      </div>

      {/* Header — z-30 so the ⋮ menu dropdown sits above message content */}
      <div className="relative z-30 flex-shrink-0 bg-white/60 backdrop-blur-md text-gray-900 px-4 py-3 flex items-center justify-between border-b border-[#2CABE3]/15">
        <div className="flex items-center gap-3">
          <div className="w-9 h-9 rounded-full bg-gradient-to-br from-[#2CABE3] to-emerald-500 flex items-center justify-center shadow-md shadow-[#2CABE3]/25">
            <svg viewBox="0 0 100 100" className="w-6 h-6">
              <circle cx="50" cy="52" r="36" fill="#f0f4f8" />
              <rect x="26" y="38" rx="12" ry="12" width="48" height="24" fill="#1e293b" opacity="0.85" />
              <path d="M35 53 Q38 46 41 53" stroke="#67e8f9" strokeWidth="4" strokeLinecap="round" fill="none" />
              <path d="M59 53 Q62 46 65 53" stroke="#67e8f9" strokeWidth="4" strokeLinecap="round" fill="none" />
            </svg>
          </div>
          <div>
            <h3 className="font-semibold text-sm text-gray-900 leading-tight">Nouri</h3>
            <p className="text-[#2CABE3] text-[10px] flex items-center gap-1.5 leading-tight mt-0.5">
              <span
                className="w-1.5 h-1.5 rounded-full bg-emerald-500 animate-pulse shadow-sm shadow-emerald-400/60"
                aria-hidden="true"
              />
              <span>
                {isAuthenticated
                  ? onlineToneLabel(language, getToneLabels(language)[tone] || tone)
                  : chatT(language, 'signInForFeatures')}
              </span>
            </p>
          </div>
        </div>

        <div className="flex items-center gap-1">
          <label className="sr-only" htmlFor="nouri-chat-language">{chatT(language, 'chatLanguage')}</label>
          <select
            id="nouri-chat-language"
            value={chatLang(language)}
            onChange={(e) => {
              const newLang = chatLang(e.target.value)
              if (newLang === chatLang(language)) return
              setLanguage(newLang)
              updateSetting('preferredLanguage', newLang)
              sendMessage(languageSwitchPrompt(newLang))
            }}
            className="text-[#2CABE3] hover:text-[#2299c7] text-[11px] font-semibold px-2 py-1 rounded-full bg-[#2CABE3]/10 border border-[#2CABE3]/20 hover:border-[#2CABE3]/35 max-w-[5.5rem] truncate"
            aria-label={chatT(language, 'chatLanguage')}
          >
            {CHAT_UI_LANGUAGES.map((code) => (
              <option key={code} value={code}>{CHAT_LANGUAGE_LABELS[code]}</option>
            ))}
          </select>

          {/* Menu */}
          <div className="relative z-40">
            <button
              onClick={() => setShowMenu(!showMenu)}
              className="text-[#2CABE3]/70 hover:text-[#2CABE3] p-1 rounded hover:bg-[#2CABE3]/10 transition-colors"
              aria-label="Chat menu"
              aria-expanded={showMenu}
            >
              <svg xmlns="http://www.w3.org/2000/svg" className="h-5 w-5" viewBox="0 0 20 20" fill="currentColor">
                <path d="M10 6a2 2 0 110-4 2 2 0 010 4zM10 12a2 2 0 110-4 2 2 0 010 4zM10 18a2 2 0 110-4 2 2 0 010 4z" />
              </svg>
            </button>
            {showMenu && (
              <div className="absolute right-0 top-full mt-1 bg-white/95 rounded-lg shadow-xl border border-[#2CABE3]/15 py-1 w-52 z-50 backdrop-blur-md">
                <div className="px-2 pt-1 pb-0.5">
                  <p className="text-[10px] uppercase tracking-wider text-gray-400 px-2 py-1">
                    {chatT(language, 'conversationTone')}
                  </p>
                  {AI_TONE_OPTIONS.map((t) => {
                    const labels = getToneLabels(language)
                    const active = tone === t
                    return (
                      <button
                        key={t}
                        type="button"
                        onClick={() => { setTone(t); setShowMenu(false) }}
                        className={`w-full text-left px-4 py-1.5 text-sm transition-colors ${
                          active
                            ? 'text-[#2CABE3] bg-[#2CABE3]/10'
                            : 'text-gray-700 hover:bg-[#2CABE3]/5 hover:text-[#2CABE3]'
                        }`}
                      >
                        {active ? '✓ ' : ''}{labels[t]}
                      </button>
                    )
                  })}
                </div>
                <div className="border-t border-[#2CABE3]/10 my-1" />
                <button
                  onClick={handleClearConversation}
                  className="w-full text-left px-4 py-2 text-sm text-gray-700 hover:bg-[#2CABE3]/5 hover:text-[#2CABE3] transition-colors"
                >
                  🗑️ Clear conversation
                </button>
                <button
                  onClick={() => { setIsExpanded(!isExpanded); setShowMenu(false) }}
                  className="w-full text-left px-4 py-2 text-sm text-gray-700 hover:bg-[#2CABE3]/5 hover:text-[#2CABE3] transition-colors"
                >
                  {isExpanded ? '🗗 Compact view' : '⬜ Full screen'}
                </button>
              </div>
            )}
          </div>

          {/* Expand / collapse */}
          <button
            onClick={() => setIsExpanded(!isExpanded)}
            className="text-[#2CABE3]/70 hover:text-[#2CABE3] p-1 rounded hover:bg-[#2CABE3]/10 transition-colors hidden md:block"
            aria-label={isExpanded ? 'Compact view' : 'Expand'}
          >
            {isExpanded ? (
              <svg xmlns="http://www.w3.org/2000/svg" className="h-4 w-4" viewBox="0 0 20 20" fill="currentColor">
                <path fillRule="evenodd" d="M5 10a1 1 0 011-1h8a1 1 0 110 2H6a1 1 0 01-1-1z" clipRule="evenodd" />
              </svg>
            ) : (
              <svg xmlns="http://www.w3.org/2000/svg" className="h-4 w-4" viewBox="0 0 20 20" fill="currentColor">
                <path fillRule="evenodd" d="M3 4a1 1 0 011-1h4a1 1 0 010 2H6.414l2.293 2.293a1 1 0 11-1.414 1.414L5 6.414V8a1 1 0 01-2 0V4zm9 1a1 1 0 010-2h4a1 1 0 011 1v4a1 1 0 11-2 0V6.414l-2.293 2.293a1 1 0 11-1.414-1.414L13.586 5H12zm-9 7a1 1 0 012 0v1.586l2.293-2.293a1 1 0 111.414 1.414L5.414 15H7a1 1 0 110 2H3a1 1 0 01-1-1v-4zm13.707.707a1 1 0 00-1.414-1.414L13 13.586V12a1 1 0 10-2 0v4a1 1 0 001 1h4a1 1 0 100-2h-1.586l2.293-2.293z" clipRule="evenodd" />
              </svg>
            )}
          </button>

          {/* Close */}
          <button
            onClick={closeAssistant}
            className="text-gray-400 hover:text-red-500 p-1 rounded hover:bg-red-50 transition-colors"
            aria-label="Close chat"
          >
            <svg xmlns="http://www.w3.org/2000/svg" className="h-5 w-5" viewBox="0 0 20 20" fill="currentColor">
              <path fillRule="evenodd" d="M4.293 4.293a1 1 0 011.414 0L10 8.586l4.293-4.293a1 1 0 111.414 1.414L11.414 10l4.293 4.293a1 1 0 01-1.414 1.414L10 11.414l-4.293 4.293a1 1 0 01-1.414-1.414L8.586 10 4.293 5.707a1 1 0 010-1.414z" clipRule="evenodd" />
            </svg>
          </button>
        </div>
      </div>

      {/* ─── Voice Mode (ChatGPT-like immersive voice UI) ─────── */}
      {voiceMode ? (
        <div
          className="relative z-0 flex-1 flex flex-col items-center justify-between py-5 px-6 overflow-hidden bg-gradient-to-b from-[#2CABE3]/5 via-white/40 to-emerald-50/30 backdrop-blur-sm"
          role="region"
          aria-label={language === 'es' ? 'Modo de voz' : 'Voice mode'}
        >
          {/* Animated aurora behind everything — keeps the surface alive
              even when idle so the mode never looks frozen. */}
          <div className="voice-aurora" aria-hidden="true" />

          {/* ─── Top bar: exit + language pill + help hint ─── */}
          <div className="relative w-full flex items-center justify-between gap-2 z-10">
            <button
              onClick={exitVoiceMode}
              className="inline-flex items-center gap-1.5 text-xs text-slate-600 hover:text-slate-900 px-2.5 py-1.5 rounded-lg hover:bg-slate-900/5 transition-all focus:outline-none focus-visible:ring-2 focus-visible:ring-cyan-400/50"
              aria-label={language === 'es' ? 'Salir del modo de voz' : 'Exit voice mode'}
            >
              <svg xmlns="http://www.w3.org/2000/svg" className="h-4 w-4" viewBox="0 0 20 20" fill="currentColor" aria-hidden="true">
                <path fillRule="evenodd" d="M9.707 16.707a1 1 0 01-1.414 0l-6-6a1 1 0 010-1.414l6-6a1 1 0 011.414 1.414L5.414 9H17a1 1 0 110 2H5.414l4.293 4.293a1 1 0 010 1.414z" clipRule="evenodd" />
              </svg>
              {language === 'es' ? 'Volver al chat' : 'Back to chat'}
            </button>

            {/* Language pill — confirms which language Whisper is listening for. */}
            <span
              className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full bg-slate-900/5 ring-1 ring-slate-300/60 text-[10px] font-semibold tracking-wider uppercase text-slate-700 backdrop-blur-sm"
              title={language === 'es' ? 'Idioma del modo de voz' : 'Voice mode language'}
            >
              <span aria-hidden="true">{language === 'es' ? '🇪🇸' : '🇺🇸'}</span>
              {language === 'es' ? 'Español' : 'English'}
            </span>

            {/* Wake-word toggle — enable always-listening "Nouri" from voice mode. */}
            {wakeWordSupported && (
              <button
                onClick={toggleWakeWord}
                className={`inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-[10px] font-semibold tracking-wide ring-1 transition-all focus:outline-none focus-visible:ring-2 focus-visible:ring-emerald-400/50 ${
                  wakeWordEnabled
                    ? 'bg-emerald-500/15 ring-emerald-500/50 text-emerald-800'
                    : 'bg-slate-900/5 ring-slate-300/70 text-slate-600 hover:text-emerald-800'
                }`}
                title={
                  wakeWordEnabled
                    ? (language === 'es' ? 'Manos libres activado — di “Nouri”' : 'Hands-free on — say “Nouri”')
                    : (language === 'es' ? 'Activar manos libres “Nouri”' : 'Enable hands-free “Nouri”')
                }
                aria-pressed={wakeWordEnabled}
              >
                <i className="fas fa-assistive-listening-systems" aria-hidden="true" />
                {wakeWordEnabled
                  ? (language === 'es' ? 'Manos libres' : 'Hands-free')
                  : '“Nouri”'}
              </button>
            )}
          </div>

          {/* ─── Center: Animated Orb ─── */}
          <div className="relative flex-1 flex items-center justify-center z-10">
            <button
              onClick={handleOrbTap}
              className="relative focus:outline-none focus-visible:ring-4 focus-visible:ring-cyan-400/30 rounded-full group"
              aria-label={
                isVoiceSpeaking
                  ? (language === 'es' ? 'Toca para interrumpir' : 'Tap to interrupt')
                  : isVoiceListening
                    ? (language === 'es' ? 'Toca para enviar' : 'Tap to send now')
                    : (language === 'es' ? 'Toca para hablar' : 'Tap to speak')
              }
            >
              {/* Listening rings (now properly animated thanks to main.css) */}
              {isVoiceListening && (
                <>
                  <div className="absolute inset-0 -m-8 rounded-full border-2 border-blue-400/40 animate-voice-ring-1 pointer-events-none" />
                  <div className="absolute inset-0 -m-14 rounded-full border border-blue-400/20 animate-voice-ring-2 pointer-events-none" />
                  <div className="absolute inset-0 -m-20 rounded-full border border-blue-400/10 animate-voice-ring-3 pointer-events-none" />
                </>
              )}

              {/* Speaking ripple */}
              {isVoiceSpeaking && (
                <>
                  <div className="absolute inset-0 -m-6 rounded-full border-2 border-teal-400/40 animate-voice-speak-ring-1 pointer-events-none" />
                  <div className="absolute inset-0 -m-10 rounded-full border border-teal-400/20 animate-voice-speak-ring-2 pointer-events-none" />
                </>
              )}

              {/* Glow */}
              <div
                className={`absolute -inset-8 rounded-full blur-2xl transition-all duration-700 pointer-events-none ${
                  isVoiceSpeaking ? 'bg-teal-500/30' : isVoiceListening ? 'bg-blue-500/30' : isLoading ? 'bg-violet-500/25' : 'bg-slate-600/10'
                }`}
              />

              {/* Main orb — scale subtly tracks live mic level while listening. */}
              <div
                className={`relative w-36 h-36 rounded-full transition-all duration-300 flex items-center justify-center cursor-pointer ${
                  isVoiceListening
                    ? 'bg-gradient-to-br from-blue-400 via-indigo-500 to-violet-600 shadow-[0_0_60px_rgba(99,102,241,0.45)]'
                    : isVoiceSpeaking
                      ? 'bg-gradient-to-br from-teal-400 via-cyan-500 to-blue-500 shadow-[0_0_60px_rgba(20,184,166,0.45)] scale-110'
                      : isLoading
                        ? 'bg-gradient-to-br from-violet-400 via-purple-500 to-fuchsia-500 shadow-[0_0_40px_rgba(168,85,247,0.35)]'
                        : 'bg-gradient-to-br from-slate-500 via-slate-600 to-slate-700 shadow-[0_0_20px_rgba(100,116,139,0.25)] scale-95 group-hover:scale-100'
                }`}
                style={
                  isVoiceListening
                    ? { transform: `scale(${(1.05 + audioLevel * 0.18).toFixed(3)})` }
                    : undefined
                }
              >
                {/* Gloss */}
                <div className="absolute inset-0 rounded-full bg-gradient-to-t from-transparent via-transparent to-white/15 pointer-events-none" />

                {/* Icon / visual based on state */}
                <div className="relative z-10 flex items-center justify-center">
                  {isVoiceSpeaking ? (
                    <div className="flex items-end gap-[3px] h-8" aria-hidden="true">
                      {[0,1,2,3,4].map(i => (
                        <span
                          key={i}
                          className="w-1.5 bg-white/90 rounded-full animate-voice-bar"
                          style={{ animationDelay: `${i * 0.12}s` }}
                        />
                      ))}
                    </div>
                  ) : isLoading ? (
                    <div className="flex items-center gap-2" aria-hidden="true">
                      {[0,1,2].map(i => (
                        <span
                          key={i}
                          className="w-2.5 h-2.5 bg-white/90 rounded-full animate-voice-dot"
                          style={{ animationDelay: `${i * 0.18}s` }}
                        />
                      ))}
                    </div>
                  ) : (
                    <svg
                      xmlns="http://www.w3.org/2000/svg"
                      className={`h-12 w-12 transition-colors ${
                        isVoiceListening ? 'text-white/95' : 'text-white/55 group-hover:text-white/85'
                      }`}
                      viewBox="0 0 24 24"
                      fill="currentColor"
                      aria-hidden="true"
                    >
                      <path d="M12 14c1.66 0 3-1.34 3-3V5c0-1.66-1.34-3-3-3S9 3.34 9 5v6c0 1.66 1.34 3 3 3z" />
                      <path d="M17 11c0 2.76-2.24 5-5 5s-5-2.24-5-5H5c0 3.53 2.61 6.43 6 6.92V21h2v-3.08c3.39-.49 6-3.39 6-6.92h-2z" />
                    </svg>
                  )}
                </div>
              </div>
            </button>
          </div>

          {/* ─── Live audio meter — visible only while listening ─── */}
          <div className="relative z-10 h-6 flex items-end justify-center gap-1 mb-1" aria-hidden="true">
            {isVoiceListening && [0, 1, 2, 3, 4, 5, 6].map((i) => {
              // Each bar tracks audioLevel with a slight per-index curve so
              // the row reads like a waveform instead of a flat block.
              const phase = Math.sin((Date.now() / 180) + i * 0.7) * 0.5 + 0.5
              const h = Math.max(4, (audioLevel * 22 + 3) * (0.4 + phase * 0.6))
              return (
                <span
                  key={i}
                  className="w-[3px] rounded-full bg-blue-400/80 transition-[height] duration-75"
                  style={{ height: `${h}px` }}
                />
              )
            })}
          </div>

          {/* ─── Bottom: persistent transcript + status + end button ─── */}
          <div className="relative flex flex-col items-center gap-3 z-10 w-full">
            {/* "Tap to hear" — shown when the browser blocked autoplay (iOS
                Safari requires a user gesture). Tapping replays the audio
                from inside a real tap, which is allowed. */}
            {tapToHear && (
              <button
                type="button"
                onClick={() => { try { tapToHear() } catch { /* noop */ } }}
                className="inline-flex items-center gap-2 px-4 py-2 rounded-full text-sm font-medium bg-teal-500/15 text-teal-200 ring-1 ring-teal-400/40 hover:bg-teal-500/25 transition-colors"
                aria-label={language === 'es' ? 'Toca para escuchar la respuesta' : 'Tap to hear the response'}
              >
                <svg xmlns="http://www.w3.org/2000/svg" className="h-4 w-4" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true">
                  <path d="M3 9v6h4l5 5V4L7 9H3zm13.5 3c0-1.77-1.02-3.29-2.5-4.03v8.05c1.48-.73 2.5-2.25 2.5-4.02zM14 3.23v2.06c2.89.86 5 3.54 5 6.71s-2.11 5.85-5 6.71v2.06c4.01-.91 7-4.49 7-8.77s-2.99-7.86-7-8.77z" />
                </svg>
                {language === 'es' ? 'Toca para escuchar' : 'Tap to hear'}
              </button>
            )}
            {/* Transcript region — fixed min-height so layout doesn't jump
                when text appears/disappears. */}
            <div className="min-h-[40px] flex items-center justify-center px-4">
              {voiceTranscript ? (
                <p
                  className={`text-sm italic text-center max-w-[300px] leading-snug transition-colors duration-300 ${
                    isVoiceListening ? 'text-white/90' : 'text-slate-600'
                  }`}
                  aria-live="polite"
                >
                  &ldquo;{voiceTranscript}&rdquo;
                </p>
              ) : (
                <p className="text-[12px] text-slate-500 italic text-center max-w-[280px]">
                  {isVoiceListening
                    ? (language === 'es' ? 'Te estoy escuchando...' : 'I&apos;m listening...')
                    : isVoiceSpeaking
                      ? (language === 'es' ? 'Habla cuando quieras interrumpir' : 'Speak any time to interrupt')
                      : isLoading
                        ? ''
                        : (language === 'es' ? 'Tu transcripción aparecerá aquí' : 'Your transcript will appear here')}
                </p>
              )}
            </div>

            {/* Status pill — replaces the bare uppercase text. */}
            <div
              className={`inline-flex items-center gap-2 px-3 py-1.5 rounded-full text-[11px] font-medium tracking-wide transition-all duration-300 ring-1 ${
                voiceError
                  ? 'bg-rose-500/10 text-rose-700 ring-rose-500/40'
                  : isVoiceSpeaking
                    ? 'bg-teal-500/10 text-teal-800 ring-teal-500/40'
                    : isLoading
                      ? 'bg-violet-500/10 text-violet-800 ring-violet-500/40'
                      : isVoiceListening
                        ? 'bg-blue-500/10 text-blue-700 ring-blue-500/40'
                        : 'bg-slate-900/5 text-slate-600 ring-slate-300/70'
              }`}
              role="status"
              aria-live="polite"
            >
              <span
                className={`h-1.5 w-1.5 rounded-full ${
                  voiceError ? 'bg-rose-400' : isVoiceSpeaking ? 'bg-teal-400 animate-pulse' : isLoading ? 'bg-violet-400 animate-pulse' : isVoiceListening ? 'bg-blue-400 animate-pulse' : 'bg-slate-500'
                }`}
                aria-hidden="true"
              />
              {voiceError
                ? voiceError
                : isVoiceSpeaking
                  ? (language === 'es' ? 'Hablando — toca para interrumpir' : 'Speaking — tap to interrupt')
                  : isLoading
                    ? (language === 'es' ? 'Pensando...' : 'Thinking...')
                    : isVoiceListening
                      ? (language === 'es' ? 'Escuchando — toca para enviar' : 'Listening — tap to send')
                      : (language === 'es' ? 'Toca el orbe para hablar' : 'Tap the orb to speak')}
            </div>

            {/* End voice mode */}
            <button
              onClick={exitVoiceMode}
              className="group/end inline-flex items-center gap-2 pl-3 pr-4 h-12 rounded-full bg-rose-500/15 hover:bg-rose-500 border border-rose-500/30 hover:border-rose-500 text-rose-300 hover:text-white transition-all hover:scale-[1.02] active:scale-95 shadow-lg shadow-rose-500/10 hover:shadow-rose-500/30 focus:outline-none focus-visible:ring-2 focus-visible:ring-rose-400/50"
              aria-label={language === 'es' ? 'Terminar conversación de voz' : 'End voice conversation'}
            >
              <span className="inline-flex h-7 w-7 items-center justify-center rounded-full bg-rose-500/25 group-hover/end:bg-white/15">
                <svg xmlns="http://www.w3.org/2000/svg" className="h-4 w-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
                  <line x1="18" y1="6" x2="6" y2="18" />
                  <line x1="6" y1="6" x2="18" y2="18" />
                </svg>
              </span>
              <span className="text-[12px] font-semibold tracking-wide">
                {language === 'es' ? 'Terminar' : 'End conversation'}
              </span>
            </button>
          </div>

        </div>
      ) : (
      <>
      {/* Messages area */}
      <div className="flex-1 relative min-h-0 z-0">
        <div
          ref={messagesContainerRef}
          className="absolute inset-0 overflow-y-auto px-4 py-3 nourish-scrollbar"
          role="log"
          aria-label="Chat messages"
          aria-live="polite"
        >
          {/* WelcomeHero — onboarding surface for empty/first-run state.
              The default INITIAL_MESSAGE bubble is suppressed when the hero
              is showing so we don't say "Hi" twice. */}
          {messages.length <= 1 && !isLoading && (
            <WelcomeHero
              language={language}
              userName={authUser?.name?.split(' ')?.[0] || null}
              onPromptClick={handleQuickAction}
              communityRole={communityRole}
            />
          )}

          {(() => {
            // Find the index of the last non-error, non-welcome assistant
            // message so we can render the Regenerate affordance on exactly
            // that one (avoids cluttering every assistant bubble).
            let lastAssistantIdx = -1
            for (let i = messages.length - 1; i >= 0; i--) {
              const m = messages[i]
              if (m.role === 'assistant' && !m.isError && m.id !== 'welcome') {
                lastAssistantIdx = i
                break
              }
            }
            return messages.map((msg, idx) => {
              // Hide the default "Hi I'm Nouri" welcome bubble while the
              // WelcomeHero is showing — the hero already greets the user.
              if (messages.length <= 1 && msg.id === 'welcome') return null

              // Day separator: show whenever the calendar date changes between
              // two consecutive messages (or above the first message).
              let separator = null
              const sepLabel = formatSeparator(msg.timestamp, language)
              if (idx === 0 && sepLabel) {
                separator = <DateSeparator key={`sep-${idx}`} label={sepLabel} />
              } else if (idx > 0) {
                const prev = messages[idx - 1]
                if (prev?.timestamp && msg.timestamp) {
                  const prevDay = new Date(prev.timestamp).toDateString()
                  const curDay = new Date(msg.timestamp).toDateString()
                  if (prevDay !== curDay && sepLabel) {
                    separator = <DateSeparator key={`sep-${idx}`} label={sepLabel} />
                  }
                }
              }

              return (
                <React.Fragment key={msg.id}>
                  {separator}
                  <MessageBubble
                    msg={msg}
                    onFeedback={submitFeedback}
                    language={language}
                    onSuggestionClick={handleQuickAction}
                    onAttachPhoto={() => photoInputRef.current?.click()}
                    onConfirmAction={confirmPendingAction}
                    isLoading={isLoading}
                    currentUser={authUser}
                    allowedCommunityIds={allowedCommunityIds}
                    onRetry={retryMessage}
                    onRegenerate={regenerateLast}
                    showRegenerate={idx === lastAssistantIdx}
                    showSuggestionChips={idx === lastAssistantIdx && !isLoading}
                  />
                </React.Fragment>
              )
            })
          })()}

          {isLoading && <TypingIndicator />}

          <div ref={messagesEndRef} />
        </div>

        {/* Floating jump-to-latest pill */}
        <ScrollToBottomPill
          visible={showScrollPill}
          onClick={jumpToLatest}
          language={language}
        />
      </div>

      {/* Input area */}
      {pendingUpload && (
        <BulkUploadPreview
          pending={pendingUpload}
          busy={uploadBusy}
          language={language}
          preferredCommunityId={authUser?.community_id}
          preferredLocation={authUser?.address}
          onCancel={cancelPendingUpload}
          onConfirm={confirmBulkCreate}
          onUpdateRow={updatePendingRow}
          onUpdateRows={updatePendingRows}
          onRemoveRow={removePendingRow}
        />
      )}

      {/* Hidden file inputs */}
      <input
        ref={photoInputRef}
        type="file"
        accept="image/*"
        className="hidden"
        onChange={handlePhotoSelected}
        aria-hidden="true"
        tabIndex={-1}
      />
      <input
        ref={inlinePhotoInputRef}
        type="file"
        accept="image/*"
        multiple
        className="hidden"
        onChange={handleInlinePhotoSelected}
        aria-hidden="true"
        tabIndex={-1}
      />
      <input
        ref={csvInputRef}
        type="file"
        accept=".csv,text/csv,application/vnd.ms-excel"
        className="hidden"
        onChange={handleCsvSelected}
        aria-hidden="true"
        tabIndex={-1}
      />

      {/* Input area */}
      <form onSubmit={handleSend} className="relative z-0 border-t border-[#2CABE3]/15 px-3 pt-2.5 pb-2 flex flex-col gap-1 flex-shrink-0 bg-white/60 backdrop-blur-md">
        {pendingChatPhotos.length > 0 && (
          <div className="flex gap-2 overflow-x-auto pb-1 nourish-scrollbar-h" aria-label={language === 'es' ? 'Fotos adjuntas' : 'Attached photos'}>
            {pendingChatPhotos.map((photo) => (
              <div key={photo.id} className="relative flex-shrink-0 w-14 h-14 rounded-lg overflow-hidden border border-[#2CABE3]/25 bg-white shadow-sm">
                <img
                  src={photo.previewUrl}
                  alt={photo.name || 'attachment'}
                  className="w-full h-full object-cover"
                />
                <button
                  type="button"
                  onClick={() => removePendingChatPhoto(photo.id)}
                  disabled={uploadBusy || isLoading}
                  className="absolute top-0.5 right-0.5 w-5 h-5 rounded-full bg-black/60 text-white text-[10px] leading-none flex items-center justify-center hover:bg-rose-600 disabled:opacity-40"
                  aria-label={language === 'es' ? 'Quitar foto' : 'Remove photo'}
                >
                  ×
                </button>
              </div>
            ))}
          </div>
        )}
        {/* Quick-suggestion chip rail — starter chips on a new conversation;
            mid-conversation shows the latest backend contextual chips (prechips). */}
        {railChips.length > 0 && (
          <div
            role="toolbar"
            aria-label={language === 'es' ? 'Sugerencias rápidas' : 'Quick suggestions'}
            className="flex gap-1.5 overflow-x-auto pb-1 nourish-scrollbar-h"
          >
            {railChips.map((chip, i) => {
              const label = typeof chip === 'string'
                ? chip
                : (chip?.label || chip?.message || '')
              const message = typeof chip === 'string'
                ? chip
                : (chip?.message || chip?.label || '')
              if (!label) return null
              return (
                <button
                  key={`${label}-${i}`}
                  type="button"
                  onClick={() => handleQuickAction(message)}
                  disabled={isLoading}
                  className="whitespace-nowrap flex-shrink-0 text-[11px] px-2.5 py-1 rounded-full border border-[#2CABE3]/30 bg-white/90 text-[#1a7a9e] font-medium hover:bg-[#2CABE3]/10 hover:border-[#2CABE3]/50 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
                >
                  {label}
                </button>
              )
            })}
          </div>
        )}

        <div className="flex items-end gap-2">
          {/* Attachments menu — donor-only (list food / listing photo / CSV).
              Recipients claim food and don't need file uploads in chat. */}
          {canAttachFiles && (
          <div ref={attachMenuRef} className="relative flex-shrink-0">
            <button
              type="button"
              onClick={() => setShowAttachMenu(v => !v)}
              disabled={isLoading || uploadBusy}
              className={`inline-flex items-center justify-center w-9 h-9 rounded-full transition-all border ${
                showAttachMenu
                  ? 'bg-[#2CABE3]/15 text-[#2CABE3] border-[#2CABE3]/30 rotate-45'
                  : 'bg-white/80 text-gray-600 border-[#2CABE3]/15 hover:bg-[#2CABE3]/10 hover:text-[#2CABE3] hover:border-[#2CABE3]/30'
              } disabled:opacity-40 disabled:cursor-not-allowed`}
              title={language === 'es' ? 'Adjuntar' : 'Attach'}
              aria-label={language === 'es' ? 'Adjuntar foto o CSV' : 'Attach photo or CSV'}
              aria-expanded={showAttachMenu}
              aria-haspopup="menu"
            >
              <i className="fas fa-plus text-sm" aria-hidden="true" />
            </button>

            {showAttachMenu && (
              <div
                role="menu"
                className="absolute bottom-full left-0 mb-2 min-w-[200px] rounded-xl border border-[#2CABE3]/15 bg-white/95 backdrop-blur-md shadow-xl shadow-[#2CABE3]/10 overflow-hidden z-30 animate-fade-in"
              >
                <button
                  type="button"
                  role="menuitem"
                  onClick={() => { setShowAttachMenu(false); triggerPhotoUpload() }}
                  className="w-full flex items-center gap-3 px-3 py-2.5 text-sm text-gray-700 hover:bg-[#2CABE3]/5 hover:text-[#2CABE3] transition-colors"
                >
                  <span className="inline-flex w-8 h-8 rounded-lg bg-fuchsia-500/15 text-fuchsia-600 items-center justify-center">
                    <i className="fas fa-camera text-[13px]" aria-hidden="true" />
                  </span>
                  <span className="flex-1 text-left">
                    <span className="block font-medium leading-tight">
                      {language === 'es' ? 'Foto → publicar' : 'Photo → list food'}
                    </span>
                    <span className="block text-[10px] text-gray-500 leading-tight mt-0.5">
                      {language === 'es' ? 'IA detecta artículos' : 'AI auto-detects items'}
                    </span>
                  </span>
                </button>
                <button
                  type="button"
                  role="menuitem"
                  onClick={() => { setShowAttachMenu(false); triggerInlinePhotoUpload() }}
                  className="w-full flex items-center gap-3 px-3 py-2.5 text-sm text-gray-700 hover:bg-[#2CABE3]/5 hover:text-[#2CABE3] transition-colors border-t border-[#2CABE3]/10"
                >
                  <span className="inline-flex w-8 h-8 rounded-lg bg-sky-500/15 text-sky-600 items-center justify-center">
                    <i className="fas fa-image text-[13px]" aria-hidden="true" />
                  </span>
                  <span className="flex-1 text-left">
                    <span className="block font-medium leading-tight">
                      {language === 'es' ? 'Adjuntar fotos al mensaje' : 'Attach photo(s) to message'}
                    </span>
                    <span className="block text-[10px] text-gray-500 leading-tight mt-0.5">
                      {language === 'es' ? 'Puedes añadir texto y enviar juntas' : 'Add a caption, then send together'}
                    </span>
                  </span>
                </button>
                <button
                  type="button"
                  role="menuitem"
                  onClick={() => { setShowAttachMenu(false); triggerCsvUpload() }}
                  className="w-full flex items-center gap-3 px-3 py-2.5 text-sm text-gray-700 hover:bg-[#2CABE3]/5 hover:text-[#2CABE3] transition-colors border-t border-[#2CABE3]/10"
                >
                  <span className="inline-flex w-8 h-8 rounded-lg bg-emerald-500/15 text-emerald-600 items-center justify-center">
                    <i className="fas fa-file-csv text-[13px]" aria-hidden="true" />
                  </span>
                  <span className="flex-1 text-left">
                    <span className="block font-medium leading-tight">
                      {language === 'es' ? 'CSV en lote' : 'Bulk import CSV'}
                    </span>
                    <span className="block text-[10px] text-gray-500 leading-tight mt-0.5">
                      {language === 'es' ? 'Sube varios listados a la vez' : 'Upload many listings at once'}
                    </span>
                  </span>
                </button>
              </div>
            )}
          </div>
          )}

          <div className="flex-1 relative">
            {/* Autocomplete dropdown */}
            {showSuggestions && (
              <ul
                role="listbox"
                aria-label={language === 'es' ? 'Sugerencias' : 'Suggestions'}
                className="absolute bottom-full left-0 right-0 mb-2 max-h-56 overflow-y-auto rounded-xl border border-[#2CABE3]/15 bg-white/95 backdrop-blur-md shadow-lg shadow-[#2CABE3]/10 z-20 nourish-scrollbar"
              >
                {filteredSuggestions.map((s, idx) => (
                  <li
                    key={s}
                    role="option"
                    aria-selected={idx === suggestionIndex}
                    onMouseDown={(e) => { e.preventDefault(); acceptSuggestion(s) }}
                    onMouseEnter={() => setSuggestionIndex(idx)}
                    className={`px-3 py-2 text-sm cursor-pointer transition-colors ${
                      idx === suggestionIndex
                        ? 'bg-[#2CABE3]/15 text-[#2299c7]'
                        : 'text-gray-700 hover:bg-[#2CABE3]/5'
                    }`}
                  >
                    {s}
                  </li>
                ))}
              </ul>
            )}
            <textarea
              ref={inputRef}
              value={inputText}
              onChange={(e) => { if (!isLoading) { setInputText(e.target.value); setSuggestionsOpen(true) } }}
              onKeyDown={handleKeyDown}
              onFocus={() => setSuggestionsOpen(true)}
              onBlur={() => setTimeout(() => setSuggestionsOpen(false), 120)}
              placeholder={
                pendingChatPhotos.length > 0
                  ? chatT(language, 'photoCaptionPlaceholder')
                  : chatT(language, 'messagePlaceholder')
              }
              className={`w-full resize-none rounded-2xl border bg-white/90 text-gray-800 placeholder-gray-400 px-4 py-2.5 text-sm leading-relaxed max-h-32 outline-none transition-all backdrop-blur-sm ${
                isLoading
                  ? 'ai-input-glow border-[#2CABE3]/60 cursor-wait'
                  : 'border-[#2CABE3]/15 focus:border-[#2CABE3]/50 focus:ring-2 focus:ring-[#2CABE3]/20 focus:bg-white'
              }`}
              rows={1}
              readOnly={isLoading}
              aria-busy={isLoading}
              aria-label="Message input"
              aria-autocomplete="list"
              aria-expanded={showSuggestions}
              aria-controls="ai-chat-suggestions"
            />
          </div>

          {/* Wake word ("Nouri") toggle — hands-free always-listening mode */}
          {wakeWordSupported && (
            <button
              type="button"
              onClick={toggleWakeWord}
              className={`flex-shrink-0 inline-flex items-center justify-center w-9 h-9 rounded-full transition-all border ${
                wakeWordEnabled
                  ? 'border-emerald-500/40 bg-emerald-50 text-emerald-600 hover:bg-emerald-100'
                  : 'border-[#2CABE3]/15 bg-white/80 text-gray-600 hover:text-emerald-600 hover:bg-emerald-50 hover:border-emerald-400/30'
              }`}
              title={
                wakeWordEnabled
                  ? (language === 'es' ? 'Palabra de activación activada — di “Nouri”' : 'Wake word on — say “Nouri”')
                  : (language === 'es' ? 'Activar manos libres con “Nouri”' : 'Enable hands-free wake word “Nouri”')
              }
              aria-label={language === 'es' ? 'Alternar palabra de activación Nouri' : 'Toggle Nouri wake word'}
              aria-pressed={wakeWordEnabled}
            >
              <span className="relative inline-flex items-center justify-center">
                <i className={`fas fa-assistive-listening-systems text-[13px] ${wakeActive ? 'animate-pulse' : ''}`} aria-hidden="true" />
                {wakeActive && (
                  <span className="absolute -top-1.5 -right-1.5 h-2 w-2 rounded-full bg-emerald-400 animate-ping" aria-hidden="true" />
                )}
              </span>
            </button>
          )}

          {/* Voice mode — AI speaks responses aloud */}
          <button
            type="button"
            onClick={enterVoiceMode}
            disabled={isLoading}
            className="flex-shrink-0 inline-flex items-center justify-center w-9 h-9 rounded-full transition-all border border-[#2CABE3]/15 bg-white/80 text-gray-600 hover:text-[#2CABE3] hover:bg-[#2CABE3]/10 hover:border-[#2CABE3]/30 disabled:opacity-40 disabled:cursor-not-allowed"
            title={language === 'es' ? 'Modo voz' : 'Voice mode'}
            aria-label="Switch to voice mode"
          >
            <i className="fas fa-microphone text-[13px]" aria-hidden="true" />
          </button>

          {/* Send button — stronger affordance, clearer disabled state */}
          <button
            type="submit"
            disabled={(!inputText.trim() && pendingChatPhotos.length === 0) || isLoading || uploadBusy}
            className={`flex-shrink-0 inline-flex items-center justify-center w-9 h-9 rounded-full transition-all ${
              (inputText.trim() || pendingChatPhotos.length > 0) && !isLoading && !uploadBusy
                ? 'bg-gradient-to-br from-[#2CABE3] to-emerald-500 text-white hover:from-[#2299c7] hover:to-emerald-600 shadow-md shadow-[#2CABE3]/25 hover:scale-105 active:scale-95'
                : 'bg-gray-100 text-gray-400 border border-gray-200 cursor-not-allowed'
            }`}
            aria-label={language === 'es' ? 'Enviar mensaje' : 'Send message'}
          >
            <i className="fas fa-paper-plane text-[12px]" aria-hidden="true" />
          </button>
        </div>

        {/* Keyboard / status hint — subtle so it doesn't add visual noise */}
        <div className="flex items-center justify-between px-1 text-[10px] text-slate-600">
          <span className="hidden sm:inline">
            {language === 'es'
              ? 'Enter para enviar · Shift+Enter para línea nueva'
              : 'Enter to send · Shift+Enter for new line'}
          </span>
          <span className={`ml-auto tabular-nums transition-colors ${
            inputText.length > 4000 ? 'text-rose-600 font-medium' : inputText.length > 2000 ? 'text-amber-700' : 'text-slate-500'
          }`}>
            {inputText.length > 0 ? `${inputText.length}` : ''}
          </span>
        </div>
      </form>
      </>
      )}

      {/* Futuristic scrollbar + ambient glow + voice panel animations */}
      <style>{`
        .nourish-scrollbar::-webkit-scrollbar { width: 4px; height: 4px; }
        .nourish-scrollbar::-webkit-scrollbar-track { background: transparent; }
        .nourish-scrollbar::-webkit-scrollbar-thumb { background: rgba(34,211,238,0.2); border-radius: 4px; }
        .nourish-scrollbar::-webkit-scrollbar-thumb:hover { background: rgba(34,211,238,0.4); }

        /* Thin horizontal scrollbar for the quick-chip rail */
        .nourish-scrollbar-h::-webkit-scrollbar { height: 4px; }
        .nourish-scrollbar-h::-webkit-scrollbar-track { background: transparent; }
        .nourish-scrollbar-h::-webkit-scrollbar-thumb { background: rgba(34,211,238,0.15); border-radius: 4px; }
        .nourish-scrollbar-h::-webkit-scrollbar-thumb:hover { background: rgba(34,211,238,0.3); }

        /* Fade-in for menus / pills */
        @keyframes ai-fade-in {
          from { opacity: 0; transform: translateY(4px); }
          to   { opacity: 1; transform: translateY(0); }
        }
        .animate-fade-in { animation: ai-fade-in 180ms ease-out both; }

        /* Voice orb animations */
        @keyframes voice-ring-out {
          0% { transform: scale(1); opacity: 1; }
          100% { transform: scale(1.6); opacity: 0; }
        }
        .animate-voice-ring-1 { animation: voice-ring-out 2s ease-out infinite; }
        .animate-voice-ring-2 { animation: voice-ring-out 2s ease-out 0.4s infinite; }
        .animate-voice-ring-3 { animation: voice-ring-out 2s ease-out 0.8s infinite; }

        @keyframes voice-speak-ring {
          0% { transform: scale(1); opacity: 0.6; }
          100% { transform: scale(1.4); opacity: 0; }
        }
        .animate-voice-speak-ring-1 { animation: voice-speak-ring 1.5s ease-out infinite; }
        .animate-voice-speak-ring-2 { animation: voice-speak-ring 1.5s ease-out 0.3s infinite; }

        /* Speaking wave bars */
        @keyframes voice-bar-bounce {
          0%, 100% { height: 8px; }
          50% { height: 28px; }
        }
        .animate-voice-bar { animation: voice-bar-bounce 0.6s ease-in-out infinite; }

        /* Thinking dots */
        @keyframes voice-dot-pulse {
          0%, 100% { transform: scale(1); opacity: 0.5; }
          50% { transform: scale(1.4); opacity: 1; }
        }
        .animate-voice-dot { animation: voice-dot-pulse 0.8s ease-in-out infinite; }
      `}</style>
      </div>
    </div>
  )
}

export default AIChatPanel
