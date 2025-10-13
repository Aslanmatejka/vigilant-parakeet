import { getApiConfig } from './config.js';

/**
 * OpenAI API Client
 * Handles communication with OpenAI's API
 */
class OpenAIClient {
    constructor() {
        this.config = getApiConfig().OPENAI;
    }

    async _makeRequest(endpoint, options = {}) {
        const url = `${this.config.API_ENDPOINT}${endpoint}`;
        
        const requestOptions = {
            method: 'POST',
            headers: {
                'Authorization': `Bearer ${this.config.API_KEY}`,
                'Content-Type': 'application/json',
                ...options.headers
            },
            body: JSON.stringify(options.body),
            ...options
        };

        try {
            const response = await fetch(url, requestOptions);
            
            if (!response.ok) {
                const errorText = await response.text();
                throw new Error(`OpenAI API request failed: ${response.status} ${errorText}`);
            }

            return await response.json();
        } catch (error) {
            console.error('OpenAI API Error:', error);
            throw new Error(`API request failed: ${error.message}`);
        }
    }

    /**
     * Send a chat completion request
     * @param {Array} messages - Array of message objects
     * @param {Object} options - Optional configuration
     * @returns {Promise<string>} The assistant's response
     */
    async chat(messages, options = {}) {
        const {
            model = this.config.MODELS.CHAT,
            temperature = 0.7,
            max_tokens = 1000,
            top_p = 1,
            frequency_penalty = 0,
            presence_penalty = 0
        } = options;

        const requestBody = {
            model,
            messages,
            temperature,
            max_tokens,
            top_p,
            frequency_penalty,
            presence_penalty
        };

        try {
            const response = await this._makeRequest('/chat/completions', {
                body: requestBody
            });

            return response.choices?.[0]?.message?.content || '';
        } catch (error) {
            console.error('OpenAI Chat Error:', error);
            throw error;
        }
    }

    /**
     * Send a completion request (for older models)
     * @param {string} prompt - The prompt text
     * @param {Object} options - Optional configuration
     * @returns {Promise<string>} The completion response
     */
    async completion(prompt, options = {}) {
        const {
            model = this.config.MODELS.COMPLETION,
            temperature = 0.7,
            max_tokens = 1000,
            top_p = 1,
            frequency_penalty = 0,
            presence_penalty = 0
        } = options;

        const requestBody = {
            model,
            prompt,
            temperature,
            max_tokens,
            top_p,
            frequency_penalty,
            presence_penalty
        };

        try {
            const response = await this._makeRequest('/completions', {
                body: requestBody
            });

            return response.choices?.[0]?.text || '';
        } catch (error) {
            console.error('OpenAI Completion Error:', error);
            throw error;
        }
    }

    /**
     * Test the connection to OpenAI API
     * @returns {Promise<boolean>} True if connection is successful
     */
    async testConnection() {
        try {
            const testMessages = [
                { role: 'user', content: 'Hello, can you respond with just "OK"?' }
            ];

            const response = await this.chat(testMessages, { max_tokens: 10 });
            return response.toLowerCase().includes('ok');
        } catch (error) {
            console.error('OpenAI connection test failed:', error);
            return false;
        }
    }
}

// Export a singleton instance
const openaiClient = new OpenAIClient();
export default openaiClient;
