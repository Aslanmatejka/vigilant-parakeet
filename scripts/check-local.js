#!/usr/bin/env node

const { createClient } = require('@supabase/supabase-js');

console.log('🔧 DoGoods Local Development Environment');
console.log('========================================');
console.log('');

// Local Supabase configuration
const supabaseUrl = 'http://127.0.0.1:54321';
const supabaseKey = 'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZS1kZW1vIiwicm9sZSI6ImFub24iLCJleHAiOjE5ODM4MTI5OTZ9.CRXP1A7WOeoJeXxjNni43kdQwgnWNReilDMblYTn_I0';

console.log('📍 Service URLs:');
console.log(`   App: http://localhost:3000`);
console.log(`   API: ${supabaseUrl}`);
console.log(`   Studio: http://127.0.0.1:54323`);
console.log(`   Inbucket (Email): http://127.0.0.1:54324`);
console.log(`   Database: postgresql://postgres:postgres@127.0.0.1:54322/postgres`);
console.log('');

// Test connection
async function testConnection() {
  try {
    console.log('🔌 Testing Supabase connection...');
    
    const supabase = createClient(supabaseUrl, supabaseKey);
    
    // Test basic connectivity
    const { data, error } = await supabase.from('users').select('count').limit(1);
    
    if (error && error.code !== 'PGRST116') { // PGRST116 = table doesn't exist (which is fine)
      console.log('❌ Connection failed:', error.message);
      process.exit(1);
    }
    
    console.log('✅ Supabase connection successful!');
    console.log('');
    
    console.log('🚀 Quick Start Commands:');
    console.log('   npm run dev              - Start development server');
    console.log('   npm run supabase:studio  - Open database studio');
    console.log('   npm run supabase:reset   - Reset local database');
    console.log('   npm run supabase:stop    - Stop local Supabase');
    console.log('');
    
  } catch (err) {
    console.log('❌ Connection test failed:', err.message);
    console.log('Make sure local Supabase is running: npm run supabase:start');
    process.exit(1);
  }
}

testConnection();
