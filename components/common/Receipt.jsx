import { useState } from 'react';
import PropTypes from 'prop-types';
import supabase, { SUPABASE_AUTH_KEY } from '../../utils/supabaseClient';
import { formatDate } from '../../utils/helpers';

// REST helper for food_listings updates (avoids RLS issues for non-owner updates)
async function patchFoodListings(ids, status) {
    const supabaseUrl = import.meta.env.VITE_SUPABASE_URL;
    const supabaseKey = import.meta.env.VITE_SUPABASE_ANON_KEY;
    let accessToken = supabaseKey;
    try {
        const session = JSON.parse(localStorage.getItem(SUPABASE_AUTH_KEY) || '{}');
        if (session?.access_token) accessToken = session.access_token;
    } catch (_) { /* use anon key */ }

    for (const id of ids) {
        try {
            const resp = await fetch(`${supabaseUrl}/rest/v1/food_listings?id=eq.${id}`, {
                method: 'PATCH',
                headers: {
                    'Content-Type': 'application/json',
                    apikey: supabaseKey,
                    Authorization: `Bearer ${accessToken}`,
                    Prefer: 'return=minimal',
                },
                body: JSON.stringify({ status }),
            });
            if (!resp.ok) {
                // fetch() doesn't reject on HTTP errors (only network failures),
                // so RLS denials (403) and server errors would otherwise pass
                // through unnoticed and leave inventory out of sync.
                console.warn('Failed to update listing status:', id, resp.status, await resp.text().catch(() => ''));
            }
        } catch (err) {
            console.warn('Failed to update listing status:', id, err);
        }
    }
}

/**
 * Receipt Component - Displays aggregated food claims
 * Three states: pending (green "Pick Up"), completed (grey), expired (orange "Reclaim")
 */
export default function Receipt({ receipt, items, onUpdate }) {
    const [loading, setLoading] = useState(false);

    // A receipt is effectively expired if it's still pending but the pickup
    // deadline has passed. The DB cron/RPC will eventually flip the status,
    // but we render the expired UI immediately so users aren't confused.
    const isPastDeadline = (() => {
        if (!receipt?.pickup_by) return false;
        const deadline = new Date(receipt.pickup_by).getTime();
        return Number.isFinite(deadline) && deadline < Date.now();
    })();
    const effectiveStatus = receipt.status === 'pending' && isPastDeadline
        ? 'expired'
        : receipt.status;

    // Determine receipt state and styling
    const getReceiptState = () => {
        if (effectiveStatus === 'completed') {
            return {
                headerClass: 'bg-gray-400',
                buttonText: 'Complete',
                buttonClass: 'bg-gray-400 cursor-not-allowed',
                buttonDisabled: true
            };
        } else if (effectiveStatus === 'expired') {
            return {
                headerClass: 'bg-orange-500',
                buttonText: 'Reclaim',
                buttonClass: 'bg-primary-600 hover:bg-primary-700 shadow-lg',
                buttonDisabled: false
            };
        } else {
            return {
                headerClass: 'bg-primary-600',
                buttonText: 'Pick Up',
                buttonClass: 'bg-primary-600 hover:bg-primary-700 shadow-lg',
                buttonDisabled: false
            };
        }
    };

    const state = getReceiptState();

    // Handle pickup button click
    const handlePickup = async () => {
        if (loading) return;

        setLoading(true);
        try {
            // Update receipt status to completed
            const { error: receiptError } = await supabase
                .from('receipts')
                .update({
                    status: 'completed',
                    picked_up_at: new Date().toISOString()
                })
                .eq('id', receipt.id);

            if (receiptError) throw receiptError;

            // Update all associated food_claims
            const { error: claimsError } = await supabase
                .from('food_claims')
                .update({ status: 'completed' })
                .eq('receipt_id', receipt.id);

            if (claimsError) throw claimsError;

            // Permanently remove items from inventory (they've been picked up)
            const foodIds = items.map(item => item.food_id).filter(Boolean);
            if (foodIds.length > 0) {
                await patchFoodListings(foodIds, 'completed');
            }

            // Notify parent component of update
            if (onUpdate) onUpdate();

        } catch (error) {
            console.error('Error completing pickup:', error);
            alert('Failed to complete pickup. Please try again.');
        } finally {
            setLoading(false);
        }
    };

    // Handle reclaim button click (for expired receipts)
    const handleReclaim = async () => {
        if (loading) return;

        setLoading(true);
        try {
            // STEP 1: Verify every item is still available in inventory before
            // creating a new receipt. After expiry, the donor may have deleted
            // the listing, another user may have claimed it, or the quantity
            // may have dropped below what this receipt needs.
            const foodIds = items.map(item => item.food_id).filter(Boolean);
            if (foodIds.length === 0) {
                alert('This receipt has no items to reclaim.');
                return;
            }

            const { data: liveListings, error: liveError } = await supabase
                .from('food_listings')
                .select('id, status, quantity, title')
                .in('id', foodIds);

            if (liveError) throw liveError;

            const liveById = new Map((liveListings || []).map(l => [l.id, l]));
            const unavailable = [];
            for (const item of items) {
                if (!item.food_id) continue;
                const listing = liveById.get(item.food_id);
                const needed = Number(item.quantity) || 1;
                if (!listing) {
                    unavailable.push(`${item.food_name || 'Item'} (no longer listed)`);
                } else if (listing.status !== 'active') {
                    unavailable.push(`${item.food_name || listing.title || 'Item'} (already claimed)`);
                } else if ((Number(listing.quantity) || 0) < needed) {
                    unavailable.push(
                        `${item.food_name || listing.title || 'Item'} (only ${listing.quantity || 0} left, need ${needed})`
                    );
                }
            }

            if (unavailable.length > 0) {
                alert(
                    'These items are no longer available and cannot be reclaimed:\n\n' +
                    unavailable.map(s => `• ${s}`).join('\n')
                );
                return;
            }

            // STEP 2: Create the new receipt now that we know every item is available.
            const pickupBy = new Date();
            let daysUntilFriday = (5 - pickupBy.getDay() + 7) % 7;
            if (daysUntilFriday === 0) daysUntilFriday = 7; // If Friday, push to next Friday
            pickupBy.setDate(pickupBy.getDate() + daysUntilFriday);
            pickupBy.setHours(23, 59, 59, 0);

            // Use plain REST for receipt insert/update/delete — the Supabase JS
            // client is known to hang on this app, which left the old expired
            // receipt undeleted and let users reclaim it repeatedly.
            const supabaseUrl = import.meta.env.VITE_SUPABASE_URL;
            const supabaseKey = import.meta.env.VITE_SUPABASE_ANON_KEY;
            let accessToken = supabaseKey;
            try {
                const session = JSON.parse(localStorage.getItem(SUPABASE_AUTH_KEY) || '{}');
                if (session?.access_token) accessToken = session.access_token;
            } catch (_) { /* use anon key */ }
            const restHeaders = {
                'Content-Type': 'application/json',
                apikey: supabaseKey,
                Authorization: `Bearer ${accessToken}`,
            };

            const insertResp = await fetch(`${supabaseUrl}/rest/v1/receipts`, {
                method: 'POST',
                headers: { ...restHeaders, Prefer: 'return=representation' },
                body: JSON.stringify({
                    user_id: receipt.user_id,
                    status: 'pending',
                    pickup_location: receipt.pickup_location,
                    pickup_address: receipt.pickup_address,
                    pickup_window: receipt.pickup_window,
                    pickup_by: pickupBy.toISOString(),
                }),
            });
            if (!insertResp.ok) {
                throw new Error(`Failed to create new receipt: ${insertResp.status} ${await insertResp.text().catch(() => '')}`);
            }
            const insertedRows = await insertResp.json();
            const newReceipt = Array.isArray(insertedRows) ? insertedRows[0] : insertedRows;
            if (!newReceipt?.id) throw new Error('New receipt did not return an id');

            // STEP 3: Decrement quantity (or mark fully claimed) for each listing.
            // Mirrors ClaimFoodForm's decrement-then-flag-claimed logic.
            for (const item of items) {
                if (!item.food_id) continue;
                const listing = liveById.get(item.food_id);
                const needed = Number(item.quantity) || 1;
                const remaining = (Number(listing.quantity) || 0) - needed;
                const patchBody = remaining <= 0
                    ? { status: 'claimed' }
                    : { quantity: remaining };
                try {
                    const resp = await fetch(`${supabaseUrl}/rest/v1/food_listings?id=eq.${item.food_id}`, {
                        method: 'PATCH',
                        headers: { ...restHeaders, Prefer: 'return=minimal' },
                        body: JSON.stringify(patchBody),
                    });
                    if (!resp.ok) {
                        console.warn(
                            'Failed to update listing on reclaim:',
                            item.food_id, resp.status, await resp.text().catch(() => '')
                        );
                    }
                } catch (err) {
                    console.warn('Failed to update listing on reclaim:', item.food_id, err);
                }
            }

            // STEP 4: Re-point claims from the OLD expired receipt to the NEW one.
            // Filter by receipt_id so we only touch claims tied to THIS receipt.
            // If this fails, roll back the new receipt so we don't leave a duplicate.
            const claimsResp = await fetch(
                `${supabaseUrl}/rest/v1/food_claims?receipt_id=eq.${receipt.id}`,
                {
                    method: 'PATCH',
                    headers: { ...restHeaders, Prefer: 'return=minimal' },
                    body: JSON.stringify({ receipt_id: newReceipt.id, status: 'approved' }),
                }
            );
            if (!claimsResp.ok) {
                const errText = await claimsResp.text().catch(() => '');
                // Roll back the new receipt so the user doesn't end up with two cards.
                await fetch(`${supabaseUrl}/rest/v1/receipts?id=eq.${newReceipt.id}`, {
                    method: 'DELETE',
                    headers: restHeaders,
                }).catch(() => {});
                throw new Error(`Failed to re-point claims: ${claimsResp.status} ${errText}`);
            }

            // STEP 5: Delete the old expired receipt so it can't be reclaimed again.
            // Claims have been re-pointed above, so CASCADE won't wipe them.
            const deleteResp = await fetch(
                `${supabaseUrl}/rest/v1/receipts?id=eq.${receipt.id}`,
                { method: 'DELETE', headers: restHeaders }
            );
            if (!deleteResp.ok) {
                // Non-fatal: new receipt + claims are intact. Log loudly so we notice.
                console.error(
                    'Failed to delete old expired receipt:',
                    deleteResp.status, await deleteResp.text().catch(() => '')
                );
            }

            // Notify parent component
            if (onUpdate) onUpdate();

        } catch (error) {
            console.error('Error reclaiming items:', error);
            alert('Failed to reclaim items. Please try again.');
        } finally {
            setLoading(false);
        }
    };

    const handleButtonClick = () => {
        if (effectiveStatus === 'expired') {
            handleReclaim();
        } else if (effectiveStatus === 'pending') {
            handlePickup();
        }
    };

    return (
        <div className="bg-white rounded-2xl shadow-lg overflow-hidden border-2 border-gray-200 max-w-sm">
            {/* Header */}
            <div className={`${state.headerClass} text-white px-6 py-4`}>
                <h3 className="text-xl font-bold">Receipt</h3>
            </div>

            {/* Expired Notice (if applicable) */}
            {effectiveStatus === 'expired' && (
                <div className="bg-orange-50 border-l-4 border-orange-500 p-4 mx-4 mt-4">
                    <p className="text-sm text-orange-800">
                        <strong>Claim Expired:</strong> This claim was not picked up by the Friday deadline and has been 
                        automatically expired. The items have been returned to inventory. Click Reclaim if you 
                        would like to claim them again. Some items may no longer be available.
                    </p>
                </div>
            )}

            {/* Items List */}
            <div className="px-6 py-6">
                <div className="space-y-2 mb-6">
                    {items.map((item, index) => (
                        <div key={index} className="flex justify-between text-gray-800">
                            <span className="font-medium">{item.food_name || item.name}</span>
                            <span className="ml-4">{item.amount || item.quantity || 1}</span>
                        </div>
                    ))}
                </div>

                {/* Pickup Location */}
                <div className="border-t pt-4 mt-4 text-sm text-gray-700 space-y-1">
                    <p className="font-semibold">Pick-up location: {receipt.pickup_location}</p>
                    <p><strong>Address:</strong> {receipt.pickup_address}</p>
                    <p><strong>Pick-up window:</strong> {receipt.pickup_window}</p>
                </div>

                {/* Dates */}
                <div className="mt-4 text-xs text-gray-500">
                    <p>Claimed: {formatDate(receipt.claimed_at)}</p>
                    <p>Pickup by: {formatDate(receipt.pickup_by)}</p>
                    {receipt.picked_up_at && (
                        <p>Picked up: {formatDate(receipt.picked_up_at)}</p>
                    )}
                </div>
            </div>

            {/* Action Button */}
            <div className="px-6 pb-6">
                <button
                    onClick={handleButtonClick}
                    disabled={state.buttonDisabled || loading}
                    className={`w-full py-3 rounded-full text-white font-bold text-lg transition-all duration-200 ${state.buttonClass}`}
                >
                    {loading ? 'Processing...' : state.buttonText}
                </button>
            </div>

            {effectiveStatus === 'expired' && (
                <div className="bg-orange-500 text-white px-6 py-4 text-center border-t-4 border-orange-600">
                    <p className="text-xs font-bold uppercase tracking-wider text-orange-100 mb-1">
                        Expiration date
                    </p>
                    <p className="text-lg font-extrabold tracking-tight">
                        {formatDate(receipt.expired_at || receipt.pickup_by)}
                    </p>
                </div>
            )}
        </div>
    );
}

Receipt.propTypes = {
    receipt: PropTypes.shape({
        id: PropTypes.string.isRequired,
        user_id: PropTypes.string.isRequired,
        status: PropTypes.oneOf(['pending', 'completed', 'expired']).isRequired,
        pickup_location: PropTypes.string,
        pickup_address: PropTypes.string,
        pickup_window: PropTypes.string,
        claimed_at: PropTypes.string.isRequired,
        pickup_by: PropTypes.string.isRequired,
        picked_up_at: PropTypes.string,
        expired_at: PropTypes.string
    }).isRequired,
    items: PropTypes.arrayOf(PropTypes.shape({
        food_id: PropTypes.oneOfType([PropTypes.string, PropTypes.number]),
        food_name: PropTypes.string,
        name: PropTypes.string,
        quantity: PropTypes.oneOfType([PropTypes.string, PropTypes.number]),
        amount: PropTypes.string
    })).isRequired,
    onUpdate: PropTypes.func
};
