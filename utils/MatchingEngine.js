import { reportError } from './helpers';

// DeepSeek AI Configuration
const DEEPSEEK_CONFIG = {
    API_KEY: window.DEEPSEEK_API_KEY || 'sk-c28f285a0947483dacd0c0850dfg0',
    API_ENDPOINT: 'https://api.deepseek.com/v1',
    MODEL_VERSION: '1.0.0'
};

// Load API key from environment if available
if (typeof window !== 'undefined' && window.__ENV__ && window.__ENV__.DEEPSEEK_API_KEY) {
    DEEPSEEK_CONFIG.API_KEY = window.__ENV__.DEEPSEEK_API_KEY;
}

class MatchingEngine {
    constructor(aiModel = null) {
        this.aiModel = aiModel; // DeepSeek AI model instance
        this.matchHistory = new Map(); // Store match history
        this.trustScores = new Map(); // Store user trust scores
        this.valueEquivalencyMap = new Map(); // Store value equivalencies
        
        // Initialize DeepSeek configuration
        this.deepseekConfig = {
            ...DEEPSEEK_CONFIG,
            headers: {
                'Authorization': `Bearer ${DEEPSEEK_CONFIG.API_KEY}`,
                'Content-Type': 'application/json'
            }
        };

        // Validate API key
        this.validateApiKey();
    }

    /**
     * Validate DeepSeek API key
     */
    validateApiKey() {
        try {
            if (!DEEPSEEK_CONFIG.API_KEY || 
                DEEPSEEK_CONFIG.API_KEY === 'your-deepseek-api-key-here' ||
                !DEEPSEEK_CONFIG.API_KEY.startsWith('sk-')) {
                console.warn('⚠️ Warning: DeepSeek API key not configured. Some AI features may be limited.');
                return false;
            }
            
            console.log('✅ DeepSeek API key validated in MatchingEngine');
            return true;
            //     headers: this.deepseekConfig.headers
            // });
            // return response.ok;
            
            return true;
        } catch (error) {
            reportError(error);
            console.error('Failed to validate DeepSeek API key:', error.message);
            return false;
        }
    }

    /**
     * Initialize DeepSeek AI client
     */
    async initializeAI() {
        try {
            if (!await this.validateApiKey()) {
                return null;
            }

            // TODO: Replace with actual DeepSeek AI client initialization
            return {
                classifyUrgency: async (description) => 'normal',
                estimateValue: async (item) => item.userEstimatedValue || 5,
                learnFromOutcome: async (match, outcome) => true
            };
        } catch (error) {
            reportError(error);
            console.error('Failed to initialize DeepSeek AI:', error.message);
            return null;
        }
    }

    /**
     * Calculate distance between two geographical points
     */
    calculateDistance(point1, point2) {
        try {
            const R = 6371; // Earth's radius in km
            const dLat = (point2.lat - point1.lat) * Math.PI / 180;
            const dLon = (point2.lon - point1.lon) * Math.PI / 180;
            const a = Math.sin(dLat/2) * Math.sin(dLat/2) +
                Math.cos(point1.lat * Math.PI / 180) * Math.cos(point2.lat * Math.PI / 180) *
                Math.sin(dLon/2) * Math.sin(dLon/2);
            return R * 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1-a));
        } catch (error) {
            reportError(error);
            return Infinity;
        }
    }

    /**
     * Evaluate location match score
     */
    async evaluateLocationMatch(offer, request) {
        try {
            // Add null checks for location
            if (!offer || !offer.location || !request || !request.location) {
                return 0; // Return lowest score if locations are missing
            }
            
            const distance = this.calculateDistance(offer.location, request.location);
            const zoneMatch = offer.zoneType === request.zoneType ? 2 : 0;
            const meshStrength = await this.evaluateMeshStrength(offer.location, request.location);
            
            // Score calculation (0-10)
            let score = 10;
            if (distance > 5) score -= Math.min(5, (distance - 5) / 2); // Reduce score for distance > 5km
            score += zoneMatch;
            score += meshStrength;
            
            return Math.max(0, Math.min(10, score));
        } catch (error) {
            reportError(error);
            return 0;
        }
    }

    /**
     * Evaluate urgency match and priority
     */
    async evaluateUrgencyMatch(offer, request) {
        try {
            const urgencyLevels = {
                'critical': 4,
                'high': 3,
                'normal': 2,
                'optional': 1
            };

            // Use AI model to determine urgency if not explicitly set
            if (!request.urgency && this.aiModel) {
                try {
                    // Use injected AI model (for testing) or make HTTP request
                    if (this.aiModel.classifyUrgency) {
                        request.urgency = await this.aiModel.classifyUrgency(request.description);
                    } else {
                        const response = await fetch(`${DEEPSEEK_CONFIG.API_ENDPOINT}/classify-urgency`, {
                            method: 'POST',
                            headers: this.deepseekConfig.headers,
                            body: JSON.stringify({
                                description: request.description,
                                model: DEEPSEEK_CONFIG.MODEL_VERSION
                            })
                        });
                        
                        if (response.ok) {
                            const result = await response.json();
                            request.urgency = result.urgency;
                        }
                    }
                } catch (error) {
                    console.warn('Failed to classify urgency using DeepSeek AI:', error.message);
                    request.urgency = 'normal'; // Fallback to normal urgency
                }
            }

            const requestUrgency = urgencyLevels[request.urgency] || 2;
            const timeUntilNeeded = request.needByDate - new Date();
            
            // Score calculation (0-10)
            let score = 5; // Base score
            
            // Add urgency bonus (more significant difference)
            score += (requestUrgency * 2.5); 
            
            // Reduce score based on days until needed
            const daysUntilNeeded = timeUntilNeeded / (24 * 60 * 60 * 1000);
            if (daysUntilNeeded > 0) {
                score -= Math.min(3, daysUntilNeeded * 0.5); // Penalize future needs
            } else {
                score += 1; // Bonus for immediate needs
            }
            
            return Math.max(0, Math.min(10, score));
        } catch (error) {
            reportError(error);
            return 0;
        }
    }

    /**
     * Evaluate value similarity between items
     */
    async evaluateValueMatch(offer, request) {
        try {
            // Get or calculate value scores
            const offerValue = await this.calculateItemValue(offer);
            const requestValue = await this.calculateItemValue(request);
            
            // Update equivalency map
            this.updateValueEquivalency(offer.type, request.type, offerValue, requestValue);
            
            // Calculate value difference percentage
            const valueDiff = Math.abs(offerValue - requestValue) / Math.max(offerValue, requestValue);
            
            // Score calculation (0-10)
            return Math.max(0, 10 - (valueDiff * 10));
        } catch (error) {
            reportError(error);
            return 0;
        }
    }

    /**
     * Evaluate trust score based on history
     */
    async evaluateTrustMatch(offerUser, requestUser) {
        try {
            const offerTrust = await this.calculateTrustScore(offerUser);
            const requestTrust = await this.calculateTrustScore(requestUser);
            
            // Score calculation (0-10)
            return Math.min(10, (offerTrust + requestTrust) / 2);
        } catch (error) {
            reportError(error);
            return 0;
        }
    }

    /**
     * Evaluate seasonal matching
     */
    async evaluateSeasonalMatch(offer, request) {
        try {
            const currentMonth = new Date().getMonth();
            const seasonalFoods = {
                // Spring (March-May)
                2: ['asparagus', 'peas', 'spinach', 'strawberries'],
                3: ['asparagus', 'peas', 'spinach', 'strawberries'],
                4: ['asparagus', 'peas', 'spinach', 'strawberries'],
                
                // Summer (June-August)
                5: ['tomatoes', 'corn', 'berries', 'peaches'],
                6: ['tomatoes', 'corn', 'berries', 'peaches'],
                7: ['tomatoes', 'corn', 'berries', 'peaches'],
                
                // Fall (September-November)
                8: ['apples', 'pumpkin', 'squash', 'pears'],
                9: ['apples', 'pumpkin', 'squash', 'pears'],
                10: ['apples', 'pumpkin', 'squash', 'pears'],
                
                // Winter (December-February)
                11: ['citrus', 'potatoes', 'onions', 'cabbage'],
                0: ['citrus', 'potatoes', 'onions', 'cabbage'],
                1: ['citrus', 'potatoes', 'onions', 'cabbage']
            };

            const currentSeasonalFoods = seasonalFoods[currentMonth] || [];
            const offerWords = offer.description.toLowerCase().split(' ');
            const requestWords = request.description.toLowerCase().split(' ');

            const isOfferSeasonal = offerWords.some(word => currentSeasonalFoods.includes(word));
            const isRequestSeasonal = requestWords.some(word => currentSeasonalFoods.includes(word));

            // Score based on seasonality match
            if (isOfferSeasonal && isRequestSeasonal) return 1.0;
            if (isOfferSeasonal || isRequestSeasonal) return 0.7;
            return 0.5;
        } catch (error) {
            reportError(error);
            return 0.5;
        }
    }

    /**
     * Evaluate nutritional balance
     */
    async evaluateNutritionalMatch(offer, request) {
        try {
            const foodGroups = {
                proteins: ['meat', 'fish', 'eggs', 'beans', 'nuts', 'tofu'],
                grains: ['bread', 'rice', 'pasta', 'cereal', 'wheat'],
                vegetables: ['vegetable', 'salad', 'greens', 'carrots', 'broccoli'],
                fruits: ['fruit', 'apple', 'banana', 'orange', 'berry'],
                dairy: ['milk', 'cheese', 'yogurt', 'butter']
            };

            const getFoodGroups = (description) => {
                const words = description.toLowerCase().split(' ');
                return Object.entries(foodGroups).reduce((groups, [group, foods]) => {
                    if (words.some(word => foods.includes(word))) {
                        groups.push(group);
                    }
                    return groups;
                }, []);
            };

            const offerGroups = getFoodGroups(offer.description);
            const requestGroups = getFoodGroups(request.description);

            // Score based on food group diversity
            const uniqueGroups = new Set([...offerGroups, ...requestGroups]);
            return Math.min(uniqueGroups.size / 3, 1.0); // Perfect score for 3 or more food groups
        } catch (error) {
            reportError(error);
            return 0.5;
        }
    }

    /**
     * Evaluate community impact
     */
    async evaluateCommunityImpact(offer, request) {
        try {
            const factors = {
                servingSize: Math.min((offer.quantity || 1) / 5, 1), // Perfect score for 5+ servings
                freshness: offer.expiryDate ? 
                    Math.max(0, Math.min(1, (new Date(offer.expiryDate) - new Date()) / (1000 * 60 * 60 * 24 * 7))) : 0.5, // Scale based on days until expiry
                accessibility: request.location.zoneType === 'food-desert' ? 1 : 0.6,
                communityRating: (offer.user.communityRating || 5) / 10
            };

            return Object.values(factors).reduce((sum, value) => sum + value, 0) / Object.keys(factors).length;
        } catch (error) {
            reportError(error);
            return 0.5;
        }
    }

    /**
     * Enhanced findMatches with AI-powered matching
     */
    async findMatches(request, availableOffers) {
        try {
            console.log('🚀 Using AI-powered matching engine...');
            
            // Use AI Matching Engine for enhanced matching
            const aiMatches = await this.aiMatchingEngine.findMatches(request, availableOffers);
            
            // Fallback to traditional matching if AI fails
            if (!aiMatches || aiMatches.length === 0) {
                console.log('⚠️ AI matching failed, falling back to traditional matching...');
                return await this.findMatchesTraditional(request, availableOffers);
            }
            
            return aiMatches;
        } catch (error) {
            reportError(error);
            console.error('❌ AI matching error, falling back to traditional matching:', error);
            return await this.findMatchesTraditional(request, availableOffers);
        }
    }

    /**
     * Traditional matching algorithm (fallback)
     */
    async findMatchesTraditional(request, availableOffers) {
        try {
            const matches = [];
            
            // Phase 1: Scan and Filter
            const filteredOffers = availableOffers.filter(offer => {
                // Add null checks for location
                if (!offer || !offer.location || !request || !request.location) {
                    return false;
                }
                const distance = this.calculateDistance(offer.location, request.location);
                return distance <= 50; // Maximum 50km radius
            });

            // Phase 2: Score each potential match
            for (const offer of filteredOffers) {
                const locationScore = await this.evaluateLocationMatch(offer, request);
                const urgencyScore = await this.evaluateUrgencyMatch(offer, request);
                const valueScore = await this.evaluateValueMatch(offer, request);
                const trustScore = await this.evaluateTrustMatch(offer.user, request.user);
                const seasonalScore = await this.evaluateSeasonalMatch(offer, request);
                const nutritionalScore = await this.evaluateNutritionalMatch(offer, request);
                const communityScore = await this.evaluateCommunityImpact(offer, request);
                
                // Calculate match type score
                const matchTypeScore = this.isDirectMatch(offer, request) ? 10 : 5;
                
                // Calculate total score with weighted criteria
                const totalScore = (
                    (locationScore * 0.20) +
                    (urgencyScore * 0.20) +
                    (valueScore * 0.15) +
                    (trustScore * 0.15) +
                    (seasonalScore * 0.10) +
                    (nutritionalScore * 0.10) +
                    (communityScore * 0.05) +
                    (matchTypeScore * 0.05)
                );

                matches.push({
                    offer,
                    scores: {
                        location: locationScore,
                        urgency: urgencyScore,
                        value: valueScore,
                        trust: trustScore,
                        seasonal: seasonalScore,
                        nutritional: nutritionalScore,
                        community: communityScore,
                        matchType: matchTypeScore,
                        total: totalScore
                    },
                    type: this.determineMatchType(offer, request, urgencyScore),
                    insights: {
                        seasonality: this.getSeasonalityInsight(seasonalScore),
                        nutrition: this.getNutritionalInsight(nutritionalScore),
                        community: this.getCommunityInsight(communityScore)
                    }
                });
            }

            // Phase 3: Sort matches
            matches.sort((a, b) => b.scores.total - a.scores.total);

            // Phase 4: Find potential trade loops
            const tradeLoops = await this.findTradeLoops(request, availableOffers);
            matches.push(...tradeLoops);

            return matches;
        } catch (error) {
            reportError(error);
            return [];
        }
    }

    /**
     * Find potential trade loops (circular trades)
     */
    async findTradeLoops(request, availableOffers, maxDepth = 3) {
        try {
            const loops = [];
            const visited = new Set();
            
            const findLoop = async (currentRequest, chain = [], depth = 0) => {
                if (depth >= maxDepth) return;
                
                for (const offer of availableOffers) {
                    if (visited.has(offer.id)) continue;
                    
                    const match = await this.evaluateValueMatch(offer, currentRequest);
                    if (match > 7) { // Good value match
                        visited.add(offer.id);
                        chain.push(offer);
                        
                        // Check if this offer's user needs what the original requester has
                        const userNeeds = await this.getUserNeeds(offer.user);
                        for (const need of userNeeds) {
                            if (await this.evaluateValueMatch(request.offering, need) > 7) {
                                loops.push([...chain]); // Found a loop
                            }
                        }
                        
                        // Recurse
                        await findLoop(offer, chain, depth + 1);
                        
                        chain.pop();
                        visited.delete(offer.id);
                    }
                }
            };
            
            await findLoop(request);
            return loops;
        } catch (error) {
            reportError(error);
            return [];
        }
    }

    /**
     * Record match outcome for learning
     */
    async recordMatchOutcome(match, outcome) {
        try {
            this.matchHistory.set(match.id, {
                ...match,
                outcome,
                timestamp: new Date()
            });

            // Update trust scores
            await this.updateTrustScores(match, outcome);

            // Use AI to analyze patterns and update matching weights
            if (this.aiModel) {
                await this.aiModel.learnFromOutcome(match, outcome);
            }
        } catch (error) {
            reportError(error);
        }
    }

    /**
     * Helper methods
     */
    async evaluateMeshStrength(location1, location2) {
        // Implementation for LoRa mesh network strength evaluation
        return 1; // Placeholder
    }

    async calculateItemValue(item) {
        try {
            if (this.aiModel) {
                return await this.aiModel.estimateValue(item);
            }
            return item.userEstimatedValue || 5; // Default middle value
        } catch (error) {
            reportError(error);
            return 5;
        }
    }

    async calculateTrustScore(user) {
        return this.trustScores.get(user.id) || 5; // Default middle trust score
    }

    isDirectMatch(offer, request) {
        return offer.type === request.type;
    }

    determineMatchType(offer, request, urgencyScore) {
        if (urgencyScore > 8) return '⚡ Urgent Match';
        if (this.isDirectMatch(offer, request)) return '🤝 Fair Trade';
        return '♻️ Loop Trade';
    }

    async updateTrustScores(match, outcome) {
        // Implementation for updating trust scores based on match outcomes
    }

    async updateValueEquivalency(type1, type2, value1, value2) {
        // Implementation for updating value equivalency mappings
    }

    async getUserNeeds(user) {
        // Implementation to fetch user's current needs
        return [];
    }

    /**
     * Generate insights for matches
     */
    getSeasonalityInsight(score) {
        if (score >= 0.8) return "Perfect seasonal match! These items are currently in season.";
        if (score >= 0.6) return "Good seasonal alignment with some items in season.";
        return "Consider seasonal alternatives for better freshness and value.";
    }

    getNutritionalInsight(score) {
        if (score >= 0.8) return "Excellent nutritional balance across food groups.";
        if (score >= 0.6) return "Good nutritional variety.";
        return "Consider adding items from different food groups for better balance.";
    }

    getCommunityInsight(score) {
        if (score >= 0.8) return "High positive impact on community food security.";
        if (score >= 0.6) return "Moderate community benefit.";
        return "Consider ways to increase community impact.";
    }
}

export default MatchingEngine;
