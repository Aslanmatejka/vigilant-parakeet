import React from 'react';
import { toast } from 'react-toastify';
import AdminLayout from './AdminLayout';
import Button from '../../components/common/Button';
import AdminFoodDetail from '../../components/admin/AdminFoodDetail';
import AdminClaimDetail from '../../components/admin/AdminClaimDetail';
import dataService from '../../utils/dataService';
import supabase from '../../utils/supabaseClient';

/**
 * Admin queue for food claims awaiting moderation.
 * When require_claim_approval is on, recipient claims land here as pending
 * until an admin approves (ready for pickup) or declines (inventory restored).
 */
function ClaimApprovals() {
    const [claims, setClaims] = React.useState([]);
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
                dataService.getFoodClaims({ status: 'pending' }),
                dataService.getRequireClaimApproval(),
            ]);
            setClaims(Array.isArray(pending) ? pending : []);
            setRequireApproval(!!required);
        } catch (err) {
            console.error('ClaimApprovals load failed:', err);
            toast.error('Failed to load pending claims');
            setClaims([]);
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
            .channel('claim-approvals')
            .on(
                'postgres_changes',
                { event: '*', schema: 'public', table: 'food_claims' },
                schedule
            )
            .subscribe();

        return () => {
            if (refetchTimer) clearTimeout(refetchTimer);
            supabase.removeChannel(channel);
        };
    }, [load]);

    const handleClaimSaved = (updated) => {
        if (!updated?.id) return;
        setClaims((prev) =>
            prev.map((c) => (c.id === updated.id ? { ...c, ...updated } : c))
        );
    };

    const handleListingSaved = (claimId, updatedListing) => {
        if (!claimId || !updatedListing?.id) return;
        setClaims((prev) =>
            prev.map((c) => {
                if (c.id !== claimId) return c;
                return {
                    ...c,
                    food_listings: {
                        ...(c.food_listings || {}),
                        ...updatedListing,
                    },
                };
            })
        );
    };

    const handleReview = async (claimId, approved) => {
        setBusyId(claimId);
        try {
            await dataService.reviewFoodClaim(claimId, approved);
            await dataService.sendClaimReviewNotification(claimId, approved);
            setClaims((prev) => prev.filter((c) => c.id !== claimId));
            toast.success(
                approved
                    ? 'Claim approved — recipient can pick up'
                    : 'Claim rejected — food returned to Find Food'
            );
        } catch (err) {
            console.error('Claim review failed:', err);
            toast.error(err.message || 'Could not update claim');
        } finally {
            setBusyId(null);
        }
    };

    const handleReviewAll = async (approved) => {
        const ids = claims.map((c) => c.id).filter(Boolean);
        if (!ids.length) return;
        const action = approved ? 'approve' : 'reject';
        const ok = window.confirm(
            `${approved ? 'Approve' : 'Reject'} all ${ids.length} pending claim${ids.length === 1 ? '' : 's'}?`
        );
        if (!ok) return;

        setBulkBusy(true);
        let succeeded = 0;
        const failed = [];
        try {
            // Sequential: rejecting restores inventory; parallel can race on same listing.
            for (const id of ids) {
                try {
                    await dataService.reviewFoodClaim(id, approved);
                    await dataService.sendClaimReviewNotification(id, approved);
                    succeeded += 1;
                    setClaims((prev) => prev.filter((c) => c.id !== id));
                } catch (err) {
                    console.error(`Claim ${action} failed for ${id}:`, err);
                    failed.push(id);
                }
            }
            if (succeeded > 0) {
                toast.success(
                    approved
                        ? `Approved ${succeeded} claim${succeeded === 1 ? '' : 's'}`
                        : `Rejected ${succeeded} claim${succeeded === 1 ? '' : 's'}`
                );
            }
            if (failed.length) {
                toast.error(`${failed.length} claim${failed.length === 1 ? '' : 's'} could not be ${action}d`);
            }
        } finally {
            setBulkBusy(false);
        }
    };

    const handleToggleRequireApproval = async () => {
        const next = !requireApproval;
        setSavingToggle(true);
        try {
            await dataService.setPlatformSetting('require_claim_approval', next);
            setRequireApproval(next);
            toast.success(
                next
                    ? 'New claims will wait for approval'
                    : 'New claims will be auto-approved'
            );
        } catch (err) {
            console.error('Toggle require claim approval failed:', err);
            toast.error('Could not update approval setting');
        } finally {
            setSavingToggle(false);
        }
    };

    return (
        <AdminLayout active="claim-approvals">
            <div className="max-w-7xl mx-auto py-8 px-4 sm:px-6 lg:px-8 space-y-6">
                <div className="flex flex-col sm:flex-row sm:items-end sm:justify-between gap-4">
                    <div>
                        <h1 className="text-2xl font-bold text-gray-900">Claim Approvals</h1>
                        <p className="mt-1 text-sm text-gray-600">
                            Edit food and claim details before recipients can pick up.
                        </p>
                    </div>
                    <div className="flex items-center gap-3 rounded-xl border border-slate-200 bg-white px-4 py-3 shadow-sm">
                        <div className="min-w-0">
                            <p className="text-sm font-semibold text-gray-900">Require approval</p>
                            <p className="text-xs text-gray-500">
                                {requireApproval
                                    ? 'Claims start as pending'
                                    : 'Claims auto-approve immediately'}
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
                    <div className="rounded-xl bg-amber-50 border border-amber-100 p-4">
                        <p className="text-xs font-semibold uppercase tracking-wide text-amber-700">Pending</p>
                        <p className="mt-1 text-2xl font-bold text-amber-900">{claims.length}</p>
                    </div>
                    <div className="rounded-xl bg-slate-50 border border-slate-200 p-4 sm:col-span-2 flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3">
                        <p className="text-sm text-slate-600">
                            Save edits before approving. Approving confirms the pickup reservation.
                            Rejecting returns the reserved quantity to Find Food. Turning off
                            require-approval only affects new claims — it does not auto-approve this queue.
                        </p>
                        {claims.length > 0 && (
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
                            <p className="mt-3 text-sm">Loading pending claims…</p>
                        </div>
                    ) : claims.length === 0 ? (
                        <div className="bg-white rounded-2xl border border-slate-200 shadow-sm p-12 text-center">
                            <i className="fas fa-check-circle text-3xl text-emerald-400" aria-hidden="true" />
                            <p className="mt-3 text-lg font-semibold text-gray-900">Queue is clear</p>
                            <p className="mt-1 text-sm text-gray-500">
                                {requireApproval
                                    ? 'New claims will show up here for review.'
                                    : 'Approval is off — new claims skip this queue.'}
                            </p>
                        </div>
                    ) : (
                        claims.map((claim) => {
                            const listing = claim.food_listings || {};
                            return (
                                <article
                                    key={claim.id}
                                    className="bg-white rounded-2xl border border-slate-200 shadow-sm overflow-hidden"
                                >
                                    <div className="p-5 sm:p-6 space-y-4">
                                        <AdminFoodDetail
                                            listing={listing}
                                            editable
                                            disabled={queueBusy}
                                            onSaved={(updated) => handleListingSaved(claim.id, updated)}
                                        />
                                        <AdminClaimDetail
                                            claim={claim}
                                            listing={listing}
                                            editable
                                            disabled={queueBusy}
                                            onSaved={handleClaimSaved}
                                        />
                                    </div>
                                    <div className="flex flex-col sm:flex-row sm:items-center sm:justify-end gap-2 border-t border-slate-100 bg-slate-50/80 px-5 py-3 sm:px-6">
                                        <Button
                                            variant="primary"
                                            size="sm"
                                            disabled={queueBusy}
                                            onClick={() => handleReview(claim.id, true)}
                                        >
                                            Approve
                                        </Button>
                                        <Button
                                            variant="danger"
                                            size="sm"
                                            disabled={queueBusy}
                                            onClick={() => handleReview(claim.id, false)}
                                        >
                                            Reject
                                        </Button>
                                    </div>
                                </article>
                            );
                        })
                    )}
                </div>
            </div>
        </AdminLayout>
    );
}

export default ClaimApprovals;
