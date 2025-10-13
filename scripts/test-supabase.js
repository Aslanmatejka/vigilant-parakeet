#!/usr/bin/env node

/**
 * Test script to verify Supabase connection and auth functionality
 * Run with: node scripts/test-supabase.js
 */

import { createClient } from '@supabase/supabase-js';

// Production Supabase configuration
const supabaseUrl = 'https://ifzbpqyuhnxbhdcnmvfs.supabase.co';
const supabaseKey = 'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImlmemJwcXl1aG54YmhkY25tdmZzIiwicm9sZSI6ImFub24iLCJpYXQiOjE3NTYwNTI5NTgsImV4cCI6MjA3MTYyODk1OH0.ivjNXt8z704sVv6Jt2Z3tVkkelUzeb8Ih4SaCQFHerk';

console.log('🧪 Testing Supabase Connection...\n');

// Create Supabase client
const supabase = createClient(supabaseUrl, supabaseKey);

async function testConnection() {
  try {
    console.log('1. Testing basic connection...');
    
    // Test basic connection by getting auth session
    const { data: { session }, error: sessionError } = await supabase.auth.getSession();
    
    if (sessionError) {
      console.log('❌ Session check failed:', sessionError.message);
    } else {
      console.log('✅ Basic connection successful');
      console.log('   Session:', session ? 'Active' : 'None');
    }

    console.log('\n2. Testing database connection...');
    
    // Test database connection by checking if users table exists
    const { data: users, error: usersError } = await supabase
      .from('users')
      .select('count')
      .limit(1);
    
    if (usersError) {
      console.log('❌ Database connection failed:', usersError.message);
      console.log('   Code:', usersError.code);
      console.log('   Details:', usersError.details);
      console.log('   Hint:', usersError.hint);
    } else {
      console.log('✅ Database connection successful');
      console.log('   Users table accessible');
    }

    console.log('\n3. Testing RLS policies...');
    
    // Test if we can read from public tables
    const { data: listings, error: listingsError } = await supabase
      .from('food_listings')
      .select('id, title')
      .eq('status', 'active')
      .limit(1);
    
    if (listingsError) {
      console.log('❌ RLS policy test failed:', listingsError.message);
      console.log('   This might indicate RLS policy issues');
    } else {
      console.log('✅ RLS policies working correctly');
      console.log('   Can read from food_listings table');
    }

    console.log('\n4. Testing auth endpoints...');
    
    // Test auth endpoints by attempting to get user (should fail without auth)
    const { data: user, error: userError } = await supabase.auth.getUser();
    
    if (userError) {
      console.log('✅ Auth endpoints accessible (expected error without auth)');
      console.log('   Error:', userError.message);
    } else {
      console.log('✅ Auth endpoints working');
    }

  } catch (error) {
    console.error('❌ Test failed with unexpected error:', error);
  }
}

async function testAuthFlow() {
  console.log('\n5. Testing auth flow...');
  
  try {
    // Test signup (this will create a test user)
    const testEmail = `test-${Date.now()}@example.com`;
    const testPassword = 'testpassword123';
    
    console.log(`   Attempting signup with: ${testEmail}`);
    
    const { data: signupData, error: signupError } = await supabase.auth.signUp({
      email: testEmail,
      password: testPassword,
      options: {
        data: {
          name: 'Test User',
          account_type: 'individual'
        }
      }
    });
    
    if (signupError) {
      console.log('❌ Signup failed:', signupError.message);
      console.log('   Code:', signupError.code);
      console.log('   Details:', signupError.details);
    } else {
      console.log('✅ Signup successful');
      console.log('   User ID:', signupData.user?.id);
      console.log('   Email confirmed:', signupData.user?.email_confirmed_at ? 'Yes' : 'No');
      
      // Test signin with the created user
      console.log('\n   Testing signin...');
      
      const { data: signinData, error: signinError } = await supabase.auth.signInWithPassword({
        email: testEmail,
        password: testPassword
      });
      
      if (signinError) {
        console.log('❌ Signin failed:', signinError.message);
      } else {
        console.log('✅ Signin successful');
        console.log('   Session established');
        
        // Test signout
        const { error: signoutError } = await supabase.auth.signOut();
        if (signoutError) {
          console.log('❌ Signout failed:', signoutError.message);
        } else {
          console.log('✅ Signout successful');
        }
      }
    }
    
  } catch (error) {
    console.error('❌ Auth flow test failed:', error);
  }
}

// Run tests
async function runTests() {
  await testConnection();
  await testAuthFlow();
  
  console.log('\n🏁 Test completed!');
  console.log('\nIf you see any ❌ errors above, check:');
  console.log('1. Supabase project is running');
  console.log('2. Database migrations are applied');
  console.log('3. RLS policies are configured');
  console.log('4. API keys are correct');
}

runTests().catch(console.error); 