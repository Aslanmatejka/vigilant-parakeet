import React, { createContext, useContext, useRef, useCallback, useMemo } from 'react'

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

function buildUIDirective(entry) {
  if (!entry) return null
  const base = entry.result && typeof entry.result === 'object' ? entry.result : entry
  const ok = entry.ok !== false && base.ok !== false && !base.error
  return {
    ok,
    action: base.action || entry.action,
    path: base.path || entry.path,
    target: base.target || entry.target,
    listing_id: base.listing_id || entry.listing_id,
    target_id: base.target_id || entry.target_id,
    lang: base.lang || entry.lang,
  }
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

  /** Run a single ui_action directive returned by the backend tool. */
  const executeUIAction = useCallback((directive) => {
    if (!directive || directive.ok === false || !directive.action) return false
    const { action } = directive

    switch (action) {
      case 'navigate': {
        const path = directive.path || directive.target
        if (path && typeof navigate === 'function') {
          navigate(path.startsWith('/') ? path : `/${path}`)
          return true
        }
        return false
      }

      case 'open_modal':
      case 'toggle_modal': {
        const target = String(directive.target || '').replace(/_/g, '-')
        const route = MODAL_TARGET_ROUTES[target] || MODAL_TARGET_ROUTES[directive.target]
        if (route && typeof navigate === 'function') {
          navigate(route)
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
          return true
        }
        return false
      }

      case 'open_listing': {
        if (directive.listing_id && typeof navigate === 'function') {
          navigate(`/find#listing=${encodeURIComponent(directive.listing_id)}`)
          return true
        }
        return false
      }

      case 'clear_map':
        return callHandler('clearMapOverlays')

      case 'scroll_to_top':
        try {
          window.scrollTo({ top: 0, behavior: 'smooth' })
          return true
        } catch { return false }

      case 'scroll_to_bottom':
        try {
          window.scrollTo({ top: document.documentElement.scrollHeight, behavior: 'smooth' })
          return true
        } catch { return false }

      case 'focus': {
        if (!directive.target_id) return false
        try {
          const el = document.querySelector(`[data-ai-id="${directive.target_id}"]`)
          if (el) {
            el.scrollIntoView({ behavior: 'smooth', block: 'center' })
            if (typeof el.focus === 'function') el.focus()
            return true
          }
        } catch (err) { console.error('focus failed:', err) }
        return false
      }

      case 'set_language':
        return callHandler('setLanguage', directive.lang)

      default:
        console.warn('Unknown ui_action:', action)
        return false
    }
  }, [navigate, callHandler])

  /** Run every ui_action / navigate_ui found in a tool_results array. */
  const executeUIActionsFromToolResults = useCallback((toolResults) => {
    if (!Array.isArray(toolResults) || toolResults.length === 0) return 0
    let count = 0
    for (const entry of toolResults) {
      if (!entry?.tool) continue
      if (entry.tool !== 'ui_action' && entry.tool !== 'navigate_ui') continue
      const directive = buildUIDirective(entry)
      if (directive && executeUIAction(directive)) count += 1
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
