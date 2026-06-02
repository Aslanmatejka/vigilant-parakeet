import React, { useState, useEffect, useRef } from 'react';
import { useNavigate } from 'react-router-dom';
import supabase from '../../utils/supabaseClient';
import { API_CONFIG } from '../../utils/config';
import { useMapContext } from '../../utils/MapContext.jsx';
import { useEffectiveLocation } from '../../utils/hooks/useLocation';

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

// Distinct, readable colors for community markers. Each community gets a
// stable color based on its id so it stays the same across renders.
const COMMUNITY_COLORS = [
    '#2563eb', // blue
    '#16a34a', // green
    '#db2777', // pink
    '#7c3aed', // purple
    '#ea580c', // orange
    '#0891b2', // cyan
    '#ca8a04', // amber
    '#dc2626', // red
    '#0d9488', // teal
    '#9333ea', // violet
    '#65a30d', // lime
    '#be185d', // rose
];
const colorForCommunity = (id) => {
    const key = String(id ?? '');
    let h = 0;
    for (let i = 0; i < key.length; i++) h = (h * 31 + key.charCodeAt(i)) >>> 0;
    return COMMUNITY_COLORS[h % COMMUNITY_COLORS.length];
};

function FoodMap({ onMarkerClick, showSignupPrompt = true, highlightedFoodId = null }) {
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
    const { aiMarkers, aiRoute, centerRequest } = useMapContext();
    const { location: userLocation, source: userLocationSource } = useEffectiveLocation();

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

        // Add navigation controls
        if (map.current && mapboxgl) {
            map.current.addControl(new mapboxgl.NavigationControl(), 'top-right');
        }

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
            if (!isNaN(lat) && !isNaN(lng)) {
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
            
            // Fetch ALL approved/active listings — we'll handle missing coordinates when placing markers
            const fetchPromise = supabase
                .from('food_listings')
                .select('*')
                .in('status', ['approved', 'active'])
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
            
            // San Francisco Bay Area bounds check: lat ~37-38, lng ~-122 to -121
            if (lat < 36 || lat > 39 || lng > -121 || lng < -123) {
                console.warn('⚠️ Coordinates outside Bay Area for', community.name, '- lat:', lat, 'lng:', lng);
            }
            
            console.log('✅ Adding community marker:', community.name);
            console.log('  Database values - lat:', community.latitude, 'lng:', community.longitude);
            console.log('  Parsed as numbers - lat:', lat, 'lng:', lng);
            console.log('  Mapbox format [lng, lat]:', [lng, lat]);

            const count = listingCountsByCommunity[community.id] || 0;
            const countStr = String(count);

            // Simple circular pin in the community's color, with a small red
            // badge in the top-right showing the active listing count.
            const dotR = 13;
            const badgeR = countStr.length >= 3 ? 11 : 9;
            const pad = badgeR + 2;
            const svgW = dotR * 2 + pad * 2;
            const svgH = dotR * 2 + pad * 2;
            const dotCx = svgW / 2;
            const dotCy = svgH / 2;

            const badgeCx = dotCx + dotR - 2;
            const badgeCy = dotCy - dotR + 2;

            const color = '#2563eb';

            const svg = `
                <svg xmlns="http://www.w3.org/2000/svg" width="${svgW}" height="${svgH}" viewBox="0 0 ${svgW} ${svgH}" style="display:block;overflow:visible;filter:drop-shadow(0 2px 3px rgba(0,0,0,0.3));">
                    <circle cx="${dotCx}" cy="${dotCy}" r="${dotR}"
                            fill="${color}" stroke="#ffffff" stroke-width="3" />
                    ${count > 0 ? `
                        <circle cx="${badgeCx}" cy="${badgeCy}" r="${badgeR}"
                                fill="#ef4444" stroke="#ffffff" stroke-width="1.75" />
                        <text x="${badgeCx}" y="${badgeCy}" text-anchor="middle" dominant-baseline="central"
                              fill="#ffffff" font-family="system-ui,-apple-system,Segoe UI,Roboto,sans-serif"
                              font-weight="700" font-size="${countStr.length >= 3 ? 9 : 11}">${countStr}</text>
                    ` : ''}
                </svg>
            `;

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
            if (!userPinCenteredRef.current) {
                userPinCenteredRef.current = true;
                try {
                    map.current.easeTo({
                        center: [nLng, nLat],
                        zoom: Math.max(map.current.getZoom() || 0, 12),
                        duration: 600,
                    });
                } catch (_) { /* ignore */ }
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
                                <div style="font-weight:600;color:#111827;">${(m.title || '').replace(/</g, '&lt;')}</div>
                                ${m.subtitle ? `<div style="font-size:12px;color:#4b5563;margin-top:4px;">${String(m.subtitle).replace(/</g, '&lt;')}</div>` : ''}
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
                    m.fitBounds(bounds, { padding: 60, duration: 800 });
                }
            } catch (err) {
                console.error('Failed to draw AI route:', err);
            }
        }

        return () => { removeRoute(); };
    }, [aiRoute, mapLoaded]);

    // Honor centerOn requests from the AI
    useEffect(() => {
        if (!mapLoaded || !map.current || !centerRequest) return;
        try {
            map.current.flyTo({
                center: [centerRequest.lng, centerRequest.lat],
                zoom: centerRequest.zoom || 13,
                duration: 800,
            });
        } catch (err) {
            console.error('Failed to fly to AI center:', err);
        }
    }, [centerRequest, mapLoaded]);

    return (
        <div className="relative w-full" style={{ height: '600px', backgroundColor: '#f0f0f0' }}>
            {/* Static map-like background - shows instantly */}
            <div 
                className="absolute inset-0" 
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
                className="absolute inset-0" 
                style={{ 
                    width: '100%', 
                    height: '100%',
                    opacity: mapLoaded ? 1 : 0,
                    transition: 'opacity 0.3s ease-in'
                }} 
            />

            {loading && (
                <div className="absolute top-4 left-1/2 transform -translate-x-1/2 bg-white rounded-lg shadow-lg px-4 py-2 z-10">
                    <div className="flex items-center gap-2">
                        <div className="animate-spin rounded-full h-4 w-4 border-b-2 border-[#2CABE3]"></div>
                        <span className="text-sm text-gray-600">Loading food locations...</span>
                    </div>
                </div>
            )}

            {!loading && foodListings.length === 0 && communities.length === 0 && (
                <div className="absolute top-4 left-1/2 transform -translate-x-1/2 bg-white/90 backdrop-blur-sm rounded-lg shadow-lg px-5 py-3 z-10 text-center max-w-sm">
                    <div className="text-gray-600 flex items-center gap-3">
                        <i className="fas fa-map-marker-alt text-xl text-gray-400"></i>
                        <div className="text-left">
                            <h3 className="font-bold text-sm">No Food Listings Yet</h3>
                            <p className="text-xs">Be the first to share food in your community!</p>
                        </div>
                    </div>
                </div>
            )}

            <div className="absolute bottom-4 left-4 bg-white rounded-lg shadow-lg px-4 py-2 z-10">
                <div className="flex items-center gap-4 text-sm flex-wrap">
                    <div className="flex items-center gap-2">
                        <div className="w-3 h-3 rounded-full bg-[#dc2626] border-2 border-white shadow-[0_1px_2px_rgba(0,0,0,0.3)]"></div>
                        <span className="font-medium text-gray-700">{foodListings.length} Listings</span>
                    </div>
                    <div className="flex items-center gap-2">
                        <div className="w-3 h-3 rounded-full bg-[#2563eb] border-2 border-white shadow-[0_1px_2px_rgba(0,0,0,0.3)]"></div>
                        <span className="font-medium text-gray-700">{communities.length} Communities</span>
                    </div>
                    {userLocation?.latitude != null && userLocation?.longitude != null && (
                        <div className="flex items-center gap-2">
                            <i className="fas fa-map-marker-alt text-[#ea4335] text-base"></i>
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
