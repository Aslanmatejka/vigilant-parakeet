import React from 'react';
import PropTypes from 'prop-types';
import { useNavigate } from 'react-router-dom';
import supabase from '../../utils/supabaseClient.js';
import { useAuthContext } from '../../utils/AuthContext';
import { useEffectiveLocation } from '../../utils/hooks/useLocation';
import { useMapContext } from '../../utils/MapContext.jsx';
import UrgencyService, { URGENCY_CONFIG } from '../../utils/urgencyService';
import { optimizeRoute, buildGoogleMapsUrl } from '../../utils/services/routeOptimizer';

// Max additional Mapbox pins (beyond the user's claimed pickups) to fold into
// the Google Maps URL. Google caps the directions URL at 9 waypoints + 1
// destination, so we leave a small headroom for the claimed pickups.
const EXTRA_PINS_CAP = 9;
// Only include extras within this radius (km) of the user's start location,
// so the Google Maps route doesn't detour halfway across the state.
const EXTRA_PINS_RADIUS_KM = 25;

// Local haversine — keeps the component self-contained.
function distanceKm(a, b) {
    if (!a || !b) return Infinity;
    const toRad = (d) => (d * Math.PI) / 180;
    const R = 6371;
    const dLat = toRad(b.latitude - a.latitude);
    const dLng = toRad(b.longitude - a.longitude);
    const lat1 = toRad(a.latitude);
    const lat2 = toRad(b.latitude);
    const h =
        Math.sin(dLat / 2) ** 2 +
        Math.sin(dLng / 2) ** 2 * Math.cos(lat1) * Math.cos(lat2);
    return 2 * R * Math.asin(Math.sqrt(h));
}

/**
 * Smart pickup route optimizer.
 *
 * Loads the user's active claims (pending/approved/scheduled), joins each
 * with food_listings (for coordinates + deadline), and produces an optimized
 * pickup ordering using utils/services/routeOptimizer.js — pure JS, no API.
 *
 * Toggle:
 *   • Urgency-aware (default)  — pulls expiring pickups earlier
 *   • Shortest distance only   — pure nearest-neighbor + 2-opt
 */
export default function PickupRouteOptimizer({ className = '', explicitStops = null }) {
    const { user } = useAuthContext();
    const navigate = useNavigate();
    const { location, error: locationError, enableLocation, refreshLocation } = useEffectiveLocation();
    const { aiMarkers } = useMapContext();

    const [stops, setStops] = React.useState([]);
    const [loading, setLoading] = React.useState(false);
    const [error, setError] = React.useState(null);
    const [weightUrgency, setWeightUrgency] = React.useState(true);
    const [avgSpeedKph, setAvgSpeedKph] = React.useState(30);
    // Other pins visible on the in-app Mapbox view (active listings + communities)
    // — pulled so we can include them in the "Open in Google Maps" URL.
    const [mapPins, setMapPins] = React.useState([]);

    const loadClaims = React.useCallback(async () => {
        if (explicitStops) {
            setStops(explicitStops);
            return;
        }
        if (!user?.id) return;
        setLoading(true);
        setError(null);
        try {
            const { data, error: err } = await supabase
                .from('food_claims')
                .select(`
                    id,
                    status,
                    pickup_date,
                    pickup_time,
                    quantity,
                    food_listings (
                        id,
                        title,
                        image_url,
                        latitude,
                        longitude,
                        location,
                        full_address,
                        pickup_by,
                        expiry_date,
                        donor_name
                    )
                `)
                .eq('claimer_id', user.id)
                .in('status', ['pending', 'approved']);

            if (err) throw err;

            const mapped = (data || [])
                .map((c) => {
                    const fl = c.food_listings || {};
                    // Synthesize a deadline: prefer claim pickup_date+time, else listing pickup_by.
                    let claimPickup = null;
                    if (c.pickup_date) {
                        const time = c.pickup_time || '23:59';
                        claimPickup = new Date(`${c.pickup_date}T${time}`).toISOString();
                    }
                    return {
                        id: c.id,
                        listing_id: fl.id,
                        title: fl.title || 'Untitled pickup',
                        image_url: fl.image_url || null,
                        latitude: typeof fl.latitude === 'number' ? fl.latitude : null,
                        longitude: typeof fl.longitude === 'number' ? fl.longitude : null,
                        location: fl.full_address || fl.location || '',
                        pickup_by: claimPickup || fl.pickup_by || null,
                        expiry_date: fl.expiry_date || null,
                        donor_name: fl.donor_name || null,
                        quantity: c.quantity || null,
                        status: c.status,
                    };
                });
            setStops(mapped);
        } catch (err) {
            setError(err?.message || 'Failed to load pickups');
        } finally {
            setLoading(false);
        }
    }, [user?.id, explicitStops]);

    React.useEffect(() => { loadClaims(); }, [loadClaims]);

    // Pull the same active listings + communities that the Mapbox view shows,
    // so the "Open in Google Maps" link can include those pins as waypoints.
    React.useEffect(() => {
        let cancelled = false;
        (async () => {
            try {
                const [listingsRes, communitiesRes] = await Promise.all([
                    supabase
                        .from('food_listings')
                        .select('id,title,latitude,longitude,full_address,location,status,listing_type')
                        .in('status', ['approved', 'active'])
                        .eq('listing_type', 'donation')
                        .not('latitude', 'is', null)
                        .not('longitude', 'is', null)
                        .limit(100),
                    supabase
                        .from('communities')
                        .select('id,name,latitude,longitude,location,is_active')
                        .eq('is_active', true)
                        .not('latitude', 'is', null)
                        .not('longitude', 'is', null)
                        .limit(50),
                ]);
                if (cancelled) return;
                const pins = [];
                for (const l of listingsRes.data || []) {
                    pins.push({
                        id: `listing-${l.id}`,
                        title: l.title || 'Food listing',
                        latitude: Number(l.latitude),
                        longitude: Number(l.longitude),
                        kind: 'listing',
                    });
                }
                for (const c of communitiesRes.data || []) {
                    pins.push({
                        id: `community-${c.id}`,
                        title: c.name || 'Community',
                        latitude: Number(c.latitude),
                        longitude: Number(c.longitude),
                        kind: 'community',
                    });
                }
                setMapPins(pins.filter((p) => Number.isFinite(p.latitude) && Number.isFinite(p.longitude)));
            } catch (err) {
                // Non-fatal: route still works without the extras.
                console.warn('PickupRouteOptimizer: failed to load map pins', err);
                if (!cancelled) setMapPins([]);
            }
        })();
        return () => { cancelled = true; };
    }, [user?.id]);

    const result = React.useMemo(() => {
        if (!location?.latitude || !location?.longitude || stops.length === 0) {
            return null;
        }
        return optimizeRoute({
            start: { latitude: location.latitude, longitude: location.longitude },
            stops,
            options: { weightUrgency, avgSpeedKph },
        });
    }, [stops, location, weightUrgency, avgSpeedKph]);

    const mapsUrl = React.useMemo(() => {
        if (!result || !location) return null;
        const start = { latitude: location.latitude, longitude: location.longitude };

        // Collect every pin shown on the in-app Mapbox view:
        //   1. AI overlay markers (search results, distribution centers, …)
        //   2. Active food listings + communities fetched above
        const aiExtras = (aiMarkers || [])
            .map((m) => ({
                id: m.id,
                title: m.title,
                latitude: Number(m.lat),
                longitude: Number(m.lng),
                kind: m.kind || 'pin',
            }))
            .filter((p) => Number.isFinite(p.latitude) && Number.isFinite(p.longitude));

        // De-dupe across sources by (id) AND (rough coordinate).
        const seenIds = new Set();
        const seenCoord = new Set();
        const coordKey = (p) =>
            `${Math.round(p.latitude * 1e4)}|${Math.round(p.longitude * 1e4)}`;
        const pickupCoords = new Set(
            result.order.map((s) => coordKey({ latitude: s.latitude, longitude: s.longitude })),
        );

        const merged = [...aiExtras, ...mapPins].filter((p) => {
            if (seenIds.has(p.id)) return false;
            const ck = coordKey(p);
            if (seenCoord.has(ck) || pickupCoords.has(ck)) return false;
            seenIds.add(p.id);
            seenCoord.add(ck);
            return true;
        });

        // Keep only nearby pins, sorted by distance, capped to Google's limit.
        const extras = merged
            .map((p) => ({ ...p, _distKm: distanceKm(start, p) }))
            .filter((p) => p._distKm <= EXTRA_PINS_RADIUS_KM)
            .sort((a, b) => a._distKm - b._distKm)
            .slice(0, EXTRA_PINS_CAP);

        return buildGoogleMapsUrl(start, result.order, extras);
    }, [result, location, mapPins, aiMarkers]);

    const hasLocation = !!(location?.latitude && location?.longitude);
    const stopCount = stops.length;
    const skipped = result?.skipped?.length || 0;
    const extraPinCount = React.useMemo(() => {
        if (!mapsUrl) return 0;
        // Parse the waypoints param to report how many extras are bundled.
        try {
            const wp = new URL(mapsUrl).searchParams.get('waypoints');
            if (!wp) return 0;
            const wpCount = wp.split('|').length;
            // result.order contributes (order.length - 1) waypoints; the rest are extras.
            return Math.max(0, wpCount - Math.max(0, result.order.length - 1));
        } catch {
            return 0;
        }
    }, [mapsUrl, result]);

    return (
        <section
            className={`bg-white rounded-2xl shadow-md border border-gray-100 overflow-hidden ${className}`}
            aria-label="Smart pickup route planner"
        >
            <header className="flex items-center justify-between px-5 py-3 border-b border-gray-100 bg-gradient-to-r from-emerald-50 to-white">
                <div className="flex items-center gap-2 text-gray-800">
                    <i className="fas fa-route text-emerald-600" aria-hidden="true" />
                    <h2 className="text-sm font-semibold">Smart pickup route</h2>
                    {stopCount > 0 && (
                        <span className="text-xs text-gray-500">
                            ({stopCount} pickup{stopCount === 1 ? '' : 's'})
                        </span>
                    )}
                </div>
                <button
                    type="button"
                    onClick={loadClaims}
                    className="text-xs text-gray-500 hover:text-emerald-600"
                    disabled={loading}
                    aria-label="Reload pickups"
                >
                    <i className={`fas fa-rotate ${loading ? 'animate-spin' : ''}`} aria-hidden="true" />
                </button>
            </header>

            <div className="px-5 py-4 space-y-3">
                {/* Controls */}
                <div className="flex flex-wrap items-center gap-3 text-xs">
                    <label className="inline-flex items-center gap-2 cursor-pointer">
                        <input
                            type="checkbox"
                            checked={weightUrgency}
                            onChange={(e) => setWeightUrgency(e.target.checked)}
                            className="rounded text-emerald-600 focus:ring-emerald-500"
                        />
                        <span className="text-gray-700">Prioritize urgent pickups</span>
                    </label>
                    <label className="inline-flex items-center gap-2">
                        <span className="text-gray-500">Avg speed</span>
                        <select
                            value={avgSpeedKph}
                            onChange={(e) => setAvgSpeedKph(Number(e.target.value))}
                            className="rounded border border-gray-200 px-2 py-1"
                        >
                            <option value={15}>15 km/h (bike)</option>
                            <option value={30}>30 km/h (city)</option>
                            <option value={50}>50 km/h (mixed)</option>
                            <option value={80}>80 km/h (highway)</option>
                        </select>
                    </label>
                    {hasLocation ? (
                        <span className="ml-auto inline-flex items-center gap-1 rounded-full bg-emerald-50 px-2 py-0.5 text-emerald-700 ring-1 ring-emerald-200">
                            <i className="fas fa-location-arrow" aria-hidden="true" />
                            GPS ready
                            <button
                                type="button"
                                onClick={refreshLocation}
                                className="ml-1 text-emerald-700/70 hover:text-emerald-800"
                                aria-label="Refresh location"
                            >
                                <i className="fas fa-rotate" aria-hidden="true" />
                            </button>
                        </span>
                    ) : (
                        <button
                            type="button"
                            onClick={enableLocation}
                            className="ml-auto inline-flex items-center gap-1 rounded-full bg-gray-100 px-2 py-0.5 text-gray-700 hover:bg-gray-200"
                        >
                            <i className="fas fa-location-crosshairs" aria-hidden="true" />
                            Enable GPS
                        </button>
                    )}
                </div>

                {(error || locationError) && (
                    <p className="text-xs text-red-600">{error || locationError}</p>
                )}

                {loading && (
                    <p className="text-xs text-gray-500">Loading your pickups…</p>
                )}

                {!loading && stopCount === 0 && (
                    <div className="rounded-md border border-dashed border-gray-200 p-4 text-center text-sm text-gray-500">
                        No active pickups to route.
                        <button
                            type="button"
                            onClick={() => navigate('/find')}
                            className="ml-1 text-emerald-600 hover:underline"
                        >
                            Browse listings
                        </button>
                    </div>
                )}

                {!loading && stopCount > 0 && !hasLocation && (
                    <div className="rounded-md border border-dashed border-gray-200 p-4 text-sm text-gray-600">
                        Enable GPS above to compute the best pickup order.
                    </div>
                )}

                {result && result.order.length > 0 && (
                    <div className="space-y-3">
                        <div className="flex flex-wrap items-center justify-between gap-2 rounded-md bg-emerald-50 px-3 py-2 ring-1 ring-emerald-200">
                            <div className="text-sm text-emerald-900">
                                <span className="font-semibold">{result.order.length} stop{result.order.length === 1 ? '' : 's'}</span>
                                <span className="mx-2 text-emerald-400">·</span>
                                <span>{result.totalDistanceKm} km</span>
                                <span className="mx-2 text-emerald-400">·</span>
                                <span>~{result.totalEtaMin} min drive</span>
                                {skipped > 0 && (
                                    <>
                                        <span className="mx-2 text-emerald-400">·</span>
                                        <span className="text-amber-700">{skipped} skipped (no GPS)</span>
                                    </>
                                )}
                            </div>
                            {mapsUrl && (
                                <a
                                    href={mapsUrl}
                                    target="_blank"
                                    rel="noopener noreferrer"
                                    className="inline-flex items-center gap-1 rounded-md bg-emerald-600 px-3 py-1.5 text-xs font-medium text-white hover:bg-emerald-700"
                                    title={
                                        extraPinCount > 0
                                            ? `Includes ${extraPinCount} nearby pin${extraPinCount === 1 ? '' : 's'} from the map (listings, communities, etc.)`
                                            : undefined
                                    }
                                >
                                    <i className="fab fa-google" aria-hidden="true" />
                                    Open in Google Maps
                                    {extraPinCount > 0 && (
                                        <span className="ml-1 rounded-full bg-white/20 px-1.5 py-0.5 text-[10px] font-semibold">
                                            +{extraPinCount}
                                        </span>
                                    )}
                                </a>
                            )}
                        </div>

                        <ol className="space-y-2">
                            {result.order.map((stop, idx) => {
                                const leg = result.legs[idx];
                                const urgency = UrgencyService.calculateUrgencyLevel(stop);
                                const cfg = URGENCY_CONFIG[urgency] || {};
                                return (
                                    <li
                                        key={stop.id}
                                        className="flex items-start gap-3 rounded-md border border-gray-100 p-3"
                                    >
                                        <span className="mt-0.5 inline-flex h-7 w-7 flex-shrink-0 items-center justify-center rounded-full bg-emerald-600 text-xs font-semibold text-white">
                                            {idx + 1}
                                        </span>
                                        {stop.image_url ? (
                                            <img
                                                src={stop.image_url}
                                                alt=""
                                                className="h-12 w-12 flex-shrink-0 rounded-md object-cover"
                                            />
                                        ) : (
                                            <span className="h-12 w-12 flex-shrink-0 rounded-md bg-gray-100 flex items-center justify-center text-gray-400">
                                                <i className="fas fa-utensils" aria-hidden="true" />
                                            </span>
                                        )}
                                        <div className="flex-1 min-w-0">
                                            <div className="flex items-start justify-between gap-2">
                                                <h3 className="text-sm font-semibold text-gray-900 truncate">
                                                    {stop.title}
                                                </h3>
                                                {cfg.label && (
                                                    <span
                                                        className={`inline-flex items-center rounded-full px-2 py-0.5 text-[10px] font-medium ${cfg.bgClass || 'bg-gray-100'} ${cfg.textClass || 'text-gray-700'}`}
                                                    >
                                                        {cfg.label}
                                                    </span>
                                                )}
                                            </div>
                                            <p className="mt-0.5 text-xs text-gray-500 truncate">
                                                {stop.location || stop.donor_name || ''}
                                            </p>
                                            <div className="mt-1 flex flex-wrap items-center gap-x-3 gap-y-1 text-[11px] text-gray-600">
                                                <span>
                                                    <i className="fas fa-route mr-1 text-emerald-500" aria-hidden="true" />
                                                    +{leg.distanceKm} km
                                                </span>
                                                <span>
                                                    <i className="fas fa-clock mr-1 text-amber-500" aria-hidden="true" />
                                                    ~{leg.etaMin} min leg
                                                </span>
                                                {stop.quantity && (
                                                    <span>
                                                        <i className="fas fa-box-open mr-1 text-gray-400" aria-hidden="true" />
                                                        {stop.quantity}
                                                    </span>
                                                )}
                                            </div>
                                        </div>
                                    </li>
                                );
                            })}
                        </ol>
                    </div>
                )}
            </div>
        </section>
    );
}

PickupRouteOptimizer.propTypes = {
    className: PropTypes.string,
    /** Optional override: pass a precomputed list of stops instead of fetching claims. */
    explicitStops: PropTypes.arrayOf(PropTypes.object),
};
