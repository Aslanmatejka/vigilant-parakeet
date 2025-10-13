# 🔧 Fix Storage Bucket Issues

## Current Problems
Your app is getting these errors:
- ❌ **400 status errors** - Missing environment variables
- ❌ **"Bucket not found"** - Storage buckets don't exist in Supabase

## Quick Fix Steps

### 1. Fix Environment Variables
The 400 errors suggest missing environment variables. Check your browser console for:
```
🔌 Connecting to Supabase: [URL]
🌍 Environment: [mode]
```

If you see "Missing Supabase configuration", you need to set environment variables.

### 2. Create Storage Buckets
Your Supabase project is missing these storage buckets:
- `avatars` - for user profile pictures
- `food-images` - for food listing images  
- `blog-images` - for blog post images

## Solution Options

### Option A: Use the Setup Script (Recommended)
```bash
# Set your Supabase credentials
export SUPABASE_URL="https://your-project.supabase.co"
export SUPABASE_ANON_KEY="your-anon-key"

# Run the storage setup script
node scripts/setup-supabase-storage.js
```

### Option B: Manual Setup in Supabase Dashboard
1. Go to your Supabase project dashboard
2. Navigate to **Storage** in the left sidebar
3. Click **Create a new bucket** for each:
   - **avatars** (public, 5MB limit)
   - **food-images** (public, 10MB limit)
   - **blog-images** (public, 10MB limit)

### Option C: SQL Commands
Run these in your Supabase SQL Editor:

```sql
-- Create storage buckets
INSERT INTO storage.buckets (id, name, public, file_size_limit, allowed_mime_types)
VALUES 
  ('avatars', 'avatars', true, 5242880, ARRAY['image/jpeg', 'image/png', 'image/gif', 'image/webp']),
  ('food-images', 'food-images', true, 10485760, ARRAY['image/jpeg', 'image/png', 'image/gif', 'image/webp']),
  ('blog-images', 'blog-images', true, 10485760, ARRAY['image/jpeg', 'image/png', 'image/gif', 'image/webp']);

-- Set up storage policies (optional, for better security)
CREATE POLICY "Public avatars are viewable by everyone" ON storage.objects
FOR SELECT USING (bucket_id = 'avatars');

CREATE POLICY "Users can upload their own avatar" ON storage.objects
FOR INSERT WITH CHECK (bucket_id = 'avatars' AND auth.uid()::text = (storage.foldername(name))[1]);
```

## Environment Variables Check

Make sure these are set in your deployment:

```bash
# For Vite (frontend)
VITE_SUPABASE_URL=https://your-project.supabase.co
VITE_SUPABASE_ANON_KEY=your-anon-key

# For Node.js scripts
SUPABASE_URL=https://your-project.supabase.co
SUPABASE_ANON_KEY=your-anon-key
```

## Testing the Fix

1. **Run the storage setup script**:
   ```bash
   node scripts/setup-supabase-storage.js
   ```

2. **Check your app**:
   - No more "Bucket not found" errors
   - File uploads should work
   - Images should display properly

3. **Test file upload**:
   - Try uploading a profile picture
   - Try creating a food listing with an image
   - Check the browser console for errors

## Common Issues

### Issue: "Bucket not found" persists
**Solution**: Make sure you're using the correct Supabase project. The buckets need to exist in the same project your app is connecting to.

### Issue: "Permission denied" on upload
**Solution**: Check storage bucket policies in Supabase dashboard. Make sure the bucket is public or has proper RLS policies.

### Issue: Images not displaying
**Solution**: Verify the bucket is public and the file URLs are correct. Check the network tab for 404 errors.

## Next Steps

1. ✅ Fix environment variables
2. ✅ Create storage buckets
3. ✅ Test file uploads
4. ✅ Verify images display correctly
5. ✅ Deploy your app

## Support

If you still have issues:
1. Check Supabase project status
2. Verify bucket permissions
3. Check browser console for specific errors
4. Test with the setup script
5. Review Supabase storage documentation 