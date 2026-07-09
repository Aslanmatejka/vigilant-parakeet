/**
 * Verification Service
 * Handles before/after pickup verification with photo uploads and status tracking
 */

import supabase from './supabaseClient';
import { reportError } from './helpers';

export const VERIFICATION_TYPES = {
  BEFORE: 'before',
  AFTER: 'after'
};

export const VERIFICATION_STATUS = {
  PENDING: 'pending',
  VERIFIED_BEFORE: 'verified_before',
  VERIFIED_AFTER: 'verified_after',
  COMPLETED: 'completed',
  DISPUTED: 'disputed',
  SKIPPED: 'skipped'
};

export const DISPUTE_TYPES = {
  QUALITY_MISMATCH: 'quality_mismatch',
  QUANTITY_MISMATCH: 'quantity_mismatch',
  NOT_AS_DESCRIBED: 'not_as_described',
  SAFETY_CONCERN: 'safety_concern',
  OTHER: 'other'
};

class VerificationService {
  /**
   * Upload verification photo to Supabase Storage
   * @param {File} file - Image file to upload
   * @param {string} listingId - Food listing ID
   * @param {string} verificationType - 'before' or 'after'
   * @returns {Promise<string>} URL of uploaded photo
   */
  static async uploadVerificationPhoto(file, listingId, verificationType) {
    try {
      // Generate unique filename
      const timestamp = Date.now();
      const fileExt = file.name.split('.').pop();
      const fileName = `${listingId}_${verificationType}_${timestamp}.${fileExt}`;
      const filePath = `verification/${listingId}/${fileName}`;

      // Upload to Supabase Storage
      const { error } = await supabase.storage
        .from('food-images') // Reuse existing bucket or create 'verification-photos'
        .upload(filePath, file, {
          cacheControl: '3600',
          upsert: false
        });

      if (error) throw error;

      // Get public URL
      const { data: urlData } = supabase.storage
        .from('food-images')
        .getPublicUrl(filePath);

      return urlData.publicUrl;
    } catch (error) {
      reportError(error);
      throw new Error(`Failed to upload verification photo: ${error.message}`);
    }
  }

  /**
   * Upload multiple verification photos
   * @param {FileList|Array} files - Files to upload
   * @param {string} listingId - Food listing ID
   * @param {string} verificationType - 'before' or 'after'
   * @returns {Promise<Array<string>>} Array of photo URLs
   */
  static async uploadVerificationPhotos(files, listingId, verificationType) {
    try {
      const uploadPromises = Array.from(files).map(file =>
        this.uploadVerificationPhoto(file, listingId, verificationType)
      );
      return await Promise.all(uploadPromises);
    } catch (error) {
      reportError(error);
      throw new Error(`Failed to upload verification photos: ${error.message}`);
    }
  }

  /**
   * Submit before-pickup verification
   * @param {string} listingId - Food listing ID
   * @param {Object} verificationData - Verification data
   * @returns {Promise<Object>} Updated listing
   */
  static async verifyBeforePickup(listingId, verificationData) {
    try {
      const { data: { user } } = await supabase.auth.getUser();
      if (!user) throw new Error('User not authenticated');

      const { photos, notes } = verificationData;

      // Upload photos if provided
      let photoUrls = [];
      if (photos && photos.length > 0) {
        photoUrls = await this.uploadVerificationPhotos(photos, listingId, VERIFICATION_TYPES.BEFORE);
      }

      // Update food listing
      const { data, error } = await supabase
        .from('food_listings')
        .update({
          verified_before_pickup: true,
          verification_before_photos: photoUrls,
          verification_before_notes: notes || null,
          verified_before_by: user.id,
          verified_before_at: new Date().toISOString()
        })
        .eq('id', listingId)
        .select()
        .single();

      if (error) throw error;

      return data;
    } catch (error) {
      reportError(error);
      throw new Error(`Failed to verify before pickup: ${error.message}`);
    }
  }

  /**
   * Submit after-pickup verification
   * @param {string} listingId - Food listing ID
   * @param {Object} verificationData - Verification data
   * @returns {Promise<Object>} Updated listing
   */
  static async verifyAfterPickup(listingId, verificationData) {
    try {
      const { data: { user } } = await supabase.auth.getUser();
      if (!user) throw new Error('User not authenticated');

      const { photos, notes } = verificationData;

      // Upload photos if provided
      let photoUrls = [];
      if (photos && photos.length > 0) {
        photoUrls = await this.uploadVerificationPhotos(photos, listingId, VERIFICATION_TYPES.AFTER);
      }

      // Update food listing
      const { data, error } = await supabase
        .from('food_listings')
        .update({
          verified_after_pickup: true,
          verification_after_photos: photoUrls,
          verification_after_notes: notes || null,
          verified_after_by: user.id,
          verified_after_at: new Date().toISOString()
        })
        .eq('id', listingId)
        .select()
        .single();

      if (error) throw error;

      return data;
    } catch (error) {
      reportError(error);
      throw new Error(`Failed to verify after pickup: ${error.message}`);
    }
  }

  /**
   * Get verification status for a listing
   * @param {string} listingId - Food listing ID
   * @returns {Promise<Object>} Verification status
   */
  static async getVerificationStatus(listingId) {
    try {
      const { data, error } = await supabase
        .from('food_listings')
        .select(`
          id,
          verification_status,
          verified_before_pickup,
          verified_after_pickup,
          verification_before_photos,
          verification_after_photos,
          verification_before_notes,
          verification_after_notes,
          verified_before_at,
          verified_after_at,
          verified_before_by,
          verified_after_by,
          verification_required
        `)
        .eq('id', listingId)
        .single();

      if (error) throw error;

      return data;
    } catch (error) {
      reportError(error);
      throw new Error(`Failed to get verification status: ${error.message}`);
    }
  }

  /**
   * Get verification logs for a listing
   * @param {string} listingId - Food listing ID
   * @returns {Promise<Array>} Verification logs
   */
  static async getVerificationLogs(listingId) {
    try {
      const { data, error } = await supabase
        .from('verification_logs')
        .select('*')
        .eq('listing_id', listingId)
        .order('created_at', { ascending: false });

      if (error) throw error;

      return data || [];
    } catch (error) {
      reportError(error);
      throw new Error(`Failed to get verification logs: ${error.message}`);
    }
  }

  /**
   * Report a dispute about a food listing
   * @param {string} listingId - Food listing ID
   * @param {Object} disputeData - Dispute information
   * @returns {Promise<Object>} Created dispute
   */
  static async reportDispute(listingId, disputeData) {
    try {
      const { data: { user } } = await supabase.auth.getUser();
      if (!user) throw new Error('User not authenticated');

      const { type, description, evidencePhotos } = disputeData;

      // Upload evidence photos if provided
      let photoUrls = [];
      if (evidencePhotos && evidencePhotos.length > 0) {
        photoUrls = await this.uploadVerificationPhotos(
          evidencePhotos, 
          listingId, 
          'dispute'
        );
      }

      // Create dispute
      const { data, error } = await supabase
        .from('verification_disputes')
        .insert({
          listing_id: listingId,
          reported_by: user.id,
          dispute_type: type,
          description,
          evidence_photos: photoUrls,
          status: 'open'
        })
        .select()
        .single();

      if (error) throw error;

      // Update listing status to disputed
      await supabase
        .from('food_listings')
        .update({ verification_status: VERIFICATION_STATUS.DISPUTED })
        .eq('id', listingId);

      return data;
    } catch (error) {
      reportError(error);
      throw new Error(`Failed to report dispute: ${error.message}`);
    }
  }

  /**
   * Get disputes for a listing
   * @param {string} listingId - Food listing ID
   * @returns {Promise<Array>} Disputes
   */
  static async getDisputes(listingId) {
    try {
      const { data, error } = await supabase
        .from('verification_disputes')
        .select('*')
        .eq('listing_id', listingId)
        .order('created_at', { ascending: false });

      if (error) throw error;

      return data || [];
    } catch (error) {
      reportError(error);
      throw new Error(`Failed to get disputes: ${error.message}`);
    }
  }

  /**
   * Skip verification (only allowed by donor)
   * @param {string} listingId - Food listing ID
   * @returns {Promise<Object>} Updated listing
   */
  static async skipVerification(listingId) {
    try {
      const { data, error } = await supabase
        .from('food_listings')
        .update({
          verification_status: VERIFICATION_STATUS.SKIPPED,
          verification_required: false
        })
        .eq('id', listingId)
        .select()
        .single();

      if (error) throw error;

      return data;
    } catch (error) {
      reportError(error);
      throw new Error(`Failed to skip verification: ${error.message}`);
    }
  }

  /**
   * Check if user can verify (donor for before, recipient for after)
   * @param {string} listingId - Food listing ID
   * @param {string} verificationType - 'before' or 'after'
   * @returns {Promise<boolean>} Can verify
   */
  static async canVerify(listingId, verificationType) {
    try {
      const { data: { user } } = await supabase.auth.getUser();
      if (!user) return false;

      const { data: listing } = await supabase
        .from('food_listings')
        .select('user_id, claimed_by')
        .eq('id', listingId)
        .single();

      if (!listing) return false;

      if (verificationType === VERIFICATION_TYPES.BEFORE) {
        // Donor can verify before pickup
        return listing.user_id === user.id;
      } else {
        // Recipient can verify after pickup
        return listing.claimed_by === user.id;
      }
    } catch (error) {
      reportError(error);
      return false;
    }
  }

  /**
   * Get verification statistics for admin dashboard
   * @returns {Promise<Object>} Verification stats
   */
  static async getVerificationStats() {
    try {
      const { data, error } = await supabase
        .from('food_listings')
        .select('verification_status');

      if (error) throw error;

      const stats = {
        total: data.length,
        pending: 0,
        verified_before: 0,
        verified_after: 0,
        completed: 0,
        disputed: 0,
        skipped: 0
      };

      data.forEach(listing => {
        const status = listing.verification_status || 'pending';
        stats[status] = (stats[status] || 0) + 1;
      });

      return stats;
    } catch (error) {
      reportError(error);
      throw new Error(`Failed to get verification stats: ${error.message}`);
    }
  }
}

export default VerificationService;
