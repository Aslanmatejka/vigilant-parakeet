// Inject is_admin claim into Supabase session for local admin testing
import supabase, { SUPABASE_AUTH_KEY } from './supabaseClient.js';

import { reportError } from './helpers.js'

class AuthService {
  constructor() {
    this.currentUser = null
    this.isAuthenticated = false
    this.isAdmin = false
    this.listeners = []
    this._initPromise = null
    this._initialized = false
    this._userExplicitlySignedOut = false
    this._signingIn = false

    // Restore from localStorage if available (synchronous, immediate)
    const storedUser = localStorage.getItem('currentUser')
    const storedAuth = localStorage.getItem('userAuthenticated')
    if (storedUser && storedAuth === 'true') {
      try {
        this.currentUser = JSON.parse(storedUser)
        this.isAuthenticated = true
        this.isAdmin = this.currentUser.role === 'admin' || this.currentUser.is_admin === true
      } catch (e) {
        this.currentUser = null
        this.isAuthenticated = false
        this.isAdmin = false
      }
    }

    // NOTE: Do NOT call this.init() here. Let AuthContext call it once.
  }

  async init() {
    // Idempotent: only run once, return the same promise for subsequent calls
    if (this._initPromise) {
      return this._initPromise
    }

    this._initPromise = this._doInit()
    return this._initPromise
  }

  async _doInit() {
    try {
      // Step 1: Try to get the current session from Supabase
      const { data: { session }, error: sessionError } = await supabase.auth.getSession()

      if (session) {
        // Valid Supabase session found - sync our state with it
        await this.setUser(session.user)
      } else if (sessionError) {
        // Network error or other issue - keep localStorage state so user stays on page
        console.warn('getSession error, keeping local state:', sessionError.message)
      } else {
        // No session and no error: user is truly signed out.
        // Clear any stale localStorage state so they don't appear logged in.
        if (this.isAuthenticated) {
          this.clearUser()
        }
      }

      // Step 2: Listen for future auth changes
      const { data: { subscription } } = supabase.auth.onAuthStateChange(async (event, session) => {
        if (event === 'INITIAL_SESSION') {
          // Already handled above via getSession - skip
          return
        } else if (event === 'SIGNED_IN' && session) {
          this._userExplicitlySignedOut = false
          // Skip if signIn() is already handling setUser to avoid duplicate calls
          if (!this._signingIn) {
            await this.setUser(session.user)
          }
        } else if (event === 'TOKEN_REFRESHED' && session) {
          // Honor a recent explicit sign-out: a refresh event queued before
          // the user clicked Sign Out would otherwise silently re-authenticate.
          if (this._userExplicitlySignedOut) return
          await this.setUser(session.user)
        } else if (event === 'PASSWORD_RECOVERY' && session) {
          if (this._userExplicitlySignedOut) return
          await this.setUser(session.user)
        } else if (event === 'SIGNED_OUT') {
          // Always clear state when Supabase says signed out.
          // This handles both explicit sign-out and session expiry.
          this.clearUser()
          this._userExplicitlySignedOut = false
        }
      })

      this._authSubscription = subscription
      this._initialized = true
    } catch (error) {
      console.error('Auth initialization error:', error)
      reportError(error)
      this._initialized = true
    }
  }

  async setUser(user) {
    try {
      // Get user profile from database, but don't let a hung JS client block login.
      // If the query doesn't complete within 4s, fall back to auth-only data and
      // refresh the profile in the background.
      const PROFILE_TIMEOUT_MS = 4000
      let profile = null
      let error = null
      let timedOut = false
      try {
        const profilePromise = supabase
          .from('users')
          .select('*')
          .eq('id', user.id)
          .single()
        const result = await Promise.race([
          profilePromise,
          new Promise((resolve) => setTimeout(() => resolve({ __timeout: true }), PROFILE_TIMEOUT_MS))
        ])
        if (result && result.__timeout) {
          timedOut = true
          console.warn('Profile fetch timed out; using auth-only data and retrying in background')
          // Background retry — update state when it eventually resolves.
          // Guard against the user having signed out / switched accounts
          // while this fetch was in flight; otherwise we'd overwrite the
          // new user with the previous user's profile.
          profilePromise.then(({ data, error: bgError }) => {
            if (bgError) return
            if (!data) return
            if (!this.currentUser || this.currentUser.id !== user.id) return
            this.currentUser = { ...user, ...data }
            this.isAdmin = this.currentUser.role === 'admin' || this.currentUser.is_admin === true
            localStorage.setItem('currentUser', JSON.stringify(this.currentUser))
            if (this.isAdmin) {
              localStorage.setItem('adminAuthenticated', 'true')
              localStorage.setItem('adminUser', JSON.stringify(this.currentUser))
            }
            this.notifyListeners()
          }).catch(() => {})
        } else {
          profile = result.data
          error = result.error
        }
      } catch (e) {
        error = e
      }

      if (timedOut || (error && error.code !== 'PGRST116')) {
        // PGRST116 is "no rows returned" - this is expected for new users
        if (error) console.error('Error fetching user profile:', error)

        // If we already have a cached profile for THIS user (e.g. from a
        // previous successful fetch / localStorage on app load), keep it.
        // Wiping it here on a transient TOKEN_REFRESHED timeout would
        // momentarily drop admin/role flags and bounce admins off /admin
        // pages back to the home page.
        const cached = this.currentUser
        if (cached && cached.id === user.id) {
          this.currentUser = { ...cached, ...user, id: cached.id }
          this.isAuthenticated = true
          this.isAdmin = cached.role === 'admin' || cached.is_admin === true
          localStorage.setItem('userAuthenticated', 'true')
          localStorage.setItem('currentUser', JSON.stringify(this.currentUser))
          this.notifyListeners()
          return
        }

        // No cached profile — fall back to auth-only data so the user can
        // still log in (this is the first-ever sign-in path). Preserve any
        // values previously persisted to localStorage so a transient timeout
        // can't wipe community_role/address/phone for the same user.
        let prev = null
        try { prev = JSON.parse(localStorage.getItem('currentUser') || 'null') } catch (_) { prev = null }
        if (prev && prev.id !== user.id) prev = null
        this.currentUser = {
          ...user,
          name: prev?.name || user.user_metadata?.name || user.email,
          address: prev?.address ?? user.user_metadata?.address ?? null,
          phone: prev?.phone ?? user.user_metadata?.phone ?? null,
          community_role: prev?.community_role ?? user.user_metadata?.community_role ?? null,
          account_type: prev?.account_type || user.user_metadata?.account_type || 'individual',
          role: prev?.role || 'user',
          status: prev?.status || 'active'
        }
        this.isAuthenticated = true
        this.isAdmin = false
        localStorage.setItem('userAuthenticated', 'true')
        localStorage.setItem('currentUser', JSON.stringify(this.currentUser))
        this.notifyListeners()
        return
      }

      // If no profile exists, create one manually (in case the trigger didn't fire)
      if (!profile) {
        console.log('No profile found, creating user profile...')
        
        try {
          const { data: newProfile, error: createError } = await supabase
            .from('users')
            .insert({
              id: user.id,
              email: user.email,
              name: user.user_metadata?.name || user.email,
              address: user.user_metadata?.address || null,
              approval_number: user.user_metadata?.approval_number || null,
              community_id: user.user_metadata?.community_id || null,
              phone: user.user_metadata?.phone || null,
              sms_opt_in: user.user_metadata?.sms_opt_in || false,
              sms_opt_in_date: user.user_metadata?.sms_opt_in_date || null,
              sms_notifications_enabled: user.user_metadata?.sms_notifications_enabled || false,
              account_type: user.user_metadata?.account_type || 'individual',
              avatar_url: user.user_metadata?.avatar_url || `https://ui-avatars.com/api/?name=${encodeURIComponent(user.user_metadata?.name || user.email)}&background=random`,
              role: 'user',
              status: 'active'
            })
            .select()
            .single()

          if (createError) {
            console.error('Error creating user profile:', createError)
            // Use auth data only if profile creation fails — but preserve any
            // cached profile fields so role/address don't get wiped.
            let prev = null
            try { prev = JSON.parse(localStorage.getItem('currentUser') || 'null') } catch (_) { prev = null }
            if (prev && prev.id !== user.id) prev = null
            this.currentUser = {
              ...user,
              name: prev?.name || user.user_metadata?.name || user.email,
              address: prev?.address ?? user.user_metadata?.address ?? null,
              phone: prev?.phone ?? user.user_metadata?.phone ?? null,
              community_role: prev?.community_role ?? user.user_metadata?.community_role ?? null,
              account_type: prev?.account_type || user.user_metadata?.account_type || 'individual',
              role: prev?.role || 'user',
              status: prev?.status || 'active'
            }
          } else {
            console.log('User profile created successfully')
            this.currentUser = {
              ...user,
              ...newProfile
            }

            // Also create initial user stats
            try {
              await supabase
                .from('user_stats')
                .insert({
                  user_id: user.id,
                  total_donations: 0,
                  total_trades: 0,
                  total_food_saved: 0.0,
                  total_impact_score: 0
                })
            } catch (statsError) {
              console.warn('Error creating user stats:', statsError)
            }
          }
        } catch (createError) {
          console.error('Error creating user profile:', createError)
          // Use auth data only if profile creation fails — but preserve any
          // cached profile fields so role/address don't get wiped.
          let prev = null
          try { prev = JSON.parse(localStorage.getItem('currentUser') || 'null') } catch (_) { prev = null }
          if (prev && prev.id !== user.id) prev = null
          this.currentUser = {
            ...user,
            name: prev?.name || user.user_metadata?.name || user.email,
            address: prev?.address ?? user.user_metadata?.address ?? null,
            phone: prev?.phone ?? user.user_metadata?.phone ?? null,
            community_role: prev?.community_role ?? user.user_metadata?.community_role ?? null,
            account_type: prev?.account_type || user.user_metadata?.account_type || 'individual',
            role: prev?.role || 'user',
            status: prev?.status || 'active'
          }
        }
      } else {
        this.currentUser = {
          ...user,
          ...profile
        }
      }

  this.isAuthenticated = true
  this.isAdmin = this.currentUser.role === 'admin' || this.currentUser.is_admin === true
      
      // Store in localStorage for persistence
      localStorage.setItem('userAuthenticated', 'true')
      localStorage.setItem('currentUser', JSON.stringify(this.currentUser))
      if (this.isAdmin) {
        localStorage.setItem('adminAuthenticated', 'true')
        localStorage.setItem('adminUser', JSON.stringify(this.currentUser))
      }

      this.notifyListeners()
    } catch (error) {
      console.error('Error setting user:', error)
      reportError(error)
    }
  }

  clearUser() {
    this.currentUser = null
    this.isAuthenticated = false
    this.isAdmin = false
    
    localStorage.removeItem('userAuthenticated')
    localStorage.removeItem('currentUser')
    localStorage.removeItem('adminAuthenticated')
    localStorage.removeItem('adminUser')
    
    this.notifyListeners()
  }

  async signUp(userData) {
    try {
      if (!userData.email || !userData.password) {
        throw new Error('Email and password are required');
      }

      console.log('Attempting signup with:', {
        email: userData.email,
        metadata: userData.options?.data
      });

      // Build the site URL for email redirect
      const siteUrl = import.meta.env.VITE_SITE_URL || window.location.origin;

      const { data, error } = await supabase.auth.signUp({
        email: userData.email,
        password: userData.password,
        options: {
          data: userData.options?.data || {},
          emailRedirectTo: `${siteUrl}/login`
        }
      })

      if (error) {
        console.error('Supabase signup error:', error);
        throw error;
      }

      if (!data?.user) {
        throw new Error('No user data received from signup');
      }

      console.log('Signup successful:', data.user);
      // Return session so caller can detect if user was auto-confirmed
      return { success: true, user: data.user, session: data.session }
    } catch (error) {
      console.error('Sign up error:', error)
      reportError(error)
      throw error
    }
  }

  async signIn(email, password) {
    this._signingIn = true
    try {
      const { data, error } = await supabase.auth.signInWithPassword({
        email,
        password
      })

      if (error) {
        // Supabase auth errors have a message property, but ensure it exists
        if (!error.message) error.message = error.msg || error.error_description || 'Authentication failed'
        throw error
      }

      if (!data?.user) {
        throw new Error('No user data received from login')
      }

      // Update local state immediately so auth context is ready before navigation
      await this.setUser(data.user)

      return { success: true, user: data.user }
    } catch (error) {
      console.error('Sign in error:', error)
      reportError(error)
      // Ensure the thrown error always has a message
      if (error instanceof Error) throw error
      throw new Error(error?.message || error?.msg || String(error) || 'Authentication failed')
    } finally {
      this._signingIn = false
    }
  }

  async signOut() {
    try {
      this._userExplicitlySignedOut = true

      // Clear local state IMMEDIATELY so the UI updates even if the network call hangs.
      // This is the key fix: previously we awaited supabase.auth.signOut() BEFORE clearing
      // local state. If that network call hung (e.g. after other activity held the token
      // refresh lock or the network was slow), the UI would appear frozen until the next click.
      this.clearUser()
      try { localStorage.removeItem(SUPABASE_AUTH_KEY) } catch (_) {}
      try { localStorage.removeItem('userAuthenticated') } catch (_) {}
      try { localStorage.removeItem('currentUser') } catch (_) {}
      try { localStorage.removeItem('adminAuthenticated') } catch (_) {}
      try { localStorage.removeItem('adminUser') } catch (_) {}

      // Fire-and-forget Supabase signOut with a short timeout and scope:'local'.
      // scope:'local' avoids a server round-trip that can hang; the token is revoked
      // locally and refresh tokens are invalidated on next server use.
      const signOutPromise = (async () => {
        try {
          const { error } = await supabase.auth.signOut({ scope: 'local' })
          if (error) console.warn('Supabase signOut warning:', error.message || error)
        } catch (e) {
          console.warn('Supabase signOut exception (ignored):', e?.message || e)
        }
      })()

      // Race with a 2-second timeout so we never block the user.
      await Promise.race([
        signOutPromise,
        new Promise(resolve => setTimeout(resolve, 2000)),
      ])

      return { success: true }
    } catch (error) {
      console.error('Sign out error:', error)
      this._userExplicitlySignedOut = true
      this.clearUser()
      try { localStorage.removeItem(SUPABASE_AUTH_KEY) } catch (_) {}
      reportError(error)
      return { success: true }
    }
  }

  async updateProfile(updates) {
    try {
      if (!this.currentUser) throw new Error('No user logged in')

      const { error } = await supabase
        .from('users')
        .update(updates)
        .eq('id', this.currentUser.id)

      if (error) throw error

      // Update local user data
      this.currentUser = { ...this.currentUser, ...updates }
      localStorage.setItem('currentUser', JSON.stringify(this.currentUser))
      
      this.notifyListeners()
      return { success: true }
    } catch (error) {
      console.error('Profile update error:', error)
      reportError(error)
      throw error
    }
  }

  async uploadAvatar(file) {
    try {
      // 1. Validate user authentication
      if (!this.currentUser) {
        throw new Error('No user logged in')
      }

      // Ensure a valid session before uploading
      const { data: { session } } = await supabase.auth.getSession()
      if (!session) {
        throw new Error('No active session')
      }

      // 2. Validate file
      if (!file || !(file instanceof File)) {
        throw new Error('Invalid file provided')
      }
      // Whitelist real raster image types so the public bucket can't serve a
      // user-supplied SVG (script-bearing) under an image content-type.
      const IMAGE_TYPE_EXT = {
        'image/jpeg': 'jpg',
        'image/jpg': 'jpg',
        'image/png': 'png',
        'image/webp': 'webp',
        'image/gif': 'gif',
      }
      const safeExt = IMAGE_TYPE_EXT[file.type?.toLowerCase()]
      if (!safeExt) {
        throw new Error('Avatar must be a JPG, PNG, WebP, or GIF image.')
      }
      const MAX_AVATAR_BYTES = 5 * 1024 * 1024
      if (file.size > MAX_AVATAR_BYTES) {
        throw new Error('Avatar file is too large. Please choose an image under 5 MB.')
      }
      console.log('Uploading file:', { name: file.name, type: file.type, size: file.size })

      // 3. Set up file path — derive extension from the whitelisted MIME type,
      // not from the user-controlled filename, so attackers can't pick the
      // stored extension or path.
      const fileName = `avatar.${safeExt}`
      const safeContentType = file.type.toLowerCase()
      const filePath = `${this.currentUser.id}/${fileName}` // Remove 'avatars/' prefix as it's the bucket name
      console.log('Upload path:', filePath)

      // 4. Test bucket access
      const { data: bucketTest, error: bucketError } = await supabase.storage
        .from('avatars')
        .list(this.currentUser.id, { limit: 1 })
      console.log('Bucket access test:', { data: bucketTest, error: bucketError })

      // 5. Upload new file to bucket
      console.log('Starting file upload...')
      const { data: uploadData, error: uploadError } = await supabase.storage
        .from('avatars')
        .upload(filePath, file, {
          upsert: true,
          contentType: safeContentType
        })

      if (uploadError) {
        console.error('Upload error details:', uploadError)
        throw new Error(`Failed to upload avatar: ${uploadError.message}`)
      }
      
      console.log('Upload successful:', uploadData)

      // 6. Get public URL
      const { data: urlData, error: urlError } = supabase.storage
        .from('avatars')
        .getPublicUrl(filePath)

      if (urlError) {
        console.error('URL error details:', urlError)
        throw new Error('Failed to get public URL for avatar')
      }

      if (!urlData?.publicUrl) {
        throw new Error('No public URL returned from storage')
      }

      console.log('Got public URL:', urlData.publicUrl)

      // 7. Update user profile
      try {
        await this.updateProfile({ 
          avatar_url: urlData.publicUrl,
          updated_at: new Date().toISOString()
        })
        console.log('Profile updated with new avatar')
      } catch (error) {
        console.error('Profile update error:', error)
        throw new Error('Failed to update profile with new avatar URL')
      }

      return { 
        success: true, 
        avatarUrl: urlData.publicUrl 
      }
    } catch (error) {
      // Log full error details
      console.error('Avatar upload error:', {
        message: error.message,
        details: error,
        user: this.currentUser?.id
      })
      reportError(error)
      throw error
    }
  }

  async refreshAuthState() {
    try {
      const { data: { session } } = await supabase.auth.getSession()
      if (session?.user) {
        await this.setUser(session.user)
      } else {
        this.clearUser()
      }
    } catch (error) {
      console.error('Auth refresh error:', error)
      reportError(error)
    }
  }

  getCurrentUser() {
    return this.currentUser
  }

  isUserAuthenticated() {
    return this.isAuthenticated
  }

  isUserAdmin() {
    return this.isAdmin
  }

  addListener(callback) {
    this.listeners.push(callback)
    return () => {
      this.listeners = this.listeners.filter(listener => listener !== callback)
    }
  }

  notifyListeners() {
    this.listeners.forEach(callback => {
      try {
        callback({
          user: this.currentUser,
          isAuthenticated: this.isAuthenticated,
          isAdmin: this.isAdmin
        })
      } catch (error) {
        console.error('Auth listener error:', error)
      }
    })
  }

  // Password reset functionality
  async resetPassword(email) {
    try {
      const { error } = await supabase.auth.resetPasswordForEmail(email, {
        redirectTo: `${window.location.origin}/reset-password`
      })

      if (error) {
        console.error('Supabase resetPasswordForEmail error:', error);
        throw error;
      }

      return { success: true }
    } catch (error) {
      console.error('Password reset error:', error)
      reportError(error)
      throw error
    }
  }

  async updatePassword(newPassword) {
    try {
      const { error } = await supabase.auth.updateUser({
        password: newPassword
      })

      if (error) throw error
      return { success: true }
    } catch (error) {
      console.error('Password update error:', error)
      reportError(error)
      throw error
    }
  }
}

// Create singleton instance
const authService = new AuthService()

export default authService 