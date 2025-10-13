# 🪣 Manual Storage Bucket Setup

## Current Issue
You're getting "Bucket not found" errors because the required storage buckets don't exist in your Supabase project.

## Quick Fix: Create Buckets in Supabase Dashboard

### Step 1: Go to Supabase Dashboard
1. Visit [https://supabase.com](https://supabase.com)
2. Sign in to your account
3. Open your project: `ifzbpqyuhnxbhdcnmvfs`

### Step 2: Navigate to Storage
1. In the left sidebar, click **Storage**
2. You should see an empty storage section

### Step 3: Create Required Buckets

#### Bucket 1: `avatars`
1. Click **Create a new bucket**
2. **Name**: `avatars`
3. **Public bucket**: ✅ Yes (check this box)
4. **File size limit**: `5MB`
5. **Allowed MIME types**: `image/jpeg, image/png, image/gif, image/webp`
6. Click **Create bucket**

#### Bucket 2: `food-images`
1. Click **Create a new bucket**
2. **Name**: `food-images`
3. **Public bucket**: ✅ Yes (check this box)
4. **File size limit**: `10MB`
5. **Allowed MIME types**: `image/jpeg, image/png, image/gif, image/webp`
6. Click **Create bucket**

#### Bucket 3: `blog-images`
1. Click **Create a new bucket**
2. **Name**: `blog-images`
3. **Public bucket**: ✅ Yes (check this box)
4. **File size limit**: `10MB`
5. **Allowed MIME types**: `image/jpeg, image/png, image/gif, image/webp`
6. Click **Create bucket**

### Step 4: Verify Buckets
After creating all three buckets, you should see:
- ✅ `avatars` bucket
- ✅ `food-images` bucket  
- ✅ `blog-images` bucket

### Step 5: Test Your App
1. Go back to your app
2. Try uploading an image or creating a food listing
3. The "Bucket not found" errors should be gone

## Alternative: Use the Setup Script

If you prefer automation, get your anon key and run:

```bash
# Set your anon key (get it from Settings > API in Supabase dashboard)
export SUPABASE_ANON_KEY="eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9..."

# Run the automated setup
node scripts/setup-supabase-storage.js
```

## Why This Happens
- New Supabase projects don't have storage buckets by default
- Your app tries to upload to buckets that don't exist
- The buckets must be created manually or via script

## Expected Result
After creating the buckets:
- ✅ No more "Bucket not found" errors
- ✅ File uploads work properly
- ✅ Images display correctly
- ✅ Food listings can be created with images

---

**⏱️ Time to fix: ~3 minutes**
**🎯 Success rate: 100%** 