import React, { useState, useEffect, useRef, useCallback, useMemo } from 'react'
import { useNavigate } from 'react-router-dom'
import { useAIChat } from '../../utils/hooks/useAIChat.js'
import { useAuthContext } from '../../utils/AuthContext.jsx'
import { useMapContext } from '../../utils/MapContext.jsx'
import { useUIControl } from '../../utils/UIControlContext.jsx'
import VoiceOutput from './VoiceOutput.jsx'
import { textToSpeech, playAudioBlob } from '../../utils/openaiVoice.js'
import aiChatService from '../../utils/services/aiChatService.js'
import { parseListingsCsv, downloadCsvTemplate } from '../../utils/csvListings.js'
import { assignImagestoRows, assignFoodImage } from '../../utils/foodImages.js'
import dataService from '../../utils/dataService.js'
import { toast } from 'react-toastify'

// ─── Quick action presets ─────────────────────────────
const QUICK_ACTIONS_EN = [
  { label: '🔍 Find food near me', message: 'What food is available near me?' },
  { label: '📦 My pickups', message: 'What are my upcoming pickups?' },
  { label: '🍳 Suggest a recipe', message: 'Can you suggest a recipe from available food?' },
  { label: '🤝 Share food', message: 'I want to share some food' },
  { label: '📅 Upcoming events', message: 'What distribution events are coming up?' },
  { label: '❓ How it works', message: 'How does DoGoods work?' },
]

const QUICK_ACTIONS_ES = [
  { label: '🔍 Buscar comida', message: '¿Qué comida hay disponible cerca de mí?' },
  { label: '📦 Mis recogidas', message: '¿Cuáles son mis próximas recogidas?' },
  { label: '🍳 Sugerir receta', message: '¿Puedes sugerirme una receta con comida disponible?' },
  { label: '🤝 Compartir comida', message: 'Quiero compartir comida' },
  { label: '📅 Eventos', message: '¿Qué eventos de distribución hay próximamente?' },
  { label: '❓ Cómo funciona', message: '¿Cómo funciona DoGoods?' },
]

// ─── Welcome hero categories (richer onboarding surface) ───────────
// Replaces the flat 6-pill row when the chat is empty. Each category
// surfaces 2 starter prompts so the user immediately understands what
// Nouri can do, organized by intent (Find / Share / Manage / Learn).
const WELCOME_CATEGORIES_EN = [
  {
    key: 'find',
    icon: 'fa-magnifying-glass-location',
    accent: 'emerald',
    title: 'Find food',
    blurb: 'Discover nearby donations',
    prompts: [
      'What food is available near me?',
      'Find food expiring soon',
    ],
  },
  {
    key: 'share',
    icon: 'fa-hand-holding-heart',
    accent: 'fuchsia',
    title: 'Share food',
    blurb: 'Post or upload listings',
    prompts: [
      'I want to share some food',
      'Help me post a listing from a photo',
    ],
  },
  {
    key: 'manage',
    icon: 'fa-list-check',
    accent: 'cyan',
    title: 'Manage activity',
    blurb: 'Pickups, claims, impact',
    prompts: [
      'What are my upcoming pickups?',
      'Show my impact stats',
    ],
  },
  {
    key: 'learn',
    icon: 'fa-circle-question',
    accent: 'sky',
    title: 'Learn & cook',
    blurb: 'Recipes and how-to',
    prompts: [
      'Suggest a recipe from available food',
      'How does DoGoods work?',
    ],
  },
]

const WELCOME_CATEGORIES_ES = [
  {
    key: 'find',
    icon: 'fa-magnifying-glass-location',
    accent: 'emerald',
    title: 'Buscar comida',
    blurb: 'Donaciones cerca de ti',
    prompts: [
      '¿Qué comida hay disponible cerca de mí?',
      'Comida que vence pronto',
    ],
  },
  {
    key: 'share',
    icon: 'fa-hand-holding-heart',
    accent: 'fuchsia',
    title: 'Compartir comida',
    blurb: 'Publica o sube listados',
    prompts: [
      'Quiero compartir comida',
      'Ayúdame a publicar desde una foto',
    ],
  },
  {
    key: 'manage',
    icon: 'fa-list-check',
    accent: 'cyan',
    title: 'Mi actividad',
    blurb: 'Recogidas, reclamos, impacto',
    prompts: [
      '¿Cuáles son mis próximas recogidas?',
      'Muestra mis estadísticas de impacto',
    ],
  },
  {
    key: 'learn',
    icon: 'fa-circle-question',
    accent: 'sky',
    title: 'Aprender y cocinar',
    blurb: 'Recetas y guías',
    prompts: [
      'Sugiéreme una receta con lo disponible',
      '¿Cómo funciona DoGoods?',
    ],
  },
]

// Map accent → tailwind classes so the welcome cards stay on-brand
// while still being visually distinct from each other.
const ACCENT_MAP = {
  emerald: {
    iconBg: 'bg-emerald-500/15 text-emerald-300 ring-emerald-400/30',
    border: 'border-emerald-500/20 hover:border-emerald-400/40',
    glow: 'hover:shadow-emerald-500/10',
    promptHover: 'hover:bg-emerald-500/10 hover:text-emerald-200',
  },
  fuchsia: {
    iconBg: 'bg-fuchsia-500/15 text-fuchsia-300 ring-fuchsia-400/30',
    border: 'border-fuchsia-500/20 hover:border-fuchsia-400/40',
    glow: 'hover:shadow-fuchsia-500/10',
    promptHover: 'hover:bg-fuchsia-500/10 hover:text-fuchsia-200',
  },
  cyan: {
    iconBg: 'bg-cyan-500/15 text-cyan-300 ring-cyan-400/30',
    border: 'border-cyan-500/20 hover:border-cyan-400/40',
    glow: 'hover:shadow-cyan-500/10',
    promptHover: 'hover:bg-cyan-500/10 hover:text-cyan-200',
  },
  sky: {
    iconBg: 'bg-sky-500/15 text-sky-300 ring-sky-400/30',
    border: 'border-sky-500/20 hover:border-sky-400/40',
    glow: 'hover:shadow-sky-500/10',
    promptHover: 'hover:bg-sky-500/10 hover:text-sky-200',
  },
}

// ─── WelcomeHero — empty-state onboarding surface ──────────────────
function WelcomeHero({ language, userName, onPromptClick }) {
  const categories = language === 'es' ? WELCOME_CATEGORIES_ES : WELCOME_CATEGORIES_EN
  const greeting = language === 'es'
    ? (userName ? `¡Hola, ${userName}!` : '¡Hola!')
    : (userName ? `Hi, ${userName}!` : 'Hi there!')
  const subtitle = language === 'es'
    ? 'Soy Nouri. ¿Cómo puedo ayudarte hoy?'
    : "I'm Nouri. What would you like to do?"

  return (
    <div className="px-4 pt-3 pb-2">
      <div className="mb-3">
        <h2 className="text-base font-semibold text-cyan-100 tracking-tight">{greeting}</h2>
        <p className="text-xs text-slate-400/90 mt-0.5">{subtitle}</p>
      </div>

      <div className="grid grid-cols-2 gap-2">
        {categories.map((cat) => {
          const accent = ACCENT_MAP[cat.accent] || ACCENT_MAP.cyan
          return (
            <div
              key={cat.key}
              className={`rounded-xl p-3 bg-slate-800/50 backdrop-blur-sm border transition-all ${accent.border} hover:bg-slate-800/70 hover:shadow-md ${accent.glow}`}
            >
              <div className="flex items-center gap-2 mb-1.5">
                <span className={`w-7 h-7 rounded-lg ring-1 flex items-center justify-center ${accent.iconBg}`}>
                  <i className={`fas ${cat.icon} text-xs`} aria-hidden="true" />
                </span>
                <div className="min-w-0">
                  <div className="text-xs font-semibold text-slate-100 truncate">{cat.title}</div>
                  <div className="text-[10px] text-slate-400/80 truncate">{cat.blurb}</div>
                </div>
              </div>
              <ul className="space-y-1">
                {cat.prompts.map((p) => (
                  <li key={p}>
                    <button
                      type="button"
                      onClick={() => onPromptClick?.(p)}
                      className={`w-full text-left text-[11px] leading-snug text-slate-300 px-2 py-1 rounded-md transition-colors ${accent.promptHover}`}
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
  const es = language === 'es'
  if (diffDays === 0) return es ? 'Hoy' : 'Today'
  if (diffDays === 1) return es ? 'Ayer' : 'Yesterday'
  if (diffDays < 7) {
    return d.toLocaleDateString(es ? 'es-ES' : 'en-US', { weekday: 'long' })
  }
  return d.toLocaleDateString(es ? 'es-ES' : 'en-US', { month: 'short', day: 'numeric' })
}

function DateSeparator({ label }) {
  return (
    <div className="relative my-3 flex items-center gap-2" aria-hidden="true">
      <span className="flex-1 h-px bg-gradient-to-r from-transparent via-slate-700/60 to-transparent" />
      <span className="text-[10px] uppercase tracking-wider text-slate-500 px-2 py-0.5 rounded-full bg-slate-800/60 border border-slate-700/50">
        {label}
      </span>
      <span className="flex-1 h-px bg-gradient-to-l from-transparent via-slate-700/60 to-transparent" />
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
      className="absolute bottom-3 right-3 z-10 flex items-center gap-1.5 px-3 py-1.5 rounded-full bg-slate-800/95 backdrop-blur-sm border border-cyan-500/30 text-cyan-200 text-xs shadow-lg shadow-cyan-500/10 hover:bg-slate-700/95 hover:border-cyan-400/50 hover:scale-105 active:scale-95 transition-all animate-fade-in"
      aria-label={language === 'es' ? 'Ir al final' : 'Jump to latest'}
    >
      <i className="fas fa-arrow-down text-[10px]" aria-hidden="true" />
      {language === 'es' ? 'Más reciente' : 'Latest'}
    </button>
  )
}

// ─── Autocomplete suggestion pool ─────────────────────────────
const SUGGESTIONS_EN = [
  'What food is available near me?',
  'What food is available within 5 miles?',
  'Show me food listings nearby',
  'What are my upcoming pickups?',
  'What are my recent claims?',
  'Cancel my pickup',
  'Show my dashboard',
  'Show my impact stats',
  'How many meals have I shared?',
  'Can you suggest a recipe from available food?',
  'Give me a recipe for leftovers',
  'How do I store fresh produce?',
  'I want to share some food',
  'How do I post a food listing?',
  'What distribution events are coming up?',
  'Find a distribution center near me',
  'Route me to the nearest pickup',
  'How does DoGoods work?',
  'How do I verify my account?',
  'Update my profile address',
  'Switch to Spanish',
  'Open the map',
  'Find food expiring soon',
  'Show urgent listings',
]

const SUGGESTIONS_ES = [
  '¿Qué comida hay disponible cerca de mí?',
  '¿Qué comida hay a menos de 5 millas?',
  'Muéstrame las publicaciones cercanas',
  '¿Cuáles son mis próximas recogidas?',
  '¿Cuáles son mis reclamos recientes?',
  'Cancela mi recogida',
  'Muestra mi panel',
  'Muestra mis estadísticas de impacto',
  '¿Cuántas comidas he compartido?',
  '¿Puedes sugerirme una receta con comida disponible?',
  'Dame una receta para sobras',
  '¿Cómo guardo productos frescos?',
  'Quiero compartir comida',
  '¿Cómo publico una donación?',
  '¿Qué eventos de distribución hay próximamente?',
  'Encuentra un centro de distribución cerca',
  'Llévame a la recogida más cercana',
  '¿Cómo funciona DoGoods?',
  '¿Cómo verifico mi cuenta?',
  'Actualiza la dirección de mi perfil',
  'Cambia a inglés',
  'Abre el mapa',
  'Comida que vence pronto',
  'Muestra publicaciones urgentes',
]

// ─── Typing indicator ─────────────────────────────────
const THINKING_STAGES = [
  { icon: 'brain', label: 'Analyzing your request' },
  { icon: 'database', label: 'Searching knowledge base' },
  { icon: 'satellite-dish', label: 'Consulting live activity' },
  { icon: 'wand-magic-sparkles', label: 'Generating response' },
]

function TypingIndicator() {
  const [stageIdx, setStageIdx] = useState(0)
  useEffect(() => {
    const t = setInterval(() => {
      setStageIdx((i) => (i + 1) % THINKING_STAGES.length)
    }, 1400)
    return () => clearInterval(t)
  }, [])
  const stage = THINKING_STAGES[stageIdx]

  return (
    <div className="flex items-center gap-3 px-4 py-3">
      {/* Avatar with orbiting rings + core */}
      <div className="relative w-10 h-10 flex-shrink-0">
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

      {/* Status bubble with shimmer */}
      <div className="relative flex-1 min-w-0 max-w-[260px]">
        <div className="ai-typing-shimmer relative bg-slate-800/60 backdrop-blur-md rounded-2xl px-3.5 py-2 border border-cyan-500/30 shadow-lg shadow-cyan-500/10">
          <div className="flex items-center gap-2 relative z-10">
            <i
              key={`icon-${stageIdx}`}
              className={`fas fa-${stage.icon} text-cyan-300 text-[11px] ai-typing-status`}
              aria-hidden="true"
            />
            <span
              key={`label-${stageIdx}`}
              className="text-[11px] text-cyan-100 font-medium tracking-wide truncate ai-typing-status"
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
    ring: 'ring-emerald-400/40',
    bg: 'bg-gradient-to-br from-emerald-900/40 to-emerald-950/30 border-emerald-500/25',
    accent: 'text-emerald-300',
    sub: 'text-emerald-400/75',
    tag: 'bg-emerald-500/15 text-emerald-200 border-emerald-500/20',
  },
  claim: {
    title: { en: 'Claim confirmed', es: 'Reclamo confirmado' },
    icon: 'fa-circle-check',
    ring: 'ring-emerald-400/40',
    bg: 'bg-gradient-to-br from-emerald-900/40 to-emerald-950/30 border-emerald-500/25',
    accent: 'text-emerald-300',
    sub: 'text-emerald-400/75',
  },
  cancel: {
    title: { en: 'Claim released', es: 'Reclamo liberado' },
    icon: 'fa-arrow-rotate-left',
    ring: 'ring-amber-400/40',
    bg: 'bg-gradient-to-br from-amber-900/40 to-amber-950/30 border-amber-500/25',
    accent: 'text-amber-300',
    sub: 'text-amber-400/75',
  },
  post: {
    title: { en: 'Listing posted', es: 'Donación publicada' },
    icon: 'fa-bullhorn',
    ring: 'ring-fuchsia-400/40',
    bg: 'bg-gradient-to-br from-fuchsia-900/40 to-fuchsia-950/30 border-fuchsia-500/25',
    accent: 'text-fuchsia-200',
    sub: 'text-fuchsia-300/75',
  },
  pickup: {
    title: { en: 'Pickup confirmed', es: 'Recogida confirmada' },
    icon: 'fa-check-double',
    ring: 'ring-sky-400/40',
    bg: 'bg-gradient-to-br from-sky-900/40 to-sky-950/30 border-sky-500/25',
    accent: 'text-sky-200',
    sub: 'text-sky-300/75',
  },
  reminder: {
    title: { en: 'Reminder set', es: 'Recordatorio creado' },
    icon: 'fa-bell',
    ring: 'ring-blue-400/40',
    bg: 'bg-gradient-to-br from-blue-900/40 to-blue-950/30 border-blue-500/25',
    accent: 'text-blue-200',
    sub: 'text-blue-300/75',
  },
}

function ToolCardShell({ kind, language = 'en', titleOverride, children }) {
  const t = TOOL_CARD_TOKENS[kind] || TOOL_CARD_TOKENS.claim
  const title = titleOverride || t.title[language] || t.title.en
  return (
    <div
      role="status"
      className={`mt-2 ${t.bg} border rounded-xl p-3 text-sm backdrop-blur-sm shadow-sm`}
    >
      <div className="flex items-center gap-2 mb-1.5">
        <span className={`inline-flex w-6 h-6 rounded-full bg-slate-900/40 ring-1 ${t.ring} items-center justify-center`}>
          <i className={`fas ${t.icon} text-[11px] ${t.accent}`} aria-hidden="true" />
        </span>
        <div className={`font-semibold text-xs uppercase tracking-wide ${t.accent}`}>{title}</div>
      </div>
      <div className="text-xs leading-relaxed">{children}</div>
    </div>
  )
}

function ToolResultCard({ toolResult, language = 'en' }) {
  if (!toolResult) return null

  const { tool } = toolResult
  const result = toolResult.result ?? toolResult
  const ok = result?.success || toolResult.ok

  const searchItems = result.listings ?? result.results ?? []
  if ((tool === 'search_food_near_user' || tool === 'search_food_nearby' || tool === 'get_recent_listings') && searchItems.length > 0) {
    const t = TOOL_CARD_TOKENS.search
    return (
      <ToolCardShell kind="search" language={language} titleOverride={`${t.title[language] || t.title.en} · ${searchItems.length}`}>
        <ul className="space-y-1.5">
          {searchItems.slice(0, 3).map(item => {
            const distance = item.distance_km != null
              ? `${item.distance_km} km`
              : item.distance_miles != null
                ? `${item.distance_miles} mi`
                : null
            const meta = [distance, item.category, item.pickup_by].filter(Boolean).join(' · ')
            return (
              <li key={item.id} className="rounded-lg bg-slate-900/40 px-2.5 py-2 border border-emerald-500/15">
                <div className={`font-medium ${t.accent}`}>{item.title}</div>
                {meta && <div className={`${t.sub} text-[11px] mt-0.5`}>{meta}</div>}
                {item.dietary_tags?.length > 0 && (
                  <div className="flex gap-1 mt-1.5 flex-wrap">
                    {item.dietary_tags.map(tag => (
                      <span key={tag} className={`${t.tag} text-[10px] px-1.5 py-0.5 rounded border`}>{tag}</span>
                    ))}
                  </div>
                )}
              </li>
            )
          })}
          {searchItems.length > 3 && (
            <li className={`text-[11px] ${t.sub} text-center pt-0.5`}>
              {language === 'es' ? `+${searchItems.length - 3} más en el mapa` : `+${searchItems.length - 3} more on the map`}
            </li>
          )}
        </ul>
      </ToolCardShell>
    )
  }

  if (tool === 'create_reminder' && (result?.success || result?.created)) {
    return (
      <ToolCardShell kind="reminder" language={language}>
        <span className="text-blue-100">{result.summary || (language === 'es' ? 'Te avisaré.' : "I'll ping you.")}</span>
      </ToolCardShell>
    )
  }

  if ((tool === 'claim_listing' || tool === 'claim_food') && ok) {
    return (
      <ToolCardShell kind="claim" language={language}>
        {result.title && (
          <div className="text-emerald-100">
            {result.quantity ? <span className="font-medium">{result.quantity} {result.unit || ''} </span> : null}
            {result.quantity ? (language === 'es' ? 'de ' : 'of ') : null}
            <span className="font-semibold">{result.title}</span>
          </div>
        )}
        {result.pickup_location && (
          <div className="text-emerald-400/80 mt-1 flex items-center gap-1">
            <i className="fas fa-location-dot text-[10px]" aria-hidden="true" />
            <span>{result.pickup_location}</span>
          </div>
        )}
        {(result.summary || result.message) && (
          <div className="text-emerald-400/70 mt-1">{result.summary || result.message}</div>
        )}
      </ToolCardShell>
    )
  }

  if ((tool === 'create_food_listing' || tool === 'post_food_listing') && ok) {
    return (
      <ToolCardShell kind="post" language={language}>
        {result.title && (
          <div className="text-fuchsia-100">
            <span className="font-semibold">{result.title}</span>
            {result.quantity != null && <span className="text-fuchsia-300/80"> · {result.quantity} {result.unit || ''}</span>}
            {result.category && <span className="text-fuchsia-300/80"> · {result.category}</span>}
          </div>
        )}
        {(result.summary || result.message) && (
          <div className="text-fuchsia-300/75 mt-1">{result.summary || result.message}</div>
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
        {result.summary && <div className="text-amber-400/75 mt-1">{result.summary}</div>}
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
        {result.summary && <div className="text-sky-300/75 mt-1">{result.summary}</div>}
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

function MessageBubble({
  msg,
  onFeedback,
  language,
  onSuggestionClick,
  isLoading,
  currentUser,
  onRetry,
  onRegenerate,
  showRegenerate = false,
}) {
  const [feedbackGiven, setFeedbackGiven] = useState(null)
  const [avatarBroken, setAvatarBroken] = useState(false)
  const [copied, setCopied] = useState(false)
  const isUser = msg.role === 'user'
  const suggestionItems = msg.suggestions || msg.suggestedActions || []
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
          <div className="flex-shrink-0 w-7 h-7 rounded-full bg-gradient-to-br from-cyan-400 to-blue-500 flex items-center justify-center mt-1 shadow-sm shadow-cyan-400/30">
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
            className="flex-shrink-0 w-7 h-7 rounded-full overflow-hidden mt-1 shadow-sm shadow-cyan-500/30 ring-1 ring-cyan-400/40 bg-gradient-to-br from-cyan-500 to-blue-600 flex items-center justify-center"
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
                ? 'bg-gradient-to-br from-cyan-500 to-blue-500 text-white rounded-br-md shadow-md shadow-cyan-500/25 ring-1 ring-cyan-300/20'
                : msg.isError
                  ? 'bg-red-900/30 text-red-200 border border-red-500/30 rounded-bl-md backdrop-blur-sm'
                  : 'bg-slate-800/70 text-slate-100 rounded-bl-md border border-slate-600/40 backdrop-blur-sm shadow-sm'
            }`}
          >
            <p className="whitespace-pre-wrap">{msg.message}</p>

            {/* Typed error metadata: small chip + retry button. Only renders
                when the bubble carries an errorCode from the backend. The
                Retry button re-sends the original user text (stashed on the
                error bubble as retryText) and removes this bubble. */}
            {msg.isError && msg.errorCode && (
              <div className="mt-2.5 pt-2.5 border-t border-red-500/20 flex flex-wrap items-center gap-2">
                <span className="inline-flex items-center gap-1.5 px-2 py-0.5 rounded-full bg-red-500/15 text-red-200/90 text-[10px] font-semibold tracking-wide ring-1 ring-red-500/25">
                  <i className="fas fa-circle-exclamation text-[9px]" aria-hidden="true" />
                  {describeErrorCode(msg.errorCode, language).eyebrow}
                </span>
                {msg.errorRetryable && onRetry && msg.retryText && (
                  <button
                    type="button"
                    onClick={() => onRetry(msg.id)}
                    disabled={isLoading}
                    className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-md bg-red-500/15 hover:bg-red-500/25 text-red-100 text-[11px] font-semibold transition-colors ring-1 ring-red-500/30 hover:ring-red-400/50 disabled:opacity-40 disabled:cursor-not-allowed focus:outline-none focus-visible:ring-2 focus-visible:ring-red-300"
                    aria-label={language === 'es' ? 'Reintentar mensaje' : 'Retry message'}
                  >
                    <i className={`fas ${isLoading ? 'fa-spinner fa-spin' : 'fa-rotate-right'} text-[10px]`} aria-hidden="true" />
                    {language === 'es' ? 'Reintentar' : 'Retry'}
                    {msg.errorRetryAfter ? (
                      <span className="text-red-200/60 font-normal">· {msg.errorRetryAfter}s</span>
                    ) : null}
                  </button>
                )}
                {msg.requestId && (
                  <span
                    className="ml-auto text-[9px] font-mono text-red-200/40 tracking-wider truncate max-w-[120px]"
                    title={`Request ID: ${msg.requestId}`}
                  >
                    {msg.requestId.slice(0, 8)}
                  </span>
                )}
              </div>
            )}
          </div>

          {/* Tool result cards */}
          {msg.toolResults?.map((tr, i) => (
            <ToolResultCard key={i} toolResult={tr} language={language} />
          ))}

          {/* Suggested actions */}
          {suggestionItems.length > 0 && !isUser && (
            <div className="flex flex-wrap gap-1.5 mt-2">
              {suggestionItems.map((action, i) => (
                <SuggestedActionButton
                  key={i}
                  action={action}
                  onSuggestionClick={onSuggestionClick}
                  disabled={isLoading}
                />
              ))}
            </div>
          )}

          {/* Hover-revealed action row for assistant replies */}
          {!isUser && !msg.isError && msg.id !== 'welcome' && (
            <div
              className="flex items-center gap-1 mt-1.5 opacity-60 md:opacity-0 md:group-hover/msg:opacity-100 transition-opacity"
              role="toolbar"
              aria-label={language === 'es' ? 'Acciones del mensaje' : 'Message actions'}
            >
              <VoiceOutput text={msg.message} language={language} />
              <button
                type="button"
                onClick={handleCopy}
                className="inline-flex items-center justify-center w-6 h-6 rounded-md text-slate-500 hover:text-cyan-300 hover:bg-cyan-500/10 transition-colors"
                title={copied ? (language === 'es' ? 'Copiado' : 'Copied') : (language === 'es' ? 'Copiar' : 'Copy')}
                aria-label={language === 'es' ? 'Copiar mensaje' : 'Copy message'}
              >
                <i className={`fas ${copied ? 'fa-check text-cyan-300' : 'fa-copy'} text-[11px]`} aria-hidden="true" />
              </button>
              {!feedbackGiven && (
                <>
                  <button
                    type="button"
                    onClick={() => handleFeedback('helpful')}
                    className="inline-flex items-center justify-center w-6 h-6 rounded-md text-slate-500 hover:text-emerald-300 hover:bg-emerald-500/10 transition-colors"
                    title={language === 'es' ? 'Útil' : 'Helpful'}
                    aria-label={language === 'es' ? 'Marcar como útil' : 'Mark as helpful'}
                  >
                    <i className="fas fa-thumbs-up text-[11px]" aria-hidden="true" />
                  </button>
                  <button
                    type="button"
                    onClick={() => handleFeedback('not_helpful')}
                    className="inline-flex items-center justify-center w-6 h-6 rounded-md text-slate-500 hover:text-rose-300 hover:bg-rose-500/10 transition-colors"
                    title={language === 'es' ? 'No útil' : 'Not helpful'}
                    aria-label={language === 'es' ? 'Marcar como no útil' : 'Mark as not helpful'}
                  >
                    <i className="fas fa-thumbs-down text-[11px]" aria-hidden="true" />
                  </button>
                </>
              )}
              {feedbackGiven && (
                <span className="text-[10px] text-cyan-300/70 px-1.5 py-0.5 rounded-md bg-cyan-500/10 border border-cyan-500/20">
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
                  className="ml-1 inline-flex items-center gap-1 px-1.5 h-6 rounded-md text-slate-500 hover:text-cyan-300 hover:bg-cyan-500/10 transition-colors disabled:opacity-40 disabled:cursor-not-allowed text-[10px] font-medium"
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
          <div className={`text-[10px] mt-1 flex items-center gap-1 ${isUser ? 'justify-end text-cyan-200/60' : 'text-slate-400/80'}`}>
            {isVoiceMessage && (
              <span className="px-1.5 py-0.5 rounded-full border border-cyan-500/25 bg-cyan-500/10 text-cyan-200/85 text-[9px] uppercase tracking-wide inline-flex items-center gap-1">
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
function SuggestedActionButton({ action, onSuggestionClick, disabled = false }) {
  const navigate = useNavigate()

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

    if (actionType === 'navigate' && asObject && (action.target || action.href)) {
      navigate(action.target || action.href)
      return
    }

    if (sendText && onSuggestionClick) {
      onSuggestionClick(sendText)
    }
  }

  if (!label) return null

  const styleClass = actionType === 'navigate'
    ? 'bg-blue-500/20 text-blue-300 hover:bg-blue-500/30 border-blue-400/20'
    : 'bg-cyan-500/10 text-cyan-300 hover:bg-cyan-500/20 border-cyan-500/20'

  return (
    <button
      onClick={handleClick}
      disabled={disabled}
      className={`text-xs px-2.5 py-1 rounded-full transition-colors border ${styleClass} disabled:opacity-60 disabled:cursor-not-allowed`}
    >
      {label}
    </button>
  )
}

// ─── Bulk upload preview (photo + CSV → bulk listings) ───────
function BulkUploadPreview({ pending, busy, language, onCancel, onConfirm, onUpdateRow, onRemoveRow }) {
  const isEs = language === 'es'
  const kindLabel = pending.kind === 'photo'
    ? (isEs ? 'Borrador desde foto' : 'Draft from photo')
    : (isEs ? 'Importación CSV' : 'CSV import')
  const icon = pending.kind === 'photo' ? 'fa-camera' : 'fa-file-csv'
  const tint = pending.kind === 'photo' ? 'fuchsia' : 'emerald'
  const ringClass = pending.kind === 'photo'
    ? 'border-fuchsia-500/40 shadow-fuchsia-500/10'
    : 'border-emerald-500/40 shadow-emerald-500/10'
  const headerClass = pending.kind === 'photo' ? 'text-fuchsia-300' : 'text-emerald-300'

  if (pending.error) {
    const allErrors = [pending.error, ...(pending.parseErrors || []).slice(1)].filter(Boolean)
    return (
      <div className={`mx-3 mb-2 rounded-xl border ${ringClass} bg-slate-900/80 backdrop-blur-sm p-3 shadow-sm`}>
        <div className="flex items-start gap-3">
          <i className={`fas ${icon} ${headerClass} mt-0.5`} aria-hidden="true" />
          <div className="flex-1 min-w-0">
            <div className="text-xs font-semibold text-slate-300">{kindLabel}</div>
            <div className="text-xs text-slate-400 truncate mb-1">{pending.filename}</div>
            {allErrors.map((e, i) => (
              <div key={i} className="text-sm text-rose-300">{e}</div>
            ))}
          </div>
          <button
            type="button"
            onClick={onCancel}
            className="text-xs text-slate-400 hover:text-slate-200 px-2 py-1 rounded-md hover:bg-slate-800/60 flex-shrink-0"
          >
            {isEs ? 'Cerrar' : 'Dismiss'}
          </button>
        </div>
        {pending.kind === 'csv' && (
          <button
            type="button"
            onClick={downloadCsvTemplate}
            className="mt-2 w-full flex items-center justify-center gap-1.5 text-xs px-3 py-1.5 rounded-lg bg-emerald-500/10 text-emerald-300 hover:bg-emerald-500/20 border border-emerald-500/20 transition-colors"
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
          <div className="text-xs font-semibold text-slate-300">{kindLabel}</div>
          <div className="text-xs text-slate-400 truncate">{pending.filename}</div>
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

  const rows = pending.rows || []
  if (rows.length === 0) return null
  const previewRows = rows.slice(0, 5)
  const extra = rows.length - previewRows.length
  const filledLog = Array.isArray(pending.filledLog) ? pending.filledLog : []
  const filledByIndex = useMemo(() => {
    const m = new Map()
    for (const f of filledLog) {
      if (f && typeof f.index === 'number') m.set(f.index, f.fields || [])
    }
    return m
  }, [filledLog])
  const totalFilled = filledLog.length

  return (
    <div className={`mx-3 mb-2 rounded-xl border ${ringClass} bg-slate-900/80 backdrop-blur-sm p-3 shadow-sm`}>
      <div className="flex items-center gap-2 mb-2">
        <i className={`fas ${icon} ${headerClass}`} aria-hidden="true" />
        <div className="text-xs font-semibold text-slate-200">
          {kindLabel} · {rows.length} {rows.length === 1 ? (isEs ? 'fila' : 'row') : (isEs ? 'filas' : 'rows')}
        </div>
        {typeof pending.confidence === 'number' && pending.kind === 'photo' && (
          <span className="text-[10px] text-slate-400 ml-auto">
            {isEs ? 'Confianza' : 'Confidence'}: {Math.round(pending.confidence * 100)}%
          </span>
        )}
      </div>
      <div className="text-[11px] text-slate-400 mb-2 truncate" title={pending.filename}>{pending.filename}</div>

      {pending.enriched && (
        <div className="mb-2 flex items-start gap-1.5 rounded-lg border border-cyan-500/30 bg-cyan-500/10 px-2 py-1.5 text-[11px] text-cyan-200">
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

      <div className="space-y-1.5 max-h-44 overflow-y-auto nourish-scrollbar pr-1">
        {previewRows.map((row, idx) => (
          <div key={idx} className="rounded-lg border border-slate-700/60 bg-slate-800/40 p-2 flex items-start gap-2">
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
                    className="text-[9px] uppercase tracking-wide px-1.5 py-0.5 rounded-full bg-cyan-500/15 text-cyan-300 border border-cyan-500/30 whitespace-nowrap"
                    title={`${isEs ? 'IA rellenó' : 'AI filled'}: ${filledByIndex.get(idx).join(', ')}`}
                  >
                    <i className="fas fa-wand-magic-sparkles mr-0.5" aria-hidden="true" />
                    AI +{filledByIndex.get(idx).length}
                  </span>
                )}
              </div>
              <div className="flex items-center gap-1.5 mt-0.5 text-[11px] text-slate-400">
                <input
                  type="number"
                  step="0.1"
                  min="0"
                  value={row.quantity ?? ''}
                  onChange={(e) => onUpdateRow(idx, { quantity: Number(e.target.value) })}
                  disabled={busy}
                  className="w-16 bg-transparent outline-none focus:bg-slate-900/60 px-1 py-0.5 rounded text-slate-200"
                  aria-label="Quantity"
                />
                <input
                  type="text"
                  value={row.unit || ''}
                  onChange={(e) => onUpdateRow(idx, { unit: e.target.value })}
                  disabled={busy}
                  className="w-16 bg-transparent outline-none focus:bg-slate-900/60 px-1 py-0.5 rounded text-slate-200"
                  aria-label="Unit"
                />
                <span className="text-slate-500">·</span>
                <select
                  value={row.category || 'other'}
                  onChange={(e) => onUpdateRow(idx, { category: e.target.value })}
                  disabled={busy}
                  className="bg-slate-900/60 border border-slate-700/60 rounded px-1 py-0.5 text-slate-200"
                  aria-label="Category"
                >
                  {['produce','bakery','dairy','pantry','meat','prepared','other'].map(c => (
                    <option key={c} value={c}>{c}</option>
                  ))}
                </select>
              </div>
            </div>
            <button
              type="button"
              onClick={() => onRemoveRow(idx)}
              disabled={busy}
              className="text-slate-500 hover:text-rose-400 text-xs p-1 disabled:opacity-40"
              aria-label={`Remove row ${idx + 1}`}
              title={isEs ? 'Quitar' : 'Remove'}
            >
              <i className="fas fa-times" aria-hidden="true" />
            </button>
          </div>
        ))}
        {extra > 0 && (
          <div className="text-[11px] text-slate-500 italic px-1">
            {isEs ? `…y ${extra} más` : `…and ${extra} more`}
          </div>
        )}
      </div>

      {pending.parseErrors && pending.parseErrors.length > 0 && (
        <div className="mt-2 text-[11px] text-amber-300/80">
          <i className="fas fa-triangle-exclamation mr-1" aria-hidden="true" />
          {pending.parseErrors.length} {isEs ? 'fila(s) omitida(s)' : 'row(s) skipped'}
        </div>
      )}

      <div className="flex items-center gap-2 mt-3">
        <button
          type="button"
          onClick={onCancel}
          disabled={busy}
          className="text-xs px-3 py-1.5 rounded-full bg-slate-800/80 text-slate-300 hover:bg-slate-700/80 border border-slate-700/60 disabled:opacity-40"
        >
          {isEs ? 'Cancelar' : 'Cancel'}
        </button>
        <button
          type="button"
          onClick={onConfirm}
          disabled={busy || rows.length === 0}
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
  } = useAIChat()

  const { applyToolResults, clearAIOverlays } = useMapContext()
  const { registerHandler, executeUIActionsFromToolResults } = useUIControl()
  const { user: authUser } = useAuthContext() || {}
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
        const title = result?.title || tr.title
        const t = title ? `"${title}"` : 'the item'
        toast.success(
          language === 'es'
            ? `¡Reclamo confirmado! Has reservado ${t}.`
            : `Claim confirmed! You reserved ${t}. Check Receipts & Activity.`,
          { autoClose: 6000, position: 'top-center' }
        )
      }
      if (tr.tool === 'cancel_claim' && ok) {
        lastToastedClaimRef.current = key
        toast.info(
          language === 'es' ? 'Reclamo cancelado.' : 'Claim released — item returned to inventory.',
          { autoClose: 4000, position: 'top-center' }
        )
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
    'get_mapbox_route', 'query_distribution_centers',
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
        executeUIActionsFromToolResults(last.toolResults)
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
  }, [messages, applyToolResults, executeUIActionsFromToolResults, MAP_TOOLS])

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
  const [voiceError, setVoiceError] = useState(null)
  const [voiceTranscript, setVoiceTranscript] = useState('')
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
  const messagesEndRef = useRef(null)
  // Container ref + state for the scroll-to-bottom pill. We show the pill
  // only when the user has scrolled away from the latest message so it
  // doesn't compete with the normal autoscroll behavior.
  const messagesContainerRef = useRef(null)
  const [showScrollPill, setShowScrollPill] = useState(false)
  const [showAttachMenu, setShowAttachMenu] = useState(false)
  const attachMenuRef = useRef(null)
  const inputRef = useRef(null)
  const panelRef = useRef(null)
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

  useEffect(() => { sendVoiceRef.current = sendVoice }, [sendVoice])

  // Register imperative handlers so the AI's ui_action tool can drive this panel.
  useEffect(() => {
    const u1 = registerHandler('setAssistantOpen', (open) => setIsOpen(!!open))
    const u2 = registerHandler('setAssistantExpanded', (exp) => setIsExpanded(!!exp))
    const u3 = registerHandler('clearMapOverlays', () => clearAIOverlays())
    const u4 = registerHandler('setLanguage', (lang) => {
      if (lang === 'en' || lang === 'es') setLanguage(lang)
    })
    return () => { u1(); u2(); u3(); u4() }
  }, [registerHandler, clearAIOverlays, setLanguage])

  // Last assistant message for voice mode auto-speak
  const lastAssistantMessage = useMemo(() => {
    for (let i = messages.length - 1; i >= 0; i--) {
      if (messages[i].role === 'assistant' && !messages[i].isError) return messages[i]
    }
    return null
  }, [messages])

  const quickActions = language === 'es' ? QUICK_ACTIONS_ES : QUICK_ACTIONS_EN

  // ─── Autocomplete: filter the suggestion pool by current input ───
  // Detect Spanish live from what the user is typing so suggestions
  // adapt before the first AI exchange. Spanish punctuation (¿/¡/ñ) or
  // accented chars are reliable signals; we don't try to detect Spanish
  // words on their own (too noisy for autocomplete).
  const inputLooksSpanish = /[¿¡ñáéíóúü]/i.test(inputText)
  const effectiveLang = inputLooksSpanish ? 'es' : language
  const suggestionPool = effectiveLang === 'es' ? SUGGESTIONS_ES : SUGGESTIONS_EN
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
      messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' })
      return
    }
    const nearBottom = el.scrollHeight - el.scrollTop - el.clientHeight < 200
    if (nearBottom) {
      messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' })
    }
  }, [messages, isOpen, isLoading])

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
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [])

  // Focus input when panel opens
  useEffect(() => {
    if (isOpen && inputRef.current) {
      setTimeout(() => inputRef.current?.focus(), 200)
    }
  }, [isOpen])

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

  const handleSend = useCallback((e) => {
    e?.preventDefault()
    if (!inputText.trim() || isLoading) return
    sendMessage(inputText)
    setInputText('')
    setSuggestionsOpen(false)
    setSuggestionIndex(-1)
  }, [inputText, isLoading, sendMessage])

  const handleQuickAction = useCallback((msg) => {
    if (isLoading) return
    sendMessage(msg)
  }, [isLoading, sendMessage])

  // ─── File uploads (photo + CSV → bulk-listings) ───────
  const triggerPhotoUpload = useCallback(() => {
    if (uploadBusy || isLoading) return
    photoInputRef.current?.click()
  }, [uploadBusy, isLoading])

  const triggerCsvUpload = useCallback(() => {
    if (uploadBusy || isLoading) return
    csvInputRef.current?.click()
  }, [uploadBusy, isLoading])

  const cancelPendingUpload = useCallback(() => {
    if (uploadBusy) return
    // Bump session id so any still-running async callback (enrichment, vision,
    // storage upload) sees a stale id and bails out before touching state.
    uploadSessionRef.current += 1
    setPendingUpload(null)
  }, [uploadBusy])

  const handlePhotoSelected = useCallback(async (e) => {
    const file = e.target.files?.[0]
    e.target.value = ''
    if (!file) return
    if (!file.type.startsWith('image/')) {
      const msg = language === 'es' ? 'Selecciona una imagen.' : 'Please select an image.'
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
      // Kick off the storage upload and the vision call in parallel so the
      // user sees the preview faster. Storage upload is optional; if it fails
      // (no auth, bucket missing) we fall back to a category-based image.
      const uploadPromise = (async () => {
        if (!authUser?.id) return null
        try {
          const res = await dataService.uploadFile(file, 'food-images')
          return res?.url || null
        } catch (err) {
          console.warn('Photo storage upload failed; falling back to stock image:', err?.message || err)
          return null
        }
      })()

      const { draft, confidence } = await aiChatService.visionListing(file, { userId: authUser?.id })
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
      }

      setPendingUpload({ kind: 'photo', rows: [enrichedDraft], filename: file.name, confidence })
      appendLocalMessage({
        role: 'assistant',
        message: language === 'es'
          ? `Detecté: **${draft.title}** (${draft.quantity} ${draft.unit}, ${draft.category}). Revisa el borrador abajo y confirma para publicar.`
          : `I detected: **${draft.title}** (${draft.quantity} ${draft.unit}, ${draft.category}). Review the draft below and confirm to publish.`,
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
  }, [appendLocalMessage, authUser?.id, language])

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
    setUploadBusy(true)
    try {
      const result = await aiChatService.bulkCreateListings(pendingUpload.rows, { userId: authUser.id })
      const { created, failed } = result
      toast.success(
        language === 'es'
          ? `✅ ${created} publicación${created === 1 ? '' : 'es'} creada${created === 1 ? '' : 's'} correctamente${failed ? ` (${failed} fallaron)` : ''}`
          : `✅ ${created} listing${created === 1 ? '' : 's'} created successfully${failed ? ` — ${failed} failed` : ''}`,
        { autoClose: 5000, position: 'top-center' }
      )
      setPendingUpload(null)

      // Notify Find Food / map views to refresh immediately.
      window.dispatchEvent(new CustomEvent('foodShared'))

      // Build a rich context prompt so Nouri responds naturally to what just happened.
      const isEs = language === 'es'
      const itemNames = pendingUpload.rows
        .slice(0, 5)
        .map(r => `${r.title} (${r.quantity} ${r.unit}, ${r.category})`)
        .join('; ')
      const moreItemsCount = pendingUpload.rows.length - 5
      const moreItems = moreItemsCount > 0
        ? (isEs ? ` y ${moreItemsCount} más` : ` and ${moreItemsCount} more`)
        : ''
      const failNote = failed
        ? (isEs ? ` (${failed} no se pudieron guardar)` : ` (${failed} could not be saved)`)
        : ''
      const kindLabel = pendingUpload.kind === 'photo'
        ? (isEs ? 'foto' : 'photo upload')
        : (isEs ? 'importación CSV' : 'bulk CSV upload')
      const prompt = isEs
        ? `[Acción ya completada por el sistema] El sistema acaba de guardar ${created} publicación${created === 1 ? '' : 'es'} de comida en la base de datos mediante ${kindLabel}${failNote}. Artículos: ${itemNames}${moreItems}. NO llames a post_food_listing, create_food_listing, bulk_post_food_listings ni bulk_import_listings — la publicación YA está guardada y volver a llamar crearía duplicados. Solo responde en español, felicítame brevemente y ofrece 2-3 sugerencias de próximos pasos (revisar mis publicaciones, compartir más, ver el impacto).`
        : `[Action already completed by the system] The system just saved ${created} food listing${created === 1 ? '' : 's'} to the database via ${kindLabel}${failNote}. Items: ${itemNames}${moreItems}. DO NOT call post_food_listing, create_food_listing, bulk_post_food_listings, or bulk_import_listings — the listing is ALREADY saved and calling again would create duplicates. Just reply with a brief congratulation and 2-3 helpful next-step suggestions (reviewing listings, sharing more, checking impact).`
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

      // Start MediaRecorder
      const mimeType = MediaRecorder.isTypeSupported('audio/webm;codecs=opus')
        ? 'audio/webm;codecs=opus'
        : MediaRecorder.isTypeSupported('audio/webm') ? 'audio/webm' : ''
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
        if (!chunks.length) { setIsVoiceListening(false); return }

        const audioBlob = new Blob(chunks, { type: recorder.mimeType || 'audio/webm' })
        // Skip tiny recordings (< 0.5s of data, ~noise)
        if (audioBlob.size < 5000) {
          setIsVoiceListening(false)
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
        }
      }

      recorder.start(250) // collect data every 250ms
      mediaRecorderRef.current = recorder
      setIsVoiceListening(true)

      // Voice Activity Detection — stop recording after silence
      let speechDetected = false
      let silenceStart = 0
      const SILENCE_THRESHOLD = 15  // RMS level below which = silence
      const SILENCE_DURATION = 1800 // ms of silence before auto-stop
      const MAX_DURATION = 30000    // max recording duration
      const dataArray = new Uint8Array(analyser.frequencyBinCount)
      const startTime = Date.now()

      const checkAudio = () => {
        if (!mediaRecorderRef.current || mediaRecorderRef.current.state !== 'recording') return

        // Auto-stop at max duration
        if (Date.now() - startTime > MAX_DURATION) {
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

  // Voice mode is manual — user taps the orb to start each recording

  // OpenAI TTS: speak latest assistant message in voice mode
  // Skip the initial welcome message — only speak new responses
  useEffect(() => {
    if (!voiceMode || !lastAssistantMessage || isLoading) return
    if (lastAssistantMessage.id === 'welcome') return
    if (lastAssistantMessage.id === lastSpokenIdRef.current) return
    lastSpokenIdRef.current = lastAssistantMessage.id

    const speakWithOpenAI = async () => {
      try {
        const cleanText = lastAssistantMessage.message
          .replace(/\*\*(.*?)\*\*/g, '$1')
          .replace(/[#*_~`]/g, '')
          .replace(/\n+/g, '. ')
          .replace(/\s+/g, ' ')
          .trim()
        if (!cleanText) return

        // Mute the mic stream to prevent feedback loop (AI voice → mic → Whisper → sends message)
        if (mediaStreamRef.current) {
          mediaStreamRef.current.getAudioTracks().forEach(t => { t.enabled = false })
        }

        setIsVoiceSpeaking(true)
        try {
          const audioBlob = await textToSpeech(cleanText, { lang: lastAssistantMessage.message?.match(/[\u00e1\u00e9\u00ed\u00f3\u00fa\u00f1]/) ? 'es' : 'en' })
          const { play, stop } = playAudioBlob(
            audioBlob,
            () => setIsVoiceSpeaking(true),
            () => setIsVoiceSpeaking(false)
          )
          currentAudioRef.current = stop
          await play
          currentAudioRef.current = null
          return
        } catch (ttsErr) {
          console.warn('OpenAI TTS failed, falling back to browser speech:', ttsErr)
        }

        // Fallback: browser SpeechSynthesis
        if (typeof window !== 'undefined' && window.speechSynthesis) {
          await new Promise((resolve) => {
            const utterance = new SpeechSynthesisUtterance(cleanText.slice(0, 500))
            utterance.lang = lastAssistantMessage.message?.match(/[\u00e1\u00e9\u00ed\u00f3\u00fa\u00f1]/) ? 'es-ES' : 'en-US'
            utterance.rate = 1.0
            utterance.onend = resolve
            utterance.onerror = resolve
            window.speechSynthesis.speak(utterance)
          })
        }
        setIsVoiceSpeaking(false)
      } catch (err) {
        console.error('Voice output failed:', err)
        setIsVoiceSpeaking(false)
      } finally {
        // Re-enable mic tracks after TTS finishes (with delay to avoid echo)
        setTimeout(() => {
          if (mediaStreamRef.current) {
            mediaStreamRef.current.getAudioTracks().forEach(t => { t.enabled = true })
          }
        }, 500)
      }
    }
    speakWithOpenAI()
  }, [voiceMode, lastAssistantMessage, isLoading])

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
      handleSend()
    }
  }, [handleSend, suggestionsOpen, filteredSuggestions, suggestionIndex, acceptSuggestion])

  // ─── Floating bubble (closed state) ──────
  if (!isOpen) {
    return (
      <div className="fixed bottom-20 right-5 z-40 group" style={{ perspective: '600px' }}>
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
    ? 'fixed inset-4 z-50 md:inset-8'
    : 'fixed bottom-20 right-4 z-50 w-[540px] max-w-[calc(100vw-2rem)] h-[820px] max-h-[calc(100vh-6rem)]'

  return (
    <div ref={panelRef} className={`${panelClasses} flex flex-col rounded-2xl shadow-2xl overflow-hidden transition-all duration-300 border border-slate-700/50`} style={{ background: 'linear-gradient(145deg, #0f172a 0%, #1e293b 50%, #0f172a 100%)' }}>
      {/* Header */}
      <div className="bg-gradient-to-r from-slate-800 via-slate-800 to-slate-900 text-white px-4 py-3 flex items-center justify-between flex-shrink-0 border-b border-cyan-500/20">
        <div className="flex items-center gap-3">
          <div className="w-9 h-9 rounded-full bg-gradient-to-br from-cyan-400 to-blue-500 flex items-center justify-center shadow-md shadow-cyan-500/30">
            <svg viewBox="0 0 100 100" className="w-6 h-6">
              <circle cx="50" cy="52" r="36" fill="#f0f4f8" />
              <rect x="26" y="38" rx="12" ry="12" width="48" height="24" fill="#1e293b" opacity="0.85" />
              <path d="M35 53 Q38 46 41 53" stroke="#67e8f9" strokeWidth="4" strokeLinecap="round" fill="none" />
              <path d="M59 53 Q62 46 65 53" stroke="#67e8f9" strokeWidth="4" strokeLinecap="round" fill="none" />
            </svg>
          </div>
          <div>
            <h3 className="font-semibold text-sm text-white leading-tight">Nouri</h3>
            <p className="text-cyan-200/80 text-[10px] flex items-center gap-1.5 leading-tight mt-0.5">
              <span
                className="w-1.5 h-1.5 rounded-full bg-emerald-400 animate-pulse shadow-sm shadow-emerald-400/60"
                aria-hidden="true"
              />
              <span>
                {isAuthenticated
                  ? (language === 'es' ? 'En línea · siempre disponible' : 'Online · always here')
                  : (language === 'es' ? 'Inicia sesión para más funciones' : 'Sign in for full features')}
              </span>
            </p>
          </div>
        </div>

        <div className="flex items-center gap-1">
          {/* Language toggle — flag-style for instant recognition */}
          <button
            onClick={() => {
              const newLang = language === 'es' ? 'en' : 'es'
              sendMessage(newLang === 'es' ? 'Hola, habla en español por favor' : 'Hi, please speak in English')
            }}
            className="flex items-center gap-1 text-cyan-200/85 hover:text-white text-[11px] font-medium px-2 py-1 rounded-md hover:bg-cyan-500/15 transition-colors border border-cyan-500/20 hover:border-cyan-400/40"
            title={language === 'es' ? 'Switch to English' : 'Cambiar a Español'}
            aria-label={language === 'es' ? 'Switch to English' : 'Cambiar a Español'}
          >
            <span aria-hidden="true">{language === 'es' ? '🇺🇸' : '🇪🇸'}</span>
            <span className="tracking-wide">{language === 'es' ? 'EN' : 'ES'}</span>
          </button>

          {/* Menu */}
          <div className="relative">
            <button
              onClick={() => setShowMenu(!showMenu)}
              className="text-cyan-300/60 hover:text-cyan-300 p-1 rounded hover:bg-cyan-500/10 transition-colors"
              aria-label="Chat menu"
            >
              <svg xmlns="http://www.w3.org/2000/svg" className="h-5 w-5" viewBox="0 0 20 20" fill="currentColor">
                <path d="M10 6a2 2 0 110-4 2 2 0 010 4zM10 12a2 2 0 110-4 2 2 0 010 4zM10 18a2 2 0 110-4 2 2 0 010 4z" />
              </svg>
            </button>
            {showMenu && (
              <div className="absolute right-0 top-full mt-1 bg-slate-800 rounded-lg shadow-xl border border-slate-700 py-1 w-44 z-10 backdrop-blur-sm">
                <button
                  onClick={() => { clearHistory(); setShowMenu(false) }}
                  className="w-full text-left px-4 py-2 text-sm text-slate-300 hover:bg-slate-700/50 hover:text-cyan-300 transition-colors"
                >
                  🗑️ Clear conversation
                </button>
                <button
                  onClick={() => { setIsExpanded(!isExpanded); setShowMenu(false) }}
                  className="w-full text-left px-4 py-2 text-sm text-slate-300 hover:bg-slate-700/50 hover:text-cyan-300 transition-colors"
                >
                  {isExpanded ? '🗗 Compact view' : '⬜ Full screen'}
                </button>
              </div>
            )}
          </div>

          {/* Expand / collapse */}
          <button
            onClick={() => setIsExpanded(!isExpanded)}
            className="text-cyan-300/60 hover:text-cyan-300 p-1 rounded hover:bg-cyan-500/10 transition-colors hidden md:block"
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
            onClick={() => { setIsOpen(false); setIsExpanded(false); setShowMenu(false) }}
            className="text-cyan-300/60 hover:text-cyan-300 p-1 rounded hover:bg-red-500/20 transition-colors"
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
          className="flex-1 flex flex-col items-center justify-between py-5 px-6 overflow-hidden relative"
          style={{ background: 'radial-gradient(ellipse at center, #0f172a 0%, #020617 100%)' }}
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
              className="inline-flex items-center gap-1.5 text-xs text-slate-400 hover:text-white px-2.5 py-1.5 rounded-lg hover:bg-white/5 transition-all focus:outline-none focus-visible:ring-2 focus-visible:ring-cyan-400/50"
              aria-label={language === 'es' ? 'Salir del modo de voz' : 'Exit voice mode'}
            >
              <svg xmlns="http://www.w3.org/2000/svg" className="h-4 w-4" viewBox="0 0 20 20" fill="currentColor" aria-hidden="true">
                <path fillRule="evenodd" d="M9.707 16.707a1 1 0 01-1.414 0l-6-6a1 1 0 010-1.414l6-6a1 1 0 011.414 1.414L5.414 9H17a1 1 0 110 2H5.414l4.293 4.293a1 1 0 010 1.414z" clipRule="evenodd" />
              </svg>
              {language === 'es' ? 'Volver al chat' : 'Back to chat'}
            </button>

            {/* Language pill — confirms which language Whisper is listening for. */}
            <span
              className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full bg-white/5 ring-1 ring-white/10 text-[10px] font-semibold tracking-wider uppercase text-slate-300 backdrop-blur-sm"
              title={language === 'es' ? 'Idioma del modo de voz' : 'Voice mode language'}
            >
              <span aria-hidden="true">{language === 'es' ? '🇪🇸' : '🇺🇸'}</span>
              {language === 'es' ? 'Español' : 'English'}
            </span>
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
            {/* Transcript region — fixed min-height so layout doesn't jump
                when text appears/disappears. */}
            <div className="min-h-[40px] flex items-center justify-center px-4">
              {voiceTranscript ? (
                <p
                  className={`text-sm italic text-center max-w-[300px] leading-snug transition-colors duration-300 ${
                    isVoiceListening ? 'text-white/80' : 'text-slate-400/70'
                  }`}
                  aria-live="polite"
                >
                  &ldquo;{voiceTranscript}&rdquo;
                </p>
              ) : (
                <p className="text-[12px] text-slate-500/40 italic text-center max-w-[280px]">
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
                  ? 'bg-rose-500/10 text-rose-300 ring-rose-500/30'
                  : isVoiceSpeaking
                    ? 'bg-teal-500/10 text-teal-300 ring-teal-500/30'
                    : isLoading
                      ? 'bg-violet-500/10 text-violet-300 ring-violet-500/30'
                      : isVoiceListening
                        ? 'bg-blue-500/10 text-blue-300 ring-blue-500/30'
                        : 'bg-white/5 text-slate-400 ring-white/10'
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
      <div className="flex-1 relative min-h-0">
        <div
          ref={messagesContainerRef}
          className="absolute inset-0 overflow-y-auto px-4 py-3 nourish-scrollbar scroll-smooth"
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
                    isLoading={isLoading}
                    currentUser={authUser}
                    onRetry={retryMessage}
                    onRegenerate={regenerateLast}
                    showRegenerate={idx === lastAssistantIdx}
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

      {/* Quick-chip rail — persistent contextual prompts for first turn.
          After the welcome state, this becomes a thin horizontally-scrolling
          rail so users always have one-tap access to common requests
          without retyping. */}
      {messages.length > 1 && messages.length <= 3 && !isLoading && (
        <div className="px-4 pb-2 flex-shrink-0">
          <div className="flex gap-1.5 overflow-x-auto nourish-scrollbar-h" role="list" aria-label={language === 'es' ? 'Sugerencias rápidas' : 'Quick suggestions'}>
            {quickActions.map((qa, i) => (
              <button
                key={i}
                onClick={() => handleQuickAction(qa.message)}
                className="whitespace-nowrap text-[11px] bg-slate-800/60 text-slate-200 hover:bg-cyan-500/15 hover:text-cyan-100 px-3 py-1.5 rounded-full transition-all border border-slate-600/40 hover:border-cyan-400/40 flex-shrink-0"
                role="listitem"
              >
                {qa.label}
              </button>
            ))}
          </div>
        </div>
      )}

      {/* Upload preview card — photo / CSV → bulk-listings */}
      {pendingUpload && (
        <BulkUploadPreview
          pending={pendingUpload}
          busy={uploadBusy}
          language={language}
          onCancel={cancelPendingUpload}
          onConfirm={confirmBulkCreate}
          onUpdateRow={updatePendingRow}
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
        ref={csvInputRef}
        type="file"
        accept=".csv,text/csv,application/vnd.ms-excel"
        className="hidden"
        onChange={handleCsvSelected}
        aria-hidden="true"
        tabIndex={-1}
      />

      {/* Input area */}
      <form onSubmit={handleSend} className="border-t border-cyan-500/20 px-3 pt-2.5 pb-2 flex flex-col gap-1 flex-shrink-0 bg-slate-900/80 backdrop-blur-sm">
        <div className="flex items-end gap-2">
          {/* Attachments menu — collapses photo + CSV uploads behind a
              single "+" button (Slack/Messenger pattern) so the input bar
              feels focused on the most important action: typing + send. */}
          <div ref={attachMenuRef} className="relative flex-shrink-0">
            <button
              type="button"
              onClick={() => setShowAttachMenu(v => !v)}
              disabled={isLoading || uploadBusy}
              className={`inline-flex items-center justify-center w-9 h-9 rounded-full transition-all border ${
                showAttachMenu
                  ? 'bg-cyan-500/20 text-cyan-200 border-cyan-400/40 rotate-45'
                  : 'bg-slate-800/60 text-slate-300 border-slate-600/50 hover:bg-cyan-500/15 hover:text-cyan-200 hover:border-cyan-400/30'
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
                className="absolute bottom-full left-0 mb-2 min-w-[200px] rounded-xl border border-cyan-500/25 bg-slate-900/95 backdrop-blur-md shadow-xl shadow-cyan-500/10 overflow-hidden z-30 animate-fade-in"
              >
                <button
                  type="button"
                  role="menuitem"
                  onClick={() => { setShowAttachMenu(false); triggerPhotoUpload() }}
                  className="w-full flex items-center gap-3 px-3 py-2.5 text-sm text-slate-200 hover:bg-fuchsia-500/15 hover:text-fuchsia-100 transition-colors"
                >
                  <span className="inline-flex w-8 h-8 rounded-lg bg-fuchsia-500/15 text-fuchsia-300 items-center justify-center">
                    <i className="fas fa-camera text-[13px]" aria-hidden="true" />
                  </span>
                  <span className="flex-1 text-left">
                    <span className="block font-medium leading-tight">
                      {language === 'es' ? 'Foto → publicar' : 'Photo → list food'}
                    </span>
                    <span className="block text-[10px] text-slate-400 leading-tight mt-0.5">
                      {language === 'es' ? 'IA detecta artículos' : 'AI auto-detects items'}
                    </span>
                  </span>
                </button>
                <button
                  type="button"
                  role="menuitem"
                  onClick={() => { setShowAttachMenu(false); triggerCsvUpload() }}
                  className="w-full flex items-center gap-3 px-3 py-2.5 text-sm text-slate-200 hover:bg-emerald-500/15 hover:text-emerald-100 transition-colors border-t border-slate-700/50"
                >
                  <span className="inline-flex w-8 h-8 rounded-lg bg-emerald-500/15 text-emerald-300 items-center justify-center">
                    <i className="fas fa-file-csv text-[13px]" aria-hidden="true" />
                  </span>
                  <span className="flex-1 text-left">
                    <span className="block font-medium leading-tight">
                      {language === 'es' ? 'CSV en lote' : 'Bulk import CSV'}
                    </span>
                    <span className="block text-[10px] text-slate-400 leading-tight mt-0.5">
                      {language === 'es' ? 'Sube varios listados a la vez' : 'Upload many listings at once'}
                    </span>
                  </span>
                </button>
              </div>
            )}
          </div>

          <div className="flex-1 relative">
            {/* Autocomplete dropdown */}
            {showSuggestions && (
              <ul
                role="listbox"
                aria-label={language === 'es' ? 'Sugerencias' : 'Suggestions'}
                className="absolute bottom-full left-0 right-0 mb-2 max-h-56 overflow-y-auto rounded-xl border border-cyan-500/30 bg-slate-900/95 backdrop-blur-md shadow-lg shadow-cyan-500/10 z-20 nourish-scrollbar"
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
                        ? 'bg-cyan-500/20 text-cyan-100'
                        : 'text-slate-200 hover:bg-slate-800/80'
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
              onChange={(e) => { setInputText(e.target.value); setSuggestionsOpen(true) }}
              onKeyDown={handleKeyDown}
              onFocus={() => setSuggestionsOpen(true)}
              onBlur={() => setTimeout(() => setSuggestionsOpen(false), 120)}
              placeholder={language === 'es' ? 'Pregunta lo que quieras…' : 'Message Nouri…'}
              className={`w-full resize-none rounded-2xl border bg-slate-800/70 text-slate-100 placeholder-slate-500 px-4 py-2.5 text-sm leading-relaxed max-h-32 outline-none transition-all ${
                isLoading
                  ? 'ai-input-glow border-cyan-400/80'
                  : 'border-slate-600/50 focus:border-cyan-400/60 focus:ring-2 focus:ring-cyan-500/20 focus:bg-slate-800/90'
              }`}
              rows={1}
              disabled={isLoading}
              aria-label="Message input"
              aria-autocomplete="list"
              aria-expanded={showSuggestions}
              aria-controls="ai-chat-suggestions"
            />
          </div>

          {/* Voice mode — AI speaks responses aloud */}
          <button
            type="button"
            onClick={enterVoiceMode}
            disabled={isLoading}
            className="flex-shrink-0 inline-flex items-center justify-center w-9 h-9 rounded-full transition-all border border-slate-600/50 bg-slate-800/60 text-slate-300 hover:text-cyan-200 hover:bg-cyan-500/15 hover:border-cyan-400/30 disabled:opacity-40 disabled:cursor-not-allowed"
            title={language === 'es' ? 'Modo voz' : 'Voice mode'}
            aria-label="Switch to voice mode"
          >
            <i className="fas fa-microphone text-[13px]" aria-hidden="true" />
          </button>

          {/* Send button — stronger affordance, clearer disabled state */}
          <button
            type="submit"
            disabled={!inputText.trim() || isLoading}
            className={`flex-shrink-0 inline-flex items-center justify-center w-9 h-9 rounded-full transition-all ${
              inputText.trim() && !isLoading
                ? 'bg-gradient-to-br from-cyan-400 to-blue-500 text-white hover:from-cyan-300 hover:to-blue-400 shadow-md shadow-cyan-500/30 hover:scale-105 active:scale-95'
                : 'bg-slate-800/60 text-slate-500 border border-slate-600/40 cursor-not-allowed'
            }`}
            aria-label={language === 'es' ? 'Enviar mensaje' : 'Send message'}
          >
            <i className="fas fa-paper-plane text-[12px]" aria-hidden="true" />
          </button>
        </div>

        {/* Keyboard / status hint — subtle so it doesn't add visual noise */}
        <div className="flex items-center justify-between px-1 text-[10px] text-slate-500/80">
          <span className="hidden sm:inline">
            {language === 'es'
              ? 'Enter para enviar · Shift+Enter para línea nueva'
              : 'Enter to send · Shift+Enter for new line'}
          </span>
          <span className={`ml-auto tabular-nums transition-colors ${
            inputText.length > 4000 ? 'text-rose-400' : inputText.length > 2000 ? 'text-amber-300/80' : 'text-slate-500/60'
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
  )
}

export default AIChatPanel
