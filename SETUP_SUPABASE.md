# Supabase Setup Guide for Deployment

## Current Configuration Status

Your project is configured to use a production Supabase instance at:
- **URL**: `https://ctnieyoayctlyvmvuhdm.supabase.co`
- **Status**: ✅ Configured

## Environment Files Created

1. **`config/env.production`** - Production environment variables
2. **`config/env.development`** - Development environment variables  
3. **`config/env.local`** - Local development with production Supabase
4. **`config/env.deploy`** - Deployment configuration

## Required Environment Variables

For your deployment, you need to set these environment variables:

```bash
# Supabase Configuration
VITE_SUPABASE_URL=https://ctnieyoayctlyvmvuhdm.supabase.co
VITE_SUPABASE_ANON_KEY=eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImN0bmlleW9heWN0bHl2bXZ1aGRtIiwicm9sZSI6ImFub24iLCJpYXQiOjE3NTM1MzU5MTIsImV4cCI6MjA2OTExMTkxMn0.dqKMBrogMlA0SFObd34znqUpwwR026tzOLQ18EMWNvI

# Environment
NODE_ENV=production
```

## Deployment Steps

### 1. Set Environment Variables

In your deployment platform (Vercel, Netlify, etc.), set these environment variables:

- `VITE_SUPABASE_URL`
- `VITE_SUPABASE_ANON_KEY`

### 2. Build and Deploy

```bash
# Install dependencies
npm install

# Build for production
npm run build

# Deploy the dist/ folder
```

### 3. Verify Supabase Connection

After deployment, check the browser console for:
- ✅ "🔌 Connecting to Supabase: https://ctnieyoayctlyvmvuhdm.supabase.co"
- ✅ No connection errors

## Potential Issues and Solutions

### Issue 1: Missing Environment Variables
**Error**: "Missing Supabase configuration"
**Solution**: Ensure `VITE_SUPABASE_URL` and `VITE_SUPABASE_ANON_KEY` are set

### Issue 2: CORS Errors
**Error**: CORS policy blocking requests
**Solution**: Check Supabase project settings for allowed origins

### Issue 3: RLS Policies
**Error**: Row Level Security blocking operations
**Solution**: Current RLS policies are configured correctly

### Issue 4: Database Schema
**Error**: Table doesn't exist
**Solution**: Run migrations on your production Supabase instance

## Testing Signup/Signin

1. **Signup Flow**:
   - User fills form → `authService.signUp()` → Supabase auth → Profile creation trigger
   - Check browser console for any errors

2. **Signin Flow**:
   - User enters credentials → `authService.signIn()` → Supabase auth → Session established
   - Check browser console for any errors

## Monitoring and Debugging

### Browser Console
Look for these messages:
- 🔌 Connecting to Supabase: [URL]
- 🌍 Environment: [mode]
- Any error messages during auth operations

### Network Tab
Check for:
- Successful requests to Supabase endpoints
- Any failed requests with error details

### Supabase Dashboard
Monitor:
- Authentication logs
- Database queries
- Real-time subscriptions

## Next Steps

1. ✅ Environment files created
2. ✅ Supabase client configured
3. ✅ Vite config updated
4. 🔄 Deploy and test
5. 🔄 Monitor for errors
6. 🔄 Fix any issues found

## Support

If you encounter issues:
1. Check browser console for errors
2. Verify environment variables are set
3. Check Supabase project status
4. Review RLS policies
5. Test with a simple signup/signin flow 