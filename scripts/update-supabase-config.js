#!/usr/bin/env node

/**
 * Quick script to update all Supabase configuration files
 * Usage: node scripts/update-supabase-config.js <NEW_URL> <NEW_ANON_KEY>
 * Example: node scripts/update-supabase-config.js https://newproject.supabase.co eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...
 */

import fs from 'fs';
import path from 'path';

const args = process.argv.slice(2);

if (args.length !== 2) {
  console.log('❌ Usage: node scripts/update-supabase-config.js <NEW_URL> <NEW_ANON_KEY>');
  console.log('Example: node scripts/update-supabase-config.js https://newproject.supabase.co eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...');
  process.exit(1);
}

const [newUrl, newAnonKey] = args;

// Validate URL format
if (!newUrl.includes('supabase.co')) {
  console.log('❌ Invalid Supabase URL. Should contain "supabase.co"');
  process.exit(1);
}

// Validate anon key format
if (!newAnonKey.startsWith('eyJ')) {
  console.log('❌ Invalid anon key format. Should start with "eyJ"');
  process.exit(1);
}

console.log('🔄 Updating Supabase configuration...\n');

const filesToUpdate = [
  'utils/supabaseClient.js',
  'config/env.production',
  'config/env.local',
  'config/env.deploy',
  'scripts/test-supabase.js'
];

let updatedCount = 0;

filesToUpdate.forEach(filePath => {
  try {
    if (fs.existsSync(filePath)) {
      let content = fs.readFileSync(filePath, 'utf8');
      let fileUpdated = false;
      
      // Update the old URL
      if (content.includes('ctnieyoayctlyvmvuhdm.supabase.co')) {
        content = content.replace(/ctnieyoayctlyvmvuhdm\.supabase\.co/g, newUrl.replace('https://', ''));
        fileUpdated = true;
      }
      
      // Update the old anon key
      if (content.includes('eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImN0bmlleW9heWN0bHl2bXZ1aGRtIiwicm9sZSI6ImFub24iLCJpYXQiOjE3NTM1MzU5MTIsImV4cCI6MjA2OTExMTkxMn0.dqKMBrogMlA0SFObd34znqUpwwR026tzOLQ18EMWNvI')) {
        content = content.replace(/eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImN0bmlleW9heWN0bHl2bXZ1aGRtIiwicm9sZSI6ImFub24iLCJpYXQiOjE3NTM1MzU5MTIsImV4cCI6MjA2OTExMTkxMn0.dqKMBrogMlA0SFObd34znqUpwwR026tzOLQ18EMWNvI/g, newAnonKey);
        fileUpdated = true;
      }
      
      if (fileUpdated) {
        fs.writeFileSync(filePath, content);
        console.log(`✅ Updated: ${filePath}`);
        updatedCount++;
      } else {
        console.log(`⏭️  No changes needed: ${filePath}`);
      }
    } else {
      console.log(`⚠️  File not found: ${filePath}`);
    }
  } catch (error) {
    console.log(`❌ Error updating ${filePath}:`, error.message);
  }
});

console.log(`\n🏁 Update complete! Updated ${updatedCount} files.`);
console.log('\nNext steps:');
console.log('1. Test the connection: node scripts/test-supabase.js');
console.log('2. Start your app: npm run dev');
console.log('3. Try signing up/signing in');

// Also update the .env.local file if it exists
const envLocalPath = '.env.local';
if (fs.existsSync(envLocalPath)) {
  try {
    let envContent = fs.readFileSync(envLocalPath, 'utf8');
    let envUpdated = false;
    
    if (envContent.includes('ctnieyoayctlyvmvuhdm.supabase.co')) {
      envContent = envContent.replace(/ctnieyoayctlyvmvuhdm\.supabase\.co/g, newUrl.replace('https://', ''));
      envUpdated = true;
    }
    
    if (envContent.includes('eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImN0bmlleW9heWN0bHl2bXZ1aGRtIiwicm9sZSI6ImFub24iLCJpYXQiOjE3NTM1MzU5MTIsImV4cCI6MjA2OTExMTkxMn0.dqKMBrogMlA0SFObd34znqUpwwR026tzOLQ18EMWNvI')) {
      envContent = envContent.replace(/eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImN0bmlleW9heWN0bHl2bXZ1aGRtIiwicm9sZSI6ImFub24iLCJpYXQiOjE3NTM1MzU5MTIsImV4cCI6MjA2OTExMTkxMn0.dqKMBrogMlA0SFObd34znqUpwwR026tzOLQ18EMWNvI/g, newAnonKey);
      envUpdated = true;
    }
    
    if (envUpdated) {
      fs.writeFileSync(envLocalPath, envContent);
      console.log(`✅ Updated: ${envLocalPath}`);
    }
  } catch (error) {
    console.log(`⚠️  Could not update ${envLocalPath}:`, error.message);
  }
} 