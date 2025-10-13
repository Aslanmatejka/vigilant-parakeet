// Load environment variables from window.__ENV__ if available
const ENV = (typeof window !== 'undefined' && window.__ENV__) || {};

// API Configuration
const API_CONFIG = {
    DEEPSEEK: {
        API_KEY: ENV.DEEPSEEK_API_KEY || 'sk-4e56de010f4544cfb8c45c742faa4faf',
        API_ENDPOINT: ENV.DEEPSEEK_API_ENDPOINT || 'https://api.deepseek.com/v1',
        MODEL_VERSION: ENV.DEEPSEEK_MODEL_VERSION || '1.0.0',
        TIMEOUT: parseInt(ENV.API_TIMEOUT) || 30000, // 30 seconds
        MAX_RETRIES: parseInt(ENV.API_MAX_RETRIES) || 3,
        MODELS: {
            CHAT: 'deepseek-chat',
            COMPLETION: 'deepseek-completion'
        }
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

// Validate API configuration
function validateApiConfig() {
    const { DEEPSEEK } = API_CONFIG;
    
    if (!DEEPSEEK.API_KEY || 
        DEEPSEEK.API_KEY === 'your-deepseek-api-key-here' ||
        !DEEPSEEK.API_KEY.startsWith('sk-')) {
        console.warn('⚠️ DeepSeek API key not configured. Some AI features may be limited.');
        return false;
    }
    
    console.log('✅ DeepSeek API key configured:', DEEPSEEK.API_KEY.substring(0, 10) + '...');
    return true;
}

// Get API configuration
function getApiConfig() {
    return {
        ...API_CONFIG,
        isValid: validateApiConfig()
    };
}

export { getApiConfig }; 