import { getApiConfig } from './config.js';

class DeepSeekClient {
    constructor() {
        // Don't cache config values - get them fresh each time
    }

    _getConfig() {
        const config = getApiConfig().DEEPSEEK;
        return config;
    }

    async chat(messages, options = {}) {
        const {
            model = 'deepseek-chat',
            temperature = 0.7,
            max_tokens = 1000,
            stream = false
        } = options;

        return this._makeRequest('/chat/completions', {
            model,
            messages,
            temperature,
            max_tokens,
            stream
        });
    }

    async complete(prompt, options = {}) {
        const {
            model = 'deepseek-completion',
            temperature = 0.7,
            max_tokens = 1000,
            stream = false
        } = options;

        return this._makeRequest('/completions', {
            model,
            prompt,
            temperature,
            max_tokens,
            stream
        });
    }

    async _makeRequest(endpoint, data) {
        const config = this._getConfig();
        const headers = {
            'Authorization': `Bearer ${config.API_KEY}`,
            'Content-Type': 'application/json'
        };

        for (let attempt = 0; attempt <= config.MAX_RETRIES; attempt++) {
            try {
                const controller = new AbortController();
                const timeoutId = setTimeout(() => controller.abort(), config.TIMEOUT);

                const response = await fetch(`${config.API_ENDPOINT}${endpoint}`, {
                    method: 'POST',
                    headers,
                    body: JSON.stringify(data),
                    signal: controller.signal
                });

                clearTimeout(timeoutId);

                if (!response.ok) {
                    let errorDetails;
                    try {
                        errorDetails = await response.json();
                    } catch (parseError) {
                        errorDetails = await response.text();
                    }
                    
                    console.error('DeepSeek API Error:', {
                        status: response.status,
                        statusText: response.statusText,
                        error: errorDetails,
                        apiKey: config.API_KEY?.substring(0, 10) + '...',
                        endpoint: `${config.API_ENDPOINT}${endpoint}`
                    });
                    
                    throw new Error(errorDetails.message || errorDetails || `API request failed: ${response.status}`);
                }

                return await response.json();
            } catch (error) {
                if (error.name === 'AbortError') {
                    throw new Error('Request timed out');
                }
                if (attempt === config.MAX_RETRIES) {
                    throw error;
                }
                // Exponential backoff with jitter
                const backoffTime = Math.pow(2, attempt) * 1000;
                const jitter = Math.random() * 1000;
                await new Promise(resolve => setTimeout(resolve, backoffTime + jitter));
            }
        }
    }

    // Helper methods for specific use cases
    async generateRecipe(ingredients) {
        const messages = [
            {
                role: 'system',
                content: 'You are a culinary expert. Generate a recipe using the provided ingredients.'
            },
            {
                role: 'user',
                content: `Create a recipe using these ingredients: ${ingredients.join(', ')}`
            }
        ];

        return this.chat(messages, {
            temperature: 0.8,
            max_tokens: 1500
        });
    }

    async getStorageTips(food) {
        const messages = [
            {
                role: 'system',
                content: 'You are a food preservation expert. Provide detailed storage tips.'
            },
            {
                role: 'user',
                content: `How should I store ${food} to keep it fresh longer?`
            }
        ];

        return this.chat(messages, {
            temperature: 0.7,
            max_tokens: 1000
        });
    }

    async calculateImpact(foodType, quantity, unit) {
        const messages = [
            {
                role: 'system',
                content: 'You are an environmental impact expert. Calculate the environmental impact of food waste prevention.'
            },
            {
                role: 'user',
                content: `Calculate the environmental impact of saving ${quantity} ${unit} of ${foodType}`
            }
        ];

        return this.chat(messages, {
            temperature: 0.5,
            max_tokens: 800
        });
    }
}

// Create and export singleton instance
const deepseekClient = new DeepSeekClient();
export default deepseekClient; 