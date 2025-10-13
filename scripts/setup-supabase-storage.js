#!/usr/bin/env node

/**
 * Script to set up required storage buckets in Supabase
 * Run this after creating your Supabase project
 */

import { createClient } from '@supabase/supabase-js';

  // Get Supabase credentials from environment or config
  const supabaseUrl = process.env.SUPABASE_URL || process.env.VITE_SUPABASE_URL;
  const supabaseKey = process.env.SUPABASE_ANON_KEY || process.env.VITE_SUPABASE_ANON_KEY;

if (!supabaseUrl || !supabaseKey) {
  console.log('❌ Missing Supabase credentials!');
  console.log('Please set SUPABASE_URL and SUPABASE_ANON_KEY environment variables');
  console.log('Or run: SUPABASE_URL=your_url SUPABASE_ANON_KEY=your_key node scripts/setup-supabase-storage.js');
  process.exit(1);
}

console.log('🔧 Setting up Supabase storage buckets...\n');

const supabase = createClient(supabaseUrl, supabaseKey);

// Required storage buckets
const buckets = [
  {
    name: 'avatars',
    public: true,
    allowedMimeTypes: ['image/jpeg', 'image/png', 'image/gif', 'image/webp'],
    fileSizeLimit: 5242880 // 5MB
  },
  {
    name: 'food-images',
    public: true,
    allowedMimeTypes: ['image/jpeg', 'image/png', 'image/gif', 'image/webp'],
    fileSizeLimit: 10485760 // 10MB
  },
  {
    name: 'blog-images',
    public: true,
    allowedMimeTypes: ['image/jpeg', 'image/png', 'image/gif', 'image/webp'],
    fileSizeLimit: 10485760 // 10MB
  }
];

async function setupStorage() {
  try {
    console.log('1. Checking existing buckets...');
    
    const { data: existingBuckets, error: listError } = await supabase.storage.listBuckets();
    
    if (listError) {
      console.log('❌ Error listing buckets:', listError.message);
      return;
    }
    
    const existingBucketNames = existingBuckets.map(bucket => bucket.name);
    console.log('   Existing buckets:', existingBucketNames);
    
    console.log('\n2. Creating missing buckets...');
    
    for (const bucket of buckets) {
      if (existingBucketNames.includes(bucket.name)) {
        console.log(`   ⏭️  Bucket '${bucket.name}' already exists`);
        continue;
      }
      
      console.log(`   Creating bucket '${bucket.name}'...`);
      
      const { error: createError } = await supabase.storage.createBucket(bucket.name, {
        public: bucket.public,
        allowedMimeTypes: bucket.allowedMimeTypes,
        fileSizeLimit: bucket.fileSizeLimit
      });
      
      if (createError) {
        console.log(`   ❌ Error creating bucket '${bucket.name}':`, createError.message);
      } else {
        console.log(`   ✅ Created bucket '${bucket.name}'`);
      }
    }
    
    console.log('\n3. Setting up bucket policies...');
    
    // Set up RLS policies for storage buckets
    const policies = [
      {
        bucket: 'avatars',
        policy: `
          CREATE POLICY "Public avatars are viewable by everyone" ON storage.objects
          FOR SELECT USING (bucket_id = 'avatars');
          
          CREATE POLICY "Users can upload their own avatar" ON storage.objects
          FOR INSERT WITH CHECK (bucket_id = 'avatars' AND auth.uid()::text = (storage.foldername(name))[1]);
          
          CREATE POLICY "Users can update their own avatar" ON storage.objects
          FOR UPDATE USING (bucket_id = 'avatars' AND auth.uid()::text = (storage.foldername(name))[1]);
          
          CREATE POLICY "Users can delete their own avatar" ON storage.objects
          FOR DELETE USING (bucket_id = 'avatars' AND auth.uid()::text = (storage.foldername(name))[1]);
        `
      },
      {
        bucket: 'food-images',
        policy: `
          CREATE POLICY "Food images are viewable by everyone" ON storage.objects
          FOR SELECT USING (bucket_id = 'food-images');
          
          CREATE POLICY "Authenticated users can upload food images" ON storage.objects
          FOR INSERT WITH CHECK (bucket_id = 'food-images' AND auth.role() = 'authenticated');
          
          CREATE POLICY "Users can update their own food images" ON storage.objects
          FOR UPDATE USING (bucket_id = 'food-images' AND auth.uid()::text = (storage.foldername(name))[1]);
          
          CREATE POLICY "Users can delete their own food images" ON storage.objects
          FOR DELETE USING (bucket_id = 'food-images' AND auth.uid()::text = (storage.foldername(name))[1]);
        `
      },
      {
        bucket: 'blog-images',
        policy: `
          CREATE POLICY "Blog images are viewable by everyone" ON storage.objects
          FOR SELECT USING (bucket_id = 'blog-images');
          
          CREATE POLICY "Authenticated users can upload blog images" ON storage.objects
          FOR INSERT WITH CHECK (bucket_id = 'blog-images' AND auth.role() = 'authenticated');
          
          CREATE POLICY "Users can update their own blog images" ON storage.objects
          FOR UPDATE USING (bucket_id = 'blog-images' AND auth.uid()::text = (storage.foldername(name))[1]);
          
          CREATE POLICY "Users can delete their own blog images" ON storage.objects
          FOR DELETE USING (bucket_id = 'blog-images' AND auth.uid()::text = (storage.foldername(name))[1]);
        `
      }
    ];
    
    for (const policy of policies) {
      console.log(`   Setting up policies for '${policy.bucket}' bucket...`);
      
      // Note: Storage policies need to be set up manually in Supabase dashboard
      // or via SQL editor since they require special permissions
      console.log(`   ⚠️  Manual setup required for '${policy.bucket}' bucket policies`);
      console.log(`      Go to Storage > ${policy.bucket} > Policies in your Supabase dashboard`);
    }
    
    console.log('\n4. Testing bucket access...');
    
    // Test if we can access the buckets
    for (const bucket of buckets) {
      try {
        const { data, error } = await supabase.storage.from(bucket.name).list('', { limit: 1 });
        
        if (error) {
          console.log(`   ❌ Error accessing '${bucket.name}' bucket:`, error.message);
        } else {
          console.log(`   ✅ Successfully accessed '${bucket.name}' bucket`);
        }
      } catch (error) {
        console.log(`   ❌ Exception accessing '${bucket.name}' bucket:`, error.message);
      }
    }
    
  } catch (error) {
    console.error('❌ Setup failed:', error);
  }
}

async function main() {
  await setupStorage();
  
  console.log('\n🏁 Storage setup completed!');
  console.log('\nNext steps:');
  console.log('1. Go to your Supabase dashboard > Storage');
  console.log('2. Verify the buckets were created');
  console.log('3. Set up RLS policies for each bucket (if needed)');
  console.log('4. Test file uploads in your app');
}

main().catch(console.error); 