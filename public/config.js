// Browser environment configuration
// IMPORTANT: Replace placeholder values with your actual keys
// Do NOT commit real API keys to version control
// NOTE: OpenAI API key is backend-only. All AI calls go through /api/ai/*
window.__ENV__ = {
    // Mapbox Configuration
    VITE_MAPBOX_TOKEN: 'pk.eyJ1Ijoic2lnbndpc2UiLCJhIjoiY21rc2tjNjQ3MGFjajNkcHJ1cTNsbWV6dyJ9.xbJQFP3HCM2jmG87wvwC1Q',
    
    // API Settings
    API_TIMEOUT: '30000',
    API_MAX_RETRIES: '3',
    
    // Rate Limiting
    RATE_LIMIT_MAX_REQUESTS: '50',
    RATE_LIMIT_PREMIUM_MAX_REQUESTS: '100',
    RATE_LIMIT_TIME_WINDOW: '60000',
    
    // Feature Flags
    ENABLE_MOCK_RESPONSES: 'false',
    DEBUG_MODE: 'false'
}; 