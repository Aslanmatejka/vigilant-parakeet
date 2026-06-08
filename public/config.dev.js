// Development configuration template
// Copy this file to config.js and replace with your actual values
// NOTE: OpenAI API key is backend-only. All AI calls go through /api/ai/*
window.__ENV__ = {
    // Mapbox Configuration
    VITE_MAPBOX_TOKEN: '', // Set in .env as VITE_MAPBOX_TOKEN
    
    // API Settings
    API_TIMEOUT: '30000',
    API_MAX_RETRIES: '3',
    
    // Rate Limiting
    RATE_LIMIT_MAX_REQUESTS: '50',
    RATE_LIMIT_PREMIUM_MAX_REQUESTS: '100',
    RATE_LIMIT_TIME_WINDOW: '60000',
    
    // Feature Flags
    ENABLE_MOCK_RESPONSES: 'false',
    DEBUG_MODE: 'true'
}; 