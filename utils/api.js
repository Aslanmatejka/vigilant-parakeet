// User API
function getCurrentUser() {
    try {
        // In a real app, this would be a fetch to your backend
        // For demo purposes, we'll return mock data
        return {
            objectId: 'user1',
            name: 'Demo User',
            email: 'demo@example.com',
        };
    } catch (error) {
        console.error('Get current user error:', error);
        throw new Error('Unable to fetch current user');
    }
}

function getFoodListings(filters) {
    try {
        // In a real app, this would be a fetch to your backend
        // For demo purposes, we'll return mock data
        const mockListings = Array(6).fill(null).map((_, i) => ({
            objectId: `listing-${i+1}`,
            title: `Food Listing ${i+1}`,
            description: 'Food description goes here.',
            image: `https://images.unsplash.com/photo-${1566385101042+i}?ixlib=rb-1.2.1&auto=format&fit=crop&w=800&q=60`,
            quantity: Math.floor(Math.random() * 10) + 1,
            unit: 'kg',
            expiryDate: '2024-01-20',
            location: 'Brooklyn, NY',
            category: i % 2 === 0 ? 'produce' : 'bakery',
            type: i % 3 === 0 ? 'trade' : 'donation',
            status: i % 4 === 0 ? 'completed' : 'available',
            createdAt: '2024-01-01T12:00:00Z',
            donor: {
                name: 'User Name',
                avatar: `https://randomuser.me/api/portraits/${i % 2 === 0 ? 'men' : 'women'}/${i+1}.jpg`
            }
        }));
        
        return {
            items: mockListings,
            nextPageToken: null
        };
    } catch (error) {
        console.error('Get food listings error:', error);
        throw new Error('Unable to fetch food listings');
    }
}

function getFoodListing(id) {
    try {
        // In a real app, this would be a fetch to your backend
        // For demo purposes, we'll return mock data
        return {
            objectId: id,
            title: 'Fresh Organic Vegetables',
            description: 'Surplus vegetables from our local farm.',
            image: 'https://images.unsplash.com/photo-1566385101042-1a0aa0c1268c?ixlib=rb-1.2.1&auto=format&fit=crop&w=800&q=60',
            quantity: 5,
            unit: 'kg',
            expiryDate: '2024-01-20',
            location: 'Brooklyn, NY',
            category: 'produce',
            type: 'donation',
            createdAt: '2024-01-01T12:00:00Z',
            donor: {
                name: 'Green Farm Co-op',
                avatar: 'https://randomuser.me/api/portraits/men/1.jpg'
            }
        };
    } catch (error) {
        console.error('Get food listing error:', error);
        throw new Error('Unable to fetch food listing');
    }
}

function createFoodListing(listingData) {
    try {
        // In a real app, this would be a fetch to your backend
        // For demo purposes, we'll just return the data with an ID
        return {
            ...listingData,
            objectId: `listing-${Date.now()}`,
            createdAt: new Date().toISOString()
        };
    } catch (error) {
        console.error('Create food listing error:', error);
        throw new Error('Unable to create food listing');
    }
}

function updateFoodListing(id, updates) {
    try {
        // In a real app, this would be a fetch to your backend
        // For demo purposes, we'll just return the data
        return {
            ...updates,
            objectId: id,
            updatedAt: new Date().toISOString()
        };
    } catch (error) {
        console.error('Update food listing error:', error);
        throw new Error('Unable to update food listing');
    }
}

function deleteFoodListing(id) {
    try {
        // In a real app, this would be a fetch to your backend
        // For demo purposes, we'll just return success
        return { success: true };
    } catch (error) {
        console.error('Delete food listing error:', error);
        throw new Error('Unable to delete food listing');
    }
}

// Trade API
function getTradeOffers(filters) {
    try {
        // In a real app, this would be a fetch to your backend
        // For demo purposes, we'll return mock data
        const mockTrades = Array(5).fill(null).map((_, i) => ({
            objectId: `trade-${i+1}`,
            offeredItem: {
                title: `Offered Item ${i+1}`,
                quantity: Math.floor(Math.random() * 5) + 1,
                unit: 'kg'
            },
            requestedItem: {
                title: `Requested Item ${i+1}`,
                quantity: Math.floor(Math.random() * 3) + 1,
                unit: 'kg'
            },
            status: ['pending', 'accepted', 'completed'][i % 3],
            createdAt: '2024-01-01T12:00:00Z',
            user: {
                name: `User ${i+1}`,
                avatar: `https://randomuser.me/api/portraits/${i % 2 === 0 ? 'men' : 'women'}/${i+1}.jpg`
            }
        }));
        
        return {
            items: mockTrades,
            nextPageToken: null
        };
    } catch (error) {
        console.error('Get trade offers error:', error);
        throw new Error('Unable to fetch trade offers');
    }
}

function createTradeOffer(offerData) {
    try {
        // In a real app, this would be a fetch to your backend
        // For demo purposes, we'll just return the data with an ID
        return {
            ...offerData,
            objectId: `trade-${Date.now()}`,
            createdAt: new Date().toISOString()
        };
    } catch (error) {
        console.error('Create trade offer error:', error);
        throw new Error('Unable to create trade offer');
    }
}

function respondToTradeOffer(id, response) {
    try {
        // In a real app, this would be a fetch to your backend
        // For demo purposes, we'll just return success
        return { success: true };
    } catch (error) {
        console.error('Respond to trade offer error:', error);
        throw new Error('Unable to respond to trade offer');
    }
}

// AI API
function getRecipeSuggestions(ingredients) {
    try {
        // In a real app, this would be a fetch to your backend
        // For demo purposes, we'll return mock data
        return [
            {
                id: 1,
                title: 'Vegetable Stir Fry',
                ingredients: ['Broccoli', 'Carrot', 'Bell Pepper', 'Soy Sauce'],
                instructions: 'Stir fry vegetables in soy sauce. Serve hot.',
                image: 'https://images.unsplash.com/photo-1581572029623-6c8f3f3f3f3f?ixlib=rb-1.2.1&auto=format&fit=crop&w=800&q=60'
            },
            {
                id: 2,
                title: 'Pasta Primavera',
                ingredients: ['Pasta', 'Zucchini', 'Tomato', 'Olive Oil'],
                instructions: 'Cook pasta. Sauté vegetables. Mix together.',
                image: 'https://images.unsplash.com/photo-1581572029623-6c8f3f3f3f3f?ixlib=rb-1.2.1&auto=format&fit=crop&w=800&q=60'
            }
        ];
    } catch (error) {
        console.error('Get recipe suggestions error:', error);
        throw new Error('Unable to get recipe suggestions');
    }
}

function getStorageTips(foodItem) {
    try {
        // In a real app, this would be a fetch to your backend
        // For demo purposes, we'll return mock data
        return [
            {
                id: 1,
                tip: 'Store in a cool, dry place.',
                image: 'https://images.unsplash.com/photo-1581572029623-6c8f3f3f3f3f?ixlib=rb-1.2.1&auto=format&fit=crop&w=800&q=60'
            },
            {
                id: 2,
                tip: 'Keep away from direct sunlight.',
                image: 'https://images.unsplash.com/photo-1581572029623-6c8f3f3f3f3f?ixlib=rb-1.2.1&auto=format&fit=crop&w=800&q=60'
            }
        ];
    } catch (error) {
        console.error('Get storage tips error:', error);
        throw new Error('Unable to get storage tips');
    }
}

// Dummy updateUserProfile function to avoid export error
function updateUserProfile(profileData) {
    try {
        // In a real app, this would be a fetch to your backend
        // For demo purposes, we'll just return the data
        return {
            ...profileData,
            updatedAt: new Date().toISOString()
        };
    } catch (error) {
        console.error('Update user profile error:', error);
        throw new Error('Unable to update user profile');
    }
}

export const api = {
    getCurrentUser,
    updateUserProfile,
    getFoodListings,
    getFoodListing,
    createFoodListing,
    updateFoodListing,
    deleteFoodListing,
    getRecipeSuggestions,
    getStorageTips
}
