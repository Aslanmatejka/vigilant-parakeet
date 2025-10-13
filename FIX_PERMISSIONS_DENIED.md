# Fixing the 'Permission Denied for Table Users' Error

## Current Status

Your authentication is working correctly:

- You are successfully logged in
- Your session token is valid
- Your user ID is: c4dcbd93-081e-4160-87eb-1d51d444413a

However, you're encountering a Supabase error:

```
permission denied for table users
```

This means your Supabase Row Level Security (RLS) policies need to be configured.

## Steps to Fix

### 1. Apply the RLS Policies

1. Log in to your Supabase dashboard at https://app.supabase.com
2. Navigate to your project (URL: `ifzbpqyuhnxbhdcnmvfs`)
3. Go to the SQL Editor
4. Copy the entire contents of `supabase/migrations/fix_permissions.sql`
5. Paste it into the SQL Editor
6. Click "Run" to execute the SQL statements

### 2. Verify/Set Your Admin Status

1. Run the SQL in `supabase/migrations/set_admin.sql` to:
   - Check if your user is an admin
   - Make your user an admin if needed

### 3. Test Again

After applying the SQL changes:

1. Refresh your application
2. Try accessing the admin dashboard again

## Why This Works

The RLS policies will:

1. Enable Row Level Security on your tables
2. Allow users to read their own records
3. Allow admins to read all user records and food claims
4. Allow users to read their own claims
5. Allow donors to read claims on their donations

## Still Having Issues?

If you're still encountering permission issues after applying the SQL:

1. Check the Supabase Logs in your dashboard
2. Verify the table names match your actual database structure
3. Check column names (especially `is_admin`, `claimant_id`, `donor_id`)
4. Try creating a simplified version of the policies for testing
