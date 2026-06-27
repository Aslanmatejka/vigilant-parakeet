// Load environment variables from window.__ENV__ if available
const ENV = (typeof window !== 'undefined' && window.__ENV__) || {};

// Also check Vite env (loaded from .env.local)
const VITE_ENV = typeof import.meta !== 'undefined' && import.meta.env ? import.meta.env : {};
const NODE_ENV = (typeof process !== 'undefined' && process.env) || {};

// API Configuration
// NOTE: OpenAI API key is backend-only (not exposed to frontend).
// All AI calls go through /api/ai/* which is proxied to the FastAPI backend.
const API_CONFIG = {
    MAPBOX: {
        ACCESS_TOKEN: VITE_ENV.VITE_MAPBOX_TOKEN || ENV.VITE_MAPBOX_TOKEN || ENV.MAPBOX_TOKEN || NODE_ENV.VITE_MAPBOX_TOKEN || NODE_ENV.MAPBOX_TOKEN || ''
    },
    RATE_LIMITS: {
        DEFAULT: {
            maxRequests: parseInt(ENV.RATE_LIMIT_MAX_REQUESTS) || 50,
            timeWindow: parseInt(ENV.RATE_LIMIT_TIME_WINDOW) || 60 * 1000, // 1 minute
        },
        PREMIUM: {
            maxRequests: parseInt(ENV.RATE_LIMIT_PREMIUM_MAX_REQUESTS) || 100,
            timeWindow: parseInt(ENV.RATE_LIMIT_TIME_WINDOW) || 60 * 1000,
        }
    }
};

const SUPABASE_CONFIG = {
    URL: VITE_ENV.VITE_SUPABASE_URL || ENV.VITE_SUPABASE_URL || ENV.SUPABASE_URL || NODE_ENV.VITE_SUPABASE_URL || NODE_ENV.SUPABASE_URL || '',
    ANON_KEY: VITE_ENV.VITE_SUPABASE_ANON_KEY || ENV.VITE_SUPABASE_ANON_KEY || ENV.SUPABASE_ANON_KEY || NODE_ENV.VITE_SUPABASE_ANON_KEY || NODE_ENV.SUPABASE_ANON_KEY || ''
};

// Get API configuration
function getApiConfig() {
    return {
        ...API_CONFIG,
    };
}

function getSupabaseConfig() {
    return {
        ...SUPABASE_CONFIG,
    };
}

export { API_CONFIG, SUPABASE_CONFIG, getApiConfig, getSupabaseConfig };