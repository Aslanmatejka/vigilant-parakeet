# Fixing Supabase Permission Issues

## The Problem

You're encountering the following errors:

1. **401 Unauthorized**: When trying to access the `food_claims` table.
2. **Permission denied for table users**: RLS (Row Level Security) policies preventing access.

## How to Fix

### 1. Run the SQL Migration

1. Go to [Supabase Dashboard](https://app.supabase.com)
2. Open your project (`ifzbpqyuhnxbhdcnmvfs`)
3. Navigate to the SQL Editor
4. Copy and paste the contents of `supabase/migrations/fix_permissions.sql`
5. Run the SQL script

### 2. Debug Your Authentication

Import the debug utility functions:

```javascript
import { checkSupabaseAuth, debugAuthState } from "./utils/authDebug";
```

Add this code to your component to check authentication status:

```javascript
useEffect(() => {
  async function checkAuth() {
    const authState = await debugAuthState();
    console.log("Auth state:", authState);
  }

  checkAuth();
}, []);
```

### 3. Common Issues and Solutions

#### Invalid or Missing Token

If the debug shows no active session or invalid token:

1. Make sure you're properly signing in users
2. Check that token persistence is enabled (it is in your supabaseClient.js)
3. Verify the token isn't being cleared accidentally

#### Session Expiration

If sessions are expiring too quickly:

1. Check your Supabase project settings for token lifetime
2. Make sure autoRefreshToken is enabled (it is in your configuration)

### 4. Testing Your Fix

1. Sign in to your application
2. Use the browser console to run `debugAuthState()`
3. Try accessing the admin dashboard again

## Need More Help?

If the issue persists:

1. Check the Supabase logs in the dashboard
2. Look for any 401/403 errors in the network tab
3. Verify your environment variables are correctly set
