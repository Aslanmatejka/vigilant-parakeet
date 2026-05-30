/**
 * Pickup route optimizer — pure JS.
 *
 * Combines the existing Haversine distance helper (locationService) and the
 * UrgencyService deadline scoring to plan a multi-stop pickup route from a
 * starting point (typically the user's current GPS).
 *
 * Algorithm:
 *   1. Urgency-weighted nearest-neighbor seed (priority items pulled earlier).
 *   2. 2-opt swap improvement on pure distance (5..50 iterations, capped).
 *
 * No external services — everything is local arithmetic.
 */

import { locationService } from '../locationService.js';
import UrgencyService from '../urgencyService.js';

const AVG_SPEED_KPH_DEFAULT = 30;

const URGENCY_PRIORITY = {
    critical: 2.0,
    high: 1.5,
    medium: 1.2,
    normal: 1.0,
    none: 0.9,
};

/**
 * @typedef {Object} Stop
 * @property {string}  id
 * @property {number}  latitude
 * @property {number}  longitude
 * @property {string}  [title]
 * @property {string|null} [pickup_by]
 * @property {string|null} [expiry_date]
 */

function distanceKm(a, b) {
    return locationService.calculateDistance(
        a.latitude, a.longitude,
        b.latitude, b.longitude,
    );
}

function urgencyWeight(stop) {
    try {
        const level = UrgencyService.calculateUrgencyLevel(stop) || 'normal';
        return URGENCY_PRIORITY[level] || 1.0;
    } catch {
        return 1.0;
    }
}

/**
 * Weighted nearest-neighbor: at each step pick the stop with smallest
 * (distance / urgencyWeight). Urgent items get pulled earlier in ties.
 */
function nearestNeighborOrder(start, stops, useUrgency) {
    const remaining = [...stops];
    const order = [];
    let cursor = start;

    while (remaining.length) {
        let bestIdx = 0;
        let bestCost = Infinity;
        for (let i = 0; i < remaining.length; i++) {
            const d = distanceKm(cursor, remaining[i]);
            const w = useUrgency ? urgencyWeight(remaining[i]) : 1;
            const cost = w > 0 ? d / w : d;
            if (cost < bestCost) {
                bestCost = cost;
                bestIdx = i;
            }
        }
        const chosen = remaining.splice(bestIdx, 1)[0];
        order.push(chosen);
        cursor = chosen;
    }
    return order;
}

/**
 * 2-opt swap on pure distance. Bounded by maxIterations and a tour-size cap.
 */
function twoOptImprove(start, order, maxIterations = 40) {
    if (order.length < 4) return order;

    const route = [start, ...order];
    let improved = true;
    let iter = 0;

    const tourDistance = (r) => {
        let total = 0;
        for (let i = 0; i < r.length - 1; i++) total += distanceKm(r[i], r[i + 1]);
        return total;
    };

    let bestDistance = tourDistance(route);

    while (improved && iter < maxIterations) {
        improved = false;
        iter++;
        for (let i = 1; i < route.length - 2; i++) {
            for (let j = i + 1; j < route.length - 1; j++) {
                const newRoute = route.slice(0, i)
                    .concat(route.slice(i, j + 1).reverse())
                    .concat(route.slice(j + 1));
                const newDistance = tourDistance(newRoute);
                if (newDistance + 1e-9 < bestDistance) {
                    bestDistance = newDistance;
                    route.splice(0, route.length, ...newRoute);
                    improved = true;
                }
            }
        }
    }
    return route.slice(1); // strip start
}

/**
 * Plan a multi-stop pickup route.
 *
 * @param {Object} params
 * @param {{latitude:number,longitude:number}} params.start
 * @param {Stop[]} params.stops
 * @param {Object} [params.options]
 * @param {boolean} [params.options.weightUrgency=true]
 * @param {number}  [params.options.avgSpeedKph=30]
 * @param {boolean} [params.options.refineWith2Opt=true]
 * @returns {{
 *   order: Stop[],
 *   legs: Array<{from:Stop, to:Stop, distanceKm:number, etaMin:number}>,
 *   totalDistanceKm: number,
 *   totalEtaMin: number,
 *   skipped: Stop[]
 * }}
 */
export function optimizeRoute({ start, stops, options = {} } = {}) {
    const {
        weightUrgency = true,
        avgSpeedKph = AVG_SPEED_KPH_DEFAULT,
        refineWith2Opt = true,
    } = options;

    const valid = (stops || []).filter(
        (s) => Number.isFinite(s?.latitude) && Number.isFinite(s?.longitude),
    );
    const skipped = (stops || []).filter(
        (s) => !Number.isFinite(s?.latitude) || !Number.isFinite(s?.longitude),
    );

    if (!start || !Number.isFinite(start.latitude) || !Number.isFinite(start.longitude)) {
        return {
            order: valid,
            legs: [],
            totalDistanceKm: 0,
            totalEtaMin: 0,
            skipped,
        };
    }

    if (valid.length === 0) {
        return { order: [], legs: [], totalDistanceKm: 0, totalEtaMin: 0, skipped };
    }

    let order = nearestNeighborOrder(start, valid, weightUrgency);
    if (refineWith2Opt && order.length >= 3) {
        order = twoOptImprove(start, order);
    }

    const legs = [];
    let cursor = start;
    let totalDistance = 0;

    for (const stop of order) {
        const km = distanceKm(cursor, stop);
        const etaMin = avgSpeedKph > 0 ? (km / avgSpeedKph) * 60 : 0;
        legs.push({
            from: cursor,
            to: stop,
            distanceKm: Math.round(km * 100) / 100,
            etaMin: Math.round(etaMin),
        });
        totalDistance += km;
        cursor = stop;
    }

    return {
        order,
        legs,
        totalDistanceKm: Math.round(totalDistance * 100) / 100,
        totalEtaMin: Math.round(avgSpeedKph > 0 ? (totalDistance / avgSpeedKph) * 60 : 0),
        skipped,
    };
}

/**
 * Build a Google Maps "Directions" URL.
 *
 * @param {{latitude:number,longitude:number}} start
 * @param {Array<{latitude:number,longitude:number}>} order
 *   The optimized pickup stops. The final entry becomes the route destination.
 * @param {Array<{latitude:number,longitude:number}>} [extras]
 *   Additional points (listings, communities, distribution centers, etc.)
 *   visible on the in-app map that the user wants to see in Google Maps.
 *   These are merged as additional waypoints, subject to Google's hard cap
 *   of 9 waypoints + 1 destination per directions URL.
 */
export function buildGoogleMapsUrl(start, order, extras = []) {
    if (!start || !order?.length) return null;
    const origin = `${start.latitude},${start.longitude}`;

    const isFiniteNum = (n) => typeof n === 'number' && Number.isFinite(n);
    const keyOf = (s) => `${Math.round(s.latitude * 1e5)}|${Math.round(s.longitude * 1e5)}`;

    // De-dupe: pickup stops first (we want their order preserved), then extras.
    const seen = new Set([keyOf(start)]);
    const dedup = (arr) => arr.filter((s) => {
        if (!s || !isFiniteNum(s.latitude) || !isFiniteNum(s.longitude)) return false;
        const k = keyOf(s);
        if (seen.has(k)) return false;
        seen.add(k);
        return true;
    });

    const orderedStops = dedup(order);
    if (orderedStops.length === 0) return null;
    const extraStops = dedup(Array.isArray(extras) ? extras : []);

    // Destination is the LAST of the user's pickups so the route still ends
    // where they expect; the extras and earlier pickups become waypoints.
    const destStop = orderedStops[orderedStops.length - 1];
    const destination = `${destStop.latitude},${destStop.longitude}`;
    const waypointStops = [
        ...orderedStops.slice(0, -1),
        ...extraStops,
    ].slice(0, 9); // Google Maps directions cap

    const waypoints = waypointStops
        .map((s) => `${s.latitude},${s.longitude}`)
        .join('|');
    const params = new URLSearchParams({
        api: '1',
        origin,
        destination,
        travelmode: 'driving',
    });
    if (waypoints) params.set('waypoints', waypoints);
    return `https://www.google.com/maps/dir/?${params.toString()}`;
}

export default { optimizeRoute, buildGoogleMapsUrl };
