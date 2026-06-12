# Geocoding & Map Marker Maintenance

## Overview

This document explains the geocoding system and how to prevent/fix map marker issues.

## How It Works

### Automatic Geocoding

**Frontend (dataService.js):**
- When creating a food listing (`createFoodListing`):
  - If `latitude`/`longitude` are missing
  - AND an address exists (`full_address` or `location`)
  - Automatically geocodes via Mapbox API
  - Saves coordinates to database

- When updating a food listing (`updateFoodListing`):
  - Same auto-geocoding logic applies
  - Ensures edited addresses get fresh coordinates

**Fallback Geocoding (FoodMap.jsx):**
- Client-side geocoding backfill for listings without coordinates
- Attempts to geocode on map load
- Uses sessionStorage cache to avoid repeat requests

### Manual Fix Script

**Location:** `scripts/fix-missing-coordinates.js`

**Purpose:** Batch geocode all listings missing coordinates

**Usage:**
```bash
node scripts/fix-missing-coordinates.js
```

**What it does:**
1. Finds all listings without `latitude`/`longitude`
2. Tries multiple address sources:
   - `full_address` (primary)
   - `location` field
   - User's profile address (fallback)
3. Geocodes via Mapbox API
4. Updates database with coordinates
5. Provides detailed report

## Preventing Future Issues

### 1. Ensure Address Data is Always Provided

When sharing food, users should provide:
- Full address, OR
- City + State + Zip

The system will auto-geocode this to map coordinates.

### 2. Backend Validation (Optional Enhancement)

Add database constraint:
```sql
-- Ensure listings either have coordinates OR an address to geocode
ALTER TABLE food_listings 
ADD CONSTRAINT listings_must_be_locatable 
CHECK (
  (latitude IS NOT NULL AND longitude IS NOT NULL) OR
  (full_address IS NOT NULL) OR
  (location IS NOT NULL)
);
```

### 3. Scheduled Maintenance

Run the fix script periodically (e.g., nightly):

**Linux/Mac (cron):**
```bash
# Edit crontab
crontab -e

# Add line (runs daily at 2am):
0 2 * * * cd /path/to/dogoods && node scripts/fix-missing-coordinates.js >> /var/log/geocode-fix.log 2>&1
```

**Windows (Task Scheduler):**
1. Open Task Scheduler
2. Create Basic Task
3. Trigger: Daily at 2:00 AM
4. Action: Start a program
5. Program: `node`
6. Arguments: `scripts\fix-missing-coordinates.js`
7. Start in: `C:\path\to\dogoods-app-ready-version2-master`

**Railway (Backend):**
```python
# In backend/app.py, add to _reminder_loop:
async def _geocode_missing_coords():
    """Scheduled job to geocode listings missing coordinates"""
    # Implementation similar to fix-missing-coordinates.js
    pass
```

### 4. Monitoring

**Check coordinate coverage:**
```sql
SELECT 
    COUNT(*) as total,
    COUNT(CASE WHEN latitude IS NOT NULL AND longitude IS NOT NULL THEN 1 END) as with_coords,
    COUNT(CASE WHEN latitude IS NULL OR longitude IS NULL THEN 1 END) as missing_coords,
    ROUND(100.0 * COUNT(CASE WHEN latitude IS NOT NULL AND longitude IS NOT NULL THEN 1 END) / COUNT(*), 2) as coverage_percent
FROM food_listings 
WHERE status IN ('approved', 'active');
```

**Expected:** 100% coverage for active/approved listings

## Troubleshooting

### Issue: Listing doesn't appear on map

**Diagnosis:**
```sql
SELECT id, title, latitude, longitude, full_address, location 
FROM food_listings 
WHERE id = 'listing-id-here';
```

**If coordinates are NULL:**
1. Check if address exists
2. Run fix script: `node scripts/fix-missing-coordinates.js`
3. Verify coordinates were added

**If coordinates exist but marker doesn't show:**
1. Check browser console for errors
2. Verify coordinates are in Bay Area bounds (isBayAreaCoord)
3. Check if listing status is 'active' or 'approved'

### Issue: Hover doesn't work

**Cause:** Marker element not in `foodMarkerElsRef` map

**Fix:**
1. Ensure listing has valid `id` field
2. Check coordinates are valid numbers (not NaN)
3. Refresh page to rebuild marker refs

### Issue: Geocoding fails for specific address

**Possible causes:**
- Invalid/incomplete address
- Address outside Bay Area bounds
- Mapbox API rate limit exceeded

**Fix:**
1. Check Mapbox token is valid: `VITE_MAPBOX_TOKEN` in `.env`
2. Verify address format in database
3. Try manual geocoding: https://www.mapbox.com/search/
4. Add delay between geocoding calls (100ms in script)

## Bay Area Bounds

Geocoding is restricted to Bay Area to prevent invalid coordinates:

**Latitude:** 36.8° to 38.3° N  
**Longitude:** -123.5° to -121.0° W

Listings outside these bounds will not get coordinates automatically.

## Rate Limits

**Mapbox Geocoding API:**
- Free tier: 100,000 requests/month
- With batch processing: ~3,000 listings/day safe
- Script includes 100ms delay to stay under rate limits

## Database Schema

```sql
-- food_listings table (relevant columns)
latitude NUMERIC(10, 8)      -- e.g., 37.76503000
longitude NUMERIC(11, 8)     -- e.g., -122.24254000
full_address TEXT            -- "1423 Park St, Alameda, CA"
location TEXT                -- JSONB or string, fallback address
```

## Files Modified

- ✅ `utils/dataService.js` - Auto-geocoding in create/update
- ✅ `scripts/fix-missing-coordinates.js` - Batch fix script
- ✅ `utils/geocoding.js` - Geocoding utility (already existed)
- ✅ `components/common/FoodMap.jsx` - Client-side geocoding fallback

## Success Metrics

**Current Status (2026-06-12):**
- ✅ 28/28 total listings have coordinates (100%)
- ✅ 13/13 active listings have coordinates (100%)
- ✅ All map markers displaying correctly
- ✅ Hover highlighting working

## Support

If geocoding issues persist:
1. Check Mapbox token in `.env`
2. Verify Supabase connection
3. Run fix script with verbose logging
4. Review database for data quality issues
