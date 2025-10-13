-- Minimal seed data for DoGoods application

-- Note: User profiles will be created automatically when users sign up through Supabase Auth
-- This seed file contains only data that doesn't depend on specific users

-- Example blog posts
INSERT INTO blog_posts (id, title, slug, excerpt, content, image_url, category, published, published_at) VALUES
(
    '990e8400-e29b-41d4-a716-446655440001',
    'Welcome to DoGoods',
    'welcome-to-dogoods',
    'Learn about our mission to reduce food waste and build stronger communities.',
    'DoGoods is a platform dedicated to reducing food waste by connecting people in communities to share excess food...',
    'https://images.unsplash.com/photo-1582213782179-e0d53f98f2ca?ixlib=rb-1.2.1&auto=format&fit=crop&w=800&q=60',
    'Community',
    true,
    NOW()
),
(
    '990e8400-e29b-41d4-a716-446655440002',
    'Tips for Reducing Food Waste',
    'tips-reducing-food-waste',
    'Simple strategies to minimize food waste in your daily life.',
    'Food waste is a significant environmental issue. Here are some practical tips to help reduce waste in your home...',
    'https://images.unsplash.com/photo-1542838132-92c53300491e?ixlib=rb-1.2.1&auto=format&fit=crop&w=800&q=60',
    'Tips',
    true,
    NOW()
);

-- Community distribution events (these don't require specific user IDs)
INSERT INTO distribution_events (id, title, description, location, latitude, longitude, event_date, start_time, end_time, capacity, status) VALUES
(
    '880e8400-e29b-41d4-a716-446655440001',
    'Downtown Food Distribution',
    'Monthly food distribution for downtown residents.',
    '123 Main St, Downtown',
    40.7589,
    -73.9851,
    (CURRENT_DATE + INTERVAL '7 days'),
    '10:00:00',
    '14:00:00',
    100,
    'scheduled'
),
(
    '880e8400-e29b-41d4-a716-446655440002',
    'Community Garden Harvest Share',
    'Share the harvest from our community garden with neighbors.',
    '456 Garden Ave, Community Garden',
    40.7282,
    -73.7949,
    (CURRENT_DATE + INTERVAL '14 days'),
    '09:00:00',
    '12:00:00',
    50,
    'scheduled'
);
