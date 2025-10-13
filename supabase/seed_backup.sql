-- Seed data for DoGoods application

-- Note: User profiles will be created automatically when users sign up through Supabase Auth
-- This seed file focuses on food listings, events, and other data that doesn't depend on auth users

-- User-dependent seed data is commented out since users will be created through Supabase Auth
-- These can be added later through the admin interface or after creating test users

-- Insert sample food listings
-- INSERT INTO food_listings (id, user_id, title, description, image_url, quantity, unit, category, listing_type, status, expiry_date, location, latitude, longitude) VALUES
(
    '660e8400-e29b-41d4-a716-446655440001',
    '550e8400-e29b-41d4-a716-446655440002',
    'Fresh Organic Carrots',
    'Freshly harvested organic carrots from my garden. No pesticides used.',
    'https://images.unsplash.com/photo-1598170845058-32b9d6a5da37?ixlib=rb-1.2.1&auto=format&fit=crop&w=800&q=60',
    2.0,
    'kg',
    'produce',
    'donation',
    'active',
    (CURRENT_DATE + INTERVAL '10 days'),
    'Brooklyn, NY',
    40.7128,
    -74.0060
),
(
    '660e8400-e29b-41d4-a716-446655440002',
    '550e8400-e29b-41d4-a716-446655440003',
    'Homegrown Tomatoes',
    'Ripe, juicy tomatoes from my backyard garden. Perfect for salads or sauces.',
    'https://images.unsplash.com/photo-1582284540020-8acbe03f4924?ixlib=rb-1.2.1&auto=format&fit=crop&w=800&q=60',
    1.5,
    'kg',
    'produce',
    'trade',
    'active',
    (CURRENT_DATE + INTERVAL '5 days'),
    'Queens, NY',
    40.7282,
    -73.7949
),
(
    '660e8400-e29b-41d4-a716-446655440003',
    '550e8400-e29b-41d4-a716-446655440004',
    'Fresh Spinach Bunch',
    'Organic spinach, freshly harvested this morning. Great for salads or cooking.',
    'https://images.unsplash.com/photo-1576045057995-568f588f82fb?ixlib=rb-1.2.1&auto=format&fit=crop&w=800&q=60',
    0.5,
    'kg',
    'produce',
    'donation',
    'active',
    (CURRENT_DATE + INTERVAL '4 days'),
    'Manhattan, NY',
    40.7589,
    -73.9851
),
(
    '660e8400-e29b-41d4-a716-446655440004',
    '550e8400-e29b-41d4-a716-446655440005',
    'Organic Apples',
    'Fresh organic apples from local orchard. Sweet and crisp.',
    'https://images.unsplash.com/photo-1570913149827-d2ac84ab3f9a?ixlib=rb-1.2.1&auto=format&fit=crop&w=800&q=60',
    2.0,
    'kg',
    'produce',
    'donation',
    'active',
    (CURRENT_DATE + INTERVAL '14 days'),
    'Brooklyn, NY',
    40.6782,
    -73.9442
),
(
    '660e8400-e29b-41d4-a716-446655440005',
    '550e8400-e29b-41d4-a716-446655440002',
    'Fresh Berries Mix',
    'Mix of strawberries, blueberries and raspberries. Freshly picked.',
    'https://images.unsplash.com/photo-1563746098251-d35aef196e83?ixlib=rb-1.2.1&auto=format&fit=crop&w=800&q=60',
    0.5,
    'kg',
    'produce',
    'trade',
    'active',
    (CURRENT_DATE + INTERVAL '3 days'),
    'Manhattan, NY',
    40.7505,
    -73.9934
),
(
    '660e8400-e29b-41d4-a716-446655440006',
    '550e8400-e29b-41d4-a716-446655440003',
    'Freshly Baked Sourdough',
    'Homemade sourdough bread baked this morning. Crusty outside, soft inside.',
    'https://images.unsplash.com/photo-1586444248902-2f64eddc13df?ixlib=rb-1.2.1&auto=format&fit=crop&w=800&q=60',
    2,
    'loaves',
    'bakery',
    'trade',
    'active',
    (CURRENT_DATE + INTERVAL '3 days'),
    'Brooklyn, NY',
    40.6501,
    -73.9496
),
(
    '660e8400-e29b-41d4-a716-446655440007',
    '550e8400-e29b-41d4-a716-446655440004',
    'Homemade Chocolate Chip Cookies',
    'Batch of homemade cookies made with organic ingredients. Soft and chewy.',
    'https://images.unsplash.com/photo-1499636136210-6f4ee915583e?ixlib=rb-1.2.1&auto=format&fit=crop&w=800&q=60',
    12,
    'cookies',
    'bakery',
    'donation',
    'active',
    (CURRENT_DATE + INTERVAL '5 days'),
    'Queens, NY',
    40.7282,
    -73.7949
),
(
    '660e8400-e29b-41d4-a716-446655440008',
    '550e8400-e29b-41d4-a716-446655440005',
    'Organic Milk',
    'Fresh organic whole milk from local dairy farm. Glass bottle can be returned.',
    'https://images.unsplash.com/photo-1563636619-e9143da7973b?ixlib=rb-1.2.1&auto=format&fit=crop&w=800&q=60',
    1,
    'liter',
    'dairy',
    'donation',
    'active',
    (CURRENT_DATE + INTERVAL '4 days'),
    'Brooklyn, NY',
    40.6782,
    -73.9442
),
(
    '660e8400-e29b-41d4-a716-446655440009',
    '550e8400-e29b-41d4-a716-446655440002',
    'Farm Fresh Eggs',
    'Free-range eggs from my backyard chickens. Collected this morning.',
    'https://images.unsplash.com/photo-1506976785307-8732e854ad03?ixlib=rb-1.2.1&auto=format&fit=crop&w=800&q=60',
    12,
    'eggs',
    'dairy',
    'donation',
    'active',
    (CURRENT_DATE + INTERVAL '14 days'),
    'Manhattan, NY',
    40.7505,
    -73.9934
),
(
    '660e8400-e29b-41d4-a716-446655440010',
    '550e8400-e29b-41d4-a716-446655440003',
    'Organic Rice',
    'Unopened bag of organic brown rice. Best before date still months away.',
    'https://images.unsplash.com/photo-1586201375761-83865001e31c?ixlib=rb-1.2.1&auto=format&fit=crop&w=800&q=60',
    1,
    'kg',
    'pantry',
    'donation',
    'active',
    (CURRENT_DATE + INTERVAL '180 days'),
    'Brooklyn, NY',
    40.6501,
    -73.9496
);

-- Insert sample trades
INSERT INTO trades (id, initiator_id, recipient_id, offered_listing_id, requested_listing_id, status, message) VALUES
(
    '770e8400-e29b-41d4-a716-446655440001',
    '550e8400-e29b-41d4-a716-446655440002',
    '550e8400-e29b-41d4-a716-446655440003',
    '660e8400-e29b-41d4-a716-446655440001',
    '660e8400-e29b-41d4-a716-446655440002',
    'pending',
    'I would love to trade my carrots for your tomatoes!'
),
(
    '770e8400-e29b-41d4-a716-446655440002',
    '550e8400-e29b-41d4-a716-446655440004',
    '550e8400-e29b-41d4-a716-446655440005',
    '660e8400-e29b-41d4-a716-446655440003',
    '660e8400-e29b-41d4-a716-446655440004',
    'accepted',
    'Great trade! Looking forward to the exchange.'
),
(
    '770e8400-e29b-41d4-a716-446655440003',
    '550e8400-e29b-41d4-a716-446655440003',
    '550e8400-e29b-41d4-a716-446655440002',
    '660e8400-e29b-41d4-a716-446655440006',
    '660e8400-e29b-41d4-a716-446655440005',
    'completed',
    'Trade completed successfully!'
);

-- User-dependent seed data is commented out since users will be created through Supabase Auth
-- These can be added later through the admin interface or after creating test users

-- Insert sample user stats
-- INSERT INTO user_stats (user_id, total_donations, total_trades, total_food_saved, total_impact_score) VALUES
-- ('550e8400-e29b-41d4-a716-446655440002', 15, 8, 45.5, 120),
-- ('550e8400-e29b-41d4-a716-446655440003', 12, 5, 38.2, 95),
-- ('550e8400-e29b-41d4-a716-446655440004', 20, 12, 62.8, 150),
-- ('550e8400-e29b-41d4-a716-446655440005', 8, 3, 25.1, 65);

-- Insert sample user badges
-- INSERT INTO user_badges (user_id, badge_name, badge_description, badge_icon) VALUES
-- ('550e8400-e29b-41d4-a716-446655440002', 'Food Hero', 'Donated 10+ food items', 'medal'),
-- ('550e8400-e29b-41d4-a716-446655440002', 'Eco Warrior', 'Saved 20kg of food waste', 'leaf'),
-- ('550e8400-e29b-41d4-a716-446655440003', 'Community Champion', 'Active community member', 'users'),
-- ('550e8400-e29b-41d4-a716-446655440004', 'Food Hero', 'Donated 10+ food items', 'medal'),
-- ('550e8400-e29b-41d4-a716-446655440005', 'Newcomer', 'Joined the community', 'star');

-- Insert sample distribution events
INSERT INTO distribution_events (id, title, description, location, latitude, longitude, event_date, start_time, end_time, capacity, registered_count, status, created_by) VALUES
(
    '880e8400-e29b-41d4-a716-446655440001',
    'Downtown Food Distribution',
    'Monthly food distribution for downtown residents.',
    '123 Main St, Downtown',
    40.7128,
    -74.0060,
    (CURRENT_DATE + INTERVAL '15 days'),
    '10:00:00',
    '14:00:00',
    150,
    87,
    'scheduled',
    '550e8400-e29b-41d4-a716-446655440001'
),
(
    '880e8400-e29b-41d4-a716-446655440002',
    'Community Center Distribution',
    'Food distribution for families in the Westside area.',
    '456 Park Ave, Westside',
    40.7589,
    -73.9851,
    (CURRENT_DATE + INTERVAL '22 days'),
    '09:00:00',
    '13:00:00',
    100,
    65,
    'scheduled',
    '550e8400-e29b-41d4-a716-446655440001'
),
(
    '880e8400-e29b-41d4-a716-446655440003',
    'School Pantry Program',
    'Food distribution for school families.',
    'Lincoln Elementary School',
    40.7505,
    -73.9934,
    (CURRENT_DATE + INTERVAL '10 days'),
    '15:00:00',
    '18:00:00',
    75,
    75,
    'full',
    '550e8400-e29b-41d4-a716-446655440001'
);

-- Insert sample blog posts
INSERT INTO blog_posts (id, title, slug, excerpt, content, image_url, category, author_id, published, published_at) VALUES
(
    '990e8400-e29b-41d4-a716-446655440001',
    'Reducing Food Waste: A Community Approach',
    'reducing-food-waste-community-approach',
    'Learn how communities are coming together to combat food waste through innovative sharing platforms and local initiatives.',
    'Food waste is a significant global issue, with approximately one-third of all food produced being wasted. In our communities, we''re seeing innovative approaches to combat this problem through food sharing platforms and local initiatives.

Local food sharing platforms like DoGoods are connecting neighbors who have surplus food with those who need it. This not only reduces waste but also builds stronger communities.

Key strategies include:
- Community gardens and urban farming
- Food sharing platforms
- Educational programs about food preservation
- Partnerships with local businesses

By working together, we can make a real difference in reducing food waste while helping those in need.',
    'https://images.unsplash.com/photo-1598170845058-32b9d6a5da37?ixlib=rb-1.2.1&auto=format&fit=crop&w=800&q=60',
    'Food Waste',
    '550e8400-e29b-41d4-a716-446655440002',
    true,
    NOW()
),
(
    '990e8400-e29b-41d4-a716-446655440002',
    'Success Stories: Making a Difference',
    'success-stories-making-difference',
    'Read inspiring stories from our community members who are making a real impact in their neighborhoods.',
    'Our community is full of inspiring individuals who are making a real difference in their neighborhoods. From local farmers sharing surplus produce to families organizing neighborhood food swaps, these stories show the power of community action.

Sarah from Brooklyn started a community garden that now feeds over 50 families. Michael in Queens organizes weekly food sharing events that have saved hundreds of pounds of food from going to waste.

These success stories demonstrate that small actions can lead to big changes. Every donation, every trade, and every shared meal contributes to a more sustainable and connected community.',
    'https://images.unsplash.com/photo-1582284540020-8acbe03f4924?ixlib=rb-1.2.1&auto=format&fit=crop&w=800&q=60',
    'Success Stories',
    '550e8400-e29b-41d4-a716-446655440003',
    true,
    NOW()
),
(
    '990e8400-e29b-41d4-a716-446655440003',
    'Tips for Food Preservation',
    'tips-food-preservation',
    'Learn essential techniques for preserving food to extend its shelf life and reduce waste.',
    'Proper food preservation is key to reducing waste and making the most of your food. Here are some essential techniques:

Freezing: Most fruits and vegetables can be frozen for later use. Blanch vegetables before freezing to preserve quality.

Canning: Preserve fruits and vegetables in jars for long-term storage. Follow proper canning procedures for safety.

Drying: Dehydrate fruits, vegetables, and herbs for extended shelf life. Use a food dehydrator or oven on low heat.

Pickling: Preserve vegetables in vinegar or brine solutions. This method adds flavor while extending shelf life.

By mastering these preservation techniques, you can reduce food waste and enjoy fresh flavors year-round.',
    'https://images.unsplash.com/photo-1576045057995-568f588f82fb?ixlib=rb-1.2.1&auto=format&fit=crop&w=800&q=60',
    'Tips & Tricks',
    '550e8400-e29b-41d4-a716-446655440004',
    true,
    NOW()
);

-- Insert sample notifications
INSERT INTO notifications (user_id, title, message, type, data) VALUES
(
    '550e8400-e29b-41d4-a716-446655440002',
    'New Trade Request',
    'Sarah wants to trade her tomatoes for your carrots',
    'trade_request',
    '{"trade_id": "770e8400-e29b-41d4-a716-446655440001", "initiator_name": "Sarah Johnson"}'
),
(
    '550e8400-e29b-41d4-a716-446655440003',
    'Trade Accepted',
    'Your trade request for tomatoes has been accepted',
    'trade_accepted',
    '{"trade_id": "770e8400-e29b-41d4-a716-446655440001", "recipient_name": "John Doe"}'
),
(
    '550e8400-e29b-41d4-a716-446655440004',
    'New Distribution Event',
    'A new food distribution event has been scheduled in your area',
    'event_announcement',
    '{"event_id": "880e8400-e29b-41d4-a716-446655440001", "event_title": "Downtown Food Distribution"}'
); 