/** San Francisco Bay Area — primary DoGoods service region. */
export const BAY_AREA = {
    minLat: 36.5,
    maxLat: 38.8,
    minLng: -123.5,
    maxLng: -121.0,
    centerLat: 37.82,
    centerLng: -122.27,
};

/** True when lat/lng is inside the Bay Area bounds. */
export function isBayAreaCoord(lat, lng) {
    const la = Number(lat);
    const ln = Number(lng);
    if (!Number.isFinite(la) || !Number.isFinite(ln)) return false;
    return (
        la >= BAY_AREA.minLat
        && la <= BAY_AREA.maxLat
        && ln >= BAY_AREA.minLng
        && ln <= BAY_AREA.maxLng
    );
}

/** Mapbox geocoding query params that bias results to the Bay Area. */
export function bayAreaGeocodeParams() {
    const { minLng, minLat, maxLng, maxLat, centerLng, centerLat } = BAY_AREA;
    return `proximity=${centerLng},${centerLat}&bbox=${minLng},${minLat},${maxLng},${maxLat}&country=US`;
}
