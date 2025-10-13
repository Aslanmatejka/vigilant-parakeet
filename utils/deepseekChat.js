import { getApiConfig } from './config.js';

/**
 * Send a chat conversation to Deepseek LLM and get a response.
 * @param {Array} messages - Array of {role: 'user'|'assistant'|'system', content: string}
 * @param {Object} options - Optional: { model, temperature, max_tokens, stream }
 * @returns {Promise<string>} - The assistant's reply
 */
export async function deepseekChat(messages, options = {}) {
    const config = getApiConfig().DEEPSEEK;
    const endpoint = config.API_ENDPOINT + '/chat/completions';
    const apiKey = config.API_KEY;
    const model = options.model || config.MODELS?.CHAT || 'deepseek-chat';
    const temperature = options.temperature ?? 0.7;
    const max_tokens = options.max_tokens ?? 1000;
    const stream = options.stream ?? false;

    const body = {
        model,
        messages,
        temperature,
        max_tokens,
        stream
    };

    try {
        const res = await fetch(endpoint, {
            method: 'POST',
            headers: {
                'Authorization': `Bearer ${apiKey}`,
                'Content-Type': 'application/json'
            },
            body: JSON.stringify(body)
        });

        if (!res.ok) {
            const errorText = await res.text();
            throw new Error(`Deepseek LLM error: ${res.status} ${errorText}`);
        }

        if (stream) {
            return res.body;
        }

        const data = await res.json();
        return data.choices?.[0]?.message?.content || '';
    } catch (error) {
        console.error('Deepseek API error:', error);
        throw error;
    }
}

/**
 * Stream chat response from Deepseek LLM
 * @param {Array} messages - Array of message objects
 * @param {Function} onChunk - Callback for each chunk received
 * @param {Object} options - Optional configuration
 * @returns {Promise<void>}
 */
export async function streamDeepseekChat(messages, onChunk, options = {}) {
    try {
        const stream = await deepseekChat(messages, { ...options, stream: true });
        const reader = stream.getReader();
        const decoder = new TextDecoder();

        while (true) {
            const { done, value } = await reader.read();
            if (done) break;

            const chunk = decoder.decode(value);
            const lines = chunk.split('\n');

            for (const line of lines) {
                if (line.startsWith('data: ')) {
                    const data = line.slice(6);
                    if (data === '[DONE]') return;

                    try {
                        const parsed = JSON.parse(data);
                        const content = parsed.choices?.[0]?.delta?.content;
                        if (content) {
                            onChunk(content);
                        }
                    } catch (e) {
                        // Skip invalid JSON
                    }
                }
            }
        }
    } catch (error) {
        console.error('Streaming error:', error);
        throw error;
    }
}

/**
 * Test the Deepseek API connection
 * @returns {Promise<boolean>}
 */
export async function testDeepseekConnection() {
    try {
        const testMessage = [
            { role: 'user', content: 'Hello' }
        ];
        await deepseekChat(testMessage, { max_tokens: 10 });
        return true;
    } catch (error) {
        console.error('Deepseek connection test failed:', error);
        return false;
    }
} 