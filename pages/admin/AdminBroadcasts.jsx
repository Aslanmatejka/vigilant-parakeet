import React from 'react';
import AdminLayout from './AdminLayout';
import Card from '../../components/common/Card';
import Button from '../../components/common/Button';
import supabase from '../../utils/supabaseClient';
import { useAuthContext } from '../../utils/AuthContext';

const DEFAULT_FORM = {
    title: '',
    message: '',
    channel: 'in_app',
    targetRole: 'all',
    communityId: ''
};

function formatDate(value) {
    if (!value) return '-';
    return new Date(value).toLocaleString();
}

function AdminBroadcasts() {
    const { user } = useAuthContext();
    const [form, setForm] = React.useState(DEFAULT_FORM);
    const [broadcasts, setBroadcasts] = React.useState([]);
    const [communities, setCommunities] = React.useState([]);
    const [loading, setLoading] = React.useState(true);
    const [submitting, setSubmitting] = React.useState(false);
    const [error, setError] = React.useState('');
    const [success, setSuccess] = React.useState('');
    const [statusFilter, setStatusFilter] = React.useState('all');

    const loadBroadcasts = React.useCallback(async () => {
        const { data, error: fetchError } = await supabase
            .from('admin_broadcasts')
            .select('id, title, message, channel, target_role, community_id, sent, sent_at, delivered_count, created_at')
            .order('created_at', { ascending: false })
            .limit(100);

        if (fetchError) throw fetchError;
        setBroadcasts(data || []);
    }, []);

    const loadCommunities = React.useCallback(async () => {
        const { data, error: fetchError } = await supabase
            .from('communities')
            .select('id, name')
            .order('name', { ascending: true });

        if (fetchError) throw fetchError;
        setCommunities(data || []);
    }, []);

    const loadData = React.useCallback(async () => {
        setLoading(true);
        setError('');

        try {
            await Promise.all([loadBroadcasts(), loadCommunities()]);
        } catch (loadError) {
            console.error('Failed to load admin broadcast data:', loadError);
            setError(loadError.message || 'Failed to load broadcast data.');
        } finally {
            setLoading(false);
        }
    }, [loadBroadcasts, loadCommunities]);

    React.useEffect(() => {
        loadData();
    }, [loadData]);

    const filteredBroadcasts = React.useMemo(() => {
        if (statusFilter === 'all') return broadcasts;
        if (statusFilter === 'pending') return broadcasts.filter((item) => !item.sent);
        return broadcasts.filter((item) => item.sent);
    }, [broadcasts, statusFilter]);

    const pendingCount = broadcasts.filter((item) => !item.sent).length;
    const sentCount = broadcasts.filter((item) => item.sent).length;

    const handleInputChange = (field, value) => {
        setForm((prev) => ({ ...prev, [field]: value }));
    };

    const handleCreateBroadcast = async (event) => {
        event.preventDefault();
        setError('');
        setSuccess('');

        if (!form.title.trim() || !form.message.trim()) {
            setError('Title and message are required.');
            return;
        }

        const newBroadcast = {
            title: form.title.trim(),
            message: form.message.trim(),
            channel: form.channel,
            target_role: form.targetRole === 'all' ? null : form.targetRole,
            community_id: form.communityId ? Number(form.communityId) : null,
            created_by: user?.id || null,
            sent: false
        };

        try {
            setSubmitting(true);
            const { error: insertError } = await supabase
                .from('admin_broadcasts')
                .insert(newBroadcast);

            if (insertError) throw insertError;

            setForm(DEFAULT_FORM);
            setSuccess('Broadcast queued successfully. It will be processed by the hourly automation worker.');
            await loadBroadcasts();
        } catch (insertErr) {
            console.error('Failed to queue broadcast:', insertErr);
            setError(insertErr.message || 'Failed to queue broadcast.');
        } finally {
            setSubmitting(false);
        }
    };

    return (
        <AdminLayout active="broadcasts">
            <div className="p-6 space-y-6">
                <div>
                    <h1 className="text-2xl font-bold text-gray-900">Admin Broadcasts</h1>
                    <p className="mt-1 text-gray-600">Queue announcements for in-app and SMS delivery via the automation worker.</p>
                </div>

                {error && (
                    <div className="rounded-md border border-red-200 bg-red-50 px-4 py-3 text-red-700">
                        <i className="fas fa-circle-exclamation mr-2"></i>
                        {error}
                    </div>
                )}

                {success && (
                    <div className="rounded-md border border-[#2CABE3]/30 bg-[#2CABE3]/10 px-4 py-3 text-[#2CABE3]">
                        <i className="fas fa-check-circle mr-2"></i>
                        {success}
                    </div>
                )}

                <div className="grid grid-cols-1 gap-4 md:grid-cols-3">
                    <Card>
                        <p className="text-sm text-gray-500">Total Broadcasts</p>
                        <p className="mt-2 text-2xl font-bold text-gray-900">{broadcasts.length}</p>
                    </Card>
                    <Card>
                        <p className="text-sm text-gray-500">Pending Queue</p>
                        <p className="mt-2 text-2xl font-bold text-yellow-600">{pendingCount}</p>
                    </Card>
                    <Card>
                        <p className="text-sm text-gray-500">Sent</p>
                        <p className="mt-2 text-2xl font-bold text-[#2CABE3]">{sentCount}</p>
                    </Card>
                </div>

                <Card>
                    <div className="p-6">
                        <h2 className="text-lg font-semibold text-gray-900">Create Broadcast</h2>
                        <form className="mt-4 space-y-4" onSubmit={handleCreateBroadcast}>
                            <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
                                <div>
                                    <label className="mb-1 block text-sm font-medium text-gray-700">Title</label>
                                    <input
                                        type="text"
                                        value={form.title}
                                        onChange={(e) => handleInputChange('title', e.target.value)}
                                        className="w-full rounded-md border border-gray-300 px-3 py-2 focus:border-transparent focus:outline-none focus:ring-2 focus:ring-[#2CABE3]"
                                        placeholder="Community Update"
                                    />
                                </div>

                                <div>
                                    <label className="mb-1 block text-sm font-medium text-gray-700">Channel</label>
                                    <select
                                        value={form.channel}
                                        onChange={(e) => handleInputChange('channel', e.target.value)}
                                        className="w-full rounded-md border border-gray-300 px-3 py-2 focus:border-transparent focus:outline-none focus:ring-2 focus:ring-[#2CABE3]"
                                    >
                                        <option value="in_app">In-App</option>
                                        <option value="sms">SMS</option>
                                        <option value="both">In-App + SMS</option>
                                    </select>
                                </div>

                                <div>
                                    <label className="mb-1 block text-sm font-medium text-gray-700">Target Role</label>
                                    <select
                                        value={form.targetRole}
                                        onChange={(e) => handleInputChange('targetRole', e.target.value)}
                                        className="w-full rounded-md border border-gray-300 px-3 py-2 focus:border-transparent focus:outline-none focus:ring-2 focus:ring-[#2CABE3]"
                                    >
                                        <option value="all">All Users</option>
                                        <option value="donor">Donor</option>
                                        <option value="recipient">Recipient</option>
                                        <option value="organizer">Organizer</option>
                                    </select>
                                </div>

                                <div>
                                    <label className="mb-1 block text-sm font-medium text-gray-700">Community</label>
                                    <select
                                        value={form.communityId}
                                        onChange={(e) => handleInputChange('communityId', e.target.value)}
                                        className="w-full rounded-md border border-gray-300 px-3 py-2 focus:border-transparent focus:outline-none focus:ring-2 focus:ring-[#2CABE3]"
                                    >
                                        <option value="">All Communities</option>
                                        {communities.map((community) => (
                                            <option key={community.id} value={community.id}>{community.name}</option>
                                        ))}
                                    </select>
                                </div>
                            </div>

                            <div>
                                <label className="mb-1 block text-sm font-medium text-gray-700">Message</label>
                                <textarea
                                    rows={4}
                                    value={form.message}
                                    onChange={(e) => handleInputChange('message', e.target.value)}
                                    className="w-full rounded-md border border-gray-300 px-3 py-2 focus:border-transparent focus:outline-none focus:ring-2 focus:ring-[#2CABE3]"
                                    placeholder="Type your announcement..."
                                />
                            </div>

                            <div className="flex justify-end">
                                <Button type="submit" loading={submitting}>Queue Broadcast</Button>
                            </div>
                        </form>
                    </div>
                </Card>

                <Card>
                    <div className="p-6">
                        <div className="mb-4 flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
                            <h2 className="text-lg font-semibold text-gray-900">Broadcast Queue</h2>
                            <div className="flex items-center gap-2">
                                <select
                                    value={statusFilter}
                                    onChange={(e) => setStatusFilter(e.target.value)}
                                    className="rounded-md border border-gray-300 px-3 py-2 text-sm focus:border-transparent focus:outline-none focus:ring-2 focus:ring-[#2CABE3]"
                                >
                                    <option value="all">All</option>
                                    <option value="pending">Pending</option>
                                    <option value="sent">Sent</option>
                                </select>
                                <Button variant="secondary" size="sm" onClick={loadBroadcasts}>Refresh</Button>
                            </div>
                        </div>

                        {loading ? (
                            <div className="py-10 text-center text-gray-500">
                                <i className="fas fa-spinner fa-spin mr-2"></i>
                                Loading broadcasts...
                            </div>
                        ) : filteredBroadcasts.length === 0 ? (
                            <div className="py-10 text-center text-gray-500">No broadcasts found for this filter.</div>
                        ) : (
                            <div className="overflow-x-auto">
                                <table className="min-w-full divide-y divide-gray-200">
                                    <thead className="bg-gray-50">
                                        <tr>
                                            <th className="px-3 py-2 text-left text-xs font-semibold uppercase tracking-wide text-gray-600">Title</th>
                                            <th className="px-3 py-2 text-left text-xs font-semibold uppercase tracking-wide text-gray-600">Channel</th>
                                            <th className="px-3 py-2 text-left text-xs font-semibold uppercase tracking-wide text-gray-600">Target</th>
                                            <th className="px-3 py-2 text-left text-xs font-semibold uppercase tracking-wide text-gray-600">Status</th>
                                            <th className="px-3 py-2 text-left text-xs font-semibold uppercase tracking-wide text-gray-600">Delivered</th>
                                            <th className="px-3 py-2 text-left text-xs font-semibold uppercase tracking-wide text-gray-600">Created</th>
                                            <th className="px-3 py-2 text-left text-xs font-semibold uppercase tracking-wide text-gray-600">Sent At</th>
                                        </tr>
                                    </thead>
                                    <tbody className="divide-y divide-gray-100 bg-white">
                                        {filteredBroadcasts.map((item) => (
                                            <tr key={item.id}>
                                                <td className="px-3 py-2 text-sm text-gray-900">
                                                    <div className="font-medium">{item.title}</div>
                                                    <div className="line-clamp-2 max-w-md text-xs text-gray-500">{item.message}</div>
                                                </td>
                                                <td className="px-3 py-2 text-sm text-gray-700">{item.channel}</td>
                                                <td className="px-3 py-2 text-sm text-gray-700">
                                                    {item.target_role || 'all'}
                                                    {item.community_id ? ` / community ${item.community_id}` : ''}
                                                </td>
                                                <td className="px-3 py-2 text-sm">
                                                    {item.sent ? (
                                                        <span className="rounded-full bg-[#2CABE3]/15 px-2 py-1 text-xs font-medium text-[#2CABE3]">Sent</span>
                                                    ) : (
                                                        <span className="rounded-full bg-yellow-100 px-2 py-1 text-xs font-medium text-yellow-800">Pending</span>
                                                    )}
                                                </td>
                                                <td className="px-3 py-2 text-sm text-gray-700">{item.delivered_count || 0}</td>
                                                <td className="px-3 py-2 text-sm text-gray-700">{formatDate(item.created_at)}</td>
                                                <td className="px-3 py-2 text-sm text-gray-700">{formatDate(item.sent_at)}</td>
                                            </tr>
                                        ))}
                                    </tbody>
                                </table>
                            </div>
                        )}
                    </div>
                </Card>
            </div>
        </AdminLayout>
    );
}

export default AdminBroadcasts;