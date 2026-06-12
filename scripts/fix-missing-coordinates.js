import { createClient } from '@supabase/supabase-js';
import dotenv from 'dotenv';
import fetch from 'node-fetch';

// Load environment variables
dotenv.config();

const SUPABASE_URL = process.env.VITE_SUPABASE_URL;
const SUPABASE_SERVICE_KEY = process.env.SUPABASE_SERVICE_ROLE_KEY || process.env.VITE_SUPABASE_ANON_KEY;
const MAPBOX_TOKEN = process.env.VITE_MAPBOX_TOKEN || process.env.MAPBOX_TOKEN;

if (!SUPABASE_URL || !SUPABASE_SERVICE_KEY) {
  console.error('❌ Missing Supabase credentials');
  process.exit(1);
}

if (!MAPBOX_TOKEN) {
  console.error('❌ Missing Mapbox token');
  process.exit(1);
}

const supabase = createClient(SUPABASE_URL, SUPABASE_SERVICE_KEY);

/**
 * Geocode an address using Mapbox Geocoding API
 * @param {string} address - The address to geocode
 * @returns {Promise<{lat: number, lng: number} | null>}
 */
async function geocodeAddress(address) {
  if (!address || typeof address !== 'string') {
    return null;
  }

  try {
    const encodedAddress = encodeURIComponent(address.trim());
    const url = `https://api.mapbox.com/geocoding/v5/mapbox.places/${encodedAddress}.json?access_token=${MAPBOX_TOKEN}&limit=1&country=US&proximity=-122.27,37.82`;
    
    const response = await fetch(url);
    if (!response.ok) {
      console.error(`Mapbox API error: ${response.status}`);
      return null;
    }

    const data = await response.json();
    if (!data.features || data.features.length === 0) {
      console.warn(`No results found for address: ${address}`);
      return null;
    }

    const [lng, lat] = data.features[0].center;
    return { lat, lng };
  } catch (error) {
    console.error(`Geocoding error for "${address}":`, error.message);
    return null;
  }
}

/**
 * Fix listings missing coordinates
 */
async function fixMissingCoordinates() {
  console.log('🔍 Finding listings with missing coordinates...\n');

  // Find listings without coordinates
  const { data: listings, error: fetchError } = await supabase
    .from('food_listings')
    .select(`
      id,
      title,
      latitude,
      longitude,
      full_address,
      location,
      user_id,
      users:user_id (
        address,
        name
      )
    `)
    .in('status', ['approved', 'active'])
    .eq('listing_type', 'donation')
    .or('latitude.is.null,longitude.is.null');

  if (fetchError) {
    console.error('❌ Error fetching listings:', fetchError);
    return;
  }

  console.log(`Found ${listings.length} listing(s) with missing coordinates\n`);

  if (listings.length === 0) {
    console.log('✅ All listings have coordinates!');
    return;
  }

  let fixed = 0;
  let failed = 0;

  for (const listing of listings) {
    console.log(`\n📍 Processing: "${listing.title}" (${listing.id})`);
    
    // Determine address to geocode
    let addressToGeocode = null;
    let addressSource = null;

    if (listing.full_address) {
      addressToGeocode = listing.full_address;
      addressSource = 'full_address';
    } else if (listing.location && typeof listing.location === 'string') {
      addressToGeocode = listing.location;
      addressSource = 'location';
    } else if (listing.location && typeof listing.location === 'object' && listing.location.address) {
      addressToGeocode = listing.location.address;
      addressSource = 'location.address';
    } else if (listing.users && listing.users.address) {
      addressToGeocode = listing.users.address;
      addressSource = 'user profile address';
    }

    if (!addressToGeocode) {
      console.log('   ⚠️  No address available to geocode');
      failed++;
      continue;
    }

    console.log(`   📮 Address: ${addressToGeocode} (from ${addressSource})`);

    // Geocode the address
    const coords = await geocodeAddress(addressToGeocode);
    
    if (!coords) {
      console.log('   ❌ Failed to geocode address');
      failed++;
      continue;
    }

    console.log(`   🎯 Coordinates: ${coords.lat}, ${coords.lng}`);

    // Update the listing with coordinates
    const updateData = {
      latitude: coords.lat,
      longitude: coords.lng
    };

    // If we used user's address, also update full_address
    if (addressSource === 'user profile address') {
      updateData.full_address = addressToGeocode;
    }

    const { error: updateError } = await supabase
      .from('food_listings')
      .update(updateData)
      .eq('id', listing.id);

    if (updateError) {
      console.log('   ❌ Failed to update listing:', updateError.message);
      failed++;
    } else {
      console.log('   ✅ Updated successfully!');
      fixed++;
    }

    // Rate limiting - wait 100ms between requests
    await new Promise(resolve => setTimeout(resolve, 100));
  }

  console.log('\n' + '='.repeat(50));
  console.log(`\n📊 Summary:`);
  console.log(`   ✅ Fixed: ${fixed}`);
  console.log(`   ❌ Failed: ${failed}`);
  console.log(`   📍 Total: ${listings.length}\n`);
}

// Run the script
fixMissingCoordinates()
  .then(() => {
    console.log('✨ Script completed!');
    process.exit(0);
  })
  .catch((error) => {
    console.error('💥 Script failed:', error);
    process.exit(1);
  });
