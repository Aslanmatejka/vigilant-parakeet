import { useState, useEffect, useCallback, useRef } from 'react'
import authService from '../authService.js'
import dataService from '../dataService.js'
import { getRecipeSuggestions as _getRecipeSuggestions } from '../aiAgent.js'

// Authentication hook
export const useAuth = () => {
  // Initialize from authService's localStorage-restored values to prevent
  // brief false state that causes hard-redirect bugs in consuming components
  const [user, setUser] = useState(() => authService.getCurrentUser())
  const [isAuthenticated, setIsAuthenticated] = useState(() => authService.isUserAuthenticated())
  const [isAdmin, setIsAdmin] = useState(() => authService.isUserAdmin())
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    let isMounted = true;
    
    const unsubscribe = authService.addListener(({ user, isAuthenticated, isAdmin }) => {
      if (isMounted) {
        setUser(user)
        setIsAuthenticated(isAuthenticated)
        setIsAdmin(isAdmin)
        setLoading(false)
      }
    })

    // Set initial state
    setUser(authService.getCurrentUser())
    setIsAuthenticated(authService.isUserAuthenticated())
    setIsAdmin(authService.isUserAdmin())
    setLoading(false)

    return () => {
      isMounted = false;
      if (unsubscribe) {
        unsubscribe();
      }
    }
  }, [])

  const signIn = useCallback(async (email, password) => {
    try {
      setLoading(true)
      const result = await authService.signIn(email, password)
      return result
    } catch (error) {
      throw error
    } finally {
      setLoading(false)
    }
  }, [])

  const signUp = useCallback(async (userData) => {
    try {
      setLoading(true)
      const result = await authService.signUp(userData)
      return result
    } catch (error) {
      throw error
    } finally {
      setLoading(false)
    }
  }, [])

  const signOut = useCallback(async () => {
    try {
      setLoading(true)
      const result = await authService.signOut()
      return result
    } catch (error) {
      throw error
    } finally {
      setLoading(false)
    }
  }, [])

  const updateProfile = useCallback(async (updates) => {
    try {
      setLoading(true)
      const result = await authService.updateProfile(updates)
      return result
    } catch (error) {
      throw error
    } finally {
      setLoading(false)
    }
  }, [])

  const uploadAvatar = useCallback(async (file) => {
    try {
      setLoading(true)
      const result = await authService.uploadAvatar(file)
      return result
    } catch (error) {
      throw error
    } finally {
      setLoading(false)
    }
  }, [])

  return {
    user,
    isAuthenticated,
    isAdmin,
    loading,
    signIn,
    signUp,
    signOut,
    updateProfile,
    uploadAvatar
  }
}

// Food listings hook
export const useFoodListings = (filters = {}, limit = null) => {
  const [listings, setListings] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  // Track whether we've completed at least one successful fetch so background
  // refreshes don't flip `loading` back on and make the UI flicker.
  const hasLoadedRef = useRef(false)

  const fetchListings = useCallback(async () => {
    try {
      if (!hasLoadedRef.current) setLoading(true)
      setError(null)
      const fetchFilters = { ...filters };
      if (limit) {
        fetchFilters.page = 1;
        fetchFilters.limit = limit;
      }
      const data = await dataService.getFoodListings(fetchFilters)
      setListings(data)
      hasLoadedRef.current = true
    } catch (error) {
      setError(error.message)
    } finally {
      setLoading(false)
    }
  }, [JSON.stringify(filters), limit]);

  useEffect(() => {
    fetchListings()
  }, [fetchListings])

  // Keep a stable ref to fetchListings so the realtime subscription can
  // always call the latest version without needing to re-subscribe when
  // non-status filters (community, category, etc.) change.
  const fetchListingsRef = useRef(fetchListings)
  useEffect(() => { fetchListingsRef.current = fetchListings }, [fetchListings])

  // Real-time subscription
  useEffect(() => {
    const allowedStatuses = filters.status
      ? (Array.isArray(filters.status) ? filters.status : [filters.status])
      : null;

    // Debounce re-fetches so bursts of events (e.g. bulk import) only trigger
    // one round-trip. We store the timer in a ref so the closure always sees
    // the latest value without requiring it in the dependency array.
    let refetchTimer = null;
    const scheduleRefetch = () => {
      clearTimeout(refetchTimer);
      refetchTimer = setTimeout(() => { fetchListingsRef.current(); }, 400);
    };

    const subscription = dataService.subscribeToFoodListings((payload) => {
      if (payload.eventType === 'INSERT') {
        // Only react if the new listing matches the status filter
        if (allowedStatuses && !allowedStatuses.includes(payload.new?.status)) return;
        // Re-fetch with full JOIN so community_name, expiry_date etc. are
        // all populated correctly (payload.new is a raw DB row with no joins).
        scheduleRefetch();
      } else if (payload.eventType === 'UPDATE') {
        const matchesFilter = !allowedStatuses || allowedStatuses.includes(payload.new?.status);
        if (matchesFilter) {
          // Re-fetch to get joined community name and other enriched fields.
          scheduleRefetch();
        } else if (payload.new?.id) {
          // Status no longer matches — remove from list immediately.
          // Guard against payload.new being null (Supabase can deliver
          // UPDATEs with RLS-stripped rows).
          setListings(prev => prev.filter(l => l.id !== payload.new.id))
        }
      } else if (payload.eventType === 'DELETE') {
        if (payload.old?.id) {
          setListings(prev => prev.filter(listing => listing.id !== payload.old.id))
        }
      }
    })

    return () => {
      clearTimeout(refetchTimer);
      // Unsubscribe by handle so a second mount of this hook can't take
      // over the 'food_listings' Map slot and leave our channel orphaned
      // on the realtime connection.
      dataService.unsubscribeChannel(subscription);
    }
  }, [JSON.stringify(filters.status)])

  const createListing = useCallback(async (listingData) => {
    try {
      setLoading(true)
      const result = await dataService.createFoodListing(listingData)
      return result
    } catch (error) {
      setError(error.message)
      throw error
    } finally {
      setLoading(false)
    }
  }, [])

  const updateListing = useCallback(async (id, updates) => {
    try {
      setLoading(true)
      const result = await dataService.updateFoodListing(id, updates)
      return result
    } catch (error) {
      setError(error.message)
      throw error
    } finally {
      setLoading(false)
    }
  }, [])

  const deleteListing = useCallback(async (id) => {
    try {
      setLoading(true)
      const result = await dataService.deleteFoodListing(id)
      return result
    } catch (error) {
      setError(error.message)
      throw error
    } finally {
      setLoading(false)
    }
  }, [])

  return {
    listings,
    loading,
    error,
    fetchListings,
    createListing,
    updateListing,
    deleteListing
  }
}

// Blog hook
export const useBlog = (filters = {}) => {
  const [posts, setPosts] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)

  const fetchPosts = useCallback(async () => {
    try {
      setLoading(true)
      setError(null)
      const data = await dataService.getBlogPosts(filters)
      setPosts(data)
    } catch (error) {
      setError(error.message)
    } finally {
      setLoading(false)
    }
  }, [filters])

  useEffect(() => {
    fetchPosts()
  }, [fetchPosts])

  return {
    posts,
    loading,
    error,
    fetchPosts
  }
}

// Notifications hook
export const useNotifications = (userId) => {
  const [notifications, setNotifications] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)

  const fetchNotifications = useCallback(async () => {
    if (!userId) return

    try {
      setLoading(true)
      setError(null)
      const data = await dataService.getNotifications(userId)
      setNotifications(data)
    } catch (error) {
      setError(error.message)
    } finally {
      setLoading(false)
    }
  }, [userId])

  useEffect(() => {
    fetchNotifications()
  }, [fetchNotifications])

  // Real-time subscription
  useEffect(() => {
    if (!userId) return

    // Debounce bursts (e.g. system broadcast to all users) into one refetch
    // so the UI doesn't re-render once per notification row.
    let refetchTimer = null;
    const scheduleRefetch = () => {
      clearTimeout(refetchTimer);
      refetchTimer = setTimeout(() => { fetchNotifications(); }, 400);
    };

    const subscription = dataService.subscribeToNotifications(userId, (payload) => {
      if (payload.eventType === 'INSERT' || payload.eventType === 'UPDATE') {
        // Refetch instead of appending payload.new so any joined
        // sender/sender_name columns stay consistent with fetched rows.
        scheduleRefetch();
      } else if (payload.eventType === 'DELETE') {
        if (payload.old?.id) {
          setNotifications(prev => prev.filter(notification => notification.id !== payload.old.id))
        }
      }
    })

    return () => {
      clearTimeout(refetchTimer);
      dataService.unsubscribeChannel(subscription);
    }
  }, [userId, fetchNotifications])

  const markAsRead = useCallback(async (notificationId) => {
    try {
      const result = await dataService.markNotificationAsRead(notificationId)
      return result
    } catch (error) {
      setError(error.message)
      throw error
    }
  }, [])

  const unreadCount = notifications.filter(n => !n.read).length

  return {
    notifications,
    loading,
    error,
    fetchNotifications,
    markAsRead,
    unreadCount
  }
}

// User profile hook
export const useUserProfile = (userId) => {
  const [profile, setProfile] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)

  const fetchProfile = useCallback(async () => {
    if (!userId) {
      setProfile(null)
      setLoading(false)
      return
    }
    try {
      setLoading(true)
      setError(null)
      const data = await dataService.getUserProfile(userId)
      setProfile(data)
    } catch (error) {
      setError(error.message)
    } finally {
      setLoading(false)
    }
  }, [userId])

  useEffect(() => {
    fetchProfile()
  }, [fetchProfile])

  const updateUserProfile = useCallback(async (updates) => {
    if (!userId) return
    try {
      setLoading(true)
      const updatedProfile = await dataService.updateUserProfile(userId, updates)
      setProfile(updatedProfile)
      return updatedProfile
    } catch (error) {
      setError(error.message)
      throw error
    } finally {
      setLoading(false)
    }
  }, [userId])

  return { profile, loading, error, fetchProfile, updateUserProfile }
}

// Distribution events hook
export const useDistributionEvents = () => {
  const [events, setEvents] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)

  const fetchEvents = useCallback(async () => {
    try {
      setLoading(true)
      setError(null)
      const data = await dataService.getDistributionEvents()
      setEvents(data)
    } catch (error) {
      setError(error.message)
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    fetchEvents()
  }, [fetchEvents])

  const registerForEvent = useCallback(async (eventId, userId) => {
    try {
      const result = await dataService.registerForEvent(eventId, userId)
      // Refresh so attendee count / "you're attending" badge reflect the
      // registration immediately instead of waiting for a manual reload.
      await fetchEvents()
      return result
    } catch (error) {
      setError(error.message)
      throw error
    }
  }, [fetchEvents])

  return {
    events,
    loading,
    error,
    fetchEvents,
    registerForEvent
  }
}

// File upload hook
export const useFileUpload = () => {
  const [uploading, setUploading] = useState(false)
  const [error, setError] = useState(null)

  const uploadFile = useCallback(async (file, bucket) => {
    try {
      setUploading(true)
      setError(null)
      const result = await dataService.uploadFile(file, bucket)
      return result
    } catch (error) {
      setError(error.message)
      throw error
    } finally {
      setUploading(false)
    }
  }, [])

  return {
    uploading,
    error,
    uploadFile
  }
}

// Search hook
export const useSearch = () => {
  const [results, setResults] = useState([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)

  const search = useCallback(async (searchTerm, filters = {}) => {
    try {
      setLoading(true)
      setError(null)
      const data = await dataService.searchFoodListings(searchTerm, filters)
      setResults(data)
      return data
    } catch (error) {
      setError(error.message)
      throw error
    } finally {
      setLoading(false)
    }
  }, [])

  return {
    results,
    loading,
    error,
    search
  }
}

// Admin hooks
export const useAdminStats = () => {
  const [stats, setStats] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)

  const fetchStats = useCallback(async () => {
    try {
      setLoading(true)
      setError(null)
      const data = await dataService.getAdminStats()
      setStats(data)
    } catch (error) {
      setError(error.message)
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    fetchStats()
  }, [fetchStats])

  return {
    stats,
    loading,
    error,
    fetchStats
  }
}

export const useAdminListings = (limit = 10) => {
  const [recentListings, setRecentListings] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)

  const fetchRecentListings = useCallback(async () => {
    try {
      setLoading(true)
      setError(null)
      const data = await dataService.getRecentListings(limit)
      setRecentListings(data)
    } catch (error) {
      setError(error.message)
    } finally {
      setLoading(false)
    }
  }, [limit])

  useEffect(() => {
    fetchRecentListings()
  }, [fetchRecentListings])

  return {
    recentListings,
    loading,
    error,
    fetchRecentListings
  }
}

export const useAdminUsers = (limit = 10) => {
  const [recentUsers, setRecentUsers] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)

  const fetchRecentUsers = useCallback(async () => {
    try {
      setLoading(true)
      setError(null)
      const data = await dataService.getRecentUsers(limit)
      setRecentUsers(data)
    } catch (error) {
      setError(error.message)
    } finally {
      setLoading(false)
    }
  }, [limit])

  useEffect(() => {
    fetchRecentUsers()
  }, [fetchRecentUsers])

  return {
    recentUsers,
    loading,
    error,
    fetchRecentUsers
  }
}

// AI Assistant hook (used by FoodCard for recipe suggestions)
export const useAI = () => {
  const [isLoading, setIsLoading] = useState(false)
  const [error, setError] = useState(null)
  // Track the in-flight request so a newer call (or unmount) can cancel
  // an older one — otherwise a stale fetch can resolve after the user
  // closed the panel and overwrite fresh UI state.
  const abortRef = useRef(null)

  const getRecipeSuggestions = useCallback(async (ingredients) => {
    // Cancel any prior in-flight request
    abortRef.current?.abort()
    const controller = new AbortController()
    abortRef.current = controller

    try {
      setIsLoading(true)
      setError(null)

      const userId = authService.getCurrentUser()?.id
      const result = await _getRecipeSuggestions(ingredients, {
        userId,
        signal: controller.signal,
      })

      return result
    } catch (error) {
      if (error?.name === 'AbortError') throw error
      setError(error.message)
      throw error
    } finally {
      // Only clear loading if THIS call is still the active one; otherwise
      // a newer call has already taken over the flag.
      if (abortRef.current === controller) {
        setIsLoading(false)
        abortRef.current = null
      }
    }
  }, [])

  // Abort any in-flight request on unmount so React doesn't try to set
  // state on an unmounted component.
  useEffect(() => () => {
    abortRef.current?.abort()
    abortRef.current = null
  }, [])

  return {
    isLoading,
    error,
    getRecipeSuggestions,
  }
}

