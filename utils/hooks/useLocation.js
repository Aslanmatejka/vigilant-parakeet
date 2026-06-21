import { useState, useEffect, useRef } from 'react';
import { locationService } from '../locationService';
import { useAuthContext } from '../AuthContext';

export function useGeoLocation() {
    const [location, setLocation] = useState(null);
    const [loading, setLoading] = useState(false);
    const [error, setError] = useState(null);
    const [watching, setWatching] = useState(false);
    const watchingRef = useRef(false);
    // Stable per-instance callback reference so we can unsubscribe THIS
    // consumer on unmount without tearing down the shared watch out from
    // under other components still using useGeoLocation.
    const watchCallbackRef = useRef(null);

    useEffect(() => {
        // Check if we have permission when the hook is first used
        checkPermission();
        
        // Cleanup any watching when component unmounts
        return () => {
            if (watchingRef.current && watchCallbackRef.current) {
                locationService.stopWatchingPosition(watchCallbackRef.current);
                watchingRef.current = false;
                watchCallbackRef.current = null;
            }
        };
    }, []);

    const checkPermission = async () => {
        try {
            const permissionStatus = await locationService.requestLocationPermission();
            if (permissionStatus === 'granted') {
                // If we already have permission, get the location silently.
                // 'prompt' is intentionally NOT auto-triggered here — wait for the user to
                // click "Enable GPS" so the browser prompt is tied to a user gesture.
                getCurrentPosition();
            }
        } catch (err) {
            // Permissions API is unavailable in some browsers (older Safari/Firefox).
            // Don't surface this as an error — the user can still click "Enable GPS".
            // eslint-disable-next-line no-console
            console.debug('Geolocation permission check unavailable:', err?.message);
        }
    };

    const getCurrentPosition = async () => {
        setLoading(true);
        setError(null);
        
        try {
            const position = await locationService.getCurrentPosition();
            setLocation(position);
            startWatching(); // Start watching for location updates
        } catch (err) {
            // Distinguish "denied" from "unavailable" / "timeout" for clearer UX.
            const code = err?.code;
            if (code === 1) {
                setError('Location permission denied. Please enable location access in your browser settings.');
            } else if (code === 3) {
                setError('Location request timed out. Please try again.');
            } else {
                setError('Unable to get your location. Please ensure location services are enabled.');
            }
        } finally {
            setLoading(false);
        }
    };

    const startWatching = () => {
        if (!watchingRef.current) {
            const cb = (position) => { setLocation(position); };
            watchCallbackRef.current = cb;
            locationService.startWatchingPosition(cb);
            setWatching(true);
            watchingRef.current = true;
        }
    };

    const enableLocation = async () => {
        // Always try to acquire the position directly. If permission is 'prompt',
        // this triggers the browser prompt (which only works inside a user gesture).
        // If it's 'denied', getCurrentPosition will reject with code 1 and we'll
        // surface a clear error message.
        await getCurrentPosition();
    };

    return {
        location,
        loading,
        error,
        enableLocation,
        refreshLocation: getCurrentPosition
    };
}

/**
 * Returns the best-effort user location with a documented source.
 * - `gps`     : live geolocation reading (preferred)
 * - `profile` : geocoded coordinates of the user's saved profile address
 * - `null`    : no location available
 *
 * Consumers can use the returned coordinates as the origin for distance
 * calculations, route rendering, and AI tools whether or not the browser
 * has granted geolocation permission.
 */
export function useEffectiveLocation() {
    const gps = useGeoLocation();
    let profileCoords = null;
    try {
        const { user } = useAuthContext() || {};
        const lat = user?.latitude;
        const lng = user?.longitude;
        if (typeof lat === 'number' && typeof lng === 'number') {
            profileCoords = { latitude: lat, longitude: lng };
        } else if (lat != null && lng != null) {
            const nLat = Number(lat);
            const nLng = Number(lng);
            if (Number.isFinite(nLat) && Number.isFinite(nLng)) {
                profileCoords = { latitude: nLat, longitude: nLng };
            }
        }
    } catch (_) {
        // Hook used outside AuthProvider — fall back to GPS only.
    }

    const effective = gps.location || profileCoords;
    const source = gps.location ? 'gps' : (profileCoords ? 'profile' : null);

    return {
        ...gps,
        location: effective,
        gpsLocation: gps.location,
        profileLocation: profileCoords,
        source,
    };
}
