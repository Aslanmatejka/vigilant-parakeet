import React, { useState, useEffect, useCallback } from 'react';
import { useAuthContext } from '../utils/AuthContext';
import Receipt from '../components/common/Receipt';
import receiptService from '../utils/receiptService';
import supabase from '../utils/supabaseClient';
import { reportError } from '../utils/helpers';

const TABS = [
    { key: 'all', label: 'All' },
    { key: 'pending', label: 'Pending' },
    { key: 'completed', label: 'Completed' },
    { key: 'expired', label: 'Expired' },
];

export default function UserReceipts() {
    const { user } = useAuthContext();
    const [receipts, setReceipts] = useState([]);
    const [loading, setLoading] = useState(true);
    const [activeTab, setActiveTab] = useState('all');
    const [expiryRunning, setExpiryRunning] = useState(false);

    const fetchReceipts = useCallback(async () => {
        if (!user?.id) return;
        setLoading(true);
        try {
            const { data, error } = await supabase
                .from('receipts')
                .select('*')
                .eq('user_id', user.id)
                .order('claimed_at', { ascending: false });

            if (error) throw error;

            // For each receipt, fetch associated food claims + listings
            const withItems = await Promise.all(
                (data || []).map(async (receipt) => {
                    try {
                        const { data: claims } = await supabase
                            .from('food_claims')
                            .select('id, food_id, quantity, status, food_listings(title, unit)')
                            .eq('receipt_id', receipt.id);

                        const items = (claims || []).map((c) => ({
                            food_id: c.food_id,
                            food_name: c.food_listings?.title || 'Food item',
                            quantity: c.quantity ?? 1,
                            unit: c.food_listings?.unit || '',
                            amount: `${c.quantity ?? 1} ${c.food_listings?.unit || ''}`.trim(),
                        }));

                        return { receipt, items };
                    } catch {
                        return { receipt, items: [] };
                    }
                })
            );

            setReceipts(withItems);
        } catch (error) {
            reportError(error);
            console.error('Failed to fetch receipts:', error);
        } finally {
            setLoading(false);
        }
    }, [user?.id]);

    useEffect(() => {
        fetchReceipts();
    }, [fetchReceipts]);

    // Run expiry check on page load (client-side fallback if cron not set up)
    useEffect(() => {
        if (!user?.id) return;
        const runExpiry = async () => {
            setExpiryRunning(true);
            try {
                await receiptService.expireOldReceipts();
                // Re-fetch after expiry to show updated statuses
                await fetchReceipts();
            } catch {
                // Silently fail — expiry is a best-effort background task
            } finally {
                setExpiryRunning(false);
            }
        };
        runExpiry();
    // Only run once on mount
    // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [user?.id]);

    // Hide empty expired receipts. After a Reclaim the old expired receipt's
    // claims are moved to the new receipt; if the DB DELETE was blocked by
    // RLS (missing receipts_delete_own policy on older deploys), the orphan
    // would otherwise appear as an empty expired card.
    const visibleReceipts = receipts.filter(
        (r) => !(r.receipt.status === 'expired' && (!r.items || r.items.length === 0))
    );

    const filtered = activeTab === 'all'
        ? visibleReceipts
        : visibleReceipts.filter((r) => r.receipt.status === activeTab);

    const counts = {
        all: visibleReceipts.length,
        pending: visibleReceipts.filter((r) => r.receipt.status === 'pending').length,
        completed: visibleReceipts.filter((r) => r.receipt.status === 'completed').length,
        expired: visibleReceipts.filter((r) => r.receipt.status === 'expired').length,
    };

    return (
        <div className="min-h-screen bg-gradient-to-b from-green-50 via-white to-green-100 py-8 px-4">
            <div className="max-w-6xl mx-auto">
                {/* Header */}
                <div className="mb-8">
                    <h1 className="text-3xl font-bold text-gray-900">My Receipts</h1>
                    <p className="text-gray-600 mt-1">
                        Track your food claims, pickups, and order history
                    </p>
                </div>

                {/* Stats cards */}
                <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-8">
                    <div className="bg-white/80 backdrop-blur-md rounded-xl p-4 shadow-sm border border-gray-100">
                        <p className="text-sm text-gray-500">Total</p>
                        <p className="text-2xl font-bold text-gray-900">{counts.all}</p>
                    </div>
                    <div className="bg-white/80 backdrop-blur-md rounded-xl p-4 shadow-sm border border-green-100">
                        <p className="text-sm text-green-600">Pending Pickup</p>
                        <p className="text-2xl font-bold text-green-700">{counts.pending}</p>
                    </div>
                    <div className="bg-white/80 backdrop-blur-md rounded-xl p-4 shadow-sm border border-gray-100">
                        <p className="text-sm text-gray-500">Completed</p>
                        <p className="text-2xl font-bold text-gray-700">{counts.completed}</p>
                    </div>
                    <div className="bg-white/80 backdrop-blur-md rounded-xl p-4 shadow-sm border border-orange-100">
                        <p className="text-sm text-orange-600">Expired</p>
                        <p className="text-2xl font-bold text-orange-700">{counts.expired}</p>
                    </div>
                </div>

                {/* Filter tabs */}
                <div className="flex space-x-2 mb-6 overflow-x-auto">
                    {TABS.map((tab) => (
                        <button
                            key={tab.key}
                            onClick={() => setActiveTab(tab.key)}
                            className={`px-4 py-2 rounded-full text-sm font-medium whitespace-nowrap transition-all ${
                                activeTab === tab.key
                                    ? 'bg-green-600 text-white shadow-md'
                                    : 'bg-white text-gray-600 hover:bg-gray-100 border border-gray-200'
                            }`}
                        >
                            {tab.label} ({counts[tab.key]})
                        </button>
                    ))}
                </div>

                {/* Content */}
                {loading ? (
                    <div className="flex justify-center py-20">
                        <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-green-600"></div>
                    </div>
                ) : filtered.length === 0 ? (
                    <div className="text-center py-20 bg-white/60 backdrop-blur-sm rounded-2xl">
                        <div className="text-6xl mb-4">🧾</div>
                        <h3 className="text-xl font-semibold text-gray-700 mb-2">
                            {activeTab === 'all' ? 'No receipts yet' : `No ${activeTab} receipts`}
                        </h3>
                        <p className="text-gray-500">
                            {activeTab === 'all'
                                ? 'When you claim food items, your receipts will appear here.'
                                : `You don't have any ${activeTab} receipts at the moment.`}
                        </p>
                        {activeTab === 'all' && (
                            <a
                                href="/find"
                                className="inline-block mt-4 px-6 py-2 bg-green-600 text-white rounded-full hover:bg-green-700 transition-colors"
                            >
                                Find Food
                            </a>
                        )}
                    </div>
                ) : (
                    <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
                        {filtered.map(({ receipt, items }) => (
                            <Receipt
                                key={receipt.id}
                                receipt={receipt}
                                items={items}
                                onUpdate={fetchReceipts}
                            />
                        ))}
                    </div>
                )}

                {/* Expiry notice */}
                {expiryRunning && (
                    <p className="text-center text-xs text-gray-400 mt-8">
                        Checking for expired receipts...
                    </p>
                )}
            </div>
        </div>
    );
}
