// Quick test to check food_listings table
import { createClient } from '@supabase/supabase-js';
import dotenv from 'dotenv';

dotenv.config({ path: '.env.local' });

const supabaseUrl = process.env.VITE_SUPABASE_URL || process.env.SUPABASE_URL;
const supabaseKey = process.env.VITE_SUPABASE_ANON_KEY || process.env.SUPABASE_ANON_KEY;

const supabase = createClient(supabaseUrl, supabaseKey);

async function checkListings() {
    console.log('Checking existing food listings...\n');
    
    const { data, error } = await supabase
        .from('food_listings')
        .select('id, title, status, latitude, longitude')
        .limit(10);

    if (error) {
        console.error('Error:', error);
        return;
    }

    console.log(`Found ${data?.length || 0} listings\n`);
    
    if (data && data.length > 0) {
        data.forEach(listing => {
            console.log(`- ${listing.title}`);
            console.log(`  Status: ${listing.status}`);
            console.log(`  Coordinates: ${listing.latitude}, ${listing.longitude}`);
            console.log('');
        });
    } else {
        console.log('No listings found. The map will be empty.');
        console.log('\nTo add food listings with coordinates:');
        console.log('1. Sign up/login to the app');
        console.log('2. Go to Share Food page');
        console.log('3. Fill in the form with location data');
        console.log('4. The listing goes live immediately and appears on Find Food / the map');
    }
    
    // Check listings with coordinates
    const { data: withCoords } = await supabase
        .from('food_listings')
        .select('id, title')
        .not('latitude', 'is', null)
        .not('longitude', 'is', null);
    
    console.log(`\nListings with coordinates: ${withCoords?.length || 0}`);
}

checkListings();
