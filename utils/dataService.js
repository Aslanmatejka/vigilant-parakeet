import supabase, { SUPABASE_AUTH_KEY } from './supabaseClient.js'
import { reportError } from './helpers.js'
import { assignFoodImage } from './foodImages.js'
import { geocodeAddress } from './geocoding.js'

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
            pickup_by,
            preparation_date,
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
            dietary_tags,
            allergens,
            allergen_info,
            ingredients,
            storage_requirements,
            packaging_type,
            current_condition,
            is_perishable,
            requires_refrigeration,
            requires_freezing,
            storage_temperature_min,
            storage_temperature_max,
            current_storage_temp,
            safe_handling_instructions,
            reheating_instructions,
            safety_notes,
            passed_safety_check,
            safety_check_date,
            urgency_level,
            weight_per_package,
            weight_unit,
            created_at,
            communities:community_id(id, name)
          )
        `)
        .eq('status', status)
        .order('created_at', { ascending: false });

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
      const activeListings = sharedFood.filter(item => item.status === 'approved' || item.status === 'active').length;
      const expiredListings = sharedFood.filter(item => item.status === 'expired').length;
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
        expiredListings,
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

      // Get user's donation listings only (requests are needs, not impact donations)
      const { data: userListings, error: listingsError } = await supabase
        .from('food_listings')
        .select('id, quantity, unit, category, status, created_at')
        .eq('user_id', userId)
        .eq('listing_type', 'donation');

      if (listingsError) throw listingsError;

      // Get claims for this user's food listings
      const listingIds = userListings.map(l => l.id);
      let claims = [];

      if (listingIds.length > 0) {
        let userClaims = [];
        try {
          const { data, error: claimsError } = await supabase
            .from('food_claims')
            .select('id, food_id, members_count, people, school_staff, students, status, created_at')
            .in('food_id', listingIds)
            .eq('status', 'approved');
          if (claimsError) throw claimsError;
          userClaims = data || [];
        } catch (err) {
          if (err && err.code === '42703') {
            const { data, error: claimsError2 } = await supabase
              .from('food_claims')
              .select('id, food_id, members_count, school_staff, students, status, created_at')
              .in('food_id', listingIds)
              .eq('status', 'approved');
            if (claimsError2) throw claimsError2;
            userClaims = data || [];
          } else {
            throw err;
          }
        }
        claims = userClaims;
      }

      // Calculate metrics
      const totalListings = userListings.length;
      const activeListings = userListings.filter(l => l.status === 'approved' || l.status === 'active').length;
      const expiredListings = userListings.filter(l => l.status === 'expired').length;
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
        expiredListings,
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

  // Create a food claim request
  async createFoodClaim(claimData) {
    try {
      const foodId = claimData?.food_id;
      if (foodId) {
        const { data: listing, error: listingError } = await supabase
          .from('food_listings')
          .select('id, listing_type, status')
          .eq('id', foodId)
          .maybeSingle();
        if (listingError) throw listingError;
        if (!listing) throw new Error('Listing not found');
        if (String(listing.listing_type || '').toLowerCase() === 'request') {
          throw new Error("That's a food request, not a donation — it can't be claimed.");
        }
      }

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

  /** Read a platform_settings JSON value (defaults when missing). */
  async getPlatformSetting(key, fallback = null) {
    try {
      const { data, error } = await supabase
        .from('platform_settings')
        .select('value')
        .eq('key', key)
        .maybeSingle();
      if (error) throw error;
      if (data == null || data.value === undefined) return fallback;
      return data.value;
    } catch (error) {
      console.warn('getPlatformSetting failed:', key, error);
      return fallback;
    }
  }

  async setPlatformSetting(key, value) {
    const { data: { session } } = await supabase.auth.getSession();
    const { error } = await supabase
      .from('platform_settings')
      .upsert({
        key,
        value,
        updated_at: new Date().toISOString(),
        updated_by: session?.user?.id || null,
      });
    if (error) throw error;
    return true;
  }

  async getRequireListingApproval() {
    const value = await this.getPlatformSetting('require_listing_approval', true);
    return value === true || value === 'true';
  }

  async getRequireRequestApproval() {
    const value = await this.getPlatformSetting('require_request_approval', true);
    return value === true || value === 'true';
  }

  async getRequireClaimApproval() {
    const value = await this.getPlatformSetting('require_claim_approval', true);
    return value === true || value === 'true';
  }

  /**
   * Initial listing status for community posts.
   * Admin-trusted posts (skipApproval) always go live as approved.
   * Food requests use require_request_approval; donations use require_listing_approval.
   */
  async resolveCreateListingStatus({ skipApproval = false, listing_type = 'donation' } = {}) {
    if (skipApproval) return 'approved';
    const isRequest = String(listing_type || '').toLowerCase() === 'request';
    const required = isRequest
      ? await this.getRequireRequestApproval()
      : await this.getRequireListingApproval();
    return required ? 'pending' : 'approved';
  }

  async resolveCreateClaimStatus() {
    const required = await this.getRequireClaimApproval();
    return required ? 'pending' : 'approved';
  }

  async updateFoodListingStatus(listingId, status) {
    const { data, error } = await supabase
      .from('food_listings')
      .update({ status })
      .eq('id', listingId)
      .select('id, title, user_id, status')
      .maybeSingle();
    if (error) throw error;
    return data;
  }

  async updateFoodClaimStatus(claimId, status) {
    const { data, error } = await supabase
      .from('food_claims')
      .update({ status })
      .eq('id', claimId)
      .select(`
        id,
        status,
        quantity,
        claimer_id,
        food_id,
        food_listings(id, title, quantity, status, unit)
      `)
      .maybeSingle();
    if (error) throw error;
    return data;
  }

  /**
   * Update claim fields from admin approval queue.
   * If quantity changes while pending, adjust listing inventory by the delta.
   */
  async updateFoodClaim(claimId, updates) {
    const { data: existing, error: fetchError } = await supabase
      .from('food_claims')
      .select(`
        id,
        status,
        quantity,
        food_id,
        food_listings(id, quantity, status, unit)
      `)
      .eq('id', claimId)
      .maybeSingle();
    if (fetchError) throw fetchError;
    if (!existing) throw new Error('Claim not found');

    const allowed = [
      'quantity',
      'requester_name',
      'requester_email',
      'requester_phone',
      'school',
      'school_district',
      'school_contact',
      'school_contact_email',
      'school_contact_phone',
      'members_count',
      'people',
      'students',
      'school_staff',
      'dietary_restrictions',
      'pickup_date',
      'pickup_time',
      'pickup_place',
      'pickup_contact',
      'dropoff_place',
      'dropoff_time',
      'dropoff_contact',
      'category',
    ];
    const patch = {};
    for (const key of allowed) {
      if (Object.prototype.hasOwnProperty.call(updates, key)) {
        patch[key] = updates[key];
      }
    }
    if (!Object.keys(patch).length) {
      throw new Error('No claim fields to update');
    }

    const oldQty = Number(existing.quantity) || 0;
    const nextQty = Object.prototype.hasOwnProperty.call(patch, 'quantity')
      ? Number(patch.quantity)
      : oldQty;
    if (!Number.isFinite(nextQty) || nextQty < 1) {
      throw new Error('Claim quantity must be at least 1');
    }
    patch.quantity = Math.round(nextQty);

    const qtyDelta = patch.quantity - oldQty;
    const listing = existing.food_listings;
    const listingId = listing?.id || existing.food_id;

    if (qtyDelta !== 0 && listingId && String(existing.status || '').toLowerCase() === 'pending') {
      const currentListingQty = Number(listing?.quantity) || 0;
      // Increasing the claim draws more from remaining listing qty.
      if (qtyDelta > 0 && currentListingQty < qtyDelta) {
        throw new Error(
          `Only ${currentListingQty} portion${currentListingQty === 1 ? '' : 's'} left on the listing`
        );
      }
      let restoredQty = currentListingQty - qtyDelta;
      if (restoredQty < 0) restoredQty = 0;
      const listingStatus = String(listing?.status || '').toLowerCase();
      const listingPatch = { quantity: restoredQty };
      if (restoredQty <= 0 && listingStatus !== 'claimed') {
        listingPatch.status = 'claimed';
      } else if (restoredQty > 0 && listingStatus === 'claimed') {
        listingPatch.status = 'approved';
      }
      const { error: listingError } = await supabase
        .from('food_listings')
        .update(listingPatch)
        .eq('id', listingId);
      if (listingError) throw listingError;
    }

    const { data, error } = await supabase
      .from('food_claims')
      .update(patch)
      .eq('id', claimId)
      .select(`
        *,
        food_listings(
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
          pickup_by,
          preparation_date,
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
          dietary_tags,
          allergens,
          allergen_info,
          ingredients,
          storage_requirements,
          packaging_type,
          current_condition,
          is_perishable,
          requires_refrigeration,
          requires_freezing,
          storage_temperature_min,
          storage_temperature_max,
          current_storage_temp,
          safe_handling_instructions,
          reheating_instructions,
          safety_notes,
          passed_safety_check,
          safety_check_date,
          urgency_level,
          weight_per_package,
          weight_unit,
          created_at,
          updated_at,
          communities:community_id(id, name)
        )
      `)
      .maybeSingle();
    if (error) throw error;
    if (!data) throw new Error('Claim update failed');
    return data;
  }

  /**
   * Approve or decline a pending claim.
   * Decline restores reserved inventory to the listing.
   */
  async reviewFoodClaim(claimId, approved) {
    const { data: claim, error: fetchError } = await supabase
      .from('food_claims')
      .select(`
        id,
        status,
        quantity,
        claimer_id,
        food_id,
        food_listings(id, title, quantity, status, unit)
      `)
      .eq('id', claimId)
      .maybeSingle();
    if (fetchError) throw fetchError;
    if (!claim) throw new Error('Claim not found');
    if (String(claim.status || '').toLowerCase() !== 'pending') {
      throw new Error(`Claim is already ${claim.status}`);
    }

    const nextStatus = approved ? 'approved' : 'declined';
    const { data: updated, error: updateError } = await supabase
      .from('food_claims')
      .update({ status: nextStatus })
      .eq('id', claimId)
      .eq('status', 'pending')
      .select('id, status, quantity, claimer_id, food_id')
      .maybeSingle();
    if (updateError) throw updateError;
    if (!updated) throw new Error('Claim was already reviewed by someone else');

    if (!approved && claim.food_id) {
      const listing = claim.food_listings;
      const listingId = listing?.id || claim.food_id;
      const claimQty = Number(claim.quantity) || 1;
      const currentQty = Number(listing?.quantity) || 0;
      const listingStatus = String(listing?.status || '').toLowerCase();
      let restoredQty = currentQty + claimQty;
      // Fully claimed rows may still show stale qty equal to the claim amount.
      if (listingStatus === 'claimed' && currentQty <= 0) {
        restoredQty = claimQty;
      } else if (listingStatus === 'claimed' && currentQty === claimQty) {
        restoredQty = claimQty;
      }
      const { error: restoreError } = await supabase
        .from('food_listings')
        .update({
          quantity: restoredQty,
          status: 'approved',
        })
        .eq('id', listingId);
      if (restoreError) {
        console.error('Failed to restore listing after claim decline:', restoreError);
        throw new Error('Claim declined but inventory restore failed — check Food Distribution');
      }
    }

    return updated;
  }

  async sendClaimReviewNotification(claimId, approved) {
    try {
      const { data: claim, error } = await supabase
        .from('food_claims')
        .select(`
          id,
          claimer_id,
          quantity,
          food_listings(title, unit)
        `)
        .eq('id', claimId)
        .maybeSingle();
      if (error || !claim?.claimer_id) return false;
      const title = claim.food_listings?.title || 'your food claim';
      const qty = claim.quantity || 1;
      const unit = claim.food_listings?.unit || '';
      const qtyLabel = `${qty}${unit ? ` ${unit}` : ''}`.trim();
      const { error: notifError } = await supabase.from('notifications').insert({
        user_id: claim.claimer_id,
        title: approved ? 'Claim approved' : 'Claim not approved',
        message: approved
          ? `Good news — your claim for ${qtyLabel} of "${title}" was approved. You can pick it up from Receipts & Activity.`
          : `Your claim for ${qtyLabel} of "${title}" was not approved. The food is back on Find Food.`,
        type: approved ? 'claim_approved' : 'claim_declined',
        read: false,
        data: { claimId, status: approved ? 'approved' : 'declined' },
      });
      if (notifError) {
        console.warn('sendClaimReviewNotification insert failed:', notifError);
        return false;
      }
      return true;
    } catch (err) {
      console.warn('sendClaimReviewNotification failed:', err);
      return false;
    }
  }

  async sendListingReviewNotification(listingId, approved) {
    try {
      const { data: listing, error } = await supabase
        .from('food_listings')
        .select('id, title, user_id, listing_type, community_id')
        .eq('id', listingId)
        .maybeSingle();
      if (error || !listing?.user_id) return false;
      const title = listing.title || 'your listing';
      const isRequest = String(listing.listing_type || '').toLowerCase() === 'request';

      // Requester + donor "listed" notices for approved food requests are owned
      // by the DB trigger notify_requester_food_request_listed (form, Nouri,
      // admin approve). Skip duplicates here; still notify on decline and for
      // donation approvals.
      const skipRequestLiveNotifs = approved && isRequest;
      if (!skipRequestLiveNotifs) {
        const { error: notifError } = await supabase.from('notifications').insert({
          user_id: listing.user_id,
          title: approved
            ? (isRequest ? 'Food request approved' : 'Listing approved')
            : (isRequest ? 'Food request not approved' : 'Listing not approved'),
          message: approved
            ? (isRequest
              ? `Good news — "${title}" is live on Community Requests so donors can share matching food.`
              : `Good news — "${title}" is live on Find Food and neighbors can claim it.`)
            : `"${title}" was not approved. Please review the guidelines and try again.`,
          type: approved
            ? (isRequest ? 'food_request_approved' : 'listing_approved')
            : 'submission_declined',
          read: false,
          data: {
            listingId,
            status: approved ? 'approved' : 'declined',
            listing_type: listing.listing_type || 'donation',
          },
        });
        if (notifError) {
          console.warn('sendListingReviewNotification insert failed:', notifError);
          return false;
        }
      }

      return true;
    } catch (err) {
      console.warn('sendListingReviewNotification failed:', err);
      return false;
    }
  }

  async countPendingListings() {
    const { count, error } = await supabase
      .from('food_listings')
      .select('id', { count: 'exact', head: true })
      .eq('status', 'pending')
      .eq('listing_type', 'donation');
    if (error) throw error;
    return count || 0;
  }

  async countPendingRequests() {
    const { count, error } = await supabase
      .from('food_listings')
      .select('id', { count: 'exact', head: true })
      .eq('status', 'pending')
      .eq('listing_type', 'request');
    if (error) throw error;
    return count || 0;
  }

  async countPendingClaims() {
    const { count, error } = await supabase
      .from('food_claims')
      .select('id', { count: 'exact', head: true })
      .eq('status', 'pending');
    if (error) throw error;
    return count || 0;
  }

  /**
   * Count live food_listings for nav badges (Find Food / Community Requests).
   * Matches browse filters: approved|active, not expired, optional community scope.
   */
  async countLiveListings({
    listing_type = 'donation',
    community_ids = null,
    exclude_user_id = null,
  } = {}) {
    try {
      if (Array.isArray(community_ids) && community_ids.length === 0) {
        return 0;
      }

      const _d = new Date();
      const todayStr = [
        _d.getFullYear(),
        String(_d.getMonth() + 1).padStart(2, '0'),
        String(_d.getDate()).padStart(2, '0'),
      ].join('-');

      let q = supabase
        .from('food_listings')
        .select('id', { count: 'exact', head: true })
        .eq('listing_type', listing_type)
        .in('status', ['approved', 'active'])
        .or(`expiry_date.is.null,expiry_date.gte.${todayStr}`);

      if (Array.isArray(community_ids)) {
        q = q.in('community_id', community_ids);
      } else if (community_ids != null && community_ids !== '') {
        q = q.eq('community_id', community_ids);
      }

      if (exclude_user_id) {
        q = q.neq('user_id', exclude_user_id);
      }

      const { count, error } = await q;
      if (error) throw error;
      return count || 0;
    } catch (error) {
      console.warn('countLiveListings failed:', error);
      return 0;
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
          user_id,
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
            email,
            address
          ),
          communities:community_id (
            id,
            name
          )
        `;

      const selectWithoutCommunityJoin = selectWithCommunity.replace(
        /\n\s*communities:community_id \([\s\S]*?\)\n/,
        '\n'
      );
      const selectWithoutCommunity = selectWithoutCommunityJoin.replace(/\n\s*community_id,?/, '\n');

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
        // Find Food / public browse: hide the viewer's own donations so they
        // don't try to claim food they posted. My Listings uses user_id instead.
        if (filters.exclude_user_id && !filters.user_id) {
          q = q.neq('user_id', filters.exclude_user_id);
        }
        // Community scope for Find Food / Near Me / map. Own-listing queries
        // (user_id set) and admin/explicit bypasses skip this.
        if (!filters.user_id && !filters.skipCommunityScope) {
          if (Array.isArray(filters.community_ids)) {
            if (filters.community_ids.length === 0) {
              // Impossible match → empty result set without throwing.
              q = q.eq('id', '00000000-0000-0000-0000-000000000000');
            } else {
              q = q.in('community_id', filters.community_ids);
            }
          } else if (filters.community_id != null && filters.community_id !== '') {
            q = q.eq('community_id', filters.community_id);
          }
        }

        // Safety filter: exclude already-expired listings unless caller is viewing own listings.
        // Items with null expiry_date are kept (no expiration set).
        // Use local date so listings don't vanish from results several hours before
        // they actually expire in the user's timezone (UTC-7/8 after 5pm/4pm).
        if (!filters.user_id && !filters.includeExpired) {
          const _d = new Date();
          const todayStr = [_d.getFullYear(), String(_d.getMonth() + 1).padStart(2, '0'), String(_d.getDate()).padStart(2, '0')].join('-');
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
      const withDonor = (listing) => {
        const community = listing.communities;
        const communityRecord = Array.isArray(community) ? community[0] : community;
        const isRequest = String(listing.listing_type || '').toLowerCase() === 'request';
        return {
          ...listing,
          // Food requests are text-only — never show or invent a photo.
          image_url: isRequest
            ? null
            : (listing.image_url || assignFoodImage(listing)),
          donor: listing.users,
          community_name: communityRecord?.name || listing.community_name || null,
        };
      };
      try {
        const q1 = buildQuery(selectWithCommunity);
        const { data, error } = await q1.order('created_at', { ascending: false }).abortSignal(controller.signal);
        clearTimeout(timeoutId);
        if (error) throw error;
        return data.map(withDonor);
      } catch (err) {
        clearTimeout(timeoutId);
        const errMsg = err?.message || '';
        const missingRelationship = err?.code === 'PGRST200' || errMsg.includes('relationship');
        if (missingRelationship) {
          const controllerJoin = new AbortController();
          const timeoutJoin = setTimeout(() => controllerJoin.abort(), 15000);
          const qJoin = buildQuery(selectWithoutCommunityJoin);
          const { data: dataJoin, error: errorJoin } = await qJoin.order('created_at', { ascending: false }).abortSignal(controllerJoin.signal);
          clearTimeout(timeoutJoin);
          if (errorJoin) throw errorJoin;
          return dataJoin.map(withDonor);
        }
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
      // Aborts (timeouts / effect-cleanup) are expected and shouldn't be noisy.
      const msg = error?.message || '';
      if (error?.name === 'AbortError' || error?.code === '20' || msg.includes('aborted')) {
        throw error;
      }
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

      // Handle image upload if File object is provided (donations only —
      // food requests never include photos).
      const isRequest = String(listingData.listing_type || '').toLowerCase() === 'request';
      let imageUrl = isRequest ? null : (listingData.image_url || null);
      if (!isRequest && listingData.image instanceof File) {
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

      // Status is always resolved server-side logic — never trust caller-supplied
      // status (prevents bypassing admin approval via direct REST insert).
      const status = await this.resolveCreateListingStatus({
        skipApproval: !!listingData.skipApproval,
        listing_type: listingData.listing_type || 'donation',
      });

      // Build clean listing object with only valid food_listings columns
      const listing = {
        title: listingData.title,
        description: listingData.description,
        quantity: listingData.quantity,
        unit: listingData.unit,
        category: listingData.category,
        expiry_date: listingData.expiry_date || null,
        pickup_by: listingData.pickup_by || null,
        status,
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
      };
      if (isRequest) {
        listing.image_url = null;
      }

      const fullAddress = listingData.full_address?.trim?.() || listingData.full_address || null;
      if (fullAddress) {
        listing.full_address = fullAddress;
        listing.location = fullAddress;
      } else if (listingData.donor_city || listingData.donor_state) {
        listing.location = [listingData.donor_city, listingData.donor_state, listingData.donor_zip].filter(Boolean).join(', ').trim() || null;
      }

      // Auto-geocode address if coordinates are missing
      // This prevents map marker issues when users don't provide lat/lng
      if (!listing.latitude || !listing.longitude) {
        const addressToGeocode = listing.full_address || listing.location;
        if (addressToGeocode) {
          try {
            console.log(`[createFoodListing] Geocoding address: ${addressToGeocode}`);
            const coords = await geocodeAddress(addressToGeocode);
            if (coords) {
              listing.latitude = coords.latitude;
              listing.longitude = coords.longitude;
              console.log(`[createFoodListing] Geocoded successfully: ${coords.latitude}, ${coords.longitude}`);
            } else {
              console.warn(`[createFoodListing] Failed to geocode address: ${addressToGeocode}`);
            }
          } catch (geocodeErr) {
            // Log but don't fail the listing creation - geocoding can be retried later
            console.error('[createFoodListing] Geocoding error:', geocodeErr);
          }
        } else {
          console.warn('[createFoodListing] No address available for geocoding');
        }
      }

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

      // Food requests never carry photos — strip any image fields.
      let isRequestUpdate = String(toUpdate.listing_type || '').toLowerCase() === 'request';
      if (!isRequestUpdate && id) {
        try {
          const { data: existing } = await supabase
            .from('food_listings')
            .select('listing_type')
            .eq('id', id)
            .maybeSingle();
          isRequestUpdate = String(existing?.listing_type || '').toLowerCase() === 'request';
        } catch (_) {
          /* best-effort; proceed without blocking the update */
        }
      }
      if (isRequestUpdate) {
        toUpdate.image_url = null;
        delete toUpdate.image;
      }

      // Handle image upload if File object provided (donations only)
      if (!isRequestUpdate && toUpdate.image instanceof File) {
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
      // NOTE: full_address IS a real DB column — do NOT delete it.
      delete toUpdate.image;
      delete toUpdate.school_district;
      delete toUpdate.donor;
      delete toUpdate.users;

      // Never trust client-supplied privileged columns on update.
      const privilegedKeys = [
        'status',
        'listing_type',
        'user_id',
        'id',
        'created_at',
        'updated_at',
        'skipApproval',
        'communities',
      ];
      for (const key of privilegedKeys) {
        delete toUpdate[key];
      }

      // Keep location (varchar) in sync with full_address on edit.
      // Without this the location column retains the old address string.
      if (toUpdate.full_address && typeof toUpdate.full_address === 'string') {
        toUpdate.location = toUpdate.full_address.trim();
      }

      // Auto-geocode if address changed but coordinates are missing
      // This ensures updated addresses get proper map markers
      const hasExplicitCoords =
        toUpdate.latitude != null && toUpdate.longitude != null
        && Number.isFinite(Number(toUpdate.latitude))
        && Number.isFinite(Number(toUpdate.longitude));
      if ((toUpdate.full_address || toUpdate.location) && !hasExplicitCoords) {
        const addressToGeocode = toUpdate.full_address || toUpdate.location;
        if (addressToGeocode && typeof addressToGeocode === 'string') {
          try {
            console.log(`[updateFoodListing] Geocoding updated address: ${addressToGeocode}`);
            const coords = await geocodeAddress(addressToGeocode);
            if (coords) {
              toUpdate.latitude = coords.latitude;
              toUpdate.longitude = coords.longitude;
              console.log(`[updateFoodListing] Geocoded successfully: ${coords.latitude}, ${coords.longitude}`);
            } else {
              console.warn(`[updateFoodListing] Failed to geocode address: ${addressToGeocode}`);
            }
          } catch (geocodeErr) {
            console.error('[updateFoodListing] Geocoding error:', geocodeErr);
          }
        }
      }

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

      // Note: no denormalized counter on distribution_events. If we ever
      // need a count, derive it from `distribution_registrations` with a
      // COUNT(*) query rather than maintaining a stale column.
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

  // Unsubscribe by channel reference instead of by table-name key. The
  // name-keyed Map stores only ONE channel per table, so two hooks that
  // both subscribe to e.g. food_listings would have the first channel
  // orphaned on the Supabase realtime connection. Callers that hold the
  // returned subscription handle should prefer this method so their own
  // channel is torn down even if a second consumer has overwritten the
  // Map slot since.
  unsubscribeChannel(subscription) {
    if (!subscription) return
    try {
      supabase.removeChannel(subscription)
    } catch (error) {
      console.error('Error unsubscribing channel:', error)
    }
    // Sweep any Map slot that points at this same channel so we don't
    // leak a stale entry that future unsubscribe(name) calls would try
    // to remove again.
    for (const [name, sub] of this.subscriptions.entries()) {
      if (sub === subscription) this.subscriptions.delete(name)
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

      const _sd = new Date();
      const todayStr = [_sd.getFullYear(), String(_sd.getMonth() + 1).padStart(2, '0'), String(_sd.getDate()).padStart(2, '0')].join('-');

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

      // Apply additional filters
      if (filters.category) {
        query = query.eq('category', filters.category)
      }
      // Default to donations only — requests are a separate feed.
      // Caller can override by passing listing_type explicitly.
      query = query.eq('listing_type', filters.listing_type || 'donation')

      if (!filters.user_id && !filters.skipCommunityScope) {
        if (Array.isArray(filters.community_ids)) {
          if (filters.community_ids.length === 0) {
            query = query.eq('id', '00000000-0000-0000-0000-000000000000');
          } else {
            query = query.in('community_id', filters.community_ids);
          }
        } else if (filters.community_id != null && filters.community_id !== '') {
          query = query.eq('community_id', filters.community_id);
        }
      }
      if (filters.exclude_user_id && !filters.user_id) {
        query = query.neq('user_id', filters.exclude_user_id);
      }

      const { data, error } = await query.order('created_at', { ascending: false })

      if (error) throw error

      // Expiry filter applied client-side — a second .or() would overwrite the
      // title/description .or() above (PostgREST uses searchParams.set).
      const activeRows = (data || []).filter((row) => {
        if (!row.expiry_date) return true
        return String(row.expiry_date).slice(0, 10) >= todayStr
      })

      return activeRows.map(listing => {
        const isRequest = String(listing.listing_type || '').toLowerCase() === 'request';
        return {
          ...listing,
          image_url: isRequest
            ? null
            : (listing.image_url || assignFoodImage(listing)),
          donor: listing.users
        };
      })
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
        { count: totalDonations },
        { count: pendingApprovals },
        { count: pendingRequests },
      ] = await Promise.all([
        supabase.from('users').select('*', { count: 'exact', head: true }),
        supabase.from('food_listings').select('*', { count: 'exact', head: true }),
        supabase.from('food_listings').select('*', { count: 'exact', head: true }).eq('listing_type', 'donation'),
        supabase.from('food_listings').select('*', { count: 'exact', head: true }).eq('status', 'pending').eq('listing_type', 'donation'),
        supabase.from('food_listings').select('*', { count: 'exact', head: true }).eq('status', 'pending').eq('listing_type', 'request'),
      ])

      return {
        totalUsers,
        totalListings,
        totalDonations,
        pendingApprovals: pendingApprovals || 0,
        pendingRequests: pendingRequests || 0,
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
        .select('total_donated, donation_count, status')
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
    // Parse startDate as LOCAL midnight (appending T00:00:00 without TZ offset)
    // to avoid the UTC-midnight shift that puts Pacific users a day behind.
    const date = new Date(startDate + 'T00:00:00')
    const now = currentDate instanceof Date ? currentDate : new Date(currentDate)

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

    // Return using local date components to match the local-midnight parse above.
    return [date.getFullYear(), String(date.getMonth() + 1).padStart(2, '0'), String(date.getDate()).padStart(2, '0')].join('-')
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