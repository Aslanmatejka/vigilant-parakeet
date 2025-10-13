import MatchingEngine from '../utils/MatchingEngine';
import { jest } from '@jest/globals';

describe('MatchingEngine', () => {
    let matchingEngine;
    let mockAIModel;

    beforeEach(() => {
        // Mock AI model
        mockAIModel = {
            classifyUrgency: jest.fn().mockResolvedValue('normal'),
            estimateValue: jest.fn().mockResolvedValue(5),
            learnFromOutcome: jest.fn().mockResolvedValue(true)
        };
        matchingEngine = new MatchingEngine(mockAIModel);
    });

    describe('Location Matching', () => {
        test('should calculate correct distance between two points', () => {
            const point1 = { lat: 40.7128, lon: -74.0060 }; // New York
            const point2 = { lat: 34.0522, lon: -118.2437 }; // Los Angeles
            const distance = matchingEngine.calculateDistance(point1, point2);
            expect(distance).toBeCloseTo(3935.75, 2); // ~3935.75 km
        });

        test('should give higher score for closer locations', async () => {
            const offer = {
                location: { lat: 40.7128, lon: -74.0060 },
                zoneType: 'urban'
            };
            const request1 = {
                location: { lat: 40.7589, lon: -73.9851 }, // ~5km away
                zoneType: 'urban'
            };
            const request2 = {
                location: { lat: 34.0522, lon: -118.2437 }, // ~3935km away
                zoneType: 'urban'
            };

            const score1 = await matchingEngine.evaluateLocationMatch(offer, request1);
            const score2 = await matchingEngine.evaluateLocationMatch(offer, request2);
            expect(score1).toBeGreaterThan(score2);
        });
    });

    describe('Urgency Matching', () => {
        test('should prioritize critical needs', async () => {
            const offer = { urgency: 'normal' };
            const request1 = { urgency: 'critical', needByDate: new Date() };
            const request2 = { urgency: 'optional', needByDate: new Date() };

            const score1 = await matchingEngine.evaluateUrgencyMatch(offer, request1);
            const score2 = await matchingEngine.evaluateUrgencyMatch(offer, request2);
            expect(score1).toBeGreaterThan(score2);
        });

        test('should use AI to classify urgency when not specified', async () => {
            const offer = {};
            const request = { 
                description: 'Need food immediately',
                needByDate: new Date()
            };

            await matchingEngine.evaluateUrgencyMatch(offer, request);
            expect(mockAIModel.classifyUrgency).toHaveBeenCalledWith(request.description);
        });
    });

    describe('Value Matching', () => {
        test('should match items of similar value', async () => {
            const offer = { estimatedValue: 50 };
            const request1 = { estimatedValue: 55 };
            const request2 = { estimatedValue: 100 };

            const score1 = await matchingEngine.evaluateValueMatch(offer, request1);
            const score2 = await matchingEngine.evaluateValueMatch(offer, request2);
            expect(score1).toBeGreaterThan(score2);
        });

        test('should use AI to estimate value when not specified', async () => {
            const offer = { type: 'food', description: 'Fresh vegetables' };
            const request = { type: 'food', description: 'Canned goods' };

            await matchingEngine.evaluateValueMatch(offer, request);
            expect(mockAIModel.estimateValue).toHaveBeenCalledTimes(2);
        });
    });

    describe('Trust Matching', () => {
        test('should prefer users with higher trust scores', async () => {
            const user1 = { id: 1, rating: 4.5 };
            const user2 = { id: 2, rating: 2.5 };

            matchingEngine.trustScores.set(1, 9);
            matchingEngine.trustScores.set(2, 5);

            const score1 = await matchingEngine.evaluateTrustMatch(user1, user1);
            const score2 = await matchingEngine.evaluateTrustMatch(user2, user2);
            expect(score1).toBeGreaterThan(score2);
        });
    });


    describe('Match Learning', () => {
        test('should record and learn from match outcomes', async () => {
            const match = {
                id: 'match1',
                offer: { id: 1, type: 'food' },
                request: { id: 2, type: 'food' },
                scores: {
                    total: 0.85,
                    location: 0.9,
                    urgency: 0.8,
                    value: 0.85,
                    trust: 0.85
                }
            };

            const outcome = {
                success: true,
                rating: 5,
                feedback: 'Great trade!'
            };

            await matchingEngine.recordMatchOutcome(match, outcome);
            expect(mockAIModel.learnFromOutcome).toHaveBeenCalledWith(match, outcome);
            expect(matchingEngine.matchHistory.has('match1')).toBe(true);
        });
    });

    describe('Integration Tests', () => {
        test('should find and rank matches correctly', async () => {
            const request = {
                type: 'food',
                description: 'Fresh vegetables',
                location: { lat: 40.7128, lon: -74.0060 },
                value: 50,
                urgency: 'high',
                user: { id: 1, rating: 4.5 }
            };

            const availableOffers = [
                {
                    id: 1,
                    type: 'food',
                    description: 'Fresh fruits',
                    location: { lat: 40.7589, lon: -73.9851 },
                    value: 55,
                    urgency: 'normal',
                    user: { id: 2, rating: 4.8 }
                },
                {
                    id: 2,
                    type: 'food',
                    description: 'Canned goods',
                    location: { lat: 34.0522, lon: -118.2437 },
                    value: 45,
                    urgency: 'low',
                    user: { id: 3, rating: 3.5 }
                }
            ];

            const matches = await matchingEngine.findMatches(request, availableOffers);
            expect(matches.length).toBe(2);
            expect(matches[0].scores.total).toBeGreaterThan(matches[1].scores.total);
        });
    });
}); 