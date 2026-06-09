import React from "react";
import { useNavigate, useLocation } from "react-router-dom";
import Button from "../components/common/Button";
import supabase, { SUPABASE_AUTH_KEY } from "../utils/supabaseClient";
import communitiesStatic from '../utils/communities';
import twilioService from '../utils/twilioService';
import { useAuthContext } from '../utils/AuthContext';
import { assignFoodImage } from '../utils/foodImages.js';
import { toast } from 'react-toastify';

// Calculate next Friday from today (food returns to inventory at 11:59PM Friday)
const getNextFriday = () => {
    const today = new Date();
    const dayOfWeek = today.getDay(); // 0 = Sunday, 5 = Friday
    
    // Days until next Friday, minimum 1 day away
    let daysUntilFriday = (5 - dayOfWeek + 7) % 7;
    if (daysUntilFriday === 0) daysUntilFriday = 7; // If Friday, push to next Friday
    
    const nextFriday = new Date(today);
    nextFriday.setDate(today.getDate() + daysUntilFriday);
    
    // Return ISO date string (YYYY-MM-DD) for database column type "date"
    return nextFriday.toISOString().split('T')[0];
};

// Human-readable version for display purposes
const formatPickupDate = (isoDate) => {
    const d = new Date(isoDate + 'T00:00:00');
    const months = [
        'January', 'February', 'March', 'April', 'May', 'June',
        'July', 'August', 'September', 'October', 'November', 'December'
    ];
    return `${months[d.getMonth()]} ${d.getDate()}`;
};

export default function ClaimFoodForm() {
    const navigate = useNavigate();
    const location = useLocation();
    const { user } = useAuthContext();
    const food = location.state?.food;
    const pickupDeadline = getNextFriday();
    const [community, setCommunity] = React.useState(null);
    const [loading, setLoading] = React.useState(true);
    const [claiming, setClaiming] = React.useState(false);
    const MAX_CLAIM = 2;
    const availableQty = food ? Math.max(1, parseInt(food.quantity) || 1) : 1;
    const maxAllowed = Math.min(MAX_CLAIM, availableQty);
    const [claimQty, setClaimQty] = React.useState(1);

    React.useEffect(() => {
        const fetchCommunity = async () => {
            if (!food?.community_id) {
                setLoading(false);
                return;
            }

            try {
                // Try to fetch from database first
                const { data, error } = await supabase
                    .from('communities')
                    .select('*')
                    .eq('id', food.community_id)
                    .maybeSingle();

                if (data) {
                    // Merge with static data for contact info
                    const staticCommunity = communitiesStatic.find(c => c.name === data.name);
                    setCommunity({
                        ...staticCommunity,
                        ...data
                    });
                } else if (error) {
                    // Fallback to static data
                    const staticCommunity = communitiesStatic.find(c => c.id === food.community_id);
                    setCommunity(staticCommunity);
                }
            } catch (err) {
                console.error('Error fetching community:', err);
                // Fallback to static data
                const staticCommunity = communitiesStatic.find(c => c.id === food.community_id);
                setCommunity(staticCommunity);
            } finally {
                setLoading(false);
            }
        };

        fetchCommunity();
    }, [food?.community_id]);

    const handleConfirmClaim = async () => {
        if (!user) {
            toast.error('Please log in to claim food');
            navigate('/login');
            return;
        }

        try {
            setClaiming(true);

            // Check if user has a pending receipt for the SAME pickup location.
            // We intentionally do NOT restrict by claimed_at date so that claims
            // made across multiple days before the Friday deadline all aggregate
            // into the same receipt.

            // food_listings.location is a JSONB column (dict from frontend writes);
            // always extract a plain-text address before using it as a string.
            const foodAddressText = food.full_address
                || (typeof food.location === 'string' ? food.location : food.location?.address)
                || '';
            const pickupLocationName = community?.name || foodAddressText || 'Community Location';
            const pickupAddress = community?.location || foodAddressText || 'Address not available';

            const { data: existingReceipts, error: receiptCheckError } = await supabase
                .from('receipts')
                .select('id')
                .eq('user_id', user.id)
                .eq('status', 'pending')
                .eq('pickup_location', pickupLocationName)
                .limit(1);

            if (receiptCheckError) throw receiptCheckError;

            let receiptId;

            // If no pending receipt for today, create a new one
            if (!existingReceipts || existingReceipts.length === 0) {
                const pickupWindow = "Tuesday 2:00 PM - 3:30 PM, Thursday 2:00 PM - 3:30 PM, Friday 7:00 AM - 8:00 AM & 2:00 PM - 3:30 PM";
                
                const { data: newReceipt, error: receiptError } = await supabase
                    .from('receipts')
                    .insert({
                        user_id: user.id,
                        status: 'pending',
                        pickup_location: pickupLocationName,
                        pickup_address: pickupAddress,
                        pickup_window: pickupWindow,
                        // pickup_by is intentionally omitted — the DB BEFORE INSERT trigger
                        // (set_receipt_pickup_deadline) computes the correct Friday 11:59 PM
                        // Pacific deadline. Setting it here with new Date() produces an
                        // incorrect UTC time in all non-UTC timezones (off by 7-8 hours).
                    })
                    .select()
                    .single();

                if (receiptError) throw receiptError;
                receiptId = newReceipt.id;
            } else {
                // Use existing pending receipt
                receiptId = existingReceipts[0].id;
            }

            // Create claim in database (auto-approved) and link to receipt
            const { data: claimData, error: claimError } = await supabase
                .from('food_claims')
                .insert({
                    food_id: food.id,
                    claimer_id: user.id,
                    receipt_id: receiptId,
                    requester_name: user.name || user.email || 'Anonymous',
                    requester_email: user.email || null,
                    requester_phone: user.phone || null,
                    status: 'approved',
                    pickup_date: pickupDeadline,
                    quantity: claimQty,
                })
                .select()
                .single();

            if (claimError) throw claimError;

            // Update food listing: decrement quantity, or mark claimed if fully taken
            try {
                const supabaseUrl = import.meta.env.VITE_SUPABASE_URL;
                const supabaseKey = import.meta.env.VITE_SUPABASE_ANON_KEY;
                let accessToken = supabaseKey;
                try {
                    const session = JSON.parse(localStorage.getItem(SUPABASE_AUTH_KEY) || '{}');
                    if (session?.access_token) accessToken = session.access_token;
                } catch (_) { /* use anon key */ }

                const remainingQty = availableQty - claimQty;
                const patchBody = remainingQty <= 0
                    ? { status: 'claimed' }
                    : { quantity: remainingQty };

                const patchResp = await fetch(
                    `${supabaseUrl}/rest/v1/food_listings?id=eq.${food.id}`,
                    {
                        method: 'PATCH',
                        headers: {
                            'Content-Type': 'application/json',
                            apikey: supabaseKey,
                            Authorization: `Bearer ${accessToken}`,
                            Prefer: 'return=minimal',
                        },
                        body: JSON.stringify(patchBody),
                    }
                );
                if (!patchResp.ok) {
                    console.warn('Could not update listing:', patchResp.status, await patchResp.text());
                }
            } catch (statusErr) {
                console.warn('Non-critical: failed to update listing', statusErr);
            }

            // Send SMS notifications if phone numbers are available
            try {
                // Send confirmation to claimer
                if (user.phone) {
                    await twilioService.sendClaimConfirmation({
                        claimerPhone: user.phone,
                        claimerName: user.name || 'there',
                        foodTitle: food.title || food.name,
                        pickupLocation: community?.name || foodAddressText || 'your pickup location',
                        pickupDeadline: formatPickupDate(pickupDeadline),
                    });
                }

                // Send notification to donor
                if (food.donor_phone) {
                    await twilioService.sendClaimNotification({
                        donorPhone: food.donor_phone,
                        donorName: food.donor_name || 'Donor',
                        claimerName: user.name || 'A community member',
                        foodTitle: food.title || food.name,
                        pickupLocation: community?.name || foodAddressText || 'the pickup location',
                    });
                }
            } catch (smsError) {
                // Don't fail the claim if SMS fails
                console.error('SMS notification error:', smsError);
            }

            toast.success('Added to your receipt — view it in Receipts & Activity!', { autoClose: 5000, position: 'top-center' });
            navigate('/find');
        } catch (error) {
            console.error('Error claiming food:', error);
            toast.error(error.message || 'Failed to claim food');
        } finally {
            setClaiming(false);
        }
    };

    if (!food) {
        return (
            <div className="max-w-2xl mx-auto py-8 px-4">
                <div className="bg-yellow-50 border border-yellow-200 rounded-lg p-6 text-center">
                    <i className="fas fa-exclamation-triangle text-yellow-600 text-3xl mb-3"></i>
                    <h2 className="text-xl font-bold text-gray-900 mb-2">No Food Selected</h2>
                    <p className="text-gray-600 mb-4">Please select a food item from the Find Food page.</p>
                    <Button onClick={() => navigate("/find")}>Go to Find Food</Button>
                </div>
            </div>
        );
    }

    return (
        <div className="max-w-4xl mx-auto py-8 px-4">
            <div className="mb-6">
                <Button 
                    onClick={() => navigate("/find")}
                    variant="secondary"
                    className="mb-4"
                >
                    <i className="fas fa-arrow-left mr-2"></i>
                    Back to Find Food
                </Button>
                <h1 className="text-3xl font-bold text-gray-900 mb-2">Claim Food</h1>
                <p className="text-gray-600">Review the details below and confirm your claim</p>
            </div>

            {/* Food Details Section */}
            <div className="bg-white rounded-2xl shadow-lg p-6 mb-6 border border-gray-100">
                <h2 className="text-2xl font-bold text-gray-900 mb-4">
                    <i className="fas fa-utensils text-[#2CABE3] mr-3"></i>
                    Food Details
                </h2>
                
                <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                    {/* Food Image */}
                    <div>
                        <img 
                            src={food.image_url || assignFoodImage(food)} 
                            alt={food.title || food.name}
                            className="w-full h-64 object-cover rounded-lg shadow-md"
                        />
                    </div>

                    {/* Food Information */}
                    <div className="space-y-4">
                        <div>
                            <h3 className="text-xl font-bold text-gray-900 mb-2">
                                {food.title || food.name || "Food Item"}
                            </h3>
                            <p className="text-gray-600">{food.description || "No description available"}</p>
                        </div>

                        <div className="border-t border-gray-200 pt-4 space-y-3">
                            <div className="flex items-center">
                                <i className="fas fa-box text-[#2CABE3] w-6"></i>
                                <span className="text-gray-700 font-medium">Available:</span>
                                <span className="ml-2 text-gray-900">
                                    {food.quantity || "N/A"} {food.unit || ""}
                                </span>
                            </div>

                            {/* Quantity selector */}
                            <div className="flex items-center">
                                <i className="fas fa-hand-holding text-[#2CABE3] w-6"></i>
                                <span className="text-gray-700 font-medium">How many do you want?</span>
                                <div className="ml-3 flex items-center gap-2">
                                    <button
                                        type="button"
                                        onClick={() => setClaimQty(q => Math.max(1, q - 1))}
                                        className="w-8 h-8 rounded-full border-2 border-[#2CABE3] text-[#2CABE3] font-bold text-lg flex items-center justify-center hover:bg-[#2CABE3] hover:text-white transition-colors disabled:opacity-40"
                                        disabled={claimQty <= 1}
                                    >−</button>
                                    <span className="w-8 text-center text-lg font-bold text-gray-900">{claimQty}</span>
                                    <button
                                        type="button"
                                        onClick={() => setClaimQty(q => Math.min(maxAllowed, q + 1))}
                                        className="w-8 h-8 rounded-full border-2 border-[#2CABE3] text-[#2CABE3] font-bold text-lg flex items-center justify-center hover:bg-[#2CABE3] hover:text-white transition-colors disabled:opacity-40"
                                        disabled={claimQty >= maxAllowed}
                                    >+</button>
                                    <span className="text-sm text-gray-500">{food.unit || ""} (max {maxAllowed})</span>
                                </div>
                            </div>

                            <div className="flex items-center">
                                <i className="fas fa-calendar-alt text-[#2CABE3] w-6"></i>
                                <span className="text-gray-700 font-medium">Expiration Date:</span>
                                <span className="ml-2 text-gray-900">
                                    {food.expiry_date ? new Date(food.expiry_date + 'T00:00:00').toLocaleDateString('en-US', { 
                                        year: 'numeric', 
                                        month: 'long', 
                                        day: 'numeric' 
                                    }) : "Not specified"}
                                </span>
                            </div>
                        </div>
                    </div>
                </div>
            </div>

            {/* School Location Section */}
            <div className="bg-white rounded-2xl shadow-lg p-6 mb-6 border border-gray-100">
                <h2 className="text-2xl font-bold text-gray-900 mb-4">
                    <i className="fas fa-school text-[#2CABE3] mr-3"></i>
                    Pickup Location
                </h2>
                
                {loading ? (
                    <div className="text-center py-4">
                        <i className="fas fa-spinner fa-spin text-[#2CABE3] text-2xl"></i>
                        <p className="text-gray-600 mt-2">Loading location...</p>
                    </div>
                ) : community ? (
                    <div className="space-y-3">
                        <div>
                            <span className="text-gray-700 font-medium">School Name:</span>
                            <p className="text-lg text-gray-900">{community.name}</p>
                        </div>
                        
                        <div>
                            <span className="text-gray-700 font-medium">Address:</span>
                            <p className="text-lg text-gray-900">{community.location}</p>
                        </div>

                        {community.contact && (
                            <div>
                                <span className="text-gray-700 font-medium">Contact:</span>
                                <p className="text-lg text-gray-900">{community.contact}</p>
                            </div>
                        )}

                        {community.phone && (
                            <div>
                                <span className="text-gray-700 font-medium">Phone:</span>
                                <p className="text-lg text-gray-900">
                                    <a href={`tel:${community.phone}`} className="text-[#2CABE3] hover:underline">
                                        {community.phone}
                                    </a>
                                </p>
                            </div>
                        )}

                        {community.hours && (
                            <div>
                                <span className="text-gray-700 font-medium">Hours:</span>
                                <p className="text-lg text-gray-900">{community.hours}</p>
                            </div>
                        )}
                    </div>
                ) : (
                    <div className="bg-yellow-50 border border-yellow-200 rounded-lg p-4">
                        <p className="text-yellow-800">
                            <i className="fas fa-exclamation-triangle mr-2"></i>
                            Location information not available. Please contact support.
                        </p>
                    </div>
                )}
            </div>

            {/* Pickup Windows Section */}
            <div className="bg-white rounded-2xl shadow-lg p-6 mb-6 border border-gray-100">
                <h2 className="text-2xl font-bold text-gray-900 mb-4">
                    <i className="fas fa-clock text-[#2CABE3] mr-3"></i>
                    Pickup Windows
                </h2>
                
                <div className="space-y-3">
                    <div className="flex items-start">
                        <i className="fas fa-calendar-day text-[#2CABE3] mt-1 mr-3"></i>
                        <div>
                            <span className="font-semibold text-gray-900">Tuesday</span>
                            <p className="text-gray-700">2:00 PM - 3:30 PM</p>
                        </div>
                    </div>
                    
                    <div className="flex items-start">
                        <i className="fas fa-calendar-day text-[#2CABE3] mt-1 mr-3"></i>
                        <div>
                            <span className="font-semibold text-gray-900">Thursday</span>
                            <p className="text-gray-700">2:00 PM - 3:30 PM</p>
                        </div>
                    </div>
                    
                    <div className="flex items-start">
                        <i className="fas fa-calendar-day text-[#2CABE3] mt-1 mr-3"></i>
                        <div>
                            <span className="font-semibold text-gray-900">Friday</span>
                            <p className="text-gray-700">7:00 AM - 8:00 AM, 2:00 PM - 3:30 PM</p>
                        </div>
                    </div>
                </div>
            </div>

            {/* Deadline Warning */}
            <div className="bg-red-50 border-2 border-red-500 rounded-xl p-6 mb-6">
                <div className="flex items-start">
                    <i className="fas fa-exclamation-triangle text-red-600 text-2xl mt-1 mr-4"></i>
                    <div className="flex-1">
                        <h3 className="text-lg font-bold text-red-900 mb-2">Important Pickup Deadline</h3>
                        <p className="text-red-800 leading-relaxed">
                            Your food must be picked up by <strong>Friday, {formatPickupDate(pickupDeadline)} at 3:30 PM</strong> or it will be marked as unclaimed and added back into inventory for other people to access. You may re-submit your claim if you miss the latest pick-up window.
                        </p>
                    </div>
                </div>
            </div>

            {/* Confirm Claim Button */}
            <div className="flex justify-center">
                <Button 
                    variant="primary" 
                    className="px-12 py-4 text-lg font-semibold bg-[#2CABE3] hover:opacity-90"
                    onClick={handleConfirmClaim}
                    disabled={claiming}
                >
                    <i className="fas fa-check-circle mr-2"></i>
                    {claiming ? 'Processing...' : 'Confirm Claim'}
                </Button>
            </div>
        </div>
    );
}
