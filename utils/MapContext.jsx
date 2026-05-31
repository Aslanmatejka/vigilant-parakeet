import React, { createContext, useContext, useState, useCallback, useMemo } from 'react'

/**
 * MapContext — bridges AI chat tool results to the FoodMap component.
 *
 * The AI assistant calls backend tools like `search_food_near_user`,
 * `get_mapbox_route`, and `query_distribution_centers`. When their results
 * arrive in the chat, AIChatPanel pushes them here so any mounted FoodMap
 * (or other map view) can display the markers, draw the route line, and
 * pan/zoom to the relevant area.
 */

const MapContext = createContext(null)

const initialState = {
  // [{ id, lat, lng, title, subtitle, kind: 'food'|'distribution'|'user'|'pin', meta }]
  aiMarkers: [],
  // GeoJSON LineString geometry from get_mapbox_route, plus origin/destination
  aiRoute: null,
  // { lat, lng, zoom } – request to center the map
  centerRequest: null,
  // Highlighted listing id (e.g. when AI references a specific result)
  highlightId: null,
  // Tick that increments whenever the AI updates the map (for FoodMap effects)
  updateNonce: 0,
}

export function MapProvider({ children }) {
  const [state, setState] = useState(initialState)

  const setAIMarkers = useCallback((markers) => {
    setState(prev => ({
      ...prev,
      aiMarkers: Array.isArray(markers) ? markers : [],
      updateNonce: prev.updateNonce + 1,
    }))
  }, [])

  const setAIRoute = useCallback((route) => {
    setState(prev => ({
      ...prev,
      aiRoute: route || null,
      updateNonce: prev.updateNonce + 1,
    }))
  }, [])

  /**
   * Center the map on a coordinate.
   *
   * Supports both call styles for backwards compatibility:
   *   centerOn(lat, lng, zoom)
   *   centerOn({ lat, lng, zoom })
   */
  const centerOn = useCallback((latOrOpts, maybeLng, maybeZoom = 13) => {
    let lat, lng, zoom
    if (typeof latOrOpts === 'object' && latOrOpts !== null) {
      lat = Number(latOrOpts.lat)
      lng = Number(latOrOpts.lng)
      zoom = Number(latOrOpts.zoom ?? 13)
    } else {
      lat = Number(latOrOpts)
      lng = Number(maybeLng)
      zoom = Number(maybeZoom)
    }
    if (!Number.isFinite(lat) || !Number.isFinite(lng)) return
    if (!Number.isFinite(zoom)) zoom = 13
    setState(prev => ({
      ...prev,
      centerRequest: { lat, lng, zoom, ts: Date.now() },
      updateNonce: prev.updateNonce + 1,
    }))
  }, [])

  const highlightListing = useCallback((id) => {
    setState(prev => ({ ...prev, highlightId: id || null }))
  }, [])

  const clearAIOverlays = useCallback(() => {
    setState(prev => ({
      ...prev,
      aiMarkers: [],
      aiRoute: null,
      highlightId: null,
      updateNonce: prev.updateNonce + 1,
    }))
  }, [])

  /**
   * Inspect a list of {tool, args, result} entries from the AI and update
   * the map accordingly. Safe to call with empty/undefined input.
   */
  const applyToolResults = useCallback((toolResults) => {
    if (!Array.isArray(toolResults) || toolResults.length === 0) return

    let nextMarkers = null
    let nextRoute = null
    let nextCenter = null

    for (const entry of toolResults) {
      if (!entry || !entry.tool) continue
      const result = entry.result ?? entry
      const { tool } = entry

      // search_food_near_user → drop food markers and recenter
      if (tool === 'search_food_near_user' || tool === 'search_food_nearby' || tool === 'get_recent_listings') {
        const listings = Array.isArray(result.listings)
          ? result.listings
          : (Array.isArray(result.results) ? result.results : [])
        const markers = listings
          .map(l => {
            const lat = parseFloat(l.latitude ?? l.lat)
            const lng = parseFloat(l.longitude ?? l.lng)
            if (Number.isNaN(lat) || Number.isNaN(lng)) return null
            return {
              id: l.id || `${tool}-${lat}-${lng}`,
              lat,
              lng,
              title: l.title || l.name || 'Food listing',
              subtitle: [l.category, l.address, l.distance_km ? `${l.distance_km} km` : null]
                .filter(Boolean)
                .join(' · '),
              kind: 'food',
              meta: l,
            }
          })
          .filter(Boolean)
        if (markers.length > 0) {
          nextMarkers = (nextMarkers || []).concat(markers)
          if (!nextCenter) {
            nextCenter = { lat: markers[0].lat, lng: markers[0].lng, zoom: 12 }
          }
        }
      }

      // query_distribution_centers → drop distribution markers
      if (tool === 'query_distribution_centers') {
        const centers = Array.isArray(result.centers || result.events || result.results)
          ? (result.centers || result.events || result.results)
          : []
        const markers = centers
          .map(c => {
            const lat = parseFloat(c.latitude ?? c.lat)
            const lng = parseFloat(c.longitude ?? c.lng)
            if (Number.isNaN(lat) || Number.isNaN(lng)) return null
            return {
              id: c.id || `dist-${lat}-${lng}`,
              lat,
              lng,
              title: c.name || c.title || 'Distribution center',
              subtitle: [c.address, c.event_date, c.start_time].filter(Boolean).join(' · '),
              kind: 'distribution',
              meta: c,
            }
          })
          .filter(Boolean)
        if (markers.length > 0) {
          nextMarkers = (nextMarkers || []).concat(markers)
          if (!nextCenter) {
            nextCenter = { lat: markers[0].lat, lng: markers[0].lng, zoom: 12 }
          }
        }
      }

      // get_mapbox_route → draw route line + endpoint markers.
      // Route data can live in three places depending on flow:
      //   - live response: result.geometry / origin / destination
      //   - flat legacy:   entry.route.{geometry, ...}
      //   - rehydrated:    result.route.{geometry, ...} (after normalizer)
      if (tool === 'get_mapbox_route' && result && !result.error) {
        const routePayload = entry.route || result.route || result
        const geometry = routePayload.geometry || null
        const origin = routePayload.origin || result.origin
        const destination = routePayload.destination || result.destination
        nextRoute = {
          geometry,
          origin,
          destination,
          distance_km: routePayload.distance_km ?? result.distance_km,
          duration_text: routePayload.duration_text ?? result.duration_text,
          profile: routePayload.profile ?? result.profile,
        }
        if (origin && destination) {
          const endpointMarkers = [
            {
              id: 'route-origin',
              lat: origin.lat,
              lng: origin.lng,
              title: 'Start',
              kind: 'pin',
            },
            {
              id: 'route-destination',
              lat: destination.lat,
              lng: destination.lng,
              title: 'Destination',
              kind: 'pin',
            },
          ]
          nextMarkers = (nextMarkers || []).concat(endpointMarkers)
          if (!nextCenter) {
            nextCenter = {
              lat: (origin.lat + destination.lat) / 2,
              lng: (origin.lng + destination.lng) / 2,
              zoom: 11,
            }
          }
        }
      }
    }

    setState(prev => ({
      ...prev,
      aiMarkers: nextMarkers !== null ? nextMarkers : prev.aiMarkers,
      aiRoute: nextRoute !== null ? nextRoute : prev.aiRoute,
      centerRequest: nextCenter ? { ...nextCenter, ts: Date.now() } : prev.centerRequest,
      updateNonce: prev.updateNonce + 1,
    }))
  }, [])

  const value = useMemo(() => ({
    ...state,
    setAIMarkers,
    setAIRoute,
    centerOn,
    highlightListing,
    clearAIOverlays,
    applyToolResults,
  }), [state, setAIMarkers, setAIRoute, centerOn, highlightListing, clearAIOverlays, applyToolResults])

  return <MapContext.Provider value={value}>{children}</MapContext.Provider>
}

export function useMapContext() {
  const ctx = useContext(MapContext)
  if (!ctx) {
    // Safe no-op fallback so components mounted outside the provider
    // (e.g. in tests) don't crash.
    return {
      aiMarkers: [],
      aiRoute: null,
      centerRequest: null,
      highlightId: null,
      updateNonce: 0,
      setAIMarkers: () => {},
      setAIRoute: () => {},
      centerOn: () => {},
      highlightListing: () => {},
      clearAIOverlays: () => {},
      applyToolResults: () => {},
    }
  }
  return ctx
}

export default MapContext
