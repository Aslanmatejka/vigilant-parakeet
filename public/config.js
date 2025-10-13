// Browser environment configuration
window.__ENV__ = {
    // DeepSeek Configuration
    DEEPSEEK_API_KEY: 'sk-4e56de010f4544cfb8c45c742faa4faf', // Updated with your actual API key
    DEEPSEEK_API_ENDPOINT: 'https://api.deepseek.com/v1',
    DEEPSEEK_MODEL_VERSION: '1.0.0',
    
    // API Settings
    API_TIMEOUT: '30000',
    API_MAX_RETRIES: '3',
    
    // Rate Limiting
    RATE_LIMIT_MAX_REQUESTS: '50',
    RATE_LIMIT_PREMIUM_MAX_REQUESTS: '100',
    RATE_LIMIT_TIME_WINDOW: '60000',
    
    // Feature Flags
    ENABLE_MOCK_RESPONSES: 'false', // Disable mock responses since we have a real API key
    DEBUG_MODE: 'false'
}; 