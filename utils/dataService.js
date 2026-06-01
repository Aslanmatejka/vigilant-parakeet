import supabase, { SUPABASE_AUTH_KEY } from './supabaseClient.js'
import { reportError } from './helpers.js'
import communities from './communities.js'
import { assignFoodImage } from './foodImages.js'

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
      // Some deployments may not have the `people` column. Try the full select first
      // and if Postgres returns a column-not-found error (42703) retry without that column.
      let claims = [];
      try {
        const res = await supabase
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

        if (res.error) throw res.error;
        claims = res.data || [];
      } catch (err) {
        // If people column doesn't exist, retry excluding it
        if (err && err.code === '42703') {
          const res2 = await supabase
            .from('food_claims')
            .select(`
              id,
              food_id, 
              members_count, 
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

          if (res2.error) throw res2.error;
          claims = res2.data || [];
        } else {
          console.error('Error fetching claims:', err);
          throw err;
        }
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
      const pendingListings = sharedFood.filter(item => item.status === 'pending').length;
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
        pendingListings,
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

  async getUserImpact(userId) {
    try {
      console.log(`Fetching impact data for user ${userId}...`);

      // Get user's food listings
      const { data: userListings, error: listingsError } = await supabase
        .from('food_listings')
        .select('id, quantity, unit, category, status, created_at')
        .eq('user_id', userId);

      if (listingsError) throw listingsError;

      // Get claims for this user's food listings
      const listingIds = userListings.map(l => l.id);
      let claims = [];

      if (listingIds.length > 0) {
        const { data: userClaims, error: claimsError } = await supabase
          .from('food_claims')
          .select('id, food_id, members_count, people, school_staff, students, status, created_at')
          .in('food_id', listingIds)
          .eq('status', 'approved');

        if (claimsError) throw claimsError;
        claims = userClaims || [];
      }

      // Calculate metrics
      const totalListings = userListings.length;
      const activeListings = userListings.filter(l => l.status === 'approved').length;
      const pendingListings = userListings.filter(l => l.status === 'pending').length;
      const claimedListings = claims.length;

      const totalFoodShared = userListings.reduce((sum, l) => sum + (l.quantity || 0), 0);
      const foodClaimed = claims.reduce((sum, c) => {
        const listing = userListings.find(l => l.id === c.food_id);
        return sum + (listing?.quantity || 0);
      }, 0);

      const peopleHelped = claims.reduce((sum, c) => sum + (c.members_count || 0), 0);
      const studentsHelped = claims.reduce((sum, c) => sum + (c.students || 0), 0);
      const staffHelped = claims.reduce((sum, c) => sum + (c.school_staff || 0), 0);
      const livesImpacted = peopleHelped + studentsHelped + staffHelped;

      const co2Reduced = foodClaimed * 2.5; // 1 lb food = 2.5 lb CO2

      const result = {
        totalListings,
        activeListings,
        pendingListings,
        claimedListings,
        totalFoodShared,
        foodClaimed,
        peopleHelped,
        studentsHelped,
        staffHelped,
        livesImpacted,
        co2Reduced,
        lastUpdated: new Date().toISOString()
      };

      console.log('User impact data calculated:', result);
      return result;
    } catch (error) {
      console.error('Error in getUserImpact:', error);
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
      // Get the claim to find claimer info and food title.
      // Use maybeSingle() so a missing claim returns null instead of throwing.
      const { data: claim, error: claimError } = await supabase
        .from('food_claims')
        .select('requester_name, requester_email, food_id')
        .eq('id', claimId)
        .maybeSingle();
      if (claimError) throw claimError;
      if (!claim) {
        console.warn('sendClaimReviewNotification: claim not found, skipping', claimId);
        return false;
      }

      // Get food title
      let foodTitle = '';
      if (claim.food_id) {
        const { data: food, error: foodError } = await supabase
          .from('food_listings')
          .select('title')
          .eq('id', claim.food_id)
          .maybeSingle();
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
      const { error: notifError } = await supabase.from('notifications').insert(notif);
      if (notifError) {
        console.error('Failed to insert notification:', notifError);
        reportError(notifError);
      }

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
      // NOTE: The previous inline auto-expire UPDATE was removed because it
      // mutated rows on every fetch, which fired Supabase realtime UPDATE
      // events. Any component subscribed to food_listings changes that
      // called getFoodListings in response would feedback-loop. Expiry is
      // now handled at the query layer (the OR expiry_date filter below)
      // and by a scheduled server-side job.

      // Try selecting with community_id, but some schemas may not have that column.
      const selectWithCommunity = `
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
          full_address,
          donor_name,
          donor_email,
          donor_phone,
          donor_city,
          donor_state,
          donor_zip,
          donor_occupation,
          donor_type,
          community_id,
          latitude,
          longitude,
          created_at,
          updated_at,
          pickup_by,
          urgency_level,
          verification_status,
          verified_before_pickup,
          verified_after_pickup,
          dietary_tags,
          allergens,
          allergen_info,
          ingredients,
          storage_requirements,
          requires_refrigeration,
          requires_freezing,
          preparation_date,
          storage_temperature_min,
          storage_temperature_max,
          current_storage_temp,
          safe_handling_instructions,
          reheating_instructions,
          safety_notes,
          passed_safety_check,
          safety_check_date,
          safety_checked_by,
          users:user_id (
            id,
            name,
            avatar_url,
            organization,
            email
          )
        `;

      const selectWithoutCommunity = selectWithCommunity.replace(/\n\s*community_id,?/, '\n');

      // Helper to build query given a select string
      const buildQuery = (selectStr) => {
        let q = supabase
          .from('food_listings')
          .select(selectStr);

        // Apply status filter: skip when viewing own listings (user_id filter present)
        if (filters.status) {
          if (Array.isArray(filters.status)) {
            q = q.in('status', filters.status);
          } else {
            q = q.eq('status', filters.status);
          }
        } else if (!filters.user_id) {
          q = q.in('status', ['approved', 'active']);
        }

        if (filters.category) q = q.eq('category', filters.category);
        if (filters.listing_type) q = q.eq('listing_type', filters.listing_type);
        if (filters.location) q = q.ilike('location', `%${filters.location}%`);
        if (filters.user_id) q = q.eq('user_id', filters.user_id);

        // Safety filter: exclude already-expired listings unless caller is viewing own listings.
        // Items with null expiry_date are kept (no expiration set).
        if (!filters.user_id && !filters.includeExpired) {
          const todayStr = new Date().toISOString().slice(0, 10);
          q = q.or(`expiry_date.is.null,expiry_date.gte.${todayStr}`);
        }
        if (filters.page && filters.limit) {
          const from = (filters.page - 1) * filters.limit;
          const to = from + filters.limit - 1;
          q = q.range(from, to);
        }
        return q;
      };

      // Add timeout to prevent hanging
      const controller = new AbortController();
      const timeoutId = setTimeout(() => controller.abort(), 15000);

      // First attempt: include community_id
      const withDonor = (listing) => ({
        ...listing,
        image_url: listing.image_url || assignFoodImage(listing),
        donor: listing.users,
      });
      try {
        const q1 = buildQuery(selectWithCommunity);
        const { data, error } = await q1.order('created_at', { ascending: false }).abortSignal(controller.signal);
        clearTimeout(timeoutId);
        if (error) throw error;
        return data.map(withDonor);
      } catch (err) {
        clearTimeout(timeoutId);
        // If community_id column doesn't exist, retry without it
        if (err && err.code === '42703') {
          const controller2 = new AbortController();
          const timeoutId2 = setTimeout(() => controller2.abort(), 15000);
          const q2 = buildQuery(selectWithoutCommunity);
          const { data: data2, error: error2 } = await q2.order('created_at', { ascending: false }).abortSignal(controller2.signal);
          clearTimeout(timeoutId2);
          if (error2) throw error2;
          return data2.map(withDonor);
        }
        throw err;
      }
    } catch (error) {
      console.error('Get food listings error:', error)
      reportError(error)
      throw error
    }
  }

  async createFoodListing(listingData) {
    try {
      // Get user_id from data (already set by calling component) or from localStorage
      let userId = listingData.user_id;
      if (!userId) {
        try {
          const sessionData = JSON.parse(localStorage.getItem(SUPABASE_AUTH_KEY) || '{}');
          userId = sessionData?.user?.id;
        } catch (e) {
          console.warn('[createFoodListing] Failed to read user from localStorage');
        }
        if (!userId) throw new Error('User must be authenticated to create a food listing');
      }

      // Handle image upload if File object is provided
      let imageUrl = listingData.image_url || null;
      if (listingData.image instanceof File) {
        try {
          const uploadResult = await this.uploadFile(listingData.image, 'food-images');
          if (uploadResult?.url) {
            imageUrl = uploadResult.url;
          }
        } catch (uploadErr) {
          console.error('[createFoodListing] Image upload failed:', uploadErr);
          throw new Error('Failed to upload image. Please try again.');
        }
      }

      // Map school_district to community_id if provided
      let communityId = listingData.community_id || null;
      if (listingData.school_district && !communityId) {
        try {
          const { data: commData } = await supabase
            .from('communities')
            .select('id, name')
            .eq('name', listingData.school_district)
            .limit(1);
          if (commData && commData.length > 0) {
            communityId = commData[0].id;
          }
        } catch (e) {
          console.warn('[createFoodListing] Failed to look up community:', e);
        }
      }

      // Validate expiry_date is not in the past
      if (listingData.expiry_date) {
        const today = new Date();
        today.setHours(0, 0, 0, 0);
        const expiry = new Date(listingData.expiry_date + 'T00:00:00');
        if (expiry < today) throw new Error('Expiry date cannot be in the past');
      }

      // Build clean listing object with only valid food_listings columns
      const listing = {
        title: listingData.title,
        description: listingData.description,
        quantity: listingData.quantity,
        unit: listingData.unit,
        category: listingData.category,
        expiry_date: listingData.expiry_date || null,
        pickup_by: listingData.pickup_by || null,
        status: listingData.status || 'pending',
        user_id: userId,
        image_url: imageUrl,
        donor_name: listingData.donor_name || null,
        donor_email: listingData.donor_email || null,
        donor_phone: listingData.donor_phone || null,
        donor_city: listingData.donor_city || null,
        donor_state: listingData.donor_state || null,
        donor_zip: listingData.donor_zip || null,
        donor_occupation: listingData.donor_occupation || null,
        donor_type: listingData.donor_type || null,
        community_id: communityId,
        listing_type: listingData.listing_type || 'donation',
        latitude: listingData.latitude || null,
        longitude: listingData.longitude || null,
        dietary_tags: listingData.dietary_tags || [],
        allergens: listingData.allergens || [],
        ingredients: listingData.ingredients || null,
        location: listingData.donor_city || listingData.donor_state ? {
          address: [listingData.donor_city, listingData.donor_state, listingData.donor_zip].filter(Boolean).join(', ').trim(),
          latitude: listingData.latitude,
          longitude: listingData.longitude
        } : (listingData.full_address || null)
      };

      // Use direct REST API to avoid Supabase JS client auth issues
      const supabaseUrl = import.meta.env.VITE_SUPABASE_URL;
      const supabaseKey = import.meta.env.VITE_SUPABASE_ANON_KEY;

      let accessToken = supabaseKey;
      try {
        const sessionData = JSON.parse(localStorage.getItem(SUPABASE_AUTH_KEY) || '{}');
        if (sessionData?.access_token) accessToken = sessionData.access_token;
      } catch (e) { /* use anon key */ }

      const controller = new AbortController();
      const timeout = setTimeout(() => controller.abort(), 15000);

      const response = await fetch(`${supabaseUrl}/rest/v1/food_listings`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'apikey': supabaseKey,
          'Authorization': `Bearer ${accessToken}`,
          'Prefer': 'return=representation'
        },
        body: JSON.stringify(listing),
        signal: controller.signal
      });

      clearTimeout(timeout);

      if (!response.ok) {
        const errText = await response.text();
        throw new Error(`Create food listing failed: ${response.status} - ${errText}`);
      }

      const result = await response.json();
      return Array.isArray(result) ? result[0] : result;
    } catch (error) {
      console.error('Create food listing error:', error)
      reportError(error)
      throw error
    }
  }

  async updateFoodListing(id, updates) {
    try {
      const toUpdate = { ...updates };

      // Handle image upload if File object provided
      if (toUpdate.image instanceof File) {
        try {
          const uploadResult = await this.uploadFile(toUpdate.image, 'food-images');
          if (uploadResult?.url) {
            toUpdate.image_url = uploadResult.url;
          }
        } catch (uploadErr) {
          console.error('[updateFoodListing] Image upload failed:', uploadErr);
          throw new Error('Failed to upload image. Please try again.');
        }
      }

      // Map school_district to community_id on update
      if (toUpdate.school_district) {
        try {
          const { data: commData } = await supabase
            .from('communities')
            .select('id, name')
            .eq('name', toUpdate.school_district)
            .limit(1);
          if (commData && commData.length > 0) {
            toUpdate.community_id = commData[0].id;
          }
        } catch (e) {
          console.warn('[updateFoodListing] Failed to look up community:', e);
        }
      }

      // Remove non-column fields that shouldn't be sent to DB
      delete toUpdate.image;
      delete toUpdate.school_district;
      delete toUpdate.full_address;
      delete toUpdate.donor;
      delete toUpdate.users;

      const { data, error } = await supabase
        .from('food_listings')
        .update(toUpdate)
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

      const { error: rpcError } = await supabase.rpc('increment_likes_count', { post_id_arg: postId })
      if (rpcError) {
        console.error('Failed to increment likes count:', rpcError)
        reportError(rpcError)
      }

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

      const { error: rpcError } = await supabase.rpc('decrement_likes_count', { post_id_arg: postId })
      if (rpcError) {
        console.error('Failed to decrement likes count:', rpcError)
        reportError(rpcError)
      }

      return { success: true }
    } catch (error) {
      console.error('Unlike post error:', error)
      reportError(error)
      throw error
    }
  }

  // Community Posts (main definitions in the Community Posts Methods section below)

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
      const { error: rpcError } = await supabase.rpc('increment_registration_count', { event_id: eventId })
      if (rpcError) {
        console.error('Failed to increment registration count:', rpcError)
        reportError(rpcError)
      }

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
      try {
        supabase.removeChannel(subscription)
        this.subscriptions.delete(channelName)
      } catch (error) {
        console.error(`Error unsubscribing from ${channelName}:`, error)
      }
    }
  }

  unsubscribeAll() {
    this.subscriptions.forEach((subscription, channelName) => {
      try {
        supabase.removeChannel(subscription)
      } catch (error) {
        console.error(`Error unsubscribing from ${channelName}:`, error)
      }
    })
    this.subscriptions.clear()
  }

  // File upload
  async uploadFile(file, bucket = 'food-images') {
    try {
      if (!file || typeof file.name !== 'string') {
        throw new Error('Invalid file provided')
      }
      // Validate type + size up front. Without this any binary could be
      // pushed into the bucket and quotas/CDN bandwidth would suffer.
      if (!file.type || !file.type.startsWith('image/')) {
        throw new Error('Only image files are allowed.')
      }
      const MAX_BYTES = 10 * 1024 * 1024
      if (file.size > MAX_BYTES) {
        throw new Error('Image is too large. Please choose a file under 10 MB.')
      }
      const fileExt = file.name.split('.').pop()
      const fileName = `${Date.now()}-${Math.random().toString(36).substring(2)}.${fileExt}`
      // Use the file name at the root of the bucket (avoid duplicate bucket segments)
      const filePath = `${fileName}`

      // Verify user is authenticated via localStorage (avoids getUser() which can hang)
      try {
        const sessionData = JSON.parse(localStorage.getItem(SUPABASE_AUTH_KEY) || '{}');
        if (!sessionData?.access_token) {
          throw new Error('User must be authenticated to upload files');
        }
      } catch (e) {
        if (e.message && e.message.includes('authenticated')) throw e;
        throw new Error('User must be authenticated to upload files');
      }

      const uploadRes = await supabase.storage
        .from(bucket)
        .upload(filePath, file)

      if (uploadRes.error) throw uploadRes.error

      // getPublicUrl may return different shapes across SDK versions
      const pub = await supabase.storage.from(bucket).getPublicUrl(filePath)
      let publicUrl = null
      if (pub) {
        publicUrl = pub.data?.publicUrl || pub.data?.public_url || pub.data?.publicUrl || pub.publicURL || null
      }

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
      // Sanitize: PostgREST .or() uses commas, parens, and dots as syntax.
      // Raw user input containing any of those characters returns HTTP 400
      // ("failed to parse logic tree"), so strip them before interpolating.
      const safeTerm = String(searchTerm || '')
        .replace(/[,()*%]/g, ' ')
        .replace(/\s+/g, ' ')
        .trim()

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
        .in('status', ['approved', 'active'])
        .or(`title.ilike.%${safeTerm}%,description.ilike.%${safeTerm}%`)

      // Exclude expired listings
      const todayStr = new Date().toISOString().slice(0, 10);
      query = query.or(`expiry_date.is.null,expiry_date.gte.${todayStr}`);

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
        image_url: listing.image_url || assignFoodImage(listing),
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
      const { data, error} = await supabase
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

  // Community Posts Methods
  async getCommunityPosts(filters = {}) {
    try {
      let query = supabase
        .from('community_posts')
        .select(`
          *,
          users!community_posts_author_id_fkey (
            id,
            name,
            avatar_url
          )
        `)
        .eq('published', true)

      if (filters.category) {
        query = query.eq('category', filters.category)
      }

      if (filters.post_type) {
        query = query.eq('post_type', filters.post_type)
      }

      const { data, error } = await query.order('created_at', { ascending: false })

      if (error) throw error

      return data || []
    } catch (error) {
      console.error('Get community posts error:', error)
      reportError(error)
      throw error
    }
  }

  async createCommunityPost(postData) {
    try {
      const { data: { user } } = await supabase.auth.getUser()
      if (!user) throw new Error('User must be authenticated')

      const { data, error } = await supabase
        .from('community_posts')
        .insert({
          ...postData,
          author_id: user.id,
          published: true
        })
        .select(`
          *,
          users!community_posts_author_id_fkey (
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

  async updateCommunityPost(postId, updates) {
    try {
      const { data, error } = await supabase
        .from('community_posts')
        .update(updates)
        .eq('id', postId)
        .select(`
          *,
          users!community_posts_author_id_fkey (
            id,
            name,
            avatar_url
          )
        `)
        .single()

      if (error) throw error

      return data
    } catch (error) {
      console.error('Update community post error:', error)
      reportError(error)
      throw error
    }
  }

  async deleteCommunityPost(postId) {
    try {
      const { error } = await supabase
        .from('community_posts')
        .delete()
        .eq('id', postId)

      if (error) throw error

      return { success: true }
    } catch (error) {
      console.error('Delete community post error:', error)
      reportError(error)
      throw error
    }
  }

  async togglePostLike(postId) {
    try {
      const { data: { user } } = await supabase.auth.getUser()
      if (!user) throw new Error('User must be authenticated to like posts')

      // Check if user already liked the post
      const { data: existingLike, error: checkError } = await supabase
        .from('post_likes')
        .select('id')
        .eq('post_id', postId)
        .eq('user_id', user.id)
        .maybeSingle()

      if (checkError) throw checkError

      if (existingLike) {
        // Unlike: remove the like
        const { error: deleteError } = await supabase
          .from('post_likes')
          .delete()
          .eq('id', existingLike.id)

        if (deleteError) throw deleteError

        return { liked: false }
      } else {
        // Like: add the like
        const { error: insertError } = await supabase
          .from('post_likes')
          .insert({
            post_id: postId,
            user_id: user.id
          })

        if (insertError) throw insertError

        return { liked: true }
      }
    } catch (error) {
      console.error('Toggle post like error:', error)
      reportError(error)
      throw error
    }
  }

  async getUserPostLikes(userId) {
    try {
      const { data, error } = await supabase
        .from('post_likes')
        .select('post_id')
        .eq('user_id', userId)

      if (error) throw error

      return (data || []).map(like => like.post_id)
    } catch (error) {
      console.error('Get user post likes error:', error)
      reportError(error)
      throw error
    }
  }

  subscribeToCommunityPosts(callback) {
    console.log('Setting up community posts subscription')
    const subscription = supabase
      .channel('community_posts_changes')
      .on('postgres_changes', {
        event: '*',
        schema: 'public',
        table: 'community_posts'
      }, (payload) => {
        console.log('Community post change detected:', payload.eventType, payload.new?.id)
        callback(payload)
      })
      .subscribe((status) => {
        console.log('Community posts subscription status:', status)
      })

    this.subscriptions.set('community_posts', subscription)
    return subscription
  }

  subscribeToPostLikes(callback) {
    console.log('Setting up post likes subscription')
    const subscription = supabase
      .channel('post_likes_changes')
      .on('postgres_changes', {
        event: '*',
        schema: 'public',
        table: 'post_likes'
      }, (payload) => {
        console.log('Post like change detected:', payload.eventType)
        callback(payload)
      })
      .subscribe((status) => {
        console.log('Post likes subscription status:', status)
      })

    this.subscriptions.set('post_likes', subscription)
    return subscription
  }

  // Messaging functions
  async getOrCreateConversation(userId) {
    try {
      // Check if conversation already exists for this user
      const { data: existing, error: checkError } = await supabase
        .from('conversations')
        .select('*')
        .eq('user_id', userId)
        .eq('status', 'open')
        .maybeSingle()

      if (checkError) throw checkError

      if (existing) {
        return existing
      }

      // Create new conversation
      const { data: newConversation, error: createError } = await supabase
        .from('conversations')
        .insert({
          user_id: userId,
          subject: 'Support Request',
          status: 'open'
        })
        .select()
        .single()

      if (createError) throw createError

      return newConversation
    } catch (error) {
      console.error('Get or create conversation error:', error)
      reportError(error)
      throw error
    }
  }

  async getConversationMessages(conversationId) {
    try {
      const { data, error } = await supabase
        .from('messages')
        .select('*')
        .eq('conversation_id', conversationId)
        .order('created_at', { ascending: true })

      if (error) throw error

      return data || []
    } catch (error) {
      console.error('Get conversation messages error:', error)
      reportError(error)
      throw error
    }
  }

  async sendMessage(conversationId, message, isFromAdmin = false) {
    try {
      const { data: { user } } = await supabase.auth.getUser()
      if (!user) throw new Error('User must be authenticated to send messages')

      const { data, error } = await supabase
        .from('messages')
        .insert({
          conversation_id: conversationId,
          user_id: user.id,
          message: message,
          is_from_admin: isFromAdmin
        })
        .select()
        .single()

      if (error) throw error

      return data
    } catch (error) {
      console.error('Send message error:', error)
      reportError(error)
      throw error
    }
  }

  async getAdminConversations() {
    try {
      console.log('dataService: getAdminConversations called')

      // First check if user is authenticated
      const { data: { user: currentUser } } = await supabase.auth.getUser()
      console.log('dataService: Current user:', currentUser?.email)

      // Check if user is admin
      if (currentUser) {
        const { data: userProfile } = await supabase
          .from('users')
          .select('is_admin, role')
          .eq('id', currentUser.id)
          .single()
        console.log('dataService: User profile:', userProfile)
      }

      // Fetch conversations without all messages - huge performance improvement
      const { data: conversations, error } = await supabase
        .from('conversations')
        .select(`
          *,
          users:user_id (
            id,
            name,
            email,
            avatar_url
          )
        `)
        .order('last_message_at', { ascending: false })

      if (error) {
        console.error('dataService: Supabase error:', {
          message: error.message,
          code: error.code,
          details: error.details,
          hint: error.hint
        })
        throw error
      }

      // For each conversation, get just the unread count and last message
      const conversationsWithMetadata = await Promise.all(
        conversations.map(async (conv) => {
          // Get unread message count (only from users, not admin messages)
          const { count: unreadCount } = await supabase
            .from('messages')
            .select('*', { count: 'exact', head: true })
            .eq('conversation_id', conv.id)
            .eq('is_from_admin', false)
            .is('read_at', null)

          // Get last message preview
          const { data: lastMessage } = await supabase
            .from('messages')
            .select('message, is_from_admin, created_at')
            .eq('conversation_id', conv.id)
            .order('created_at', { ascending: false })
            .limit(1)
            .maybeSingle()

          return {
            ...conv,
            unread_count: unreadCount || 0,
            last_message: lastMessage,
            messages: [] // Don't load all messages here
          }
        })
      )

      console.log('dataService: Returning conversations:', conversationsWithMetadata?.length || 0)
      return conversationsWithMetadata || []
    } catch (error) {
      console.error('dataService: Get admin conversations error:', error)
      reportError(error)
      throw error
    }
  }

  async markMessageAsRead(messageId) {
    try {
      const { error } = await supabase
        .from('messages')
        .update({ read_at: new Date().toISOString() })
        .eq('id', messageId)
        .is('read_at', null)

      if (error) throw error

      return { success: true }
    } catch (error) {
      console.error('Mark message as read error:', error)
      reportError(error)
      throw error
    }
  }

  async closeConversation(conversationId) {
    try {
      const { error } = await supabase
        .from('conversations')
        .update({ status: 'closed', updated_at: new Date().toISOString() })
        .eq('id', conversationId)

      if (error) throw error

      return { success: true }
    } catch (error) {
      console.error('Close conversation error:', error)
      reportError(error)
      throw error
    }
  }

  async reopenConversation(conversationId) {
    try {
      const { error } = await supabase
        .from('conversations')
        .update({ status: 'open', updated_at: new Date().toISOString() })
        .eq('id', conversationId)

      if (error) throw error

      return { success: true }
    } catch (error) {
      console.error('Reopen conversation error:', error)
      reportError(error)
      throw error
    }
  }

  subscribeToMessages(conversationId, callback) {
    console.log('Setting up messages subscription for conversation:', conversationId)
    const subscription = supabase
      .channel(`messages_${conversationId}`)
      .on('postgres_changes', {
        event: '*',
        schema: 'public',
        table: 'messages',
        filter: `conversation_id=eq.${conversationId}`
      }, (payload) => {
        console.log('Message change detected:', payload.eventType)
        callback(payload)
      })
      .subscribe((status) => {
        console.log('Messages subscription status:', status)
      })

    this.subscriptions.set(`messages_${conversationId}`, subscription)
    return subscription
  }

  subscribeToConversations(callback) {
    console.log('Setting up conversations subscription')
    const subscription = supabase
      .channel('conversations_changes')
      .on('postgres_changes', {
        event: '*',
        schema: 'public',
        table: 'conversations'
      }, (payload) => {
        console.log('Conversation change detected:', payload.eventType)
        callback(payload)
      })
      .subscribe((status) => {
        console.log('Conversations subscription status:', status)
      })

    this.subscriptions.set('conversations', subscription)
    return subscription
  }

  async createDonationSchedule(scheduleData) {
    try {
      const { data: { user } } = await supabase.auth.getUser()
      if (!user) throw new Error('User not authenticated')

      const { data, error } = await supabase
        .from('donation_schedules')
        .insert({
          user_id: user.id,
          ...scheduleData
        })
        .select()
        .single()

      if (error) throw error
      return data
    } catch (error) {
      console.error('Create donation schedule error:', error)
      reportError(error)
      throw error
    }
  }

  async getUserDonationSchedules(userId = null) {
    try {
      let query = supabase
        .from('donation_schedules')
        .select('*')
        .order('created_at', { ascending: false })

      if (userId) {
        query = query.eq('user_id', userId)
      }

      const { data, error } = await query

      if (error) throw error
      return data || []
    } catch (error) {
      console.error('Get donation schedules error:', error)
      reportError(error)
      throw error
    }
  }

  async getDonationSchedule(scheduleId) {
    try {
      const { data, error } = await supabase
        .from('donation_schedules')
        .select('*')
        .eq('id', scheduleId)
        .single()

      if (error) throw error
      return data
    } catch (error) {
      console.error('Get donation schedule error:', error)
      reportError(error)
      throw error
    }
  }

  async updateDonationSchedule(scheduleId, updates) {
    try {
      const { data, error } = await supabase
        .from('donation_schedules')
        .update(updates)
        .eq('id', scheduleId)
        .select()
        .single()

      if (error) throw error
      return data
    } catch (error) {
      console.error('Update donation schedule error:', error)
      reportError(error)
      throw error
    }
  }

  async deleteDonationSchedule(scheduleId) {
    try {
      const { error } = await supabase
        .from('donation_schedules')
        .delete()
        .eq('id', scheduleId)

      if (error) throw error
      return { success: true }
    } catch (error) {
      console.error('Delete donation schedule error:', error)
      reportError(error)
      throw error
    }
  }

  async pauseDonationSchedule(scheduleId) {
    try {
      return await this.updateDonationSchedule(scheduleId, { status: 'paused' })
    } catch (error) {
      console.error('Pause donation schedule error:', error)
      throw error
    }
  }

  async resumeDonationSchedule(scheduleId) {
    try {
      return await this.updateDonationSchedule(scheduleId, { status: 'active' })
    } catch (error) {
      console.error('Resume donation schedule error:', error)
      throw error
    }
  }

  async getDonationHistory(userId = null, scheduleId = null) {
    try {
      let query = supabase
        .from('donation_history')
        .select('*')
        .order('created_at', { ascending: false })

      if (userId) {
        query = query.eq('user_id', userId)
      }

      if (scheduleId) {
        query = query.eq('schedule_id', scheduleId)
      }

      const { data, error } = await query

      if (error) throw error
      return data || []
    } catch (error) {
      console.error('Get donation history error:', error)
      reportError(error)
      throw error
    }
  }

  async getUserDonationStats(userId) {
    try {
      const { data, error } = await supabase
        .from('donation_schedules')
        .select('total_donated, donation_count')
        .eq('user_id', userId)

      if (error) throw error

      const stats = {
        totalDonated: data?.reduce((sum, schedule) => sum + (parseFloat(schedule.total_donated) || 0), 0) || 0,
        totalDonations: data?.reduce((sum, schedule) => sum + (schedule.donation_count || 0), 0) || 0,
        activeSchedules: data?.filter(s => s.status === 'active').length || 0
      }

      return stats
    } catch (error) {
      console.error('Get donation stats error:', error)
      reportError(error)
      throw error
    }
  }

  calculateNextDonationDate(startDate, frequency, currentDate = new Date()) {
    const date = new Date(startDate)
    const now = new Date(currentDate)

    while (date <= now) {
      switch (frequency) {
        case 'daily':
          date.setDate(date.getDate() + 1)
          break
        case 'weekly':
          date.setDate(date.getDate() + 7)
          break
        case 'monthly':
          date.setMonth(date.getMonth() + 1)
          break
        case 'yearly':
          date.setFullYear(date.getFullYear() + 1)
          break
        default:
          throw new Error(`Invalid frequency: ${frequency}`)
      }
    }

    return date.toISOString().split('T')[0]
  }

  // ──────────────────────────────────────────────
  // AI Conversations
  // ──────────────────────────────────────────────

  async getAIConversations(userId, limit = 50) {
    try {
      const { data, error } = await supabase
        .from('ai_conversations')
        .select('*')
        .eq('user_id', userId)
        .order('created_at', { ascending: true })
        .limit(limit)

      if (error) throw error
      return data || []
    } catch (error) {
      console.error('Get AI conversations error:', error)
      reportError(error)
      throw error
    }
  }

  async saveAIMessage(userId, role, message, metadata = {}) {
    try {
      const { data, error } = await supabase
        .from('ai_conversations')
        .insert({
          user_id: userId,
          role,
          message,
          metadata
        })
        .select()
        .single()

      if (error) throw error
      return data
    } catch (error) {
      console.error('Save AI message error:', error)
      reportError(error)
      throw error
    }
  }

  async deleteAIConversations(userId) {
    try {
      const { error } = await supabase
        .from('ai_conversations')
        .delete()
        .eq('user_id', userId)

      if (error) throw error
      return { success: true }
    } catch (error) {
      console.error('Delete AI conversations error:', error)
      reportError(error)
      throw error
    }
  }

  // ──────────────────────────────────────────────
  // AI Reminders
  // ──────────────────────────────────────────────

  async getAIReminders(userId) {
    try {
      const { data, error } = await supabase
        .from('ai_reminders')
        .select('*')
        .eq('user_id', userId)
        .order('trigger_time', { ascending: true })

      if (error) throw error
      return data || []
    } catch (error) {
      console.error('Get AI reminders error:', error)
      reportError(error)
      throw error
    }
  }

  async createAIReminder(userId, message, triggerTime, reminderType = 'general', relatedId = null) {
    try {
      const insertData = {
        user_id: userId,
        message,
        trigger_time: triggerTime,
        reminder_type: reminderType
      }
      if (relatedId) {
        insertData.related_id = relatedId
      }

      const { data, error } = await supabase
        .from('ai_reminders')
        .insert(insertData)
        .select()
        .single()

      if (error) throw error
      return data
    } catch (error) {
      console.error('Create AI reminder error:', error)
      reportError(error)
      throw error
    }
  }

  async deleteAIReminder(reminderId) {
    try {
      const { error } = await supabase
        .from('ai_reminders')
        .delete()
        .eq('id', reminderId)

      if (error) throw error
      return { success: true }
    } catch (error) {
      console.error('Delete AI reminder error:', error)
      reportError(error)
      throw error
    }
  }

  // ──────────────────────────────────────────────
  // AI Feedback
  // ──────────────────────────────────────────────

  async saveAIFeedback(conversationId, userId, rating, comment = null) {
    try {
      const { data, error } = await supabase
        .from('ai_feedback')
        .insert({
          conversation_id: conversationId,
          user_id: userId,
          rating,
          comment
        })
        .select()
        .single()

      if (error) throw error
      return data
    } catch (error) {
      console.error('Save AI feedback error:', error)
      reportError(error)
      throw error
    }
  }

  async getAIFeedbackStats() {
    try {
      const { data, error } = await supabase
        .from('ai_feedback')
        .select('rating')

      if (error) throw error

      const stats = {
        total: data?.length || 0,
        helpful: data?.filter(f => f.rating === 'helpful').length || 0,
        notHelpful: data?.filter(f => f.rating === 'not_helpful').length || 0
      }
      stats.helpfulRate = stats.total > 0 ? Math.round((stats.helpful / stats.total) * 100) : 0

      return stats
    } catch (error) {
      console.error('Get AI feedback stats error:', error)
      reportError(error)
      throw error
    }
  }
}

// Create singleton instance
const dataService = new DataService()

export default dataService