# Authentication Fix for Supabase Requests

You were getting errors with Supabase authentication when making requests to the `food_claims` table. I've made the following fixes:

## Changes Made

1. **Updated `dataService.js`** to check for an active session before making requests to Supabase
2. **Improved error handling** in the AdminClaimDashboard component
3. **Added authentication utilities** in `authDebug.js` including a new `ensureAuthenticated()` function

## How to Test the Fix

1. Open your browser's developer console (F12)
2. Run this code in the console to check your authentication status:
   ```javascript
   import("/src/utils/authDebug.js").then((m) => m.debugAuthState());
   ```
3. If not authenticated, log in to your application
4. Try accessing the admin dashboard again to see if the food claims load

## Common Issues to Check

If you're still having problems:

1. **Session Storage**: Make sure your browser isn't blocking cookies or local storage
2. **Authentication Flow**: Verify that login is working correctly
3. **Supabase RLS Policies**: You may still need to apply the RLS policies in the SQL file I provided

## Example for Using ensureAuthenticated

```javascript
import { ensureAuthenticated } from "../utils/authDebug";

async function fetchProtectedData() {
  try {
    // Will throw an error if not authenticated
    await ensureAuthenticated();

    // Now make your Supabase request
    const { data, error } = await supabase.from("food_claims").select("*");

    // Handle the result
  } catch (error) {
    // Handle authentication errors
    console.error(error);
  }
}
```

This pattern ensures you're always checking authentication before making protected requests.
