// Script to add sample food listings with coordinates for testing the map
import { createClient } from '@supabase/supabase-js';
import dotenv from 'dotenv';
import fs from 'fs';

// Load from .env.local if it exists, otherwise fall back to .env
const envPath = fs.existsSync('.env.local') ? '.env.local' : '.env';
dotenv.config({ path: envPath });

const supabaseUrl = process.env.VITE_SUPABASE_URL || process.env.SUPABASE_URL;
const supabaseKey = process.env.SUPABASE_SERVICE_ROLE_KEY || process.env.VITE_SUPABASE_ANON_KEY || process.env.SUPABASE_ANON_KEY;

if (!supabaseUrl || !supabaseKey) {
    console.error('Missing Supabase credentials. Please check your .env.local file');
    process.exit(1);
}

const supabase = createClient(supabaseUrl, supabaseKey);

// Generate an expiry_date N days from now (YYYY-MM-DD)
const daysFromNow = (n) => {
    const d = new Date();
    d.setDate(d.getDate() + n);
    return d.toISOString().slice(0, 10);
};

const rawSampleListings = [
    {
        title: 'Fresh Organic Apples',
        description: 'Delicious organic apples from local farm, perfect condition',
        quantity: 10,
        unit: 'lb',
        category: 'produce',
        status: 'approved',
        expiry_date: daysFromNow(7),
        latitude: 40.7128,
        longitude: -74.0060,
        donor_name: 'NYC Community Garden',
        donor_email: 'garden@example.com',
        donor_city: 'New York',
        donor_state: 'NY',
        image_url: 'https://images.unsplash.com/photo-1619566636858-adf3ef46400b?w=400'
    },
    {
        title: 'Whole Wheat Bread',
        description: 'Freshly baked whole wheat bread, made this morning',
        quantity: 5,
        unit: 'loaves',
        category: 'bakery',
        status: 'approved',
        expiry_date: daysFromNow(3),
        latitude: 34.0522,
        longitude: -118.2437,
        donor_name: 'LA Bakery',
        donor_email: 'bakery@example.com',
        donor_city: 'Los Angeles',
        donor_state: 'CA',
        image_url: 'https://images.unsplash.com/photo-1608198093002-ad4e005484ec?w=400'
    },
    {
        title: 'Mixed Vegetables',
        description: 'Assorted fresh vegetables - carrots, broccoli, peppers',
        quantity: 15,
        unit: 'lb',
        category: 'produce',
        status: 'approved',
        expiry_date: daysFromNow(5),
        latitude: 41.8781,
        longitude: -87.6298,
        donor_name: 'Chicago Farmers Market',
        donor_email: 'market@example.com',
        donor_city: 'Chicago',
        donor_state: 'IL',
        image_url: 'https://images.unsplash.com/photo-1542838132-92c53300491e?w=400'
    },
    {
        title: 'Canned Soup Variety Pack',
        description: 'Variety of canned soups, all unexpired',
        quantity: 20,
        unit: 'cans',
        category: 'pantry',
        status: 'approved',
        expiry_date: daysFromNow(180),
        latitude: 29.7604,
        longitude: -95.3698,
        donor_name: 'Houston Food Bank',
        donor_email: 'foodbank@example.com',
        donor_city: 'Houston',
        donor_state: 'TX',
        image_url: 'https://images.unsplash.com/photo-1593759608892-b0033064e78c?w=400'
    },
    {
        title: 'Dairy Bundle',
        description: 'Milk, cheese, and yogurt - all fresh',
        quantity: 8,
        unit: 'items',
        category: 'dairy',
        status: 'approved',
        expiry_date: daysFromNow(6),
        latitude: 33.4484,
        longitude: -112.0740,
        donor_name: 'Phoenix Dairy',
        donor_email: 'dairy@example.com',
        donor_city: 'Phoenix',
        donor_state: 'AZ',
        image_url: 'https://images.unsplash.com/photo-1628088062854-d1870b4553da?w=400'
    },
    {
        title: 'Bananas',
        description: 'Ripe bananas, great for smoothies or banana bread',
        quantity: 25,
        unit: 'lb',
        category: 'produce',
        status: 'approved',
        expiry_date: daysFromNow(4),
        latitude: 39.9526,
        longitude: -75.1652,
        donor_name: 'Philly Grocery Co-op',
        donor_email: 'coop@example.com',
        donor_city: 'Philadelphia',
        donor_state: 'PA',
        image_url: 'https://images.unsplash.com/photo-1571771894821-ce9b6c11b08e?w=400'
    },
    {
        title: 'Rice (Long Grain)',
        description: 'Sealed bags of long-grain white rice',
        quantity: 30,
        unit: 'lb',
        category: 'pantry',
        status: 'approved',
        expiry_date: daysFromNow(365),
        latitude: 32.7767,
        longitude: -96.7970,
        donor_name: 'Dallas Pantry Project',
        donor_email: 'pantry@example.com',
        donor_city: 'Dallas',
        donor_state: 'TX',
        image_url: 'https://images.unsplash.com/photo-1586201375761-83865001e31c?w=400'
    },
    {
        title: 'Frozen Chicken Breasts',
        description: 'Boneless, skinless chicken breasts, individually wrapped',
        quantity: 12,
        unit: 'lb',
        category: 'meat',
        status: 'approved',
        expiry_date: daysFromNow(60),
        latitude: 47.6062,
        longitude: -122.3321,
        donor_name: 'Seattle Meal Share',
        donor_email: 'meals@example.com',
        donor_city: 'Seattle',
        donor_state: 'WA',
        image_url: 'https://images.unsplash.com/photo-1604908176997-125f25cc6f3d?w=400'
    },
    {
        title: 'Pasta Assortment',
        description: 'Spaghetti, penne, and rotini - dry pasta in original packaging',
        quantity: 18,
        unit: 'boxes',
        category: 'pantry',
        status: 'approved',
        expiry_date: daysFromNow(300),
        latitude: 42.3601,
        longitude: -71.0589,
        donor_name: 'Boston Community Kitchen',
        donor_email: 'kitchen@example.com',
        donor_city: 'Boston',
        donor_state: 'MA',
        image_url: 'https://images.unsplash.com/photo-1551462147-37885acc36f1?w=400'
    },
    {
        title: 'Fresh Eggs (Free Range)',
        description: 'Local free-range eggs from a small farm',
        quantity: 6,
        unit: 'dozen',
        category: 'dairy',
        status: 'approved',
        expiry_date: daysFromNow(14),
        latitude: 30.2672,
        longitude: -97.7431,
        donor_name: 'Austin Hen House',
        donor_email: 'eggs@example.com',
        donor_city: 'Austin',
        donor_state: 'TX',
        image_url: 'https://images.unsplash.com/photo-1582722872445-44dc5f7e3c8f?w=400'
    },
    {
        title: 'Citrus Box (Oranges & Lemons)',
        description: 'Mixed citrus from a local grove',
        quantity: 20,
        unit: 'lb',
        category: 'produce',
        status: 'approved',
        expiry_date: daysFromNow(10),
        latitude: 25.7617,
        longitude: -80.1918,
        donor_name: 'Miami Grove Collective',
        donor_email: 'grove@example.com',
        donor_city: 'Miami',
        donor_state: 'FL',
        image_url: 'https://images.unsplash.com/photo-1547514701-42782101795e?w=400'
    },
    {
        title: 'Granola Bars',
        description: 'Individually wrapped granola bars, mixed flavors',
        quantity: 50,
        unit: 'bars',
        category: 'pantry',
        status: 'approved',
        expiry_date: daysFromNow(120),
        latitude: 39.7392,
        longitude: -104.9903,
        donor_name: 'Denver Snack Drive',
        donor_email: 'snacks@example.com',
        donor_city: 'Denver',
        donor_state: 'CO',
        image_url: 'https://images.unsplash.com/photo-1606312619070-d48b4c652a52?w=400'
    }
];

const sampleListings = rawSampleListings.map(l => ({ listing_type: 'donation', ...l }));

async function addSampleListings() {
    console.log('Adding sample food listings with coordinates...\n');

    for (const listing of sampleListings) {
        const { error } = await supabase
            .from('food_listings')
            .insert([listing])
            .select();

        if (error) {
            console.error(`❌ Error adding ${listing.title}:`, error.message);
        } else {
            console.log(`✅ Added: ${listing.title} at (${listing.latitude}, ${listing.longitude})`);
        }
    }

    console.log('\n✨ Sample listings added successfully!');
    console.log('You should now see markers on the map at these locations:');
    console.log('- New York City');
    console.log('- Los Angeles');
    console.log('- Chicago');
    console.log('- Houston');
    console.log('- Phoenix');
}

addSampleListings();
