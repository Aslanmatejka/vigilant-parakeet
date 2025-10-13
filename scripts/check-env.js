#!/usr/bin/env node

/**
 * Script to check environment variables and Supabase configuration
 */

console.log('🔍 Environment Variables Check\n');

// Check for environment variables
const envVars = {
  'NODE_ENV': process.env.NODE_ENV,
  'SUPABASE_URL': process.env.SUPABASE_URL,
  'SUPABASE_ANON_KEY': process.env.SUPABASE_ANON_KEY,
  'VITE_SUPABASE_URL': process.env.VITE_SUPABASE_URL,
  'VITE_SUPABASE_ANON_KEY': process.env.VITE_SUPABASE_ANON_KEY
};

console.log('1. Environment Variables:');
Object.entries(envVars).forEach(([key, value]) => {
  if (value) {
    console.log(`   ✅ ${key}: ${key.includes('KEY') ? value.substring(0, 20) + '...' : value}`);
  } else {
    console.log(`   ❌ ${key}: Not set`);
  }
});

// Check if we can read the config files
console.log('\n2. Configuration Files:');
const fs = require('fs');
const path = require('path');

const configFiles = [
  'config/env.local',
  'config/env.production',
  'config/env.development',
  'config/env.deploy'
];

configFiles.forEach(filePath => {
  try {
    if (fs.existsSync(filePath)) {
      const content = fs.readFileSync(filePath, 'utf8');
      const hasSupabaseUrl = content.includes('SUPABASE_URL') || content.includes('VITE_SUPABASE_URL');
      const hasSupabaseKey = content.includes('SUPABASE_ANON_KEY') || content.includes('VITE_SUPABASE_ANON_KEY');
      
      if (hasSupabaseUrl && hasSupabaseKey) {
        console.log(`   ✅ ${filePath}: Contains Supabase config`);
      } else {
        console.log(`   ⚠️  ${filePath}: Missing some Supabase config`);
      }
    } else {
      console.log(`   ❌ ${filePath}: File not found`);
    }
  } catch (error) {
    console.log(`   ❌ ${filePath}: Error reading file - ${error.message}`);
  }
});

// Check supabaseClient.js
console.log('\n3. Supabase Client Configuration:');
try {
  const supabaseClientPath = 'utils/supabaseClient.js';
  if (fs.existsSync(supabaseClientPath)) {
    const content = fs.readFileSync(supabaseClientPath, 'utf8');
    
    if (content.includes('import.meta.env.VITE_SUPABASE_URL')) {
      console.log('   ✅ supabaseClient.js: Uses Vite environment variables');
    } else if (content.includes('process.env.SUPABASE_URL')) {
      console.log('   ✅ supabaseClient.js: Uses Node environment variables');
    } else {
      console.log('   ❌ supabaseClient.js: No environment variable usage found');
    }
    
    if (content.includes('Missing Supabase configuration')) {
      console.log('   ✅ supabaseClient.js: Has error handling for missing config');
    } else {
      console.log('   ⚠️  supabaseClient.js: Missing error handling for missing config');
    }
  } else {
    console.log('   ❌ supabaseClient.js: File not found');
  }
} catch (error) {
  console.log('   ❌ Error checking supabaseClient.js:', error.message);
}

// Check package.json for type
console.log('\n4. Package Configuration:');
try {
  const packagePath = 'package.json';
  if (fs.existsSync(packagePath)) {
    const packageJson = JSON.parse(fs.readFileSync(packagePath, 'utf8'));
    
    if (packageJson.type === 'module') {
      console.log('   ✅ package.json: Type is "module" (ES modules)');
    } else {
      console.log('   ⚠️  package.json: Type is not "module" (CommonJS)');
    }
    
    if (packageJson.scripts && packageJson.scripts.dev) {
      console.log('   ✅ package.json: Has dev script');
    } else {
      console.log('   ❌ package.json: Missing dev script');
    }
  } else {
    console.log('   ❌ package.json: File not found');
  }
} catch (error) {
  console.log('   ❌ Error checking package.json:', error.message);
}

console.log('\n🏁 Environment check completed!');
console.log('\nIf you see ❌ errors above:');
console.log('1. Set the missing environment variables');
console.log('2. Check your configuration files');
console.log('3. Verify Supabase project is accessible'); 