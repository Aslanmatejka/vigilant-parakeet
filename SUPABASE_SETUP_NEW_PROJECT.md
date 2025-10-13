# 🚨 URGENT: Supabase Project Setup Required

## Current Issue
The Supabase project URL `https://ctnieyoayctlyvmvuhdm.supabase.co` is **NOT ACCESSIBLE**.
This means:
- ❌ The project has been deleted
- ❌ The project is suspended
- ❌ The URL is incorrect
- ❌ Signup/signin will NOT work

## Solution: Create New Supabase Project

### Step 1: Go to Supabase
1. Visit [https://supabase.com](https://supabase.com)
2. Click "Start your project" or "Sign In"
3. Sign in with GitHub, Google, or email

### Step 2: Create New Project
1. Click "New Project"
2. Choose your organization
3. Enter project details:
   - **Name**: `dogoods-app` (or your preferred name)
   - **Database Password**: Create a strong password (save this!)
   - **Region**: Choose closest to your users
4. Click "Create new project"

### Step 3: Get Project Credentials
1. Wait for project to be ready (2-3 minutes)
2. Go to **Settings** → **API**
3. Copy these values:
   - **Project URL** (looks like: `https://abcdefghijklmnop.supabase.co`)
   - **Anon public key** (starts with `eyJ...`)

### Step 4: Update Configuration Files

#### Update `utils/supabaseClient.js`:
```javascript
// Replace the hardcoded URL with your new project URL
const supabaseUrl = import.meta.env.VITE_SUPABASE_URL || 'https://YOUR_NEW_PROJECT_URL.supabase.co'
const supabaseKey = import.meta.env.VITE_SUPABASE_ANON_KEY || 'YOUR_NEW_ANON_KEY'
```

#### Update environment files:
```bash
# config/env.production
SUPABASE_URL=https://YOUR_NEW_PROJECT_URL.supabase.co
SUPABASE_ANON_KEY=YOUR_NEW_ANON_KEY

# config/env.local
VITE_SUPABASE_URL=https://YOUR_NEW_PROJECT_URL.supabase.co
VITE_SUPABASE_ANON_KEY=YOUR_NEW_ANON_KEY

# config/env.deploy
SUPABASE_URL=https://YOUR_NEW_PROJECT_URL.supabase.co
SUPABASE_ANON_KEY=YOUR_NEW_ANON_KEY
```

### Step 5: Set Up Database Schema
1. Go to **SQL Editor** in your Supabase dashboard
2. Run the migration files from `supabase/migrations/`:

```sql
-- Start with 001_initial_schema.sql
-- Then run the others in order
```

### Step 6: Configure Authentication
1. Go to **Authentication** → **Settings**
2. Set **Site URL** to your deployment URL
3. Add redirect URLs:
   - `http://localhost:3000`
   - `http://localhost:3001`
   - Your production domain

### Step 7: Test Connection
Run the test script:
```bash
node scripts/test-supabase.js
```

## Alternative: Use Local Supabase

If you prefer to develop locally:

### Install Supabase CLI
```bash
# macOS
brew install supabase/tap/supabase

# Or download from: https://supabase.com/docs/guides/cli
```

### Start Local Instance
```bash
supabase start
```

### Update Configuration
```javascript
// Use local URLs
const supabaseUrl = 'http://127.0.0.1:54321'
const supabaseKey = 'your-local-anon-key'
```

## Quick Fix for Testing

To test immediately, you can temporarily use a working Supabase project:

1. Create a free project at [supabase.com](https://supabase.com)
2. Get the URL and anon key
3. Update the configuration files
4. Test signup/signin

## Next Steps

1. **IMMEDIATE**: Create new Supabase project
2. **Update**: All configuration files with new credentials
3. **Test**: Run test script to verify connection
4. **Deploy**: Your app should work after updating credentials

## Support

If you need help:
1. Check [Supabase documentation](https://supabase.com/docs)
2. Join [Supabase Discord](https://discord.supabase.com)
3. Check [GitHub issues](https://github.com/supabase/supabase/issues)

---

**⚠️ IMPORTANT**: Your app will NOT work for signup/signin until you create a new Supabase project and update the configuration! 