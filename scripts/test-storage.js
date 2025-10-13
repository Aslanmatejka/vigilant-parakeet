#!/usr/bin/env node

/**
 * Script to test Supabase storage buckets
 */

import { createClient } from '@supabase/supabase-js';

const supabaseUrl = 'https://ifzbpqyuhnxbhdcnmvfs.supabase.co';
const supabaseKey = 'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImlmemJwcXl1aG54YmhkY25tdmZzIiwicm9sZSI6ImFub24iLCJpYXQiOjE3NTYwNTI5NTgsImV4cCI6MjA3MTYyODk1OH0.ivjNXt8z704sVv6Jt2Z3tVkkelUzeb8Ih4SaCQFHerk';

console.log('🧪 Testing Supabase Storage...\n');

const supabase = createClient(supabaseUrl, supabaseKey);

async function testStorage() {
  try {
    console.log('1. Listing all storage buckets...');
    
    const { data: buckets, error: bucketsError } = await supabase.storage.listBuckets();
    
    if (bucketsError) {
      console.log('❌ Error listing buckets:', bucketsError.message);
      return;
    }
    
    console.log('   Available buckets:');
    buckets.forEach(bucket => {
      console.log(`   - ${bucket.name} (public: ${bucket.public}, size limit: ${bucket.file_size_limit} bytes)`);
    });
    
    if (buckets.length === 0) {
      console.log('   No buckets found!');
      return;
    }
    
    console.log('\n2. Testing bucket access...');
    
    const requiredBuckets = ['avatars', 'food-images', 'blog-images'];
    
    for (const bucketName of requiredBuckets) {
      const bucket = buckets.find(b => b.name === bucketName);
      
      if (bucket) {
        console.log(`   ✅ Bucket '${bucketName}' exists`);
        
        // Test listing files in the bucket
        try {
          const { data: files, error: listError } = await supabase.storage
            .from(bucketName)
            .list('', { limit: 5 });
          
          if (listError) {
            console.log(`      ❌ Error listing files: ${listError.message}`);
          } else {
            console.log(`      📁 Files in bucket: ${files.length}`);
            if (files.length > 0) {
              files.forEach(file => {
                console.log(`        - ${file.name} (${file.metadata?.size || 'unknown'} bytes)`);
              });
            }
          }
        } catch (error) {
          console.log(`      ❌ Exception listing files: ${error.message}`);
        }
      } else {
        console.log(`   ❌ Bucket '${bucketName}' missing`);
      }
    }
    
    console.log('\n3. Testing file upload (small test)...');
    
    // Test with a small text file
    const testContent = 'This is a test file for storage bucket testing';
    const testBlob = new Blob([testContent], { type: 'text/plain' });
    const testFile = new File([testBlob], 'test.txt', { type: 'text/plain' });
    
    // Try to upload to food-images bucket
    try {
      const { data: uploadData, error: uploadError } = await supabase.storage
        .from('food-images')
        .upload(`test-${Date.now()}.txt`, testFile);
      
      if (uploadError) {
        console.log(`   ❌ Upload failed: ${uploadError.message}`);
        console.log(`      Code: ${uploadError.code}`);
        console.log(`      Details: ${uploadError.details}`);
      } else {
        console.log(`   ✅ Upload successful: ${uploadData.path}`);
        
        // Try to get public URL
        const { data: { publicUrl } } = supabase.storage
          .from('food-images')
          .getPublicUrl(uploadData.path);
        
        console.log(`      Public URL: ${publicUrl}`);
        
        // Clean up - delete the test file
        const { error: deleteError } = await supabase.storage
          .from('food-images')
          .remove([uploadData.path]);
        
        if (deleteError) {
          console.log(`      ⚠️  Could not delete test file: ${deleteError.message}`);
        } else {
          console.log(`      🗑️  Test file deleted`);
        }
      }
    } catch (error) {
      console.log(`   ❌ Upload exception: ${error.message}`);
    }
    
  } catch (error) {
    console.error('❌ Storage test failed:', error);
  }
}

async function main() {
  await testStorage();
  
  console.log('\n🏁 Storage test completed!');
  console.log('\nIf you see ❌ errors above:');
  console.log('1. Check if storage buckets exist in Supabase dashboard');
  console.log('2. Verify bucket permissions and policies');
  console.log('3. Check if RLS policies are blocking storage operations');
}

main().catch(console.error); 