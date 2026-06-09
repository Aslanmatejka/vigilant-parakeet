import React, { useState, useEffect, useRef } from 'react';
import { useNavigate } from 'react-router-dom';
import supabase from '../../utils/supabaseClient';
import { API_CONFIG } from '../../utils/config';
import { bayAreaGeocodeParams, isBayAreaCoord } from '../../utils/mapBounds';
import { useMapContext } from '../../utils/MapContext.jsx';
import { useEffectiveLocation } from '../../utils/hooks/useLocation';
import CommunityPinIcon, { getCommunityPinDimensions, renderCommunityPinSvg } from './CommunityPinIcon.jsx';

// Mapbox is loaded via CDN in index.html
// Access it from window.mapboxgl
const getMapboxgl = () => window.mapboxgl;

// Get Mapbox token from centralized config (window.__ENV__ → import.meta.env → hardcoded fallback)
const MAPBOX_TOKEN = API_CONFIG.MAPBOX.ACCESS_TOKEN;

// HTML-escape user-provided strings before interpolating into popup innerHTML.
// Without this, a malicious food listing title/description could execute
// arbitrary JavaScript in every viewer's browser (stored XSS).
const escapeHtml = (value) => {
    if (value === null || value === undefined) return '';
    return String(value)
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;')
        .replace(/'/g, '&#39;');
};

// Forward-geocode an address string to [lng, lat] via Mapbox, with a
// sessionStorage cache so the same address isn't looked up twice. Returns
// null on any failure. This is the client-side safety net for listings that
// were saved without coordinates — without it they'd render in the sidebar
// list but have NO marker, so hovering them does nothing on the map.
const _geocodeCache = new Map();
const geocodeAddress = async (address) => {
    const key = String(address || '').trim();
    if (!key || !MAPBOX_TOKEN) return null;
    if (_geocodeCache.has(key)) return _geocodeCache.get(key);
    try {
        if (typeof sessionStorage !== 'undefined') {
            const cached = sessionStorage.getItem(`dg.geo.${key}`);
            if (cached) {
                const parsed = JSON.parse(cached);
                _geocodeCache.set(key, parsed);
                return parsed;
            }
        }
    } catch { /* ignore storage errors */ }
    try {
        const url = `https://api.mapbox.com/geocoding/v5/mapbox.places/${encodeURIComponent(key)}.json?access_token=${MAPBOX_TOKEN}&limit=1&${bayAreaGeocodeParams()}`;
        const resp = await fetch(url);
        if (!resp.ok) { _geocodeCache.set(key, null); return null; }
        const data = await resp.json();
        const center = data?.features?.[0]?.center;
        if (!Array.isArray(center) || center.length < 2) {
            _geocodeCache.set(key, null);
            return null;
        }
        const lng = Number(center[0]);
        const lat = Number(center[1]);
        if (!isBayAreaCoord(lat, lng)) {
            _geocodeCache.set(key, null);
            return null;
        }
        const result = [lng, lat]; // [lng, lat]
        _geocodeCache.set(key, result);
        try {
            if (typeof sessionStorage !== 'undefined') {
                sessionStorage.setItem(`dg.geo.${key}`, JSON.stringify(result));
            }
        } catch { /* ignore */ }
        return result;
    } catch (err) {
        console.warn('Geocode failed for', key, err);
        _geocodeCache.set(key, null);
        return null;
    }
};

const MAPBOX_UI_STYLE_ID = 'dogoods-mapbox-ui-overrides';

function ensureMapboxControlStyles() {
    if (typeof document === 'undefined' || document.getElementById(MAPBOX_UI_STYLE_ID)) return;
    const style = document.createElement('style');
    style.id = MAPBOX_UI_STYLE_ID;
    style.textContent = `
        /* Canvas can paint over built-in controls — keep attribution above tiles only */
        .dogoods-food-map .mapboxgl-canvas-container {
            z-index: 1 !important;
        }
        .dogoods-food-map .mapboxgl-control-container {
            z-index: 2 !important;
            pointer-events: none;
        }
        .dogoods-food-map .mapboxgl-control-container .mapboxgl-ctrl {
            pointer-events: auto;
        }
        .dogoods-food-map .mapboxgl-ctrl-bottom-right,
        .dogoods-food-map .mapboxgl-ctrl-bottom-left {
            z-index: 2 !important;
        }
        .dogoods-food-map .mapboxgl-ctrl-bottom-right {
            bottom: 8px !important;
            right: 8px !important;
        }
        .dogoods-food-map-legend {
            z-index: 90 !important;
            top: auto !important;
            left: 10px !important;
            bottom: 44px !important;
            pointer-events: none;
        }
        .dogoods-food-map-legend > * {
            pointer-events: auto;
        }
        .dogoods-food-map-zoom {
            z-index: 100 !important;
            top: auto !important;
            right: 10px !important;
            bottom: 72px !important;
            pointer-events: auto;
        }
        .dogoods-food-map-overlay {
            z-index: 25 !important;
            pointer-events: none;
        }
        @media (max-width: 1023px) {
            .dogoods-food-map-zoom {
                bottom: 5.5rem !important;
                right: 10px !important;
            }
            .dogoods-food-map-legend {
                left: 8px !important;
                bottom: 40px !important;
                max-width: calc(100% - 4.5rem) !important;
            }
        }
    `;
    document.head.appendChild(style);
}

function FoodMap({ onMarkerClick, showSignupPrompt = true, highlightedFoodId = null, className = '' }) {
    const navigate = useNavigate();
    const mapContainer = useRef(null);
    const map = useRef(null);
    const markersRef = useRef([]);
    // Map of food listing id → marker DOM element, so we can toggle a
    // highlight style when the parent page reports a hovered listing.
    const foodMarkerElsRef = useRef(new Map());
    const popupRef = useRef(null);
    const aiMarkersRef = useRef([]);
    const userMarkerRef = useRef(null);
    const userPinCenteredRef = useRef(false);
    const mapInitialized = useRef(false); // Prevent double initialization in Strict Mode
    const [foodListings, setFoodListings] = useState([]);
    const [communities, setCommunities] = useState([]);
    const [loading, setLoading] = useState(true);
    const [mapLoaded, setMapLoaded] = useState(false);
    // Tracks listing ids we've already attempted to geocode so the
    // backfill effect never loops on an address Mapbox can't resolve.
    const geocodeAttemptedRef = useRef(new Set());
    const { aiMarkers, aiRoute, centerRequest } = useMapContext();
    const { location: userLocation, source: userLocationSource } = useEffectiveLocation();

    useEffect(() => {
        ensureMapboxControlStyles();
    }, []);

    useEffect(() => {
        // Prevent double initialization from React Strict Mode
        if (mapInitialized.current) {
            // Map already initialized from a previous mount (Strict Mode remount)
            // We have a NEW mapLoaded state (starts false), so we need to sync it
            if (map.current) {
                console.log('🔄 Map already initialized (Strict Mode remount), syncing state...');
                if (map.current.loaded()) {
                    console.log('✅ Map already loaded, setting mapLoaded=true');
                    setMapLoaded(true);
                } else {
                    // Listen for load on existing map
                    const onLoad = () => {
                        console.log('✅ Map loaded (from remount listener)');
                        setMapLoaded(true);
                    };
                    map.current.on('load', onLoad);
                    // Fallback timeout
                    const remountTimeout = setTimeout(() => {
                        console.warn('⚠️ Remount fallback: forcing mapLoaded=true');
                        setMapLoaded(true);
                    }, 2000);
                    return () => {
                        clearTimeout(remountTimeout);
                    };
                }
            }
            return;
        }
        
        const mapboxgl = getMapboxgl();
        if (!mapboxgl || !mapContainer.current) return;

        if (!MAPBOX_TOKEN) {
            console.error('❌ Mapbox token is missing');
            return;
        }

        ensureMapboxControlStyles();

        mapInitialized.current = true;        try {
            console.log('🗺️ Creating Mapbox map...');
            
            // Check if Mapbox is actually available
            if (!mapboxgl) {
                console.error('❌ Mapbox GL JS not loaded from CDN');
                return;
            }
            
            // Validate token
            if (!MAPBOX_TOKEN || MAPBOX_TOKEN.length < 20) {
                console.error('❌ Invalid Mapbox token');
                return;
            }
            
            mapboxgl.accessToken = MAPBOX_TOKEN;
            
            map.current = new mapboxgl.Map({
                container: mapContainer.current,
                style: 'mapbox://styles/mapbox/streets-v12',
                center: [-122.27, 37.82],
                zoom: 11,
                attributionControl: true,
                renderWorldCopies: false,
                preserveDrawingBuffer: false
            });
            console.log('🗺️ Map object created:', map.current);

            map.current.on('load', () => {
                console.log('✅ Map loaded successfully!');
                ensureMapboxControlStyles();
                setMapLoaded(true);
            });

            map.current.on('error', (e) => {
                console.error('❌ Map error event:', e);
                console.error('❌ Error type:', e.error?.message || 'Unknown');
                console.error('❌ Error status:', e.error?.status || 'No status');
            });

            // Log data requests to see if Mapbox is trying to load tiles
            map.current.on('dataloading', (e) => {
                console.log('📡 Mapbox data loading:', e.dataType);
            });

            map.current.on('data', (e) => {
                console.log('📦 Mapbox data received:', e.dataType);
            });

            map.current.on('sourcedataloading', (e) => {
                console.log('🔄 Mapbox source loading:', e.sourceId);
            });

        } catch (error) {
            console.error('❌ Map creation failed with error:', error);
            console.error('❌ Error stack:', error.stack);
        }

        // Aggressive fallback - if map doesn't load in 2 seconds, force it anyway
        const loadTimeout = setTimeout(() => {
            if (map.current) {
                console.warn('⚠️ Map load timeout (2s) - forcing mapLoaded=true to show map');
                console.warn('⚠️ Check Network tab for failed Mapbox API requests');
                setMapLoaded(true);
            }
        }, 2000);

        console.log('🎯 Map initialization complete. Waiting for tiles...');
        console.log('📍 Map center:', map.current?.getCenter());
        console.log('🔍 Map zoom:', map.current?.getZoom());

        return () => {
            // Skip cleanup during React Strict Mode's double-mount behavior in development
            // The map should persist after the first mount
            console.log('🔍 Cleanup called. mapInitialized:', mapInitialized.current);
            
            // Only truly cleanup when the component is actually being destroyed
            // (not during Strict Mode's test unmount-remount cycle)
            if (import.meta.env.DEV && mapInitialized.current) {
                console.log('⏭️ Skipping cleanup in development - keeping map alive');
                return;
            }
            
            console.log('🧹 Cleanup: Removing map');
            clearTimeout(loadTimeout);
            if (map.current) {
                map.current.remove();
                map.current = null;
            }
            mapInitialized.current = false;
        };
    }, []);

    useEffect(() => {
        // Fetch listings and communities immediately
        fetchFoodListings();
        fetchCommunities();
    }, []);

    useEffect(() => {
        // Add markers as soon as both map and data are ready
        console.log('🗺️ Map loaded:', mapLoaded, 'Listings:', foodListings.length, 'Communities:', communities.length);
        if (mapLoaded && (foodListings.length > 0 || communities.length > 0)) {
            console.log('✅ Calling addMarkers()');
            addMarkers();
        } else {
            console.log('⏳ Waiting for map or data...');
        }
    }, [mapLoaded, foodListings, communities]);

    // Coordinate backfill: some listings are saved with an address but no
    // latitude/longitude. Those render in the sidebar list but get NO map
    // marker, so hovering them does nothing. Forward-geocode each such
    // listing (using its full_address/location) and patch the coordinates
    // back into state so addMarkers can place a marker for it.
    useEffect(() => {
        if (!foodListings.length) return;
        const needsGeocode = foodListings.filter((l) => {
            if (l.id == null) return false;
            if (geocodeAttemptedRef.current.has(l.id)) return false;
            const hasCoords = !isNaN(parseFloat(l.latitude)) && !isNaN(parseFloat(l.longitude));
            const address = l.full_address || l.location;
            return !hasCoords && typeof address === 'string' && address.trim().length > 0;
        });
        if (!needsGeocode.length) return;

        let cancelled = false;
        (async () => {
            const patches = new Map();
            for (const listing of needsGeocode) {
                geocodeAttemptedRef.current.add(listing.id);
                const coords = await geocodeAddress(listing.full_address || listing.location);
                if (coords) patches.set(listing.id, coords);
            }
            if (cancelled || patches.size === 0) return;
            setFoodListings((prev) =>
                prev.map((l) => {
                    const coords = patches.get(l.id);
                    if (!coords) return l;
                    return {
                        ...l,
                        latitude: coords[1],
                        longitude: coords[0],
                    };
                })
            );
        })();

        return () => { cancelled = true; };
    }, [foodListings]);

    // Apply hover-highlight to the marker whose listing id matches the prop.
    // Re-runs whenever the highlighted id OR the marker set changes so a freshly
    // re-rendered marker still picks up the highlight.
    useEffect(() => {
        const HIGHLIGHTED = {
            width: '36px',
            height: '36px',
            backgroundColor: '#f59e0b',
            zIndex: '5',
            boxShadow: '0 0 0 4px rgba(245, 158, 11, 0.35), 0 2px 6px rgba(0,0,0,0.35)',
        };
        const NORMAL = {
            width: '24px',
            height: '24px',
            backgroundColor: '#dc2626',
            zIndex: '',
            boxShadow: '0 2px 4px rgba(0,0,0,0.3)',
        };
        foodMarkerElsRef.current.forEach((el, id) => {
            const styles = id === highlightedFoodId ? HIGHLIGHTED : NORMAL;
            Object.assign(el.style, styles);
            el.style.transition = 'width 0.15s ease, height 0.15s ease, background-color 0.15s ease, box-shadow 0.15s ease';
        });
        // Optional: pan to the highlighted marker if it's offscreen.
        if (highlightedFoodId != null && map.current) {
            const listing = foodListings.find(l => l.id === highlightedFoodId);
            const lat = listing ? parseFloat(listing.latitude) : NaN;
            const lng = listing ? parseFloat(listing.longitude) : NaN;
            if (!isNaN(lat) && !isNaN(lng) && isBayAreaCoord(lat, lng)) {
                try {
                    const bounds = map.current.getBounds();
                    if (bounds && !bounds.contains([lng, lat])) {
                        map.current.easeTo({ center: [lng, lat], duration: 400 });
                    }
                } catch (_) { /* ignore */ }
            }
        }
    }, [highlightedFoodId, foodListings]);

    const fetchFoodListings = async () => {
        try {
            setLoading(true);
            
            // Add timeout to prevent hanging
            const timeoutPromise = new Promise((_, reject) => 
                setTimeout(() => reject(new Error('Food listings fetch timeout')), 8000)
            );
            
            // Fetch donation listings only — food requests should NOT appear as
            // map markers since they are requests for food, not offers.
            // Also exclude already-expired listings so the map never shows stale pins.
            // Use local date (not UTC) so listings don't vanish from the map several
            // hours before they expire in the user's timezone (e.g. UTC-8 after 4pm).
            const _now = new Date();
            const todayStr = [
                _now.getFullYear(),
                String(_now.getMonth() + 1).padStart(2, '0'),
                String(_now.getDate()).padStart(2, '0'),
            ].join('-');
            const fetchPromise = supabase
                .from('food_listings')
                .select('id,title,description,image_url,quantity,unit,category,status,expiry_date,full_address,location,latitude,longitude,community_id,listing_type')
                .in('status', ['approved', 'active'])
                .eq('listing_type', 'donation')
                .or(`expiry_date.is.null,expiry_date.gte.${todayStr}`)
                .limit(100);

            const { data, error } = await Promise.race([fetchPromise, timeoutPromise]);

            if (error) {
                console.error('Supabase error:', error);
                throw error;
            }
            
            console.log('Fetched food listings:', data?.length || 0);
            setFoodListings(data || []);
        } catch (error) {
            console.error('Error fetching food listings:', error);
            setFoodListings([]);
        } finally {
            setLoading(false);
        }
    };

    const fetchCommunities = async () => {
        try {
            const { data, error } = await supabase
                .from('communities')
                .select('*')
                .eq('is_active', true)
                .not('latitude', 'is', null)
                .not('longitude', 'is', null);

            if (error) {
                console.error('Communities fetch error:', error);
                throw error;
            }
            
            console.log('Fetched communities:', data);
            console.log('Number of communities with coordinates:', data?.length || 0);
            setCommunities(data || []);
        } catch (error) {
            console.error('Error fetching communities:', error);
            setCommunities([]);
        }
    };

    const addMarkers = () => {
        if (!map.current || !map.current.getContainer()) {
            console.warn('⚠️ Map not ready yet, skipping marker addition');
            return;
        }
        
        console.log('Adding markers for', foodListings.length, 'listings and', communities.length, 'communities');
        
        const mapboxgl = getMapboxgl();
        if (!mapboxgl || !map.current) {
            console.warn('⚠️ Mapbox not ready for markers');
            return;
        }
        
        // Remove existing markers
        markersRef.current.forEach(marker => marker.remove());
        markersRef.current = [];
        foodMarkerElsRef.current.clear();

        // Add food listing markers
        foodListings.forEach((listing) => {
            // Parse and validate coordinates
            const lat = parseFloat(listing.latitude);
            const lng = parseFloat(listing.longitude);
            
            // Validate coordinates
            if (isNaN(lat) || isNaN(lng)) {
                console.error('❌ Invalid coordinates for listing', listing.title);
                return;
            }
            if (!isBayAreaCoord(lat, lng)) {
                console.warn('⚠️ Skipping out-of-region listing marker:', listing.title, lat, lng);
                return;
            }
            
            console.log('✅ Adding food marker:', listing.title);
            console.log('  Database values - lat:', listing.latitude, 'lng:', listing.longitude);
            console.log('  Parsed as numbers - lat:', lat, 'lng:', lng);
            console.log('  Mapbox format [lng, lat]:', [lng, lat]);
            
            // Create simple marker element for testing
            const el = document.createElement('div');
            el.className = 'food-marker';
            el.style.width = '24px';
            el.style.height = '24px';
            el.style.borderRadius = '50%';
            el.style.backgroundColor = '#dc2626';
            el.style.border = '3px solid white';
            el.style.boxShadow = '0 2px 4px rgba(0,0,0,0.3)';
            el.style.cursor = 'pointer';
            el.title = listing.title;

            el.addEventListener('click', () => {
                showPopup(listing);
            });

            try {
                const marker = new mapboxgl.Marker(el)
                    .setLngLat([lng, lat])
                    .addTo(map.current);

                markersRef.current.push(marker);
                if (listing.id != null) foodMarkerElsRef.current.set(listing.id, el);
                console.log('  ✓ Marker added at coordinates:', [lng, lat]);
            } catch (error) {
                console.error('❌ Failed to add food marker for', listing.title, ':', error.message);
            }
        });

        // Pre-compute number of active food listings per community so we can
        // render the count inside each community marker.
        const listingCountsByCommunity = foodListings.reduce((acc, l) => {
            if (l.community_id != null) {
                acc[l.community_id] = (acc[l.community_id] || 0) + 1;
            }
            return acc;
        }, {});

        // Add community markers
        communities.forEach((community) => {
            // Parse and validate coordinates
            const lat = parseFloat(community.latitude);
            const lng = parseFloat(community.longitude);
            
            // Validate coordinates are valid numbers and in correct ranges
            if (isNaN(lat) || isNaN(lng)) {
                console.error('❌ Invalid coordinates for', community.name, '- lat:', community.latitude, 'lng:', community.longitude);
                return;
            }
            if (!isBayAreaCoord(lat, lng)) {
                console.warn('⚠️ Skipping out-of-region community marker:', community.name, lat, lng);
                return;
            }
            
            console.log('✅ Adding community marker:', community.name);
            console.log('  Database values - lat:', community.latitude, 'lng:', community.longitude);
            console.log('  Parsed as numbers - lat:', lat, 'lng:', lng);
            console.log('  Mapbox format [lng, lat]:', [lng, lat]);

            const count = listingCountsByCommunity[community.id] || 0;
            const svg = renderCommunityPinSvg({
                communityId: community.id,
                count,
            });
            const { width: svgW, height: svgH } = getCommunityPinDimensions(count);

            const el = document.createElement('div');
            el.className = 'community-marker';
            el.style.width = `${svgW}px`;
            el.style.height = `${svgH}px`;
            el.style.cursor = 'pointer';
            el.innerHTML = svg;
            el.title = `${community.name} — ${count} listing${count === 1 ? '' : 's'}`;

            el.addEventListener('click', () => {
                showCommunityPopup(community);
            });

            try {
                const marker = new mapboxgl.Marker({ element: el, anchor: 'bottom' })
                    .setLngLat([lng, lat])
                    .addTo(map.current);

                markersRef.current.push(marker);
            } catch (error) {
                console.error('❌ Failed to add community marker:', error);
            }
        });
    };

    const showPopup = (listing) => {
        const mapboxgl = getMapboxgl();
        if (!mapboxgl || !map.current) {
            console.warn('⚠️ Mapbox not ready for popup');
            return;
        }

        // Safely extract a plain-text address from the listing.
        // food_listings.location is a JSONB column — direct string interpolation
        // would render "[object Object]" in the popup.
        const pickupAddress = (() => {
            if (listing.full_address && typeof listing.full_address === 'string') return listing.full_address.trim();
            const loc = listing.location;
            if (!loc) return '';
            if (typeof loc === 'string') {
                const t = loc.trim();
                if (t.startsWith('{')) {
                    try { const p = JSON.parse(t); return (p.address || p.full_address || '').trim(); } catch { /* fall through */ }
                }
                return t;
            }
            if (typeof loc === 'object') return (loc.address || loc.full_address || '').trim();
            return '';
        })();

        // Remove existing popup if clicking on a different listing
        if (popupRef.current) {
            popupRef.current.remove();
        }

        const popupContent = document.createElement('div');
        popupContent.className = 'p-3 max-w-xs';
        popupContent.style.width = '300px';

        popupContent.innerHTML = `
            ${listing.image_url ? `
                <img 
                    src="${escapeHtml(listing.image_url)}" 
                    alt="${escapeHtml(listing.title)}"
                    style="width: 100%; height: 128px; object-fit: cover; border-radius: 8px; margin-bottom: 12px;"
                />
            ` : ''}
            <h3 style="font-weight: bold; font-size: 18px; color: #111827; margin-bottom: 8px;">
                ${escapeHtml(listing.title)}
            </h3>
            <p style="font-size: 14px; color: #4B5563; margin-bottom: 12px; line-height: 1.5;">
                ${escapeHtml(listing.description || 'No description available')}
            </p>
            <div style="display: flex; align-items: center; gap: 8px; margin-bottom: 12px; font-size: 14px; color: #374151;">
                <i class="fas fa-weight" style="color: #16A34A;"></i>
                <span>${escapeHtml(listing.quantity)} ${escapeHtml(listing.unit)}</span>
            </div>
            ${pickupAddress ? `
            <div style="display: flex; align-items: center; gap: 8px; margin-bottom: 12px; font-size: 13px; color: #6B7280;">
                <i class="fas fa-map-marker-alt" style="color: #16A34A;"></i>
                <span>${escapeHtml(pickupAddress)}</span>
            </div>
            ` : ''}
            
            ${showSignupPrompt ? `
                <div style="background: #DBEAFE; border: 1px solid #93C5FD; border-radius: 8px; padding: 12px; margin-bottom: 12px;">
                    <p style="font-size: 14px; color: #1E40AF; font-weight: 500; margin-bottom: 8px;">
                        <i class="fas fa-info-circle" style="margin-right: 4px;"></i>
                        Sign up to claim this food!
                    </p>
                    <p style="font-size: 12px; color: #1E3A8A;">
                        Create a free account to connect with donors and help reduce food waste.
                    </p>
                </div>

                <div style="display: flex; gap: 8px;">
                    <button id="signup-btn" style="
                        flex: 1;
                        background: #16A34A;
                        color: white;
                        font-weight: 500;
                        padding: 8px 16px;
                        border-radius: 8px;
                        border: none;
                        cursor: pointer;
                        font-size: 14px;
                        transition: background 0.2s;
                    " onmouseover="this.style.background='#15803D'" onmouseout="this.style.background='#16A34A'">
                        Sign Up Free
                    </button>
                    <button id="login-btn" style="
                        flex: 1;
                        background: #F3F4F6;
                        color: #374151;
                        font-weight: 500;
                        padding: 8px 16px;
                        border-radius: 8px;
                        border: none;
                        cursor: pointer;
                        font-size: 14px;
                        transition: background 0.2s;
                    " onmouseover="this.style.background='#E5E7EB'" onmouseout="this.style.background='#F3F4F6'">
                        Log In
                    </button>
                </div>
            ` : `
                <button id="view-details-btn" style="
                    width: 100%;
                    background: #16A34A;
                    color: white;
                    font-weight: 500;
                    padding: 10px 16px;
                    border-radius: 8px;
                    border: none;
                    cursor: pointer;
                    font-size: 14px;
                    transition: background 0.2s;
                " onmouseover="this.style.background='#15803D'" onmouseout="this.style.background='#16A34A'">
                    <i class="fas fa-hand-holding-heart" style="margin-right: 6px;"></i>
                    View Details & Claim
                </button>
            `}
        `;

        popupRef.current = new mapboxgl.Popup({
            closeButton: true,
            closeOnClick: false,
            maxWidth: '320px',
            offset: 25
        })
            .setLngLat([listing.longitude, listing.latitude])
            .setDOMContent(popupContent)
            .addTo(map.current);

        // Add event listeners after popup is added to DOM
        setTimeout(() => {
            if (showSignupPrompt) {
                const signupBtn = document.getElementById('signup-btn');
                const loginBtn = document.getElementById('login-btn');
                
                if (signupBtn) {
                    signupBtn.addEventListener('click', () => navigate('/signup'));
                }
                if (loginBtn) {
                    loginBtn.addEventListener('click', () => navigate('/login'));
                }
            } else {
                const viewDetailsBtn = document.getElementById('view-details-btn');
                if (viewDetailsBtn) {
                    viewDetailsBtn.addEventListener('click', () => navigate('/claim', { state: { food: listing } }));
                }
            }
        }, 0);

        if (onMarkerClick) {
            onMarkerClick(listing);
        }
    };

    const showCommunityPopup = (community) => {
        const mapboxgl = getMapboxgl();
        if (!mapboxgl || !map.current) {
            console.warn('⚠️ Mapbox not ready for popup');
            return;
        }
        
        // Remove existing popup if clicking on a different community
        if (popupRef.current) {
            popupRef.current.remove();
        }

        const popupContent = document.createElement('div');
        popupContent.className = 'p-3 max-w-xs';
        popupContent.style.width = '300px';

        popupContent.innerHTML = `
            ${community.image ? `
                <img 
                    src="${escapeHtml(community.image)}" 
                    alt="${escapeHtml(community.name)}"
                    style="width: 100%; height: 128px; object-fit: cover; border-radius: 8px; margin-bottom: 12px;"
                />
            ` : ''}
            <h3 style="font-weight: bold; font-size: 18px; color: #111827; margin-bottom: 8px;">
                ${escapeHtml(community.name)}
            </h3>
            <div style="display: flex; flex-direction: column; gap: 8px; margin-bottom: 12px; font-size: 14px; color: #374151;">
                <div style="display: flex; align-items: start; gap: 8px;">
                    <i class="fas fa-map-marker-alt" style="color: #2CABE3; margin-top: 2px;"></i>
                    <span>${escapeHtml(community.location)}</span>
                </div>
                <div style="display: flex; align-items: center; gap: 8px;">
                    <i class="fas fa-clock" style="color: #2CABE3;"></i>
                    <span>${escapeHtml(community.hours)}</span>
                </div>
                <div style="display: flex; align-items: center; gap: 8px;">
                    <i class="fas fa-phone" style="color: #2CABE3;"></i>
                    <span>${escapeHtml(community.phone)}</span>
                </div>
                <div style="display: flex; align-items: center; gap: 8px;">
                    <i class="fas fa-user" style="color: #2CABE3;"></i>
                    <span>${escapeHtml(community.contact)}</span>
                </div>
            </div>
            
            <button id="view-community-btn" style="
                width: 100%;
                background: #2CABE3;
                color: white;
                font-weight: 500;
                padding: 8px 16px;
                border-radius: 8px;
                border: none;
                cursor: pointer;
                font-size: 14px;
                transition: background 0.2s;
            " onmouseover="this.style.background='#2398c7'" onmouseout="this.style.background='#2CABE3'">
                View Community
            </button>
        `;

        popupRef.current = new mapboxgl.Popup({
            closeButton: true,
            closeOnClick: false,
            maxWidth: '320px',
            offset: 25
        })
            .setLngLat([community.longitude, community.latitude])
            .setDOMContent(popupContent)
            .addTo(map.current);

        // Add event listener for view community button
        setTimeout(() => {
            const viewBtn = document.getElementById('view-community-btn');
            if (viewBtn) {
                viewBtn.addEventListener('click', () => navigate(`/community/${community.id}`));
            }
        }, 0);
    };

    // ─── User location marker (GPS or geocoded profile address) ────────
    useEffect(() => {
        if (!mapLoaded || !map.current) return;
        const mapboxgl = getMapboxgl();
        if (!mapboxgl) return;

        // Inject one-time CSS for the user marker (classic red drop pin + ground shadow)
        if (typeof document !== 'undefined' && !document.getElementById('dogoods-user-marker-style')) {
            const style = document.createElement('style');
            style.id = 'dogoods-user-marker-style';
            style.textContent = `
                .dogoods-user-marker {
                    position: relative;
                    width: 32px;
                    height: 42px;
                    cursor: pointer;
                    transform-origin: 50% 100%;
                    filter: drop-shadow(0 3px 4px rgba(0,0,0,0.35));
                    z-index: 5;
                    pointer-events: auto;
                }
                .dogoods-user-marker svg { display: block; width: 100%; height: 100%; }
                .dogoods-user-marker .shadow {
                    position: absolute;
                    left: 50%;
                    bottom: -4px;
                    transform: translateX(-50%);
                    width: 18px;
                    height: 6px;
                    background: rgba(0,0,0,0.35);
                    border-radius: 50%;
                    filter: blur(2px);
                    z-index: -1;
                }
            `;
            document.head.appendChild(style);
        }

        const lat = userLocation?.latitude;
        const lng = userLocation?.longitude;
        const nLat = Number(lat);
        const nLng = Number(lng);
        const valid = Number.isFinite(nLat) && Number.isFinite(nLng);

        // Diagnostics: helps quickly spot why the user pin isn't showing.
        // eslint-disable-next-line no-console
        console.log('📍 User-pin effect:', {
            mapLoaded,
            hasMap: !!map.current,
            source: userLocationSource,
            lat,
            lng,
            valid,
        });

        // Remove any prior marker before re-adding (handles updates + cleanup)
        if (userMarkerRef.current) {
            try { userMarkerRef.current.remove(); } catch (_) { /* ignore */ }
            userMarkerRef.current = null;
        }

        if (!valid) return;

        try {
            const el = document.createElement('div');
            el.className = 'dogoods-user-marker';
            // Classic red teardrop "Google-style" pin. Tip is at the bottom-center,
            // so we anchor the Mapbox Marker at 'bottom'.
            el.innerHTML = `
                <svg viewBox="0 0 32 42" xmlns="http://www.w3.org/2000/svg" aria-hidden="true">
                    <path
                        d="M16 1C8.268 1 2 7.268 2 15c0 9.5 12 24 13.2 25.4a1 1 0 0 0 1.6 0C18 39.4 30 24.5 30 15 30 7.268 23.732 1 16 1z"
                        fill="#ea4335"
                        stroke="#b1271b"
                        stroke-width="1.2"
                    />
                    <circle cx="16" cy="15" r="5" fill="#ffffff" />
                </svg>
                <span class="shadow"></span>
            `;

            const sourceLabel = userLocationSource === 'profile'
                ? 'Your profile address'
                : 'Your current location';
            const hint = userLocationSource === 'profile'
                ? 'Using your saved profile address — enable GPS for a live position.'
                : 'Live location from your device.';

            const marker = new mapboxgl.Marker({ element: el, anchor: 'bottom' })
                .setLngLat([nLng, nLat])
                .setPopup(
                    new mapboxgl.Popup({ offset: 24 }).setHTML(
                        `<div style="padding:6px 4px;min-width:180px;">
                            <div style="font-weight:600;color:#111827;">${escapeHtml(sourceLabel)}</div>
                            <div style="font-size:12px;color:#4b5563;margin-top:4px;">${escapeHtml(hint)}</div>
                        </div>`
                    )
                )
                .addTo(map.current);
            userMarkerRef.current = marker;
            // eslint-disable-next-line no-console
            console.log('✅ User pin added at', [nLng, nLat]);

            // First time we successfully place the user pin, gently center the map
            // on it so the user can immediately see it. Subsequent updates (e.g. live
            // GPS) leave the map alone so we don't fight user panning.
            if (!userPinCenteredRef.current && isBayAreaCoord(nLat, nLng)) {
                userPinCenteredRef.current = true;
                try {
                    map.current.easeTo({
                        center: [nLng, nLat],
                        zoom: Math.max(map.current.getZoom() || 0, 12),
                        duration: 600,
                    });
                } catch (_) { /* ignore */ }
            } else if (!userPinCenteredRef.current) {
                userPinCenteredRef.current = true;
                console.warn('Skipping map center on out-of-region user location:', nLat, nLng);
            }
        } catch (err) {
            console.error('Failed to add user-location marker:', err);
        }

        return () => {
            if (userMarkerRef.current) {
                try { userMarkerRef.current.remove(); } catch (_) { /* ignore */ }
                userMarkerRef.current = null;
            }
        };
    }, [mapLoaded, userLocation?.latitude, userLocation?.longitude, userLocationSource]);

    // ─── AI overlay: render markers & route from MapContext ──────────────
    useEffect(() => {
        if (!mapLoaded || !map.current) return;
        const mapboxgl = getMapboxgl();
        if (!mapboxgl) return;

        // Clear previous AI markers
        aiMarkersRef.current.forEach(m => m.remove());
        aiMarkersRef.current = [];

        // Add AI-driven markers (food, distribution, route endpoints)
        (aiMarkers || []).forEach(m => {
            if (typeof m.lat !== 'number' || typeof m.lng !== 'number') return;
            if (!isBayAreaCoord(m.lat, m.lng)) return;
            const el = document.createElement('div');
            el.className = 'ai-map-marker';
            el.style.width = '26px';
            el.style.height = '26px';
            el.style.borderRadius = '50%';
            el.style.border = '3px solid white';
            el.style.boxShadow = '0 2px 8px rgba(0,0,0,0.35)';
            el.style.cursor = 'pointer';
            const colors = { food: '#10b981', distribution: '#f59e0b', pin: '#6366f1', user: '#06b6d4' };
            el.style.backgroundColor = colors[m.kind] || '#8b5cf6';
            el.title = m.title || '';
            try {
                const marker = new mapboxgl.Marker(el)
                    .setLngLat([m.lng, m.lat])
                    .setPopup(
                        new mapboxgl.Popup({ offset: 20 }).setHTML(
                            `<div style="padding:6px 4px;min-width:160px;">
                                <div style="font-weight:600;color:#111827;">${escapeHtml(m.title || '')}</div>
                                ${m.subtitle ? `<div style="font-size:12px;color:#4b5563;margin-top:4px;">${escapeHtml(String(m.subtitle))}</div>` : ''}
                            </div>`
                        )
                    )
                    .addTo(map.current);
                aiMarkersRef.current.push(marker);
            } catch (err) {
                console.error('Failed to add AI marker:', err);
            }
        });
    }, [aiMarkers, mapLoaded]);

    // Draw AI route line as a GeoJSON layer
    useEffect(() => {
        if (!mapLoaded || !map.current) return;
        const m = map.current;
        const sourceId = 'ai-route-source';
        const layerId = 'ai-route-layer';

        const removeRoute = () => {
            try {
                if (m.getLayer(layerId)) m.removeLayer(layerId);
                if (m.getSource(sourceId)) m.removeSource(sourceId);
            } catch (err) { /* ignore */ }
        };

        removeRoute();

        if (aiRoute && aiRoute.geometry) {
            try {
                m.addSource(sourceId, {
                    type: 'geojson',
                    data: { type: 'Feature', geometry: aiRoute.geometry, properties: {} },
                });
                m.addLayer({
                    id: layerId,
                    type: 'line',
                    source: sourceId,
                    layout: { 'line-join': 'round', 'line-cap': 'round' },
                    paint: {
                        'line-color': '#0ea5e9',
                        'line-width': 5,
                        'line-opacity': 0.85,
                    },
                });

                // Fit bounds to route
                const coords = aiRoute.geometry.coordinates || [];
                if (coords.length > 1) {
                    const bounds = coords.reduce(
                        (b, c) => b.extend(c),
                        new (getMapboxgl()).LngLatBounds(coords[0], coords[0])
                    );
                    const ne = bounds.getNorthEast();
                    const sw = bounds.getSouthWest();
                    const spanLat = Math.abs(ne.lat - sw.lat);
                    const spanLng = Math.abs(ne.lng - sw.lng);
                    // Skip continent-scale fits (e.g. bad geocodes) that jump to Austin/NYC.
                    if (spanLat <= 1.5 && spanLng <= 1.5) {
                        m.fitBounds(bounds, { padding: 60, duration: 800, maxZoom: 14 });
                    }
                }
            } catch (err) {
                console.error('Failed to draw AI route:', err);
            }
        }

        return () => { removeRoute(); };
    }, [aiRoute, mapLoaded]);

    // Honor centerOn requests from the AI — skip outlier coords that would
    // jump the map to test data (Austin, NYC, etc.) far from the Bay Area.
    useEffect(() => {
        if (!mapLoaded || !map.current || !centerRequest) return;
        const { lat, lng, zoom } = centerRequest;
        if (!isBayAreaCoord(lat, lng)) {
            console.warn('Skipping map flyTo to outlier coordinate:', lat, lng);
            return;
        }
        try {
            map.current.flyTo({
                center: [lng, lat],
                zoom: zoom || 13,
                duration: 800,
            });
        } catch (err) {
            console.error('Failed to fly to AI center:', err);
        }
    }, [centerRequest, mapLoaded]);

    const handleZoomIn = () => {
        try {
            map.current?.zoomIn({ duration: 250 });
        } catch (err) {
            console.error('Zoom in failed:', err);
        }
    };

    const handleZoomOut = () => {
        try {
            map.current?.zoomOut({ duration: 250 });
        } catch (err) {
            console.error('Zoom out failed:', err);
        }
    };

    return (
        <div
            className={`dogoods-food-map relative isolate w-full h-full min-h-[280px] sm:min-h-[400px] lg:min-h-[500px] overflow-visible ${className}`.trim()}
            style={{ backgroundColor: '#f0f0f0' }}
        >
            {/* Static map-like background - shows instantly */}
            <div 
                className="absolute inset-0 pointer-events-none" 
                style={{
                    backgroundImage: `
                        linear-gradient(rgba(220, 220, 220, 0.5) 1px, transparent 1px),
                        linear-gradient(90deg, rgba(220, 220, 220, 0.5) 1px, transparent 1px)
                    `,
                    backgroundSize: '50px 50px',
                    backgroundColor: '#e8e8e8',
                    opacity: mapLoaded ? 0 : 1,
                    transition: 'opacity 0.3s ease-out'
                }}
            >
                <div className="absolute inset-0 flex items-center justify-center">
                    <div className="text-center text-gray-500">
                        <i className="fas fa-map-marked-alt text-5xl mb-3"></i>
                        <p className="font-medium">Loading San Francisco Map...</p>
                    </div>
                </div>
            </div>
            
            <div 
                ref={mapContainer} 
                className="absolute inset-0 z-0 overflow-hidden rounded-2xl" 
                style={{ 
                    width: '100%', 
                    height: '100%',
                    opacity: mapLoaded ? 1 : 0,
                    transition: 'opacity 0.3s ease-in'
                }} 
            />

            {mapLoaded && (
                <div
                    className="dogoods-food-map-zoom absolute flex flex-col rounded-xl overflow-hidden shadow-[0_2px_10px_rgba(0,0,0,0.15)] border border-gray-200/80 bg-white/95 backdrop-blur-sm"
                    aria-label="Map zoom controls"
                >
                    <button
                        type="button"
                        onClick={handleZoomIn}
                        className="flex h-11 w-11 items-center justify-center text-gray-700 hover:bg-gray-50 active:bg-gray-100 border-b border-gray-200/80 touch-manipulation"
                        aria-label="Zoom in"
                    >
                        <i className="fas fa-plus text-base" aria-hidden="true" />
                    </button>
                    <button
                        type="button"
                        onClick={handleZoomOut}
                        className="flex h-11 w-11 items-center justify-center text-gray-700 hover:bg-gray-50 active:bg-gray-100 touch-manipulation"
                        aria-label="Zoom out"
                    >
                        <i className="fas fa-minus text-base" aria-hidden="true" />
                    </button>
                </div>
            )}

            {loading && (
                <div className="dogoods-food-map-overlay absolute top-4 left-1/2 transform -translate-x-1/2 bg-white rounded-lg shadow-lg px-4 py-2">
                    <div className="flex items-center gap-2">
                        <div className="animate-spin rounded-full h-4 w-4 border-b-2 border-[#2CABE3]"></div>
                        <span className="text-sm text-gray-600">Loading food locations...</span>
                    </div>
                </div>
            )}

            {!loading && foodListings.length === 0 && communities.length === 0 && (
                <div className="dogoods-food-map-overlay absolute top-4 left-1/2 transform -translate-x-1/2 bg-white/90 backdrop-blur-sm rounded-lg shadow-lg px-5 py-3 text-center max-w-sm">
                    <div className="text-gray-600 flex items-center gap-3">
                        <i className="fas fa-map-marker-alt text-xl text-gray-400"></i>
                        <div className="text-left">
                            <h3 className="font-bold text-sm">No Food Listings Yet</h3>
                            <p className="text-xs">Be the first to share food in your community!</p>
                        </div>
                    </div>
                </div>
            )}

            <div
                role="note"
                aria-label="Map legend"
                className="dogoods-food-map-legend absolute bg-white/95 backdrop-blur-sm rounded-xl shadow-[0_2px_10px_rgba(0,0,0,0.12)] px-2.5 py-1.5 sm:px-3 sm:py-2 max-w-[calc(100%-4.5rem)] sm:max-w-[calc(100%-6rem)]"
            >
                <div className="flex items-center gap-2 sm:gap-3 text-[11px] sm:text-sm flex-wrap leading-tight">
                    <div className="flex items-center gap-1.5">
                        <div className="w-2.5 h-2.5 sm:w-3 sm:h-3 rounded-full bg-[#dc2626] border-2 border-white shadow-[0_1px_2px_rgba(0,0,0,0.3)] shrink-0"></div>
                        <span className="font-medium text-gray-700">{foodListings.length} Listings</span>
                    </div>
                    <div className="flex items-center gap-1.5">
                        <CommunityPinIcon size={14} className="sm:hidden shrink-0" />
                        <CommunityPinIcon size={16} className="hidden sm:block shrink-0" />
                        <span className="font-medium text-gray-700">{communities.length} Communities</span>
                    </div>
                    {userLocation?.latitude != null && userLocation?.longitude != null && (
                        <div className="flex items-center gap-1.5">
                            <i className="fas fa-map-marker-alt text-[#ea4335] text-xs sm:text-base shrink-0" aria-hidden="true"></i>
                            <span className="font-medium text-gray-700">
                                {userLocationSource === 'profile' ? 'Your address' : 'You'}
                            </span>
                        </div>
                    )}
                </div>
            </div>
        </div>
    );
}

export default FoodMap;
