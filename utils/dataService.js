import supabase from './supabaseClient.js'
import { reportError } from './helpers.js'

class DataService {
  // Get food claims by status (for admin dashboard)
  async getFoodClaims({ status }) {
    try {
      // First get the current session to ensure we're authenticated
      const { data: { session } } = await supabase.auth.getSession();
      
      if (!session) {
        throw new Error('User is not authenticated. Please log in.');
      }
      
      const { data, error } = await supabase
        .from('food_claims')
        .select(`
          *,
          food_listings(
            title, 
            description, 
            image_url,
            quantity,
            unit,
            category
          )
        `)
        .eq('status', status);
      
      if (error) throw error;
      return data;
    } catch (error) {
      reportError(error);
      throw error;
    }
  }

  async getClaimImpact() {
    try {
      console.log('Fetching impact data...');
      
      // First, get all approved food claims with their associated food listings
      const { data: claims, error: claimsError } = await supabase
        .from('food_claims')
        .select(`
          id,
          food_id, 
          members_count, 
          people, 
          school_staff, 
          students,
          created_at,
          food_listings(
            id,
            quantity,
            unit,
            category,
            donor_type,
            created_at
          )
        `)
        .eq('status', 'approved');
        
      if (claimsError) {
        console.error('Error fetching claims:', claimsError);
        throw claimsError;
      }
      
      // Get all food listings that have been shared (even if not claimed)
      const { data: sharedFood, error: sharedError } = await supabase
        .from('food_listings')
        .select(`
          id, 
          quantity, 
          unit, 
          category, 
          donor_type, 
          created_at, 
          user_id,
          status
        `);  // Removed status filter to include ALL listings
        
      if (sharedError) {
        console.error('Error fetching shared food:', sharedError);
        throw sharedError;
      }
      
      console.log(`Processing ${claims.length} claims and ${sharedFood.length} food listings (all statuses)`);
      
      // Log distribution of statuses for debugging
      const statusCounts = sharedFood.reduce((acc, item) => {
        acc[item.status] = (acc[item.status] || 0) + 1;
        return acc;
      }, {});
      console.log('Food listing status distribution:', statusCounts);
      
      // Calculate impact metrics
      const foodWasteReduced = claims.reduce((sum, claim) => {
        const quantity = claim.food_listings?.quantity || 0;
        return sum + quantity;
      }, 0);
      
      const totalFoodShared = sharedFood.reduce((sum, listing) => {
        return sum + (listing.quantity || 0);
      }, 0);
      
      const neighborsHelped = claims.length;
      const activeListings = sharedFood.filter(item => item.status === 'approved').length;
      const donorsCount = new Set(sharedFood.map(item => item.user_id).filter(Boolean)).size;
      
      // Calculate people impact
      const people = claims.reduce((sum, claim) => sum + (claim.people || 0), 0);
      const schoolStaff = claims.reduce((sum, claim) => sum + (claim.school_staff || 0), 0);
      const students = claims.reduce((sum, claim) => sum + (claim.students || 0), 0);
      
      // Calculate environmental impact (approximate CO2 reduction)
      // Using an estimate that 1 lb of food waste = 2.5 lbs of CO2 equivalent
      const co2Reduction = foodWasteReduced * 2.5;
      
      // Calculate total lives impacted
      const livesImpacted = people + schoolStaff + students;
      
      // Additional statistics
      const categoryDistribution = sharedFood.reduce((acc, item) => {
        const category = item.category || 'uncategorized';
        acc[category] = (acc[category] || 0) + 1;
        return acc;
      }, {});
      
      const result = { 
        foodWasteReduced,
        totalFoodShared,
        neighborsHelped,
        donorsCount,
        people,
        schoolStaff, 
        students,
        co2Reduction,
        livesImpacted,
        sharingCount: sharedFood.length,
        activeListings,
        categoryDistribution,
        lastUpdated: new Date().toISOString()
      };
      
      console.log('Impact data calculated:', result);
      return result;
    } catch (error) {
      console.error('Error in getClaimImpact:', error);
      reportError(error);
      throw error;
    }
  }
  // Admin: Approve or decline a food claim
  async reviewFoodClaim(claimId, approve) {
    try {
      const status = approve ? 'approved' : 'declined';
      const { data, error } = await supabase
        .from('food_claims')
        .update({ status })
        .eq('id', claimId)
        .select()
        .single();
      if (error) throw error;

      // Email notification stub
      if (approve) {
        // TODO: Integrate with email service
        console.log(`Confirmation email sent to claimer and sharer for claim ${claimId}`);
      } else {
        // TODO: Integrate with email service
        console.log(`Polite rejection email sent to claimer for claim ${claimId}`);
      }
      return data;
    } catch (error) {
      console.error('Review food claim error:', error);
      reportError(error);
      throw error;
    }
  }
  // Send notification to claimer when claim is approved or declined
  async sendClaimReviewNotification(claimId, approved) {
    try {
      // Get the claim to find claimer info and food title
      const { data: claim, error: claimError } = await supabase
        .from('food_claims')
        .select('requester_name, requester_email, food_id')
        .eq('id', claimId)
        .single();
      if (claimError || !claim) throw claimError || new Error('Claim not found');

      // Get food title
      let foodTitle = '';
      if (claim.food_id) {
        const { data: food, error: foodError } = await supabase
          .from('food_listings')
          .select('title')
          .eq('id', claim.food_id)
          .single();
        if (!foodError && food) foodTitle = food.title;
      }

      // Compose notification
      const notif = {
        title: approved ? 'Food Claim Approved' : 'Food Claim Declined',
        message: approved
          ? `Your claim for "${foodTitle}" has been approved! Please check your email for pickup details.`
          : `Your claim for "${foodTitle}" was not approved. Please review the guidelines and try again.`,
        type: approved ? 'claim_approved' : 'claim_declined',
        read: false,
        data: { claimId, foodTitle },
        // For claims, we don't have user_id, so we use email for notification (or extend schema)
      };

      // Insert notification (if you have user_id, add it)
      await supabase.from('notifications').insert(notif);

      // Send email (stub, implement with email service if needed)
      if (approved) {
        // TODO: Integrate with email service to send confirmation email to claim.requester_email
        console.log(`Confirmation email sent to ${claim.requester_email}`);
      } else {
        // TODO: Integrate with email service to send polite rejection to claim.requester_email
        console.log(`Rejection email sent to ${claim.requester_email}`);
      }
      return true;
    } catch (error) {
      console.error('Send claim review notification error:', error);
      reportError(error);
      return false;
    }
  }
  // Create a food claim request
  async createFoodClaim(claimData) {
    try {
      const { data, error } = await supabase
        .from('food_claims')
        .insert(claimData)
        .select()
        .single();
      if (error) throw error;
      return data;
    } catch (error) {
      console.error('Create food claim error:', error);
      reportError(error);
      throw error;
    }
  }

  // Update food claim status (approve/decline)
  async updateFoodClaimStatus(claimId, status) {
    try {
      const { error } = await supabase
        .from('food_claims')
        .update({ status })
        .eq('id', claimId);
      if (error) throw error;
      return true;
    } catch (error) {
      console.error('Update food claim status error:', error);
      reportError(error);
      throw error;
    }
  }
  // Update food listing status (approve/decline)
  async updateFoodListingStatus(listingId, status) {
    try {
      const { error } = await supabase
        .from('food_listings')
        .update({ status })
        .eq('id', listingId);
      if (error) throw error;
      return true;
    } catch (error) {
      console.error('Update food listing status error:', error);
      reportError(error);
      throw error;
    }
  }

  // Send notification to user if declined
  async sendDeclineNotification(listingId) {
    try {
      // Get the listing to find the user_id
      const { data: listing, error: listingError } = await supabase
        .from('food_listings')
        .select('user_id, title')
        .eq('id', listingId)
        .single();
      if (listingError || !listing) throw listingError || new Error('Listing not found');

      // Insert notification for the user
      const { error: notifError } = await supabase
        .from('notifications')
        .insert({
          user_id: listing.user_id,
          title: 'Food Submission Declined',
          message: `Your food listing "${listing.title}" was not approved by the admin. Please review the guidelines and try again.`,
          type: 'submission_declined',
          read: false,
          data: { listingId },
        });
      if (notifError) throw notifError;
      return true;
    } catch (error) {
      console.error('Send decline notification error:', error);
      reportError(error);
      return false;
    }
  }
  constructor() {
    this.subscriptions = new Map()
  }

  // Food Listings
  async getFoodListings(filters = {}) {
    try {
      let query = supabase
        .from('food_listings')
        .select(`
          id,
          title,
          description,
          image_url,
          quantity,
          unit,
          category,
          listing_type,
          status,
          expiry_date,
          location,
          donor_name,
          donor_email,
          donor_phone,
          donor_city,
          donor_state,
          donor_zip,
          donor_occupation,
          donor_type,
          latitude,
          longitude,
          created_at,
          updated_at,
          users:user_id (
            id,
            name,
            avatar_url,
            organization,
            email
          )
        `)
        .eq('status', filters.status || 'pending')

      // Apply filters
      if (filters.category) {
        query = query.eq('category', filters.category)
      }
      if (filters.listing_type) {
        query = query.eq('listing_type', filters.listing_type)
      }
      if (filters.location) {
        query = query.ilike('location', `%${filters.location}%`)
      }
      if (filters.user_id) {
        query = query.eq('user_id', filters.user_id)
      }

      // Pagination
      if (filters.page && filters.limit) {
        const from = (filters.page - 1) * filters.limit;
        const to = from + filters.limit - 1;
        query = query.range(from, to);
      }

      const { data, error } = await query.order('created_at', { ascending: false })

      if (error) throw error

      return data.map(listing => ({
        ...listing,
        donor: listing.users
      }))
    } catch (error) {
      console.error('Get food listings error:', error)
      reportError(error)
      throw error
    }
  }

  async createFoodListing(listingData) {
    try {
      // Get current user
      const userResult = await supabase.auth.getUser();
      const user = userResult.data.user;
      if (!user) throw new Error('User must be authenticated to create a food listing');

      // Prepare listing data with user_id
      // Keep location-related fields in the main listing object
      const listing = {
        ...listingData,
        user_id: user.id,
        // Keep these fields for display purposes
        donor_city: listingData.donor_city,
        donor_state: listingData.donor_state,
        donor_zip: listingData.donor_zip,
        location: listingData.donor_city && listingData.donor_state ? {
          address: `${listingData.donor_city}, ${listingData.donor_state} ${listingData.donor_zip || ''}`.trim(),
          latitude: listingData.latitude,
          longitude: listingData.longitude
        } : null
      };

      // Remove other donor fields that are stored in users table
      delete listing.donor_name;
      delete listing.donor_email;
      delete listing.donor_phone;
      delete listing.donor_occupation;

      const result = await supabase
        .from('food_listings')
        .insert(listing)
        .select(`
          *,
          users!food_listings_user_id_fkey (
            id,
            name,
            avatar_url,
            organization
          )
        `)
        .single()

      if (result.error) throw result.error
      return result.data

      return data
    } catch (error) {
      console.error('Create food listing error:', error)
      reportError(error)
      throw error
    }
  }

  async updateFoodListing(id, updates) {
    try {
      const { data, error } = await supabase
        .from('food_listings')
        .update(updates)
        .eq('id', id)
        .select()
        .single()

      if (error) throw error

      return data
    } catch (error) {
      console.error('Update food listing error:', error)
      reportError(error)
      throw error
    }
  }

  async deleteFoodListing(id) {
    try {
      const { error } = await supabase
        .from('food_listings')
        .delete()
        .eq('id', id)

      if (error) throw error

      return { success: true }
    } catch (error) {
      console.error('Delete food listing error:', error)
      reportError(error)
      throw error
    }
  }

  // Trades
  async getTrades(userId = null) {
    try {
      let query = supabase
        .from('trades')
        .select(`
          *,
          initiator:users!trades_initiator_id_fkey (
            id,
            name,
            avatar_url
          ),
          recipient:users!trades_recipient_id_fkey (
            id,
            name,
            avatar_url
          ),
          offered_listing:food_listings!trades_offered_listing_id_fkey (
            id,
            title,
            image_url,
            quantity,
            unit
          ),
          requested_listing:food_listings!trades_requested_listing_id_fkey (
            id,
            title,
            image_url,
            quantity,
            unit
          )
        `)

      if (userId) {
        query = query.or(`initiator_id.eq.${userId},recipient_id.eq.${userId}`)
      }

      const { data, error } = await query.order('created_at', { ascending: false })

      if (error) throw error

      return data
    } catch (error) {
      console.error('Get trades error:', error)
      reportError(error)
      throw error
    }
  }

  async createTrade(tradeData) {
    try {
      const { data, error } = await supabase
        .from('trades')
        .insert(tradeData)
        .select()
        .single()

      if (error) throw error

      return data
    } catch (error) {
      console.error('Create trade error:', error)
      reportError(error)
      throw error
    }
  }

  async updateTradeStatus(id, status) {
    try {
      const { data, error } = await supabase
        .from('trades')
        .update({ status })
        .eq('id', id)
        .select()
        .single()

      if (error) throw error

      return data
    } catch (error) {
      console.error('Update trade status error:', error)
      reportError(error)
      throw error
    }
  }

  // Barter Trades
  async getBarterTrades(userId = null, filters = {}) {
    try {
      console.log('Fetching barter trades with filters:', { userId, filters });
      
      // Start with a simple query first
      let query = supabase
        .from('barter_trades')
        .select(`
          *,
          initiator:users!initiator_id (
            id,
            name,
            avatar_url
          ),
          offered_listing:food_listings!offered_listing_id (
            id,
            title,
            description,
            image_url,
            quantity,
            unit,
            category
          )
        `)

      // Filter by user involvement
      if (userId) {
        if (filters.type === 'offered') {
          query = query.eq('initiator_id', userId)
        } else if (filters.type === 'received') {
          query = query.neq('initiator_id', userId)
        } else {
          // All trades involving the user
          query = query.or(`initiator_id.eq.${userId}`)
        }
      }

      // Filter by status
      if (filters.status) {
        query = query.eq('status', filters.status)
      }

      // Filter by trade type
      if (filters.trade_type) {
        query = query.eq('trade_type', filters.trade_type)
      }

      console.log('Executing barter trades query...');
      const { data, error } = await query.order('created_at', { ascending: false })

      if (error) {
        console.error('Supabase query error:', error);
        throw error;
      }

      console.log('Barter trades query successful, returned:', data?.length || 0, 'records');
      return data || []
    } catch (error) {
      console.error('Get barter trades error:', error)
      reportError(error)
      throw error
    }
  }

  async createBarterTrade(tradeData) {
    try {
      const { data, error } = await supabase
        .from('barter_trades')
        .insert({
          initiator_id: tradeData.initiator_id,
          offered_listing_id: tradeData.offered_listing_id,
          requested_items: tradeData.requested_items,
          trade_type: tradeData.trade_type || 'direct',
          message: tradeData.message,
          status: 'pending',
          analysis: tradeData.analysis,
          created_at: new Date().toISOString()
        })
        .select(`
          *,
          initiator:users!barter_trades_initiator_id_fkey (
            id,
            name,
            avatar_url
          ),
          offered_listing:food_listings!barter_trades_offered_listing_id_fkey (
            id,
            title,
            description,
            image_url,
            quantity,
            unit,
            category
          )
        `)
        .single()

      if (error) throw error

      return data
    } catch (error) {
      console.error('Create barter trade error:', error)
      reportError(error)
      throw error
    }
  }

  async updateBarterTradeStatus(tradeId, status, additionalData = {}) {
    try {
      const updateData = {
        status,
        updated_at: new Date().toISOString(),
        ...additionalData
      }

      const { data, error } = await supabase
        .from('barter_trades')
        .update(updateData)
        .eq('id', tradeId)
        .select(`
          *,
          initiator:users!barter_trades_initiator_id_fkey (
            id,
            name,
            avatar_url
          ),
          offered_listing:food_listings!barter_trades_offered_listing_id_fkey (
            id,
            title,
            description,
            image_url,
            quantity,
            unit,
            category
          )
        `)
        .single()

      if (error) throw error

      return data
    } catch (error) {
      console.error('Update barter trade status error:', error)
      reportError(error)
      throw error
    }
  }

  // Users
  async getUsers(filters = {}) {
    try {
      let query = supabase
        .from('users')
        .select('*')

      if (filters.role) {
        query = query.eq('role', filters.role)
      }
      if (filters.status) {
        query = query.eq('status', filters.status)
      }

      const { data, error } = await query.order('created_at', { ascending: false })

      if (error) throw error

      return data
    } catch (error) {
      console.error('Get users error:', error)
      reportError(error)
      throw error
    }
  }

  async getUserProfile(userId) {
    try {
      const { data, error } = await supabase
        .from('users')
        .select(`
          *,
          user_stats (*),
          user_badges (*)
        `)
        .eq('id', userId)
        .single()

      if (error) throw error

      return data
    } catch (error) {
      console.error('Get user profile error:', error)
      reportError(error)
      throw error
    }
  }

  async updateUserProfile(userId, updates) {
    try {
      const { data, error } = await supabase
        .from('users')
        .update(updates)
        .eq('id', userId)
        .select(`
          *,
          user_stats (*),
          user_badges (*)
        `)
        .single()

      if (error) throw error

      return data
    } catch (error) {
      console.error('Update user profile error:', error)
      reportError(error)
      throw error
    }
  }

  // Blog Posts
  async getBlogPosts(filters = {}) {
    try {
      let query = supabase
        .from('blog_posts')
        .select(`
          *,
          author:users!blog_posts_author_id_fkey (
            id,
            name,
            avatar_url
          )
        `)
        .eq('published', true)

      if (filters.category) {
        query = query.eq('category', filters.category)
      }

      const { data, error } = await query.order('published_at', { ascending: false })

      if (error) throw error

      return data
    } catch (error) {
      console.error('Get blog posts error:', error)
      reportError(error)
      throw error
    }
  }

  async getBlogPost(slug) {
    try {
      const { data, error } = await supabase
        .from('blog_posts')
        .select(`
          *,
          author:users!blog_posts_author_id_fkey (
            id,
            name,
            avatar_url
          )
        `)
        .eq('slug', slug)
        .eq('published', true)
        .single()

      if (error) throw error

      return data
    } catch (error) {
      console.error('Get blog post error:', error)
      reportError(error)
      throw error
    }
  }

  // Comments and Likes
  async createComment(commentData) {
    try {
      const { data, error } = await supabase
        .from('comments')
        .insert(commentData)
        .select(`
          *,
          author:users (
            id,
            name,
            avatar_url
          )
        `)
        .single()

      if (error) throw error

      return data
    } catch (error) {
      console.error('Create comment error:', error)
      reportError(error)
      throw error
    }
  }

  async getCommentsForPost(postId) {
    try {
      const { data, error } = await supabase
        .from('comments')
        .select(`
          *,
          author:users (
            id,
            name,
            avatar_url
          )
        `)
        .eq('post_id', postId)
        .order('created_at', { ascending: true })

      if (error) throw error

      return data
    } catch (error) {
      console.error('Get comments for post error:', error)
      reportError(error)
      throw error
    }
  }

  async likePost(postId, userId) {
    try {
      const { data, error } = await supabase
        .from('post_likes')
        .insert({ post_id: postId, user_id: userId })
        .select()
        .single()

      if (error) throw error

      await supabase.rpc('increment_likes_count', { post_id_arg: postId })

      return data
    } catch (error) {
      console.error('Like post error:', error)
      reportError(error)
      throw error
    }
  }

  async unlikePost(postId, userId) {
    try {
      const { error } = await supabase
        .from('post_likes')
        .delete()
        .eq('post_id', postId)
        .eq('user_id', userId)

      if (error) throw error

      await supabase.rpc('decrement_likes_count', { post_id_arg: postId })

      return { success: true }
    } catch (error) {
      console.error('Unlike post error:', error)
      reportError(error)
      throw error
    }
  }

  // Community Posts
  async getCommunityPosts(filters = {}) {
    try {
      let query = supabase
        .from('community_posts')
        .select(`
          *,
          author:users!community_posts_author_id_fkey (
            id,
            name,
            avatar_url
          ),
          comments:community_comments (
            id,
            content,
            created_at,
            author:users!community_comments_author_id_fkey (
              id,
              name,
              avatar_url
            )
          )
        `)

      // Apply filters
      if (filters.category) {
        query = query.eq('category', filters.category)
      }

      const { data, error } = await query.order('created_at', { ascending: false })

      if (error) throw error

      return data || []
    } catch (error) {
      console.error('Get community posts error:', error)
      reportError(error)
      // If community_posts table doesn't exist, return empty array for now
      return []
    }
  }

  async createCommunityPost(postData) {
    try {
      // Transform the data to match database schema
      const dbData = {
        title: postData.title,
        content: postData.content,
        category: postData.category || 'general',
        author_id: postData.author?.id || postData.author_id
      };
      console.log('Debug: Creating community post with author_id:', dbData.author_id);

      const { data, error } = await supabase
        .from('community_posts')
        .insert(dbData)
        .select(`
          *,
          author:users!community_posts_author_id_fkey (
            id,
            name,
            avatar_url
          )
        `)
        .single()

      if (error) throw error

      return data
    } catch (error) {
      console.error('Create community post error:', error)
      reportError(error)
      throw error
    }
  }

  async addCommentToCommunityPost(postId, comment) {
    try {
      const { data, error } = await supabase
        .from('community_comments')
        .insert({
          post_id: postId,
          content: comment.content,
          author_id: comment.author_id
        })
        .select(`
          *,
          author:users!community_comments_author_id_fkey (
            id,
            name,
            avatar_url
          )
        `)
        .single()

      if (error) throw error

      return data
    } catch (error) {
      console.error('Add comment to community post error:', error)
      reportError(error)
      throw error
    }
  }

  async likeCommunityPost(postId, userId) {
    try {
      const { data, error } = await supabase
        .from('community_post_likes')
        .insert({ post_id: postId, user_id: userId })
        .select()
        .single()

      if (error) throw error

      return data
    } catch (error) {
      console.error('Like community post error:', error)
      reportError(error)
      throw error
    }
  }

  async unlikeCommunityPost(postId, userId) {
    try {
      const { data, error } = await supabase
        .from('community_post_likes')
        .delete()
        .eq('post_id', postId)
        .eq('user_id', userId)

      if (error) throw error

      return data
    } catch (error) {
      console.error('Unlike community post error:', error)
      reportError(error)
      throw error
    }
  }

  // Distribution Events
  async getDistributionEvents() {
    try {
      const { data, error } = await supabase
        .from('distribution_events')
        .select('*')
        .order('event_date', { ascending: true })

      if (error) throw error

      return data
    } catch (error) {
      console.error('Get distribution events error:', error)
      reportError(error)
      throw error
    }
  }

  async registerForEvent(eventId, userId) {
    try {
      const { error } = await supabase
        .from('distribution_registrations')
        .insert({
          event_id: eventId,
          user_id: userId
        })

      if (error) throw error

      // Update event registration count
      await supabase.rpc('increment_registration_count', { event_id: eventId })

      return { success: true }
    } catch (error) {
      console.error('Register for event error:', error)
      reportError(error)
      throw error
    }
  }

  // Notifications
  async getNotifications(userId) {
    try {
      const { data, error } = await supabase
        .from('notifications')
        .select('*')
        .eq('user_id', userId)
        .order('created_at', { ascending: false })

      if (error) throw error

      return data
    } catch (error) {
      console.error('Get notifications error:', error)
      reportError(error)
      throw error
    }
  }

  async markNotificationAsRead(notificationId) {
    try {
      const { error } = await supabase
        .from('notifications')
        .update({ read: true })
        .eq('id', notificationId)

      if (error) throw error

      return { success: true }
    } catch (error) {
      console.error('Mark notification as read error:', error)
      reportError(error)
      throw error
    }
  }

  async createNotification(notificationData) {
    try {
      const { data, error } = await supabase
        .from('notifications')
        .insert(notificationData)
        .select()
        .single()

      if (error) throw error

      return data
    } catch (error) {
      console.error('Create notification error:', error)
      reportError(error)
      throw error
    }
  }

  // Real-time subscriptions
  subscribeToFoodListings(callback) {
    console.log('Setting up food listings subscription');
    const subscription = supabase
      .channel('food_listings_changes')
      .on('postgres_changes', {
        event: '*',
        schema: 'public',
        table: 'food_listings'
      }, (payload) => {
        console.log('Food listing change detected:', payload.eventType, payload.new?.id);
        callback(payload);
      })
      .subscribe((status) => {
        console.log('Food listings subscription status:', status);
      })

    this.subscriptions.set('food_listings', subscription)
    return subscription
  }
  
  subscribeToClaims(callback) {
    console.log('Setting up food claims subscription');
    const subscription = supabase
      .channel('food_claims_changes')
      .on('postgres_changes', {
        event: '*',
        schema: 'public',
        table: 'food_claims'
      }, (payload) => {
        console.log('Food claim change detected:', payload.eventType, payload.new?.id);
        callback(payload);
      })
      .subscribe((status) => {
        console.log('Food claims subscription status:', status);
      })

    this.subscriptions.set('food_claims', subscription)
    return subscription
  }

  subscribeToTrades(userId, callback) {
    const subscription = supabase
      .channel('trades_changes')
      .on('postgres_changes', {
        event: '*',
        schema: 'public',
        table: 'trades',
        filter: `initiator_id=eq.${userId} OR recipient_id=eq.${userId}`
      }, callback)
      .subscribe()

    this.subscriptions.set('trades', subscription)
    return subscription
  }

  subscribeToBarterTrades(userId, callback) {
    const subscription = supabase
      .channel('barter_trades_changes')
      .on('postgres_changes', {
        event: '*',
        schema: 'public',
        table: 'barter_trades',
        filter: `initiator_id=eq.${userId}`
      }, callback)
      .subscribe()

    this.subscriptions.set('barter_trades', subscription)
    return subscription
  }

  subscribeToNotifications(userId, callback) {
    const subscription = supabase
      .channel('notifications_changes')
      .on('postgres_changes', {
        event: '*',
        schema: 'public',
        table: 'notifications',
        filter: `user_id=eq.${userId}`
      }, callback)
      .subscribe()

    this.subscriptions.set('notifications', subscription)
    return subscription
  }

  unsubscribe(channelName) {
    const subscription = this.subscriptions.get(channelName)
    if (subscription) {
      subscription.unsubscribe()
      this.subscriptions.delete(channelName)
    }
  }

  unsubscribeAll() {
    this.subscriptions.forEach(subscription => {
      subscription.unsubscribe()
    })
    this.subscriptions.clear()
  }

  // File upload
  async uploadFile(file, bucket = 'food-images') {
    try {
      const fileExt = file.name.split('.').pop()
      const fileName = `${Date.now()}-${Math.random().toString(36).substring(2)}.${fileExt}`
      const filePath = `${bucket}/${fileName}`

      const { error: uploadError } = await supabase.storage
        .from(bucket)
        .upload(filePath, file)

      if (uploadError) throw uploadError

      const { data: { publicUrl } } = supabase.storage
        .from(bucket)
        .getPublicUrl(filePath)

      return { success: true, url: publicUrl }
    } catch (error) {
      console.error('File upload error:', error)
      reportError(error)
      throw error
    }
  }

  // Search functionality
  async searchFoodListings(searchTerm, filters = {}) {
    try {
      let query = supabase
        .from('food_listings')
        .select(`
          *,
          users!food_listings_user_id_fkey (
            id,
            name,
            avatar_url,
            organization
          )
        `)
        .eq('status', 'active')
        .or(`title.ilike.%${searchTerm}%,description.ilike.%${searchTerm}%`)

      // Apply additional filters
      if (filters.category) {
        query = query.eq('category', filters.category)
      }
      if (filters.listing_type) {
        query = query.eq('listing_type', filters.listing_type)
      }

      const { data, error } = await query.order('created_at', { ascending: false })

      if (error) throw error

      return data.map(listing => ({
        ...listing,
        donor: listing.users
      }))
    } catch (error) {
      console.error('Search food listings error:', error)
      reportError(error)
      throw error
    }
  }

  // Analytics and stats
  async getUserStats(userId) {
    try {
      const { data, error } = await supabase
        .from('user_stats')
        .select('*')
        .eq('user_id', userId)
        .single()

      if (error) throw error

      return data
    } catch (error) {
      console.error('Get user stats error:', error)
      reportError(error)
      throw error
    }
  }

  async updateUserStats(userId, updates) {
    try {
      const { data, error } = await supabase
        .from('user_stats')
        .upsert({
          user_id: userId,
          ...updates,
          last_updated: new Date().toISOString()
        })
        .select()
        .single()

      if (error) throw error

      return data
    } catch (error) {
      console.error('Update user stats error:', error)
      reportError(error)
      throw error
    }
  }

  // Admin functions
  async getAdminStats() {
    try {
      const [
        { count: totalUsers },
        { count: totalListings },
        { count: activeTrades },
        { count: totalDonations }
      ] = await Promise.all([
        supabase.from('users').select('*', { count: 'exact', head: true }),
        supabase.from('food_listings').select('*', { count: 'exact', head: true }),
        supabase.from('trades').select('*', { count: 'exact', head: true }).eq('status', 'active'),
        supabase.from('food_listings').select('*', { count: 'exact', head: true }).eq('listing_type', 'donation')
      ])

      return {
        totalUsers,
        totalListings,
        activeTrades,
        totalDonations,
        lastUpdated: new Date().toISOString()
      }
    } catch (error) {
      console.error('Get admin stats error:', error)
      reportError(error)
      throw error
    }
  }

  async getRecentListings(limit = 10) {
    try {
      const { data, error } = await supabase
        .from('food_listings')
        .select(`
          *,
          users!food_listings_user_id_fkey (
            id,
            name,
            avatar_url
          )
        `)
        .order('created_at', { ascending: false })
        .limit(limit)

      if (error) throw error

      return data
    } catch (error) {
      console.error('Get recent listings error:', error)
      reportError(error)
      throw error
    }
  }

  async getRecentUsers(limit = 10) {
    try {
      const { data, error } = await supabase
        .from('users')
        .select('id, name, email, avatar_url, created_at, organization')
        .order('created_at', { ascending: false })
        .limit(limit)

      if (error) throw error

      return data
    } catch (error) {
      console.error('Get recent users error:', error)
      reportError(error)
      throw error
    }
  }
}

// Create singleton instance
const dataService = new DataService()

export default dataService