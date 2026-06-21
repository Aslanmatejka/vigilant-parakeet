/**
 * Twilio SMS Service
 * Handles sending SMS notifications via Supabase Edge Functions
 */

import supabase from './supabaseClient';

class TwilioService {
    constructor() {
        this.functionUrl = `${supabase.supabaseUrl}/functions/v1/send-sms`;
    }

    /**
     * Format phone number to E.164 format.
     *
     * IMPORTANT: A bare 10-digit number is *assumed* to be US (+1). This is a
     * pragmatic default for the current US-focused deployment, but it will
     * mis-route any non-US 10-digit local number. Prefer storing phone numbers
     * in E.164 (`+<country><number>`) at signup and pass them through unchanged.
     *
     * @param {string} phone - Phone number to format
     * @returns {string} E.164-formatted phone number
     * @throws {Error} If the input can't be coerced into a plausible E.164 value
     */
    formatPhoneNumber(phone) {
        if (typeof phone !== 'string' || !phone.trim()) {
            throw new Error('Phone number is required');
        }
        const trimmed = phone.trim();

        // Already E.164 (or close): trust the country code the caller provided.
        if (trimmed.startsWith('+')) {
            const digitsAfterPlus = trimmed.slice(1).replace(/\D/g, '');
            // E.164 allows 8–15 digits total (country code + subscriber).
            if (digitsAfterPlus.length < 8 || digitsAfterPlus.length > 15) {
                throw new Error(`Phone number "${phone}" is not a valid E.164 value`);
            }
            return `+${digitsAfterPlus}`;
        }

        const cleaned = trimmed.replace(/\D/g, '');

        // 11 digits starting with 1 → US/Canada with country code already.
        if (cleaned.length === 11 && cleaned.startsWith('1')) {
            return `+${cleaned}`;
        }

        // 10 digits → assume US/Canada. Warn so non-US callers notice the assumption.
        if (cleaned.length === 10) {
            console.warn(
                'twilioService.formatPhoneNumber: assuming +1 for 10-digit number. ' +
                'Store phone numbers in E.164 format (+<country><number>) to avoid this.'
            );
            return `+1${cleaned}`;
        }

        throw new Error(
            `Phone number "${phone}" is not in a recognized format. ` +
            'Use E.164 (e.g. +14155551234).'
        );
    }

    /**
     * Check if user has opted in to receive SMS
     * @param {string} phone - Phone number to check
     * @returns {Promise<boolean>} Whether user has opted in
     */
    async checkUserOptIn(phone) {
        try {
            const formattedPhone = this.formatPhoneNumber(phone);
            
            const { data, error } = await supabase
                .from('users')
                .select('sms_opt_in, sms_notifications_enabled')
                .eq('phone', formattedPhone)
                .single();

            if (error || !data) {
                console.warn('Could not verify SMS opt-in status:', error);
                return false;
            }

            return data.sms_opt_in === true && data.sms_notifications_enabled === true;
        } catch (error) {
            console.error('Error checking SMS opt-in:', error);
            return false;
        }
    }

    /**
     * Send SMS via Supabase Edge Function
     * @param {Object} params - SMS parameters
     * @param {string} params.to - Recipient phone number
     * @param {string} params.message - Message content
     * @param {string} params.type - Message type (claim, reminder, verification, notification)
     * @param {boolean} params.skipOptInCheck - Skip opt-in verification (use for verification codes)
     * @returns {Promise<Object>} Response from Twilio
     */
    async sendSMS({ to, message, type = 'notification', skipOptInCheck = false }) {
        try {
            // Check if user has opted in to SMS (except for verification codes)
            if (!skipOptInCheck && type !== 'verification') {
                const isOptedIn = await this.checkUserOptIn(to);
                if (!isOptedIn) {
                    throw new Error('User has not opted in to receive SMS notifications');
                }
            }
            
            const formattedPhone = this.formatPhoneNumber(to);
            
            const { data: { session } } = await supabase.auth.getSession();
            
            const response = await fetch(this.functionUrl, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'Authorization': `Bearer ${session?.access_token || ''}`,
                },
                body: JSON.stringify({
                    to: formattedPhone,
                    message,
                    type,
                }),
            });

            const result = await response.json();

            if (!response.ok || !result.success) {
                throw new Error(result.error || 'Failed to send SMS');
            }

            return result;
        } catch (error) {
            console.error('Twilio SMS Error:', error);
            throw error;
        }
    }

    /**
     * Send food claim notification to donor
     * @param {Object} params - Claim details
     */
    async sendClaimNotification({ donorPhone, donorName, claimerName, foodTitle, pickupLocation }) {
        const message = `Hi ${donorName}, great news! ${claimerName} has claimed your "${foodTitle}". Pickup location: ${pickupLocation}. Thank you for sharing! - DoGoods`;
        
        return this.sendSMS({
            to: donorPhone,
            message,
            type: 'claim',
        });
    }

    /**
     * Send pickup reminder to claimer
     * @param {Object} params - Reminder details
     */
    async sendPickupReminder({ claimerPhone, claimerName, foodTitle, pickupLocation, pickupTime }) {
        const message = `Hi ${claimerName}, reminder: Pick up "${foodTitle}" at ${pickupLocation} by ${pickupTime}. Questions? Contact the community location. - DoGoods`;
        
        return this.sendSMS({
            to: claimerPhone,
            message,
            type: 'reminder',
        });
    }

    /**
     * Send verification code
     * @param {Object} params - Verification details
     */
    async sendVerificationCode({ phone, code }) {
        const message = `Your DoGoods verification code is: ${code}. This code expires in 10 minutes.`;
        
        return this.sendSMS({
            to: phone,
            message,
            type: 'verification',
        });
    }

    /**
     * Send claim confirmation to claimer
     * @param {Object} params - Claim confirmation details
     */
    async sendClaimConfirmation({ claimerPhone, claimerName, foodTitle, pickupLocation, pickupDeadline }) {
        const message = `Hi ${claimerName}, you've successfully claimed "${foodTitle}"! Pick up at ${pickupLocation} by ${pickupDeadline}. See you soon! - DoGoods`;
        
        return this.sendSMS({
            to: claimerPhone,
            message,
            type: 'claim',
        });
    }

    /**
     * Send new food listing notification to nearby users
     * @param {Object} params - Listing details
     */
    async sendNewListingNotification({ userPhone, userName, foodTitle, location }) {
        const message = `Hi ${userName}, new food available near you: "${foodTitle}" at ${location}. Claim it now on DoGoods!`;
        
        return this.sendSMS({
            to: userPhone,
            message,
            type: 'notification',
        });
    }
}

// Create singleton instance
const twilioService = new TwilioService();

export default twilioService;
