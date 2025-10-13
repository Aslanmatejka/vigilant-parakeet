import deepseekClient from './deepseekClient.js';
import { getApiConfig } from './config.js';

// Rate limiting system
const rateLimitStore = new Map();

async function checkRateLimit(clientId = 'default') {
    const now = Date.now();
    const config = getApiConfig().RATE_LIMITS.DEFAULT;
    
    if (!rateLimitStore.has(clientId)) {
        rateLimitStore.set(clientId, { requests: [], windowStart: now });
    }
    
    const clientData = rateLimitStore.get(clientId);
    
    // Clean old requests outside the time window
    clientData.requests = clientData.requests.filter(time => now - time < config.timeWindow);
    
    if (clientData.requests.length >= config.maxRequests) {
        throw new Error('Rate limit exceeded. Please try again later.');
    }
    
    clientData.requests.push(now);
}

// Circuit breaker pattern
class CircuitBreaker {
    constructor(failureThreshold = 5, resetTimeout = 60000) {
        this.failureThreshold = failureThreshold;
        this.resetTimeout = resetTimeout;
        this.failureCount = 0;
        this.state = 'CLOSED'; // CLOSED, OPEN, HALF_OPEN
        this.nextAttempt = Date.now();
    }

    async executeRequest(request) {
        if (this.state === 'OPEN') {
            if (Date.now() < this.nextAttempt) {
                throw new Error('Circuit breaker is OPEN');
            }
            this.state = 'HALF_OPEN';
        }

        try {
            const result = await request();
            this.onSuccess();
            return result;
        } catch (error) {
            this.onFailure();
            throw error;
        }
    }

    onSuccess() {
        this.failureCount = 0;
        this.state = 'CLOSED';
    }

    onFailure() {
        this.failureCount++;
        if (this.failureCount >= this.failureThreshold) {
            this.state = 'OPEN';
            this.nextAttempt = Date.now() + this.resetTimeout;
        }
    }
}

const circuitBreaker = new CircuitBreaker();

// AI Chat Assistant
async function chatWithNourish(message, context = '') {
    if (!message || typeof message !== 'string') {
        throw new Error('Invalid message format. Message must be a non-empty string.');
    }

    try {
        const systemPrompt = `You are Nourish, ShareFoods' AI assistant. You help users with food sharing, 
        provide cooking tips, and suggest ways to reduce food waste. Consider the following context:
        ${context}`;
    
        const response = await invokeAIAgent(systemPrompt, message);
        return response;
    } catch (error) {
        console.error('AI chat error:', error);
        throw new Error('Unable to process your request. Please try again.');
    }
}

// Recipe Suggestions
async function getRecipeSuggestions(ingredients) {
    if (!Array.isArray(ingredients) || ingredients.length === 0) {
        throw new Error('Invalid ingredients format. Must provide a non-empty array of ingredients.');
    }

    try {
        const systemPrompt = `You are a culinary expert. Suggest recipes using these ingredients: ${ingredients.join(', ')}. 
        Focus on reducing food waste and using ingredients efficiently.`;
        
        const response = await invokeAIAgent(systemPrompt, 'Suggest 3 recipes.');
        
        // Handle both string and object responses
        let parsedResponse;
        if (typeof response === 'string') {
            try {
                parsedResponse = JSON.parse(response);
            } catch (e) {
                // If response is not JSON, create a structured response
                parsedResponse = {
                    recipes: [{
                        name: "Simple Recipe",
                        ingredients: ingredients,
                        instructions: response,
                        prepTime: "N/A",
                        cookTime: "N/A",
                        difficulty: "N/A",
                        servings: 2
                    }]
                };
            }
        } else {
            parsedResponse = response;
        }

        // Validate response structure
        if (!parsedResponse.recipes || !Array.isArray(parsedResponse.recipes)) {
            throw new Error('Invalid response format from AI agent');
        }

        return parsedResponse;
    } catch (error) {
        console.error('Recipe suggestion error:', error);
        throw new Error('Unable to generate recipe suggestions. Please try again.');
    }
}

// Food Pairing Recommendations
async function getFoodPairings(food) {
    if (!food || typeof food !== 'string') {
        throw new Error('Invalid food parameter. Must provide a non-empty string.');
    }

    try {
        const systemPrompt = `You are a food pairing expert. Suggest complementary foods and ingredients that pair well with: ${food}.`;
        
        const response = await invokeAIAgent(systemPrompt, 'Suggest pairings.');
        
        // Handle both string and object responses
        let parsedResponse;
        if (typeof response === 'string') {
            try {
                parsedResponse = JSON.parse(response);
            } catch (e) {
                // If response is not JSON, create a structured response
                parsedResponse = {
                    food: food,
                    pairings: [{
                        name: "Suggested Pairing",
                        description: response
                    }]
                };
            }
        } else {
            parsedResponse = response;
        }

        // Validate response structure
        if (!parsedResponse.food || !Array.isArray(parsedResponse.pairings)) {
            throw new Error('Invalid response format from AI agent');
        }

        return parsedResponse;
    } catch (error) {
        console.error('Food pairing error:', error);
        throw new Error('Unable to generate food pairings. Please try again.');
    }
}

// Storage Tips
async function getStorageTips(food) {
    if (!food || typeof food !== 'string') {
        throw new Error('Invalid food parameter. Must provide a non-empty string.');
    }

    try {
        const systemPrompt = `You are a food preservation expert. Provide storage tips and best practices for: ${food}.`;
        
        const response = await invokeAIAgent(systemPrompt, 'Provide storage tips.');
        
        // Handle both string and object responses
        let parsedResponse;
        if (typeof response === 'string') {
            try {
                parsedResponse = JSON.parse(response);
            } catch (e) {
                // If response is not JSON, create a structured response
                parsedResponse = {
                    food: food,
                    tips: [response],
                    shelfLife: {
                        refrigerator: "Check packaging",
                        freezer: "Check packaging",
                        roomTemperature: "Check packaging"
                    }
                };
            }
        } else {
            parsedResponse = response;
        }

        // Validate response structure
        if (!parsedResponse.food || !Array.isArray(parsedResponse.tips) || !parsedResponse.shelfLife) {
            throw new Error('Invalid response format from AI agent');
        }

        return parsedResponse;
    } catch (error) {
        console.error('Storage tips error:', error);
        throw new Error('Unable to generate storage tips. Please try again.');
    }
}

// Trade Value Estimation
async function calculateEnvironmentalImpact(foodType, quantity, unit) {
    if (!foodType || typeof quantity !== 'number' || !unit) {
        throw new Error('Invalid parameters. Must provide foodType (string), quantity (number), and unit (string).');
    }

    try {
        const systemPrompt = `You are an environmental impact expert. Calculate the environmental impact of saving:
        Food Type: ${foodType}
        Quantity: ${quantity}
        Unit: ${unit}
        
        Format your response as JSON with this structure:
        {
          "foodType": "${foodType}",
          "quantity": ${quantity},
          "unit": "${unit}",
          "waterSaved": "X liters",
          "co2Prevented": "X kg",
          "landSaved": "X sq meters",
          "equivalents": {
            "carMiles": "X miles of driving",
            "showerMinutes": "X minutes of showering"
          }
        }`;
        
        const response = await invokeAIAgent(systemPrompt, 'Calculate impact.');
        
        // Handle both string and object responses
        let parsedResponse;
        if (typeof response === 'string') {
            try {
                parsedResponse = JSON.parse(response);
            } catch (parseError) {
                console.warn('Failed to parse AI response as JSON, using fallback');
                parsedResponse = {
                    foodType: foodType,
                    quantity: quantity,
                    unit: unit,
                    waterSaved: "Unable to calculate",
                    co2Prevented: "Unable to calculate", 
                    landSaved: "Unable to calculate",
                    equivalents: {
                        carMiles: "Unable to calculate",
                        showerMinutes: "Unable to calculate"
                    }
                };
            }
        } else if (typeof response === 'object' && response !== null) {
            parsedResponse = response;
        } else {
            throw new Error('Invalid response type from AI agent');
        }
        
        // Validate response structure and provide defaults
        const validatedResponse = {
            foodType: parsedResponse.foodType || foodType,
            quantity: parsedResponse.quantity || quantity,
            unit: parsedResponse.unit || unit,
            waterSaved: parsedResponse.waterSaved || "Data unavailable",
            co2Prevented: parsedResponse.co2Prevented || "Data unavailable",
            landSaved: parsedResponse.landSaved || "Data unavailable",
            equivalents: {
                carMiles: parsedResponse.equivalents?.carMiles || "Data unavailable",
                showerMinutes: parsedResponse.equivalents?.showerMinutes || "Data unavailable"
            }
        };

        return validatedResponse;
    } catch (error) {
        console.error('Impact calculation error:', error);
        throw new Error('Unable to calculate environmental impact. Please try again.');
    }
}

// Find Nearest Food Share Locations
async function findNearestFoodShares(location, radius = 5) {
    if (!location || typeof location !== 'string') {
        throw new Error('Invalid location parameter. Must provide a non-empty string.');
    }

    if (typeof radius !== 'number' || radius <= 0) {
        radius = 5; // Default to 5 miles if invalid radius provided
    }

    try {
        const systemPrompt = `You are a location specialist for ShareFoods. Find the nearest food sharing opportunities near:
        Location: ${location}
        Radius: ${radius} miles
        
        Format your response as JSON with this structure:
        {
          "location": "${location}",
          "radius": ${radius},
          "results": [
            {
              "name": "Location name",
              "address": "Full address",
              "distance": "X miles",
              "availableItems": ["item 1", "item 2"],
              "hours": "Opening hours information"
            }
          ]
        }`;
        
        const response = await invokeAIAgent(systemPrompt, 'Find food shares.');
        const parsedResponse = JSON.parse(response);
        
        // Validate response structure
        if (!parsedResponse.location || !Array.isArray(parsedResponse.results)) {
            throw new Error('Invalid response format from AI agent');
        }

        return parsedResponse;
    } catch (error) {
        console.error('Find food shares error:', error);
        throw new Error('Unable to find nearby food sharing locations. Please try again.');
    }
}

// Validation rules
const VALIDATION_RULES = {
    food: {
        minLength: 2,
        maxLength: 100,
        pattern: /^[a-zA-Z0-9\s\-,]+$/
    },
    quantity: {
        min: 0.1,
        max: 1000000
    },
    location: {
        minLength: 3,
        maxLength: 200,
        pattern: /^[a-zA-Z0-9\s\-,\.]+$/
    },
    radius: {
        min: 0.1,
        max: 100
    }
};

// Enhanced validation functions
function validateInput(value, type, fieldName) {
    if (value === undefined || value === null) {
        throw new Error(`${fieldName} is required`);
    }

    switch (type) {
        case 'string':
            if (typeof value !== 'string' || !value.trim()) {
                throw new Error(`${fieldName} must be a non-empty string`);
            }
            if (VALIDATION_RULES[fieldName.toLowerCase()]) {
                const rules = VALIDATION_RULES[fieldName.toLowerCase()];
                if (value.length < rules.minLength || value.length > rules.maxLength) {
                    throw new Error(`${fieldName} must be between ${rules.minLength} and ${rules.maxLength} characters`);
                }
                if (rules.pattern && !rules.pattern.test(value)) {
                    throw new Error(`${fieldName} contains invalid characters`);
                }
            }
            break;

        case 'number':
            if (typeof value !== 'number' || isNaN(value)) {
                throw new Error(`${fieldName} must be a valid number`);
            }
            if (VALIDATION_RULES[fieldName.toLowerCase()]) {
                const rules = VALIDATION_RULES[fieldName.toLowerCase()];
                if (value < rules.min || value > rules.max) {
                    throw new Error(`${fieldName} must be between ${rules.min} and ${rules.max}`);
                }
            }
            break;

        case 'array':
            if (!Array.isArray(value) || value.length === 0) {
                throw new Error(`${fieldName} must be a non-empty array`);
            }
            break;
    }
    return true;
}

// Update the invokeAIAgent function to use DeepSeek
async function invokeAIAgent(systemPrompt, userPrompt, options = {}) {
    const {
        retries = getApiConfig().DEEPSEEK.MAX_RETRIES,
        timeout = getApiConfig().DEEPSEEK.TIMEOUT,
        clientId = 'default',
        backoffMultiplier = 2
    } = options;

    await checkRateLimit(clientId);

    return circuitBreaker.executeRequest(async () => {
        let lastError = null;
        for (let i = 0; i < retries; i++) {
            try {
                const messages = [
                    { role: 'system', content: systemPrompt },
                    { role: 'user', content: userPrompt }
                ];

                const response = await deepseekClient.chat(messages, {
                    temperature: 0.7,
                    max_tokens: 1000
                });

                // Handle the response properly - DeepSeek API returns content directly
                let content;
                if (response.choices && response.choices[0] && response.choices[0].message) {
                    content = response.choices[0].message.content;
                } else if (typeof response === 'string') {
                    content = response;
                } else {
                    throw new Error('Unexpected response format from DeepSeek API');
                }

                // Try to parse as JSON, if it fails, return as text
                try {
                    const result = JSON.parse(content);
                    validateResponse(result);
                    return result;
                } catch (parseError) {
                    // If not JSON, return as text content
                    return { content: content, type: 'text' };
                }
            } catch (error) {
                lastError = error;
                console.error(`DeepSeek API error (attempt ${i + 1}/${retries}):`, error);
                if (i < retries - 1) {
                    await new Promise(resolve => setTimeout(resolve, timeout * Math.pow(backoffMultiplier, i)));
                }
            }
        }

        // Fallback to mock responses if API fails after all retries
        const isAuthError = lastError && (
            lastError.message.includes('401') || 
            lastError.message.includes('Unauthorized') ||
            lastError.message.includes('Authentication')
        );
        
        if (isAuthError) {
            console.warn('🔄 API authentication failed, falling back to mock response:', lastError.message);
            return generateMockResponse(systemPrompt, userPrompt);
        } else if (getApiConfig().isValid) {
            throw lastError; // If API key is valid but request failed for other reasons
        } else {
            console.warn('🔄 Falling back to mock response due to missing API key');
            return generateMockResponse(systemPrompt, userPrompt);
        }
    });
}

// Enhanced mock response generator
function generateMockResponse(systemPrompt, userPrompt) {
    const promptLower = userPrompt.toLowerCase();
    const systemLower = systemPrompt.toLowerCase();

    if (promptLower.includes('recipe') || systemLower.includes('suggest recipes')) {
        return {
            recipes: [
                {
                    name: "Vegetable Stir Fry",
                    ingredients: ["2 carrots", "1 bell pepper", "broccoli"],
                    instructions: "1. Heat oil...",
                    prepTime: "10 minutes",
                    cookTime: "8 minutes",
                    difficulty: "Easy",
                    servings: 2,
                    nutritionalInfo: {
                        calories: 250,
                        protein: "8g",
                        carbs: "25g",
                        fat: "12g"
                    },
                    tips: ["Cut vegetables uniformly", "Don't overcook"],
                    variations: ["Add tofu", "Use different vegetables"]
                },
                {
                    name: "Quick Pasta Primavera",
                    ingredients: ["pasta", "mixed vegetables", "olive oil"],
                    instructions: "1. Boil pasta...",
                    prepTime: "15 minutes",
                    cookTime: "12 minutes",
                    difficulty: "Easy",
                    servings: 4,
                    nutritionalInfo: {
                        calories: 350,
                        protein: "10g",
                        carbs: "45g",
                        fat: "15g"
                    },
                    tips: ["Reserve pasta water", "Don't overcook vegetables"],
                    variations: ["Use whole grain pasta", "Add cream sauce"]
                }
            ],
            metadata: {
                generatedAt: new Date().toISOString(),
                difficulty: "beginner-friendly",
                totalTime: "25-30 minutes",
                cuisine: "fusion"
            }
        };
    } else if (promptLower.includes('storage')) {
        return {
            food: "Leafy Greens",
            tips: [
                "Wash and dry thoroughly",
                "Store in airtight container",
                "Add paper towel to absorb moisture",
                "Keep away from ethylene-producing fruits"
            ],
            shelfLife: {
                refrigerator: "5-7 days",
                freezer: "Not recommended",
                roomTemperature: "A few hours"
            },
            signs_of_spoilage: [
                "Wilting leaves",
                "Yellow or brown spots",
                "Slimy texture",
                "Off odor"
            ],
            optimal_conditions: {
                temperature: "32-40°F (0-4°C)",
                humidity: "90-95%",
                container: "Plastic bag with holes or container",
                location: "Crisper drawer"
            }
        };
    } else if (promptLower.includes('impact')) {
        return {
            foodType: "Mixed Vegetables",
            quantity: 5,
            unit: "kg",
            waterSaved: "2500 liters",
            co2Prevented: "7.5 kg",
            landSaved: "10 sq meters",
            equivalents: {
                carMiles: "18.5 miles of driving",
                showerMinutes: "25 minutes of showering",
                lightBulbHours: "120 hours of LED light",
                treeDays: "2.5 days of tree absorption"
            },
            additionalImpact: {
                biodiversityPreserved: "2 sq meters",
                pesticideReduced: "0.5 kg",
                soilPreserved: "15 kg"
            }
        };
    } else {
        return {
            message: "I'm Nourish, your food sharing assistant.",
            suggestions: [
                "Ask about recipes",
                "Get storage tips",
                "Calculate environmental impact",
                "Find food sharing opportunities"
            ],
            capabilities: [
                "Recipe suggestions",
                "Storage advice",
                "Impact calculations",
                "Food pairing recommendations"
            ]
        };
    }
}

// Response validation
function validateResponse(response) {
    if (!response || typeof response !== 'object') {
        throw new Error('Invalid response format');
    }

    if (response.recipes) {
        validateRecipeResponse(response);
    } else if (response.food) {
        validateStorageResponse(response);
    } else if (response.foodType) {
        validateImpactResponse(response);
    }
}

function validateRecipeResponse(response) {
    if (!Array.isArray(response.recipes)) {
        throw new Error('Invalid recipe format');
    }
    response.recipes.forEach(recipe => {
        if (!recipe.name || !recipe.ingredients || !recipe.instructions) {
            throw new Error('Invalid recipe data structure');
        }
    });
}

function validateStorageResponse(response) {
    if (!response.tips || !Array.isArray(response.tips)) {
        throw new Error('Invalid storage tips format');
    }
    if (!response.shelfLife || typeof response.shelfLife !== 'object') {
        throw new Error('Invalid shelf life format');
    }
}

function validateImpactResponse(response) {
    if (!response.waterSaved || !response.co2Prevented) {
        throw new Error('Invalid impact calculation format');
    }
    if (!response.equivalents || typeof response.equivalents !== 'object') {
        throw new Error('Invalid equivalents format');
    }
}

export {
    invokeAIAgent,
    chatWithNourish,
    getRecipeSuggestions,
    getFoodPairings,
    getStorageTips,
    calculateEnvironmentalImpact,
    findNearestFoodShares
};
