
import { createClient } from '@supabase/supabase-js'

// Get environment variables — guard `process` so a missing VITE_ var
// doesn't ReferenceError in the browser (Vite only inlines NODE_ENV).
const nodeEnv = (typeof process !== 'undefined' && process.env) || {}
const supabaseUrl = import.meta.env.VITE_SUPABASE_URL || nodeEnv.SUPABASE_URL
const supabaseKey = import.meta.env.VITE_SUPABASE_ANON_KEY || nodeEnv.SUPABASE_ANON_KEY

// Validate configuration
if (!supabaseUrl || !supabaseKey) {
  console.error('❌ Missing Supabase configuration!')
  console.error('Please set VITE_SUPABASE_URL and VITE_SUPABASE_ANON_KEY environment variables')
  throw new Error('Missing Supabase configuration')
}

console.log(`🔌 Connecting to Supabase: ${supabaseUrl}`)
console.log(`🌍 Environment: ${import.meta.env.MODE || 'development'}`)

const supabase = createClient(supabaseUrl, supabaseKey, {
  auth: {
    autoRefreshToken: true,
    persistSession: true,
    detectSessionInUrl: true
  },
  realtime: {
    params: {
      eventsPerSecond: 10
    }
  },
  global: {
    headers: {
      'X-Client-Info': 'dogoods-app'
    }
  },
  db: {
    schema: 'public'
  }
})

// Derive the localStorage key Supabase uses for auth tokens
// Format: sb-{project_ref}-auth-token where project_ref is the subdomain
const projectRef = new URL(supabaseUrl).hostname.split('.')[0]
export const SUPABASE_AUTH_KEY = `sb-${projectRef}-auth-token`

export default supabase