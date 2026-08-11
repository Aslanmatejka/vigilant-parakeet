import React from 'react';
import { toast } from 'react-toastify';
import AdminLayout from './AdminLayout';
import Button from '../../components/common/Button';
import AdminFoodDetail from '../../components/admin/AdminFoodDetail';
import dataService from '../../utils/dataService';
import supabase from '../../utils/supabaseClient';

/**
 * Admin queue for food requests awaiting moderation.
 * Recipients post via /request or Nouri (listing_type=request). When
 * require_request_approval is on, they land here until approved (visible on
 * Community Requests) or declined.
 */
function RequestApprovals() {
    const [listings, setListings] = React.useState([]);
    const [loading, setLoading] = React.useState(true);
    const [busyId, setBusyId] = React.useState(null);
    const [bulkBusy, setBulkBusy] = React.useState(false);
    const [requireApproval, setRequireApproval] = React.useState(true);
    const [savingToggle, setSavingToggle] = React.useState(false);

    const queueBusy = bulkBusy || busyId != null;

    const load = React.useCallback(async () => {
        setLoading(true);
        try {
            const [pending, required] = await Promise.all([
                dataService.getFoodListings({
                    status: 'pending',
                    listing_type: 'request',
                    includeExpired: true,
                    skipCommunityScope: true,
                }),
                dataService.getRequireRequestApproval(),
            ]);
            setListings(Array.isArray(pending) ? pending : []);
            setRequireApproval(!!required);
        } catch (err) {
            console.error('RequestApprovals load failed:', err);
            toast.error('Failed to load pending food requests');
            setListings([]);
        } finally {
            setLoading(false);
        }
    }, []);

    React.useEffect(() => {
        load();

        let refetchTimer = null;
        const schedule = () => {
            if (refetchTimer) clearTimeout(refetchTimer);
            refetchTimer = setTimeout(() => {
                refetchTimer = null;
                load();
            }, 800);
        };

        const channel = supabase
            .channel('request-approvals')
            .on(
                'postgres_changes',
                { event: '*', schema: 'public', table: 'food_listings' },
                schedule
            )
            .subscribe();

        return () => {
            if (refetchTimer) clearTimeout(refetchTimer);
            supabase.removeChannel(channel);
        };
    }, [load]);

    const handleListingSaved = (updated) => {
        if (!updated?.id) return;
        setListings((prev) =>
            prev.map((l) => (l.id === updated.id ? { ...l, ...updated } : l))
        );
    };

    const handleReview = async (listingId, approved) => {
        setBusyId(listingId);
        try {
            await dataService.updateFoodListingStatus(
                listingId,
                approved ? 'approved' : 'declined'
            );
            await dataService.sendListingReviewNotification(listingId, approved);
            setListings((prev) => prev.filter((l) => l.id !== listingId));
            toast.success(
                approved
                    ? 'Request approved — now live on Community Requests'
                    : 'Request rejected'
            );
        } catch (err) {
            console.error('Request review failed:', err);
            toast.error(err.message || 'Could not update request');
        } finally {
            setBusyId(null);
        }
    };

    const handleReviewAll = async (approved) => {
        const ids = listings.map((l) => l.id).filter(Boolean);
        if (!ids.length) return;
        const action = approved ? 'approve' : 'reject';
        const ok = window.confirm(
            `${approved ? 'Approve' : 'Reject'} all ${ids.length} pending request${ids.length === 1 ? '' : 's'}?`
        );
        if (!ok) return;

        setBulkBusy(true);
        let succeeded = 0;
        const failed = [];
        try {
            for (const id of ids) {
                try {
                    await dataService.updateFoodListingStatus(
                        id,
                        approved ? 'approved' : 'declined'
                    );
                    await dataService.sendListingReviewNotification(id, approved);
                    succeeded += 1;
                    setListings((prev) => prev.filter((l) => l.id !== id));
                } catch (err) {
                    console.error(`Request ${action} failed for ${id}:`, err);
                    failed.push(id);
                }
            }
            if (succeeded > 0) {
                toast.success(
                    approved
                        ? `Approved ${succeeded} request${succeeded === 1 ? '' : 's'}`
                        : `Rejected ${succeeded} request${succeeded === 1 ? '' : 's'}`
                );
            }
            if (failed.length) {
                toast.error(`${failed.length} request${failed.length === 1 ? '' : 's'} could not be ${action}d`);
            }
        } finally {
            setBulkBusy(false);
        }
    };

    const handleToggleRequireApproval = async () => {
        const next = !requireApproval;
        setSavingToggle(true);
        try {
            await dataService.setPlatformSetting('require_request_approval', next);
            setRequireApproval(next);
            toast.success(
                next
                    ? 'New food requests will wait for approval'
                    : 'New food requests will go live immediately'
            );
        } catch (err) {
            console.error('Toggle require approval failed:', err);
            toast.error('Could not update approval setting');
        } finally {
            setSavingToggle(false);
        }
    };

    return (
        <AdminLayout active="request-approvals">
            <div className="max-w-7xl mx-auto py-8 px-4 sm:px-6 lg:px-8 space-y-6">
                <div className="flex flex-col sm:flex-row sm:items-end sm:justify-between gap-4">
                    <div>
                        <h1 className="text-2xl font-bold text-gray-900">Request Approvals</h1>
                        <p className="mt-1 text-sm text-gray-600">
                            Review food needs posted by recipients before they appear on Community Requests for donors.
                        </p>
                    </div>
                    <div className="flex items-center gap-3 rounded-xl border border-slate-200 bg-white px-4 py-3 shadow-sm">
                        <div className="min-w-0">
                            <p className="text-sm font-semibold text-gray-900">Require approval</p>
                            <p className="text-xs text-gray-500">
                                {requireApproval
                                    ? 'Requests start as pending'
                                    : 'Requests go live immediately'}
                            </p>
                        </div>
                        <button
                            type="button"
                            role="switch"
                            aria-checked={requireApproval}
                            disabled={savingToggle}
                            onClick={handleToggleRequireApproval}
                            className={`relative inline-flex h-6 w-11 shrink-0 rounded-full transition ${
                                requireApproval ? 'bg-[#2CABE3]' : 'bg-slate-300'
                            } ${savingToggle ? 'opacity-60' : ''}`}
                        >
                            <span
                                className={`inline-block h-5 w-5 transform rounded-full bg-white shadow transition mt-0.5 ${
                                    requireApproval ? 'translate-x-5' : 'translate-x-0.5'
                                }`}
                            />
                        </button>
                    </div>
                </div>

                <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
                    <div className="rounded-xl bg-emerald-50 border border-emerald-100 p-4">
                        <p className="text-xs font-semibold uppercase tracking-wide text-emerald-700">Pending requests</p>
                        <p className="mt-1 text-2xl font-bold text-emerald-900">{listings.length}</p>
                    </div>
                    <div className="rounded-xl bg-slate-50 border border-slate-200 p-4 sm:col-span-2 flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3">
                        <p className="text-sm text-slate-600">
                            Uses the same require-approval setting as donations. Approved requests show on
                            Community Requests — not Find Food.
                        </p>
                        {listings.length > 0 && (
                            <div className="flex flex-shrink-0 gap-2">
                                <Button
                                    variant="primary"
                                    size="sm"
                                    disabled={queueBusy}
                                    onClick={() => handleReviewAll(true)}
                                >
                                    {bulkBusy ? 'Working…' : 'Approve all'}
                                </Button>
                                <Button
                                    variant="danger"
                                    size="sm"
                                    disabled={queueBusy}
                                    onClick={() => handleReviewAll(false)}
                                >
                                    Reject all
                                </Button>
                            </div>
                        )}
                    </div>
                </div>

                <div className="space-y-4">
                    {loading ? (
                        <div className="bg-white rounded-2xl border border-slate-200 shadow-sm p-12 text-center text-gray-500">
                            <div className="animate-spin rounded-full h-10 w-10 border-b-2 border-[#2CABE3] mx-auto" />
                            <p className="mt-3 text-sm">Loading pending requests…</p>
                        </div>
                    ) : listings.length === 0 ? (
                        <div className="bg-white rounded-2xl border border-slate-200 shadow-sm p-12 text-center">
                            <i className="fas fa-check-circle text-3xl text-emerald-400" aria-hidden="true" />
                            <p className="mt-3 text-lg font-semibold text-gray-900">Queue is clear</p>
                            <p className="mt-1 text-sm text-gray-500">
                                {requireApproval
                                    ? 'New food requests will show up here for review.'
                                    : 'Approval is off — new requests go live without this queue.'}
                            </p>
                        </div>
                    ) : (
                        listings.map((listing) => (
                            <article
                                key={listing.id}
                                className="bg-white rounded-2xl border border-emerald-100 shadow-sm overflow-hidden"
                            >
                                <div className="flex items-center gap-2 border-b border-emerald-50 bg-emerald-50/60 px-5 py-2.5 sm:px-6">
                                    <span className="inline-flex items-center rounded-full bg-emerald-100 text-emerald-900 px-2.5 py-0.5 text-[11px] font-semibold">
                                        Food request
                                    </span>
                                    <span className="text-xs text-emerald-800/80 truncate">
                                        Approving publishes to Community Requests
                                    </span>
                                </div>
                                <div className="p-5 sm:p-6">
                                    <AdminFoodDetail
                                        listing={listing}
                                        editable
                                        disabled={queueBusy}
                                        onSaved={handleListingSaved}
                                    />
                                </div>
                                <div className="flex flex-col sm:flex-row sm:items-center sm:justify-end gap-2 border-t border-slate-100 bg-slate-50/80 px-5 py-3 sm:px-6">
                                    <Button
                                        variant="primary"
                                        size="sm"
                                        disabled={queueBusy}
                                        onClick={() => handleReview(listing.id, true)}
                                    >
                                        Approve request
                                    </Button>
                                    <Button
                                        variant="danger"
                                        size="sm"
                                        disabled={queueBusy}
                                        onClick={() => handleReview(listing.id, false)}
                                    >
                                        Reject
                                    </Button>
                                </div>
                            </article>
                        ))
                    )}
                </div>
            </div>
        </AdminLayout>
    );
}

export default RequestApprovals;
