// In the initDatabase function, update the default listings:

// Inside initDatabase function, update the defaultListings array:
const defaultListings = [
    {
        title: 'Fresh Organic Vegetables',
        description: 'Assorted organic vegetables from local farm',
        image: 'https://images.unsplash.com/photo-1566385101042-1a0aa0c1268c?ixlib=rb-1.2.1&auto=format&fit=crop&w=800&q=60',
        quantity: 5,
        unit: 'kg',
        expiryDate: '2024-02-20',
        location: 'Brooklyn, NY',
        category: 'produce',
        type: 'donation',
        status: 'active',
        userId: 2,
        createdAt: new Date().toISOString()
    },
    {
        title: 'Fresh Herbs',
        description: 'Organic fresh herbs from my garden',
        image: 'https://images.unsplash.com/photo-1600231915619-bcfb0bd75ad6?ixlib=rb-1.2.1&auto=format&fit=crop&w=800&q=60',
        quantity: 2,
        unit: 'bunches',
        expiryDate: '2024-02-18',
        location: 'Manhattan, NY',
        category: 'produce',
        status: 'active',
        userId: 2,
        createdAt: new Date().toISOString()
    },
    {
        title: 'Homemade Sourdough',
        description: 'Freshly baked sourdough bread',
        image: 'https://images.unsplash.com/photo-1586444248902-2f64eddc13df?ixlib=rb-1.2.1&auto=format&fit=crop&w=800&q=60',
        quantity: 2,
        unit: 'loaves',
        expiryDate: '2024-02-19',
        location: 'Queens, NY',
        category: 'bakery',
        type: 'trade',
        status: 'active',
        userId: 1,
        createdAt: new Date().toISOString()
    }
];
