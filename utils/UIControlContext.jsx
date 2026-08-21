import React, { createContext, useContext, useRef, useCallback, useMemo } from 'react'
import { scrollIntoView, scrollWindowTo } from './motion.js'

/**
 * UIControlContext — lets the AI assistant drive the React UI.
 *
 * The backend `ui_action` / `navigate_ui` tools return directives like:
 *   { ok: true, action: 'navigate', path: '/find' }
 *   { ok: true, action: 'open_modal', target: 'meal-suggestions' }
 *
 * AIChatPanel forwards those directives here via `executeUIAction`.
 */

const UIControlContext = createContext(null)

const MODAL_TARGET_ROUTES = {
  'meal-suggestions': '/recipes',
  meal_suggestions: '/recipes',
  'spoilage-alerts': '/dashboard',
  spoilage_alerts: '/dashboard',
  'storage-coach': '/recipes',
  storage_coach: '/recipes',
  'smart-notifications': '/settings',
  smart_notifications: '/settings',
  'pickup-reminders': '/receipts',
  pickup_reminders: '/receipts',
  'sms-consent': '/settings',
  sms_consent: '/settings',
}

/** Maps navigate_ui target names (backend/ai/tools.py) to React Router paths. */
const NAV_TARGET_ROUTES = {
  list: '/find',
  create: '/share',
  'bulk-create': '/share',
  request: '/request',
  'request-food': '/request',
  'community-requests': '/community-requests',
  claim: '/claim',
  profile: '/profile',
  settings: '/settings',
  receipts: '/receipts',
  listings: '/listings',
  'near-me': '/near-me',
  notifications: '/notifications',
  login: '/login',
  signup: '/signup',
  home: '/',
  dashboard: '/dashboard',
  dispatch: '/admin/distribution',
  admin: '/admin',
  driver: '/admin',
  schedule: '/donations',
  partners: '/sponsors',
  'food-rescue': '/find',
  'meal-planning': '/recipes',
  'ai-matching': '/find',
  routes: '/find',
  emergency: '/contact',
  nutrition: '/recipes',
  consumption: '/dashboard',
  filters: '/find',
  favorites: '/find',
}

/**
 * The AI navigate_ui tool returns action ∈ {open, close, toggle} + target.
 * Legacy ui_action uses {navigate, open_modal, open_map, …}. Normalize here.
 */
function normalizeNavigateDirective(directive) {
  if (!directive?.action) return directive
  const act = String(directive.action).toLowerCase()
  if (!['open', 'close', 'toggle'].includes(act)) return directive

  const target = directive.target
    ? String(directive.target).replace(/_/g, '-')
    : null

  if (act === 'open') {
    if (!target) return directive
    if (target === 'map') return { ...directive, action: 'open_map' }
    if (target === 'chat') return { ...directive, action: 'open_assistant' }
    if (target === 'voice') return { ...directive, action: 'expand_assistant' }
    if (MODAL_TARGET_ROUTES[target]) {
      return { ...directive, action: 'open_modal', target }
    }
    const route = NAV_TARGET_ROUTES[target]
    if (route) return { ...directive, action: 'navigate', path: route, target }
  }

  if (act === 'close') {
    if (target === 'chat' || !target) return { ...directive, action: 'close_assistant' }
    if (target && MODAL_TARGET_ROUTES[target]) {
      return { ...directive, action: 'close_modal', target }
    }
    // Unknown close target — close chat only; do not yank to /find.
    return { ...directive, action: 'close_assistant' }
  }

  if (act === 'toggle' && target) {
    if (MODAL_TARGET_ROUTES[target]) {
      return { ...directive, action: 'toggle_modal', target }
    }
    const route = NAV_TARGET_ROUTES[target]
    if (route) return { ...directive, action: 'navigate', path: route, target }
  }

  return directive
}

function buildUIDirective(entry) {
  if (!entry) return null
  const base = entry.result && typeof entry.result === 'object' ? entry.result : entry
  const ok = entry.ok !== false && base.ok !== false && base.success !== false && !base.error
  const directive = {
    ok,
    action: base.action || entry.action,
    path: base.path || entry.path,
    target: base.target || entry.target,
    listing_id: base.listing_id || entry.listing_id,
    target_id: base.target_id || entry.target_id,
    lang: base.lang || entry.lang,
  }
  return normalizeNavigateDirective(directive)
}

export function UIControlProvider({ children, navigate }) {
  const handlersRef = useRef({})

  const registerHandler = useCallback((name, fn) => {
    if (typeof fn !== 'function') return () => {}
    handlersRef.current[name] = fn
    return () => {
      if (handlersRef.current[name] === fn) {
        delete handlersRef.current[name]
      }
    }
  }, [])

  const callHandler = useCallback((name, ...args) => {
    const fn = handlersRef.current[name]
    if (typeof fn === 'function') {
      try { fn(...args) } catch (err) { console.error(`UI handler ${name} failed:`, err) }
      return true
    }
    return false
  }, [])

  /** After navigating away, collapse the chat so the destination page is visible. */
  const minimizeAssistantForNavigation = useCallback(() => {
    callHandler('setAssistantExpanded', false)
    callHandler('setAssistantOpen', false)
  }, [callHandler])

  /** Run a single ui_action directive returned by the backend tool. */
  const executeUIAction = useCallback((directive) => {
    const normalized = normalizeNavigateDirective(directive)
    if (!normalized || normalized.ok === false || !normalized.action) return false
    const { action } = normalized

    switch (action) {
      case 'navigate': {
        let path = normalized.path
        const targetKey = normalized.target
          ? String(normalized.target).replace(/_/g, '-')
          : null
        if (!path && targetKey) {
          path = NAV_TARGET_ROUTES[targetKey] || (
            targetKey.startsWith('/') ? targetKey : null
          )
        }
        // Legacy: target was sometimes a raw path segment like "create"
        // which must not become "/create".
        if (!path && targetKey && targetKey.startsWith('/')) {
          path = targetKey
        }
        if (path && typeof navigate === 'function') {
          navigate(path.startsWith('/') ? path : `/${path}`)
          minimizeAssistantForNavigation()
          return true
        }
        return false
      }

      case 'open_modal':
      case 'toggle_modal': {
        const target = String(normalized.target || '').replace(/_/g, '-')
        const route = MODAL_TARGET_ROUTES[target] || MODAL_TARGET_ROUTES[normalized.target]
        if (route && typeof navigate === 'function') {
          navigate(route)
          minimizeAssistantForNavigation()
          return true
        }
        return false
      }

      case 'close_modal':
        return true

      case 'open_assistant':
        return callHandler('setAssistantOpen', true)

      case 'close_assistant':
        return callHandler('setAssistantOpen', false)

      case 'expand_assistant':
        callHandler('setAssistantOpen', true)
        return callHandler('setAssistantExpanded', true)

      case 'open_map': {
        if (typeof navigate === 'function') {
          navigate('/find')
          minimizeAssistantForNavigation()
          return true
        }
        return false
      }

      case 'open_listing': {
        if (normalized.listing_id && typeof navigate === 'function') {
          navigate(`/find#listing=${encodeURIComponent(normalized.listing_id)}`)
          return true
        }
        return false
      }

      case 'clear_map':
        return callHandler('clearMapOverlays')

      case 'scroll_to_top':
        try {
          scrollWindowTo({ top: 0, smooth: true })
          return true
        } catch { return false }

      case 'scroll_to_bottom':
        try {
          scrollWindowTo({ top: document.documentElement.scrollHeight, smooth: true })
          return true
        } catch { return false }

      case 'focus': {
        if (!normalized.target_id) return false
        try {
          const el = document.querySelector(`[data-ai-id="${normalized.target_id}"]`)
          if (el) {
            scrollIntoView(el, { smooth: true, block: 'center' })
            if (typeof el.focus === 'function') el.focus()
            return true
          }
        } catch (err) { console.error('focus failed:', err) }
        return false
      }

      case 'set_language':
        return callHandler('setLanguage', normalized.lang)

      default:
        console.warn('Unknown ui_action:', action)
        return false
    }
  }, [navigate, callHandler, minimizeAssistantForNavigation])

  /** Run every ui_action / navigate_ui found in a tool_results array. */
  const executeUIActionsFromToolResults = useCallback((toolResults) => {
    if (!Array.isArray(toolResults) || toolResults.length === 0) return 0
    let count = 0
    for (const entry of toolResults) {
      if (!entry?.tool) continue
      // Directions tools flip to Find Food map so the route is visible.
      if (
        entry.tool === 'show_route_to_listing'
        && entry.ok !== false
        && !entry.error
        && (entry.action === 'open_map' || entry.view === 'map' || entry.result?.action === 'open_map' || entry.result?.view === 'map')
      ) {
        if (executeUIAction({ ok: true, action: 'open_map' })) count += 1
        continue
      }
      if (entry.tool !== 'ui_action' && entry.tool !== 'navigate_ui') continue
      const directive = buildUIDirective(entry)
      const executed = directive && executeUIAction(directive)
      if (executed) count += 1
    }
    return count
  }, [executeUIAction])

  const value = useMemo(() => ({
    registerHandler,
    executeUIAction,
    executeUIActionsFromToolResults,
  }), [registerHandler, executeUIAction, executeUIActionsFromToolResults])

  return <UIControlContext.Provider value={value}>{children}</UIControlContext.Provider>
}

export function useUIControl() {
  const ctx = useContext(UIControlContext)
  if (!ctx) {
    return {
      registerHandler: () => () => {},
      executeUIAction: () => false,
      executeUIActionsFromToolResults: () => 0,
    }
  }
  return ctx
}

export default UIControlContext
