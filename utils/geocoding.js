/**
 * Forward-geocode a free-form address to {latitude, longitude} via Mapbox.
 * Returns null when no result is found or the result falls outside the Bay Area.
 */
import { API_CONFIG } from './config'
import { bayAreaGeocodeParams, isBayAreaCoord } from './mapBounds'

export async function geocodeAddress(address) {
    const trimmed = (address || '').trim()
    if (!trimmed) return null

    const token = API_CONFIG?.MAPBOX?.ACCESS_TOKEN
    if (!token) {
        console.warn('Mapbox token missing — cannot geocode address')
        return null
    }

    const url = `https://api.mapbox.com/geocoding/v5/mapbox.places/${encodeURIComponent(trimmed)}.json?access_token=${token}&limit=1&${bayAreaGeocodeParams()}`
    const response = await fetch(url)
    if (!response.ok) {
        throw new Error(`Geocoding failed: ${response.status}`)
    }
    const data = await response.json()
    const feature = data?.features?.[0]
    if (!feature?.center) return null
    const [longitude, latitude] = feature.center
    if (!isBayAreaCoord(latitude, longitude)) {
        console.warn('Geocode result outside Bay Area, ignoring:', trimmed, latitude, longitude)
        return null
    }
    return {
        latitude,
        longitude,
        place_name: feature.place_name || trimmed,
    }
}
