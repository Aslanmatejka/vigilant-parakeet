# Authentication Troubleshooting Guide

## Current Issue

You're seeing this error when trying to access the admin dashboard:

```
Error: User is not authenticated. Please log in.
```

## What's Been Fixed

1. Added proper authentication check in `AdminRoute.jsx`
2. Updated `app.jsx` to use AdminRoute for admin pages
3. Added debugging tools to help diagnose issues

## How to Fix Your Authentication Issues

### 1. Make Sure You're Logged In

First, check if you're actually logged in:

```javascript
// Run this in your browser console
import("/src/utils/login-check.js").then((m) => m.checkLoginStatus());
```

This will show you if you're authenticated and if your session is working.

### 2. Check Your Admin Status

Make sure your user is marked as an admin in the database:

1. Go to your Supabase dashboard
2. Navigate to Table Editor > users
3. Find your user and check the `is_admin` field (set to true)

### 3. Update RLS Policies

If you're still having issues, apply the SQL from `supabase/migrations/fix_permissions.sql`:

1. Go to your Supabase dashboard
2. Open the SQL Editor
3. Paste in the contents of the file and run it

### 4. Test Login Manually

If automatic login isn't working, try manually logging in:

1. Go to the login page
2. Enter your credentials
3. After login, check console with:
   ```javascript
   import("/src/utils/login-check.js").then((m) => m.checkLoginStatus());
   ```

### 5. Clear Local Storage (Last Resort)

If all else fails, try clearing your local storage:

1. Open Chrome DevTools (F12)
2. Go to Application > Storage > Local Storage
3. Clear all items for your site
4. Refresh and log in again

## How the Fix Works

The new system:

1. Uses `AdminRoute` to protect admin pages
2. Checks both authentication AND admin status
3. Redirects to login if not authenticated
4. Shows a clear error if authenticated but not an admin

## Need More Help?

If you're still having issues:

1. Check Supabase logs for auth errors
2. Verify your environment variables are correct
3. Try using an incognito window to rule out cached issues
