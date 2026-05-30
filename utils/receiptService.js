import supabase from './supabaseClient';

/**
 * Receipt Service - Handles receipt operations and expiry logic
 */
class ReceiptService {
    /**
     * Check and expire receipts that are past their pickup_by deadline
     * This should be called by a scheduled task (cron job) or manually by admins
     * @returns {Promise<Object>} Results of the expiry check
     */
    async expireOldReceipts() {
        try {
            console.log('[ReceiptService] Checking for expired receipts...');

            // Call the Supabase function to expire receipts.
            // The function RETURNS TABLE(expired_count INT), so `data` is an
            // array of rows like [{ expired_count: N }].
            const { data, error } = await supabase.rpc('expire_unclaimed_receipts');

            if (error) {
                console.error('[ReceiptService] Error expiring receipts:', error);
                throw error;
            }

            let expiredCount = 0;
            if (Array.isArray(data) && data.length > 0) {
                expiredCount = Number(data[0]?.expired_count ?? 0);
            } else if (typeof data === 'number') {
                expiredCount = data;
            }
            console.log(`[ReceiptService] Expired ${expiredCount} receipts and returned items to inventory`);

            return {
                success: true,
                expiredCount,
                message: `Successfully expired ${expiredCount} receipt(s)`
            };
        } catch (error) {
            console.error('[ReceiptService] Exception in expireOldReceipts:', error);
            return {
                success: false,
                expiredCount: 0,
                error: error.message
            };
        }
    }

    /**
     * Get user's active (pending) receipts
     * @param {string} userId - User ID
     * @returns {Promise<Array>} Active receipts
     */
    async getActiveReceipts(userId) {
        try {
            const { data, error } = await supabase
                .from('receipts')
                .select(`
                    *,
                    food_claims (
                        id,
                        food_id,
                        food_listings (
                            title,
                            quantity,
                            unit
                        )
                    )
                `)
                .eq('user_id', userId)
                .eq('status', 'pending')
                .order('claimed_at', { ascending: false });

            if (error) throw error;

            return data || [];
        } catch (error) {
            console.error('[ReceiptService] Error fetching active receipts:', error);
            return [];
        }
    }

    /**
     * Mark a receipt as picked up (complete)
     * This permanently removes items from inventory
     * @param {string} receiptId - Receipt ID
     * @returns {Promise<Object>} Result of the operation
     */
    async markReceiptPickedUp(receiptId) {
        try {
            // Update receipt status
            const { error: receiptError } = await supabase
                .from('receipts')
                .update({
                    status: 'completed',
                    picked_up_at: new Date().toISOString()
                })
                .eq('id', receiptId);

            if (receiptError) throw receiptError;

            // Get all claims for this receipt
            const { data: claims, error: claimsError } = await supabase
                .from('food_claims')
                .select('food_id')
                .eq('receipt_id', receiptId);

            if (claimsError) throw claimsError;

            const foodIds = claims.map(c => c.food_id);

            // Update all associated food claims
            const { error: updateClaimsError } = await supabase
                .from('food_claims')
                .update({ status: 'completed' })
                .eq('receipt_id', receiptId);

            if (updateClaimsError) throw updateClaimsError;

            // Permanently remove items from inventory (picked up)
            const { error: listingsError } = await supabase
                .from('food_listings')
                .update({ status: 'completed' })
                .in('id', foodIds);

            if (listingsError) throw listingsError;

            return {
                success: true,
                message: 'Receipt marked as picked up successfully'
            };
        } catch (error) {
            console.error('[ReceiptService] Error marking receipt as picked up:', error);
            return {
                success: false,
                error: error.message
            };
        }
    }

    /**
     * Reclaim expired items (create new receipt from expired one)
     * @param {string} expiredReceiptId - Expired receipt ID
     * @param {string} userId - User ID
     * @returns {Promise<Object>} New receipt data
     */
    async reclaimExpiredItems(expiredReceiptId, userId) {
        try {
            // Get the expired receipt
            const { data: oldReceipt, error: fetchError } = await supabase
                .from('receipts')
                .select('*')
                .eq('id', expiredReceiptId)
                .single();

            if (fetchError) throw fetchError;

            // Create new receipt
            const { data: newReceipt, error: receiptError } = await supabase
                .from('receipts')
                .insert({
                    user_id: userId,
                    status: 'pending',
                    pickup_location: oldReceipt.pickup_location,
                    pickup_address: oldReceipt.pickup_address,
                    pickup_window: oldReceipt.pickup_window
                })
                .select()
                .single();

            if (receiptError) throw receiptError;

            // Get all claims from expired receipt
            const { data: oldClaims, error: claimsError } = await supabase
                .from('food_claims')
                .select('food_id')
                .eq('receipt_id', expiredReceiptId);

            if (claimsError) throw claimsError;

            const foodIds = oldClaims.map(c => c.food_id);

            // Check which items are still available
            const { data: availableItems, error: checkError } = await supabase
                .from('food_listings')
                .select('id')
                .in('id', foodIds)
                .eq('status', 'available');

            if (checkError) throw checkError;

            const availableIds = availableItems.map(item => item.id);

            if (availableIds.length === 0) {
                return {
                    success: false,
                    error: 'None of the items are available anymore'
                };
            }

            // Update food listings status
            const { error: listingsError } = await supabase
                .from('food_listings')
                .update({ status: 'claimed' })
                .in('id', availableIds);

            if (listingsError) throw listingsError;

            // Update claims to point to new receipt
            const { error: updateError } = await supabase
                .from('food_claims')
                .update({
                    receipt_id: newReceipt.id,
                    status: 'approved'
                })
                .in('food_id', availableIds)
                .eq('claimer_id', userId);

            if (updateError) throw updateError;

            return {
                success: true,
                newReceipt,
                reclaimedCount: availableIds.length,
                unavailableCount: foodIds.length - availableIds.length
            };
        } catch (error) {
            console.error('[ReceiptService] Error reclaiming items:', error);
            return {
                success: false,
                error: error.message
            };
        }
    }
}

// Export singleton instance
const receiptService = new ReceiptService();
export default receiptService;
