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
        } else {
          // Status no longer matches — remove from list immediately.
          setListings(prev => prev.filter(l => l.id !== payload.new.id))
        }
      } else if (payload.eventType === 'DELETE') {
        setListings(prev => prev.filter(listing => listing.id !== payload.old.id))
      }
    })

    return () => {
      clearTimeout(refetchTimer);
      dataService.unsubscribe('food_listings');
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

// Trades hook - includes both regular trades and barter trades
export const useTrades = (userId) => {
  const [trades, setTrades] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)

  const fetchTrades = useCallback(async () => {
    try {
      setLoading(true)
      setError(null)
      
      // Fetch both regular trades and barter trades
      const [regularTrades, barterTrades] = await Promise.all([
        dataService.getTrades(userId),
        dataService.getBarterTrades(userId)
      ])
      
      // Normalize regular trades to consistent format
      const normalizedRegularTrades = regularTrades.map(trade => ({
        ...trade,
        type: 'regular',
        objectId: trade.id,
        createdAt: trade.created_at,
        offeredItem: trade.offered_listing ? {
          title: trade.offered_listing.title,
          image: trade.offered_listing.image_url,
          quantity: trade.offered_listing.quantity,
          unit: trade.offered_listing.unit
        } : null,
        requestedItem: trade.requested_listing ? {
          title: trade.requested_listing.title,
          image: trade.requested_listing.image_url,
          quantity: trade.requested_listing.quantity,
          unit: trade.requested_listing.unit
        } : null,
        requestedItems: trade.requested_listing ? [{
          title: trade.requested_listing.title,
          image: trade.requested_listing.image_url,
          quantity: trade.requested_listing.quantity,
          unit: trade.requested_listing.unit
        }] : []
      }))
      
      // Normalize barter trades to consistent format
      const normalizedBarterTrades = barterTrades.map(trade => ({
        ...trade,
        type: 'barter',
        objectId: trade.id,
        createdAt: trade.created_at,
        offeredItem: trade.offered_listing ? {
          title: trade.offered_listing.title,
          image: trade.offered_listing.image_url,
          quantity: trade.offered_listing.quantity,
          unit: trade.offered_listing.unit
        } : null,
        requestedItems: trade.requested_items || [],
        requestedItem: null // Barter trades don't have single requested item
      }))
      
      // Combine and sort by created_at
      const allTrades = [
        ...normalizedRegularTrades,
        ...normalizedBarterTrades
      ].sort((a, b) => new Date(b.created_at) - new Date(a.created_at))
      
      setTrades(allTrades)
    } catch (error) {
      setError(error.message)
    } finally {
      setLoading(false)
    }
  }, [userId])

  useEffect(() => {
    fetchTrades()
  }, [fetchTrades])

  // Real-time subscriptions for both trade types
  useEffect(() => {
    const tradesSubscription = dataService.subscribeToTrades(userId, (payload) => {
      if (payload.eventType === 'INSERT') {
        setTrades(prev => [{ ...payload.new, type: 'regular' }, ...prev])
      } else if (payload.eventType === 'UPDATE') {
        setTrades(prev => prev.map(trade =>
          trade.id === payload.new.id && trade.type === 'regular' 
            ? { ...payload.new, type: 'regular' } 
            : trade
        ))
      }
    })

    const barterTradesSubscription = dataService.subscribeToBarterTrades(userId, (payload) => {
      if (payload.eventType === 'INSERT') {
        setTrades(prev => [{ ...payload.new, type: 'barter' }, ...prev])
      } else if (payload.eventType === 'UPDATE') {
        setTrades(prev => prev.map(trade =>
          trade.id === payload.new.id && trade.type === 'barter' 
            ? { ...payload.new, type: 'barter' } 
            : trade
        ))
      }
    })

    return () => {
      dataService.unsubscribe('trades')
      dataService.unsubscribe('barter_trades')
    }
  }, [userId])

  const createTrade = useCallback(async (tradeData) => {
    try {
      setLoading(true)
      const result = await dataService.createTrade(tradeData)
      return result
    } catch (error) {
      setError(error.message)
      throw error
    } finally {
      setLoading(false)
    }
  }, [])

  const updateTradeStatus = useCallback(async (id, status) => {
    try {
      setLoading(true)
      const result = await dataService.updateTradeStatus(id, status)
      return result
    } catch (error) {
      setError(error.message)
      throw error
    } finally {
      setLoading(false)
    }
  }, [])

  return { trades, loading, error, createTrade, updateTradeStatus }
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

    const subscription = dataService.subscribeToNotifications(userId, (payload) => {
      if (payload.eventType === 'INSERT') {
        setNotifications(prev => [payload.new, ...prev])
      } else if (payload.eventType === 'UPDATE') {
        setNotifications(prev => prev.map(notification => 
          notification.id === payload.new.id ? payload.new : notification
        ))
      } else if (payload.eventType === 'DELETE') {
        setNotifications(prev => prev.filter(notification => notification.id !== payload.old.id))
      }
    })

    return () => {
      dataService.unsubscribe('notifications')
    }
  }, [userId])

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
      return result
    } catch (error) {
      setError(error.message)
      throw error
    }
  }, [])

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

// Community Posts hook
export const useCommunityPosts = (filters = {}) => {
  const [posts, setPosts] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)

  const fetchPosts = useCallback(async () => {
    try {
      setLoading(true)
      setError(null)
      const data = await dataService.getCommunityPosts(filters)
      setPosts(data)
    } catch (error) {
      setError(error.message)
    } finally {
      setLoading(false)
    }
  }, [JSON.stringify(filters)])

  useEffect(() => {
    fetchPosts()
  }, [fetchPosts])

  const createPost = useCallback(async (postData) => {
    try {
      const result = await dataService.createCommunityPost(postData)
      setPosts(prev => [result, ...prev])
      return result
    } catch (error) {
      setError(error.message)
      throw error
    }
  }, [])

  const addComment = useCallback(async (postId, comment) => {
    try {
      const result = await dataService.addCommentToCommunityPost(postId, comment)
      // Refresh posts to show the new comment
      await fetchPosts()
      return result
    } catch (error) {
      setError(error.message)
      throw error
    }
  }, [fetchPosts])

  const likePost = useCallback(async (postId, userId) => {
    try {
      const result = await dataService.likeCommunityPost(postId, userId)
      return result
    } catch (error) {
      setError(error.message)
      throw error
    }
  }, [])

  return {
    posts,
    loading,
    error,
    fetchPosts,
    createPost,
    addComment,
    likePost
  }
}

// AI Assistant hook (used by FoodCard for recipe suggestions)
export const useAI = () => {
  const [isLoading, setIsLoading] = useState(false)
  const [error, setError] = useState(null)

  const getRecipeSuggestions = useCallback(async (ingredients) => {
    try {
      setIsLoading(true)
      setError(null)

      const userId = authService.getCurrentUser()?.id
      const result = await _getRecipeSuggestions(ingredients, { userId })

      return result
    } catch (error) {
      setError(error.message)
      throw error
    } finally {
      setIsLoading(false)
    }
  }, [])

  return {
    isLoading,
    error,
    getRecipeSuggestions,
  }
}

