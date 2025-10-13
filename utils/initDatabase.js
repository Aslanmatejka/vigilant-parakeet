import db from './db';

export  async function initializeDatabase() {
    try {
        await db.init();

        // Check if admin user exists
        const users = await db.getAll(db.STORES.users);
        if (users.length === 0) {
            // Add default admin user
            await db.add(db.STORES.users, {
                name: 'Admin User',
                email: 'admin@dogoods.com',
                password: 'admin123', // In real app, this should be hashed
                role: 'admin',
                status: 'active',
                joinDate: new Date().toISOString(),
                avatar: 'https://randomuser.me/api/portraits/men/1.jpg'
            });

            // Add default regular user
            await db.add(db.STORES.users, {
                name: 'John Doe',
                email: 'john@example.com',
                password: 'password123', // In real app, this should be hashed
                role: 'user',
                status: 'active',
                joinDate: new Date().toISOString(),
                avatar: 'https://randomuser.me/api/portraits/men/2.jpg'
            });
        }

        // Check if any food listings exist
        const listings = await db.getAll(db.STORES.listings);
        if (listings.length === 0) {
            // Create demo food listings for each category
            const demoListings = [
                // Produce - Vegetables
                {
                    title: 'Fresh Organic Carrots',
                    description: 'Freshly harvested organic carrots from my garden. No pesticides used.',
                    image: 'https://images.unsplash.com/photo-1598170845058-32b9d6a5da37?ixlib=rb-1.2.1&auto=format&fit=crop&w=800&q=60',
                    quantity: 2,
                    unit: 'kg',
                    expiryDate: addDays(new Date(), 10),
                    location: 'Brooklyn, NY',
                    category: 'produce',
                    type: 'donation',
                    status: 'active',
                    userId: 2,
                    createdAt: new Date().toISOString()
                },
                {
                    title: 'Homegrown Tomatoes',
                    description: 'Ripe, juicy tomatoes from my backyard garden. Perfect for salads or sauces.',
                    image: 'https://images.unsplash.com/photo-1582284540020-8acbe03f4924?ixlib=rb-1.2.1&auto=format&fit=crop&w=800&q=60',
                    quantity: 1.5,
                    unit: 'kg',
                    expiryDate: addDays(new Date(), 5),
                    location: 'Queens, NY',
                    category: 'produce',
                    status: 'active',
                    userId: 2,
                    createdAt: new Date().toISOString()
                },
                {
                    title: 'Fresh Spinach Bunch',
                    description: 'Organic spinach, freshly harvested this morning. Great for salads or cooking.',
                    image: 'https://images.unsplash.com/photo-1576045057995-568f588f82fb?ixlib=rb-1.2.1&auto=format&fit=crop&w=800&q=60',
                    quantity: 0.5,
                    unit: 'kg',
                    expiryDate: addDays(new Date(), 4),
                    location: 'Manhattan, NY',
                    category: 'produce',
                    type: 'donation',
                    status: 'active',
                    userId: 1,
                    createdAt: new Date().toISOString()
                },
                
                // Produce - Fruits
                {
                    title: 'Organic Apples',
                    description: 'Fresh organic apples from local orchard. Sweet and crisp.',
                    image: 'https://images.unsplash.com/photo-1570913149827-d2ac84ab3f9a?ixlib=rb-1.2.1&auto=format&fit=crop&w=800&q=60',
                    quantity: 2,
                    unit: 'kg',
                    expiryDate: addDays(new Date(), 14),
                    location: 'Brooklyn, NY',
                    category: 'produce',
                    type: 'donation',
                    status: 'active',
                    userId: 1,
                    createdAt: new Date().toISOString()
                },
                {
                    title: 'Fresh Berries Mix',
                    description: 'Mix of strawberries, blueberries and raspberries. Freshly picked.',
                    image: 'https://images.unsplash.com/photo-1563746098251-d35aef196e83?ixlib=rb-1.2.1&auto=format&fit=crop&w=800&q=60',
                    quantity: 0.5,
                    unit: 'kg',
                    expiryDate: addDays(new Date(), 3),
                    location: 'Manhattan, NY',
                    category: 'produce',
                    type: 'trade',
                    status: 'active',
                    userId: 2,
                    createdAt: new Date().toISOString()
                },
                {
                    title: 'Organic Bananas',
                    description: 'Bunch of ripe organic bananas. Perfect for smoothies or baking.',
                    image: 'https://images.unsplash.com/photo-1543218024-57a70143c369?ixlib=rb-1.2.1&auto=format&fit=crop&w=800&q=60',
                    quantity: 1,
                    unit: 'kg',
                    expiryDate: addDays(new Date(), 5),
                    location: 'Queens, NY',
                    category: 'produce',
                    type: 'donation',
                    status: 'active',
                    userId: 1,
                    createdAt: new Date().toISOString()
                },
                
                // Bakery
                {
                    title: 'Freshly Baked Sourdough',
                    description: 'Homemade sourdough bread baked this morning. Crusty outside, soft inside.',
                    image: 'https://images.unsplash.com/photo-1586444248902-2f64eddc13df?ixlib=rb-1.2.1&auto=format&fit=crop&w=800&q=60',
                    quantity: 2,
                    unit: 'loaves',
                    expiryDate: addDays(new Date(), 3),
                    location: 'Brooklyn, NY',
                    category: 'bakery',
                    type: 'trade',
                    status: 'active',
                    userId: 2,
                    createdAt: new Date().toISOString()
                },
                {
                    title: 'Homemade Chocolate Chip Cookies',
                    description: 'Batch of homemade cookies made with organic ingredients. Soft and chewy.',
                    image: 'https://images.unsplash.com/photo-1499636136210-6f4ee915583e?ixlib=rb-1.2.1&auto=format&fit=crop&w=800&q=60',
                    quantity: 12,
                    unit: 'cookies',
                    expiryDate: addDays(new Date(), 5),
                    location: 'Queens, NY',
                    category: 'bakery',
                    type: 'donation',
                    status: 'active',
                    userId: 1,
                    createdAt: new Date().toISOString()
                },
                {
                    title: 'Artisan Baguettes',
                    description: 'Freshly baked traditional French baguettes with crispy crust.',
                    image: 'https://images.unsplash.com/photo-1608198093002-ad4e005484ec?ixlib=rb-1.2.1&auto=format&fit=crop&w=800&q=60',
                    quantity: 3,
                    unit: 'baguettes',
                    expiryDate: addDays(new Date(), 2),
                    location: 'Manhattan, NY',
                    category: 'bakery',
                    type: 'donation',
                    status: 'active',
                    userId: 2,
                    createdAt: new Date().toISOString()
                },
                
                // Dairy
                {
                    title: 'Organic Milk',
                    description: 'Fresh organic whole milk from local dairy farm. Glass bottle can be returned.',
                    image: 'https://images.unsplash.com/photo-1563636619-e9143da7973b?ixlib=rb-1.2.1&auto=format&fit=crop&w=800&q=60',
                    quantity: 1,
                    unit: 'liter',
                    expiryDate: addDays(new Date(), 4),
                    location: 'Brooklyn, NY',
                    category: 'dairy',
                    type: 'donation',
                    status: 'active',
                    userId: 1,
                    createdAt: new Date().toISOString()
                },
                {
                    title: 'Homemade Yogurt',
                    description: 'Plain yogurt made from organic milk. No additives or preservatives.',
                    image: 'https://images.unsplash.com/photo-1584278858536-52532423b9ea?ixlib=rb-1.2.1&auto=format&fit=crop&w=800&q=60',
                    quantity: 0.5,
                    unit: 'kg',
                    expiryDate: addDays(new Date(), 5),
                    location: 'Queens, NY',
                    category: 'dairy',
                    type: 'trade',
                    status: 'active',
                    userId: 2,
                    createdAt: new Date().toISOString()
                },
                {
                    title: 'Farm Fresh Eggs',
                    description: 'Free-range eggs from my backyard chickens. Collected this morning.',
                    image: 'https://images.unsplash.com/photo-1506976785307-8732e854ad03?ixlib=rb-1.2.1&auto=format&fit=crop&w=800&q=60',
                    quantity: 12,
                    unit: 'eggs',
                    expiryDate: addDays(new Date(), 14),
                    location: 'Manhattan, NY',
                    category: 'dairy',
                    type: 'donation',
                    status: 'active',
                    userId: 1,
                    createdAt: new Date().toISOString()
                },
                
                // Pantry
                {
                    title: 'Organic Rice',
                    description: 'Unopened bag of organic brown rice. Best before date still months away.',
                    image: 'https://images.unsplash.com/photo-1586201375761-83865001e31c?ixlib=rb-1.2.1&auto=format&fit=crop&w=800&q=60',
                    quantity: 1,
                    unit: 'kg',
                    expiryDate: addDays(new Date(), 180),
                    location: 'Brooklyn, NY',
                    category: 'pantry',
                    type: 'donation',
                    status: 'active',
                    userId: 2,
                    createdAt: new Date().toISOString()
                },
                {
                    title: 'Homemade Pasta Sauce',
                    description: 'Homemade tomato pasta sauce made with garden vegetables. In glass jars.',
                    image: 'https://images.unsplash.com/photo-1592921870583-aeafb0639ffe?ixlib=rb-1.2.1&auto=format&fit=crop&w=800&q=60',
                    quantity: 2,
                    unit: 'jars',
                    expiryDate: addDays(new Date(), 14),
                    location: 'Queens, NY',
                    category: 'pantry',
                    type: 'trade',
                    status: 'active',
                    userId: 1,
                    createdAt: new Date().toISOString()
                },
                {
                    title: 'Organic Honey',
                    description: 'Raw, unfiltered local honey. Great for allergies and as a natural sweetener.',
                    image: 'https://images.unsplash.com/photo-1582359425904-5536e9d6b2dc?ixlib=rb-1.2.1&auto=format&fit=crop&w=800&q=60',
                    quantity: 0.5,
                    unit: 'kg',
                    expiryDate: addDays(new Date(), 365),
                    location: 'Manhattan, NY',
                    category: 'pantry',
                    type: 'donation',
                    status: 'active',
                    userId: 2,
                    createdAt: new Date().toISOString()
                },
                
                // Meat
                {
                    title: 'Organic Chicken Breasts',
                    description: 'Fresh organic chicken breasts. Vacuum sealed and refrigerated.',
                    image: 'https://images.unsplash.com/photo-1604503468506-a8da13d82791?ixlib=rb-1.2.1&auto=format&fit=crop&w=800&q=60',
                    quantity: 1,
                    unit: 'kg',
                    expiryDate: addDays(new Date(), 2),
                    location: 'Brooklyn, NY',
                    category: 'meat',
                    type: 'trade',
                    status: 'active',
                    userId: 1,
                    createdAt: new Date().toISOString()
                },
                {
                    title: 'Grass-Fed Ground Beef',
                    description: 'Locally sourced grass-fed beef. Perfect for burgers or meatballs.',
                    image: 'https://images.unsplash.com/photo-1588168333986-5078d3ae3976?ixlib=rb-1.2.1&auto=format&fit=crop&w=800&q=60',
                    quantity: 0.5,
                    unit: 'kg',
                    expiryDate: addDays(new Date(), 3),
                    location: 'Queens, NY',
                    category: 'meat',
                    type: 'donation',
                    status: 'active',
                    userId: 2,
                    createdAt: new Date().toISOString()
                },
                {
                    title: 'Wild-Caught Salmon Fillets',
                    description: 'Fresh wild-caught salmon fillets. Individually vacuum sealed.',
                    image: 'https://images.unsplash.com/photo-1599084993091-1cb5c0721cc6?ixlib=rb-1.2.1&auto=format&fit=crop&w=800&q=60',
                    quantity: 0.75,
                    unit: 'kg',
                    expiryDate: addDays(new Date(), 2),
                    location: 'Manhattan, NY',
                    category: 'meat',
                    type: 'trade',
                    status: 'active',
                    userId: 1,
                    createdAt: new Date().toISOString()
                },
                
                // Prepared Foods
                {
                    title: 'Homemade Vegetable Soup',
                    description: 'Freshly made vegetable soup with organic ingredients. Can be frozen.',
                    image: 'https://images.unsplash.com/photo-1547592166-23ac45744acd?ixlib=rb-1.2.1&auto=format&fit=crop&w=800&q=60',
                    quantity: 2,
                    unit: 'liters',
                    expiryDate: addDays(new Date(), 3),
                    location: 'Brooklyn, NY',
                    category: 'prepared',
                    type: 'donation',
                    status: 'active',
                    userId: 2,
                    createdAt: new Date().toISOString()
                },
                {
                    title: 'Homemade Lasagna',
                    description: 'Freshly baked vegetable lasagna. Made with organic ingredients.',
                    image: 'https://images.unsplash.com/photo-1619895092538-128341789043?ixlib=rb-1.2.1&auto=format&fit=crop&w=800&q=60',
                    quantity: 1,
                    unit: 'pan',
                    expiryDate: addDays(new Date(), 2),
                    location: 'Queens, NY',
                    category: 'prepared',
                    type: 'trade',
                    status: 'active',
                    userId: 1,
                    createdAt: new Date().toISOString()
                },
                {
                    title: 'Fresh Fruit Salad',
                    description: 'Freshly prepared fruit salad with seasonal fruits. No sugar added.',
                    image: 'https://images.unsplash.com/photo-1564093497595-593b96d80180?ixlib=rb-1.2.1&auto=format&fit=crop&w=800&q=60',
                    quantity: 1,
                    unit: 'kg',
                    expiryDate: addDays(new Date(), 1),
                    location: 'Manhattan, NY',
                    category: 'prepared',
                    type: 'donation',
                    status: 'active',
                    userId: 2,
                    createdAt: new Date().toISOString()
                }
            ];

            // Add all demo listings
            for (const listing of demoListings) {
                await db.add(db.STORES.listings, listing);
            }
        }

        console.log('Database initialized successfully');
    } catch (error) {
        console.error('Database initialization error:', error);
        throw error;
    }
}

// Helper function to add days to a date
export function addDays(date, days) {
    const result = new Date(date);
    result.setDate(result.getDate() + days);
    return result.toISOString().split('T')[0]; // Return in YYYY-MM-DD format
}
