import React from 'react';
import { useSearchParams } from 'react-router-dom';
import AdminLayout from './AdminLayout';
import Button from '../../components/common/Button';
import supabase from '../../utils/supabaseClient';
import { useAuthContext } from '../../utils/AuthContext';
import communitiesStatic from '../../utils/communities';
import organizationsStatic from '../../utils/organizations';

// Defined at module level so React never treats it as a new component type on re-renders.
// If defined inside ImpactDataEntry, every parent re-render creates a new function reference,
// causing React to unmount/remount all inputs — destroying typed values and nullifying refs.
function UncontrolledCell({ defaultValue, onBlur, type = 'text', inputRef, className }) {
    return (
        <input
            ref={inputRef}
            type={type}
            defaultValue={defaultValue}
            onBlur={(e) => {
                const value = type === 'number' ? (parseFloat(e.target.value) || 0) : e.target.value;
                onBlur(value);
            }}
            className={className || "w-full px-1 py-1 text-xs border border-gray-300 focus:outline-none focus:ring-1 focus:ring-[#2CABE3] focus:border-transparent"}
        />
    );
}

function ImpactDataEntry() {
    const { user } = useAuthContext();
    const [searchParams, setSearchParams] = useSearchParams();
    const activeTab = searchParams.get('tab') || 'organizations';
    const dateFilter = searchParams.get('dateFilter') || 'current-week';
    const setActiveTab = (tab) => setSearchParams(prev => { prev.set('tab', tab); return prev; }, { replace: true });
    const setDateFilter = (filter) => setSearchParams(prev => { prev.set('dateFilter', filter); return prev; }, { replace: true });
    const [data, setData] = React.useState([]);
    const [loading, setLoading] = React.useState(true);
    const [refreshing, setRefreshing] = React.useState(false);
    const [communities, setCommunities] = React.useState([]);
    const [organizations, setOrganizations] = React.useState([]);
    const [showArchived, setShowArchived] = React.useState(false);

    // Refs for organization impact entries
    const orgRowRefs = React.useRef({
        date: null,
        organization: null,
        food_saved_from_waste_lb: null,
        food_donated: null,
        notes: null
    });

    // Refs for community impact entries
    const communityRowRefs = React.useRef({
        date: null,
        communities_served: null,
        families_helped: null,
        school_staff_helped: null,
        food_given_lb: null,
        notes: null
    });

    React.useEffect(() => {
        fetchData();
        fetchCommunitiesAndOrganizations();
    }, []);

    const fetchCommunitiesAndOrganizations = async () => {
        try {
            // Fetch communities from database
            const { data: communitiesData, error: communitiesError } = await supabase
                .from('communities')
                .select('id, name')
                .eq('is_active', true)
                .order('name', { ascending: true });

            if (!communitiesError && communitiesData && communitiesData.length > 0) {
                setCommunities(communitiesData);
            } else {
                // Fallback to static data
                setCommunities(communitiesStatic);
            }

            // Fetch sponsors/organizations from database
            const { data: sponsorsData, error: sponsorsError } = await supabase
                .from('sponsors')
                .select('id, name')
                .eq('is_active', true)
                .order('name', { ascending: true });

            if (!sponsorsError && sponsorsData && sponsorsData.length > 0) {
                setOrganizations(sponsorsData);
            } else {
                // Fallback to static data
                setOrganizations(organizationsStatic);
            }
        } catch (error) {
            console.error('Error fetching communities and organizations:', error);
            // Use static data on error
            setCommunities(communitiesStatic);
            setOrganizations(organizationsStatic);
        }
    };

    // Safety: if refreshing gets stuck true (e.g. network stall), force-reset after 20s
    React.useEffect(() => {
        if (!refreshing) return;
        const id = setTimeout(() => setRefreshing(false), 20000);
        return () => clearTimeout(id);
    }, [refreshing]);

    const fetchData = async (isRefresh = false) => {
        try {
            if (isRefresh) {
                setRefreshing(true);
            } else {
                setLoading(true);
            }

            // Use Promise.race so the timeout is guaranteed to fire even if
            // the Supabase fetch hangs indefinitely (network stall, dropped connection).
            // AbortController + .abortSignal() can silently fail in some network conditions.
            const timeoutPromise = new Promise((_, reject) =>
                setTimeout(() => reject(new Error('Request timed out after 15s')), 15000)
            );
            const queryPromise = supabase
                .from('impact_data')
                .select('*')
                .order('date', { ascending: false });

            const { data: impactData, error } = await Promise.race([queryPromise, timeoutPromise]);

            if (error) throw error;
            setData(impactData || []);
        } catch (error) {
            console.error('Error fetching impact data:', error);
            // Keep existing data on refresh failure, clear on initial load failure
            if (!isRefresh) {
                setData([]);
            }
        } finally {
            setLoading(false);
            setRefreshing(false);
        }
    };

    // Sync aggregated metrics from impact_data to communities and sponsors tables
    const syncMetricsToTables = async () => {
        try {
            console.log('Syncing metrics to communities and sponsors tables...');

            // Fetch all impact data
            const { data: allImpactData, error: fetchError } = await supabase
                .from('impact_data')
                .select('*');

            if (fetchError) throw fetchError;

            // Aggregate metrics by community
            const communityMetrics = {};
            allImpactData?.forEach(row => {
                if (row.communities_served && row.communities_served.trim()) {
                    if (!communityMetrics[row.communities_served]) {
                        communityMetrics[row.communities_served] = {
                            food_given_lb: 0,
                            families_helped: 0,
                            school_staff_helped: 0
                        };
                    }
                    communityMetrics[row.communities_served].food_given_lb += parseFloat(row.food_given_lb) || 0;
                    communityMetrics[row.communities_served].families_helped += parseInt(row.families_helped) || 0;
                    communityMetrics[row.communities_served].school_staff_helped += parseInt(row.school_staff_helped) || 0;
                }
            });

            // Update communities table
            for (const [communityName, metrics] of Object.entries(communityMetrics)) {
                const { error: updateError } = await supabase
                    .from('communities')
                    .update({
                        food_given_lb: metrics.food_given_lb,
                        families_helped: metrics.families_helped,
                        school_staff_helped: metrics.school_staff_helped,
                        updated_at: new Date().toISOString()
                    })
                    .eq('name', communityName);

                if (updateError) {
                    console.warn(`Warning: Could not update community "${communityName}":`, updateError.message);
                }
            }

            // Aggregate metrics by organization/sponsor
            const sponsorMetrics = {};
            allImpactData?.forEach(row => {
                if (row.organization && row.organization.trim()) {
                    if (!sponsorMetrics[row.organization]) {
                        sponsorMetrics[row.organization] = {
                            food_saved_from_waste_lb: 0,
                            food_donated_lb: 0
                        };
                    }
                    sponsorMetrics[row.organization].food_saved_from_waste_lb += parseFloat(row.food_saved_from_waste_lb) || 0;
                    sponsorMetrics[row.organization].food_donated_lb += parseFloat(row.food_donated) || 0;
                }
            });

            // Update sponsors table
            for (const [sponsorName, metrics] of Object.entries(sponsorMetrics)) {
                const { error: updateError } = await supabase
                    .from('sponsors')
                    .update({
                        food_saved_from_waste_lb: metrics.food_saved_from_waste_lb,
                        food_donated_lb: metrics.food_donated_lb,
                        updated_at: new Date().toISOString()
                    })
                    .eq('name', sponsorName);

                if (updateError) {
                    console.warn(`Warning: Could not update sponsor "${sponsorName}":`, updateError.message);
                }
            }

            console.log('✅ Metrics synced successfully!');
            return true;
        } catch (error) {
            console.error('Error syncing metrics:', error);
            return false;
        }
    };

    const applyDateFilter = (filtered) => {
        if (dateFilter === 'all') return filtered;
        const now = new Date();
        const currentYear = now.getFullYear();
        const currentMonth = now.getMonth();
        return filtered.filter(row => {
            const rowDate = new Date(row.date);
            switch (dateFilter) {
                case 'current-week': {
                    const startOfWeek = new Date(now);
                    startOfWeek.setDate(now.getDate() - now.getDay());
                    startOfWeek.setHours(0, 0, 0, 0);
                    return rowDate >= startOfWeek;
                }
                case 'current-month':
                    return rowDate.getFullYear() === currentYear && rowDate.getMonth() === currentMonth;
                default:
                    return true;
            }
        });
    };

    const orgData = React.useMemo(() =>
        applyDateFilter(data.filter(row => row.organization && row.organization.trim() !== '')),
    [data, dateFilter]);

    const communityData = React.useMemo(() =>
        applyDateFilter(data.filter(row => row.communities_served && row.communities_served.trim() !== '')),
    [data, dateFilter]);

    const handleAddOrgRow = async () => {
        try {
            const newRowData = {
                date: orgRowRefs.current.date?.value || (() => { const _d = new Date(); return [_d.getFullYear(), String(_d.getMonth()+1).padStart(2,'0'), String(_d.getDate()).padStart(2,'0')].join('-'); })(),
                organization: orgRowRefs.current.organization?.value || '',
                food_saved_from_waste_lb: parseFloat(orgRowRefs.current.food_saved_from_waste_lb?.value) || 0,
                food_donated: parseFloat(orgRowRefs.current.food_donated?.value) || 0,
                notes: orgRowRefs.current.notes?.value || ''
            };

            console.log('Attempting to insert organization data:', newRowData);

            // Check authentication
            const { data: { session }, error: sessionError } = await supabase.auth.getSession();
            if (sessionError || !session) {
                throw new Error('Not authenticated. Please log in again.');
            }

            const { data, error } = await supabase
                .from('impact_data')
                .insert([newRowData])
                .select();

            if (error) {
                console.error('Supabase error details:', {
                    message: error.message,
                    details: error.details,
                    hint: error.hint,
                    code: error.code
                });
                throw error;
            }

            console.log('Successfully inserted:', data);

            if (orgRowRefs.current.date) orgRowRefs.current.date.value = (() => { const _d = new Date(); return [_d.getFullYear(), String(_d.getMonth()+1).padStart(2,'0'), String(_d.getDate()).padStart(2,'0')].join('-'); })();
            if (orgRowRefs.current.organization) orgRowRefs.current.organization.value = '';
            if (orgRowRefs.current.food_saved_from_waste_lb) orgRowRefs.current.food_saved_from_waste_lb.value = '';
            if (orgRowRefs.current.food_donated) orgRowRefs.current.food_donated.value = '';
            if (orgRowRefs.current.notes) orgRowRefs.current.notes.value = '';

            await fetchData(true);
            await syncMetricsToTables();
            alert('✅ Organization entry added and metrics synced!');
        } catch (error) {
            console.error('Error adding organization row:', error);
            const errorMessage = error.message || error.toString();
            
            // More specific error messages
            if (errorMessage.includes('Failed to fetch')) {
                alert('❌ Network error: Cannot connect to database. Please check:\n1. Your internet connection\n2. Supabase configuration in .env.local\n3. Browser console for details');
            } else if (errorMessage.includes('JWT')) {
                alert('❌ Authentication error: Please log out and log back in.');
            } else {
                alert('❌ Failed to add organization entry: ' + errorMessage);
            }
        }
    };

    const handleAddCommunityRow = async () => {
        try {
            const newRowData = {
                date: communityRowRefs.current.date?.value || new Date().toISOString().split('T')[0],
                communities_served: communityRowRefs.current.communities_served?.value || '',
                families_helped: parseInt(communityRowRefs.current.families_helped?.value) || 0,
                school_staff_helped: parseInt(communityRowRefs.current.school_staff_helped?.value) || 0,
                food_given_lb: parseFloat(communityRowRefs.current.food_given_lb?.value) || 0,
                notes: communityRowRefs.current.notes?.value || ''
            };

            console.log('Attempting to insert community data:', newRowData);

            // Check authentication
            const { data: { session }, error: sessionError } = await supabase.auth.getSession();
            if (sessionError || !session) {
                throw new Error('Not authenticated. Please log in again.');
            }

            const { data, error } = await supabase
                .from('impact_data')
                .insert([newRowData])
                .select();

            if (error) {
                console.error('Supabase error details:', {
                    message: error.message,
                    details: error.details,
                    hint: error.hint,
                    code: error.code
                });
                throw error;
            }

            console.log('Successfully inserted:', data);

            if (communityRowRefs.current.date) communityRowRefs.current.date.value = new Date().toISOString().split('T')[0];
            if (communityRowRefs.current.communities_served) communityRowRefs.current.communities_served.value = '';
            if (communityRowRefs.current.families_helped) communityRowRefs.current.families_helped.value = '';
            if (communityRowRefs.current.school_staff_helped) communityRowRefs.current.school_staff_helped.value = '';
            if (communityRowRefs.current.food_given_lb) communityRowRefs.current.food_given_lb.value = '';
            if (communityRowRefs.current.notes) communityRowRefs.current.notes.value = '';

            await fetchData(true);
            await syncMetricsToTables();
            alert('✅ Community entry added and metrics synced!');
        } catch (error) {
            console.error('Error adding community row:', error);
            const errorMessage = error.message || error.toString();
            
            // More specific error messages
            if (errorMessage.includes('Failed to fetch')) {
                alert('❌ Network error: Cannot connect to database. Please check:\n1. Your internet connection\n2. Supabase configuration in .env.local\n3. Browser console for details');
            } else if (errorMessage.includes('JWT')) {
                alert('❌ Authentication error: Please log out and log back in.');
            } else {
                alert('❌ Failed to add community entry: ' + errorMessage);
            }
        }
    };

    const handleUpdateRow = async (id, field, value) => {
        try {
            const { error } = await supabase
                .from('impact_data')
                .update({
                    [field]: value,
                    updated_at: new Date().toISOString()
                })
                .eq('id', id);

            if (error) throw error;

            // Update local data after successful save
            setData(prev => prev.map(row =>
                row.id === id ? { ...row, [field]: value } : row
            ));

            // Sync metrics if a metric field was updated
            const metricFields = ['food_saved_from_waste_lb', 'food_donated', 'families_helped', 'school_staff_helped', 'food_given_lb'];
            if (metricFields.includes(field)) {
                await syncMetricsToTables();
            }
        } catch (error) {
            console.error('Error updating row:', error);
            alert('Failed to update: ' + error.message);
        }
    };

    const handleDeleteRow = async (id) => {
        if (!confirm('Are you sure you want to delete this entry?')) return;

        try {
            const { error } = await supabase
                .from('impact_data')
                .delete()
                .eq('id', id);

            if (error) throw error;
            await fetchData(true);
            await syncMetricsToTables();
            alert('Entry deleted and metrics synced!');
        } catch (error) {
            console.error('Error deleting row:', error);
            alert('Failed to delete: ' + error.message);
        }
    };

    // Simple update handler for existing rows - uses uncontrolled inputs too

    const exportToCSV = () => {
        const dataToExport = activeTab === 'organizations' ? orgData : communityData;
        const headers = activeTab === 'organizations'
            ? ['Date', 'Organization', 'Food Saved from Waste (lb)', 'Food Provided (lb)', 'Food Donated', 'Total Meals', 'Notes']
            : ['Date', 'Community', 'Families Helped', 'School Staff Helped', 'Schools Served', 'Non-Profits Helped', 'Total Meals', 'Notes'];

        const rows = dataToExport.map(row =>
            activeTab === 'organizations'
                ? [
                    row.date,
                    row.organization || '',
                    row.food_saved_from_waste_lb || 0,
                    row.food_donated || 0,
                    row.notes || ''
                ]
                : [
                    row.date,
                    row.communities_served || '',
                    row.families_helped || 0,
                    row.school_staff_helped || 0,
                    row.food_given_lb || 0,
                    row.notes || ''
                ]
        );

        const csvContent = [headers, ...rows]
            .map(row => row.map(cell => `"${cell}"`).join(','))
            .join('\n');

        const blob = new Blob([csvContent], { type: 'text/csv;charset=utf-8;' });
        const link = document.createElement('a');
        const url = URL.createObjectURL(blob);
        link.setAttribute('href', url);
        link.setAttribute('download', `impact_${activeTab}_${new Date().toISOString()}.csv`);
        link.style.visibility = 'hidden';
        document.body.appendChild(link);
        link.click();
        document.body.removeChild(link);
    };

    return (
        <AdminLayout active="impact">
            <div className="p-6">
                <div className="mb-6 flex justify-between items-center">
                    <div>
                        <h1 className="text-2xl font-bold text-gray-900">Impact Data Entry</h1>
                        <p className="mt-2 text-gray-600">Separate entry forms for organization and community impact data</p>
                    </div>
                    <div className="flex space-x-3">
                        <Button
                            variant="primary"
                            onClick={async () => {
                                const success = await syncMetricsToTables();
                                if (success) {
                                    alert('✅ Metrics successfully synced to Communities and Sponsors tables!');
                                } else {
                                    alert('❌ Error syncing metrics. Check console for details.');
                                }
                            }}
                        >
                            <i className="fas fa-database mr-2"></i>
                            Sync Metrics
                        </Button>
                        <Button
                            variant="secondary"
                            onClick={() => fetchData(true)}
                            disabled={refreshing}
                        >
                            <i className={`fas fa-sync-alt mr-2 ${refreshing ? 'animate-spin' : ''}`}></i>
                            {refreshing ? 'Refreshing...' : 'Refresh'}
                        </Button>
                        <Button
                            variant="primary"
                            onClick={exportToCSV}
                        >
                            <i className="fas fa-download mr-2"></i>
                            Export CSV
                        </Button>
                    </div>
                </div>

                {/* Date Filter Controls */}
                <div className="mb-6 bg-blue-50 border border-blue-200 rounded-lg p-4">
                    <div className="flex items-center justify-between flex-wrap gap-4">
                        <div className="flex items-center gap-2">
                            <i className="fas fa-filter text-blue-600"></i>
                            <span className="font-medium text-gray-700">Show entries from:</span>
                        </div>
                        <div className="flex gap-2 flex-wrap">
                            <button
                                onClick={() => setDateFilter('current-week')}
                                className={`px-4 py-2 rounded-md text-sm font-medium transition-colors ${
                                    dateFilter === 'current-week'
                                        ? 'bg-blue-600 text-white'
                                        : 'bg-white text-gray-700 hover:bg-blue-100'
                                }`}
                            >
                                Current Week
                            </button>
                            <button
                                onClick={() => setDateFilter('current-month')}
                                className={`px-4 py-2 rounded-md text-sm font-medium transition-colors ${
                                    dateFilter === 'current-month'
                                        ? 'bg-blue-600 text-white'
                                        : 'bg-white text-gray-700 hover:bg-blue-100'
                                }`}
                            >
                                Current Month
                            </button>
                            <button
                                onClick={() => setDateFilter('all')}
                                className={`px-4 py-2 rounded-md text-sm font-medium transition-colors ${
                                    dateFilter === 'all'
                                        ? 'bg-blue-600 text-white'
                                        : 'bg-white text-gray-700 hover:bg-blue-100'
                                }`}
                            >
                                <i className="fas fa-archive mr-1"></i>
                                All (Archived)
                            </button>
                        </div>
                        <div className="text-sm text-gray-600">
                            Showing <span className="font-semibold text-blue-700">{activeTab === 'organizations' ? orgData.length : communityData.length}</span> of <span className="font-semibold">{data.length}</span> total entries
                        </div>
                    </div>
                </div>

                <div className="mb-6 border-b border-gray-200">
                    <nav className="-mb-px flex space-x-8">
                        <button
                            onClick={() => setActiveTab('organizations')}
                            className={`${
                                activeTab === 'organizations'
                                    ? 'border-[#2CABE3] text-[#2CABE3]'
                                    : 'border-transparent text-gray-500 hover:text-gray-700 hover:border-gray-300'
                            } whitespace-nowrap py-4 px-1 border-b-2 font-medium text-sm transition-colors`}
                        >
                            <i className="fas fa-building mr-2"></i>
                            Organization Impact
                        </button>
                        <button
                            onClick={() => setActiveTab('communities')}
                            className={`${
                                activeTab === 'communities'
                                    ? 'border-blue-500 text-blue-600'
                                    : 'border-transparent text-gray-500 hover:text-gray-700 hover:border-gray-300'
                            } whitespace-nowrap py-4 px-1 border-b-2 font-medium text-sm transition-colors`}
                        >
                            <i className="fas fa-users mr-2"></i>
                            Communities Served
                        </button>
                    </nav>
                </div>

                {loading ? (
                    <div className="p-8 text-center">
                        <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-[#2CABE3] mx-auto"></div>
                        <p className="mt-4 text-gray-600">Loading data...</p>
                    </div>
                ) : (
                    <div className="bg-white rounded-lg shadow overflow-x-auto overflow-y-auto text-xs" style={{maxHeight: 'calc(100vh - 280px)'}}>
                        <div className={activeTab !== 'organizations' ? 'hidden' : ''}>
                            <table className="min-w-full divide-y divide-gray-200 [&_td]:px-1 [&_td]:py-1">
                                <thead className="bg-gray-50 sticky top-0 z-10">
                                    <tr>
                                        <th className="px-2 py-2 text-left text-xs font-medium text-gray-500 uppercase tracking-wider min-w-[110px]">
                                            Date
                                        </th>
                                        <th className="px-2 py-2 text-left text-xs font-medium text-gray-500 uppercase tracking-wider min-w-[140px]">
                                            Organization
                                        </th>
                                        <th className="px-2 py-2 text-left text-xs font-medium text-[#2CABE3] uppercase tracking-wider min-w-[90px]">
                                            Food Saved (lb)
                                        </th>
                                        <th className="px-2 py-2 text-left text-xs font-medium text-[#2CABE3] uppercase tracking-wider min-w-[80px]">
                                            Food Donated
                                        </th>
                                        <th className="px-2 py-2 text-left text-xs font-medium text-gray-500 uppercase tracking-wider min-w-[150px]">
                                            Notes
                                        </th>
                                        <th className="px-2 py-2 text-left text-xs font-medium text-gray-500 uppercase tracking-wider min-w-[50px]">
                                            Actions
                                        </th>
                                    </tr>
                                </thead>
                                <tbody className="bg-white divide-y divide-gray-200">
                                    <tr className="bg-[#2CABE3]/10">
                                        <td className="px-3 py-2">
                                            <UncontrolledCell
                                                type="date"
                                                defaultValue={new Date().toISOString().split('T')[0]}
                                                inputRef={el => orgRowRefs.current.date = el}
                                                onBlur={() => { }}
                                            />
                                        </td>
                                        <td className="px-3 py-2">
                                            <select
                                                ref={el => orgRowRefs.current.organization = el}
                                                className="w-full px-1 py-1 text-xs border border-gray-300 focus:outline-none focus:ring-1 focus:ring-[#2CABE3] focus:border-transparent"
                                            >
                                                <option value="">Select Organization</option>
                                                {organizations.map((org) => (
                                                    <option key={org.id} value={org.name}>
                                                        {org.name}
                                                    </option>
                                                ))}
                                            </select>
                                        </td>
                                        <td className="px-3 py-2">
                                            <UncontrolledCell
                                                type="number"
                                                defaultValue=""
                                                inputRef={el => orgRowRefs.current.food_saved_from_waste_lb = el}
                                                onBlur={() => { }}
                                                className="w-full px-1 py-1 text-xs border border-gray-300 focus:outline-none focus:ring-1 focus:ring-[#2CABE3] focus:border-transparent"
                                            />
                                        </td>
                                        <td className="px-3 py-2">
                                            <UncontrolledCell
                                                type="number"
                                                defaultValue=""
                                                inputRef={el => orgRowRefs.current.food_donated = el}
                                                onBlur={() => { }}
                                                className="w-full px-1 py-1 text-xs border border-gray-300 focus:outline-none focus:ring-1 focus:ring-[#2CABE3] focus:border-transparent"
                                            />
                                        </td>
                                        <td className="px-3 py-2">
                                            <UncontrolledCell
                                                defaultValue=""
                                                inputRef={el => orgRowRefs.current.notes = el}
                                                onBlur={() => { }}
                                            />
                                        </td>
                                        <td className="px-3 py-2">
                                            <Button
                                                variant="primary"
                                                size="sm"
                                                onClick={handleAddOrgRow}
                                            >
                                                <i className="fas fa-plus"></i>
                                            </Button>
                                        </td>
                                    </tr>

                                    {orgData.map((row) => (
                                        <tr key={row.id} className="hover:bg-gray-50">
                                            <td className="px-3 py-2">
                                                <UncontrolledCell
                                                    type="date"
                                                    defaultValue={row.date}
                                                    onBlur={(val) => handleUpdateRow(row.id, 'date', val)}
                                                />
                                            </td>
                                            <td className="px-3 py-2">
                                                <select
                                                    value={row.organization || ''}
                                                    onChange={(e) => handleUpdateRow(row.id, 'organization', e.target.value)}
                                                className="w-full px-1 py-1 text-xs border border-gray-300 focus:outline-none focus:ring-1 focus:ring-[#2CABE3] focus:border-transparent"
                                                >
                                                    <option value="">Select Organization</option>
                                                    {organizations.map((org) => (
                                                        <option key={org.id} value={org.name}>
                                                            {org.name}
                                                        </option>
                                                    ))}
                                                </select>
                                            </td>
                                            <td className="px-3 py-2">
                                                <UncontrolledCell
                                                    type="number"
                                                    defaultValue={row.food_saved_from_waste_lb || 0}
                                                    onBlur={(val) => handleUpdateRow(row.id, 'food_saved_from_waste_lb', val)}
                                                className="w-full px-1 py-1 text-xs border border-gray-300 focus:outline-none focus:ring-1 focus:ring-[#2CABE3] focus:border-transparent"
                                                />
                                            </td>
                                            <td className="px-3 py-2">
                                                <UncontrolledCell
                                                    type="number"
                                                    defaultValue={row.food_donated || 0}
                                                    onBlur={(val) => handleUpdateRow(row.id, 'food_donated', val)}
                                                className="w-full px-1 py-1 text-xs border border-gray-300 focus:outline-none focus:ring-1 focus:ring-[#2CABE3] focus:border-transparent"
                                                />
                                            </td>
                                            <td className="px-3 py-2">
                                                <UncontrolledCell
                                                    defaultValue={row.notes || ''}
                                                    onBlur={(val) => handleUpdateRow(row.id, 'notes', val)}
                                                />
                                            </td>
                                            <td className="px-3 py-2">
                                                <Button
                                                    variant="danger"
                                                    size="sm"
                                                    onClick={() => handleDeleteRow(row.id)}
                                                >
                                                    <i className="fas fa-trash"></i>
                                                </Button>
                                            </td>
                                        </tr>
                                    ))}

                                    {orgData.length === 0 && (
                                        <tr>
                                            <td colSpan="8" className="px-6 py-8 text-center text-gray-500">
                                                No organization entries yet. Add your first entry using the row above.
                                            </td>
                                        </tr>
                                    )}
                                </tbody>
                            </table>
                        </div>
                        <div className={activeTab !== 'communities' ? 'hidden' : ''}>
                            <table className="min-w-full divide-y divide-gray-200 [&_td]:px-1 [&_td]:py-1">
                                <thead className="bg-gray-50 sticky top-0 z-10">
                                    <tr>
                                        <th className="px-2 py-2 text-left text-xs font-medium text-gray-500 uppercase tracking-wider min-w-[110px]">
                                            Date
                                        </th>
                                        <th className="px-2 py-2 text-left text-xs font-medium text-gray-500 uppercase tracking-wider min-w-[140px]">
                                            Community
                                        </th>
                                        <th className="px-2 py-2 text-left text-xs font-medium text-blue-600 uppercase tracking-wider min-w-[80px]">
                                            Families Helped
                                        </th>
                                        <th className="px-2 py-2 text-left text-xs font-medium text-blue-600 uppercase tracking-wider min-w-[90px]">
                                            School Staff Helped
                                        </th>
                                        <th className="px-2 py-2 text-left text-xs font-medium text-orange-600 uppercase tracking-wider min-w-[80px]">
                                            Food Given (lb)
                                        </th>
                                        <th className="px-2 py-2 text-left text-xs font-medium text-gray-500 uppercase tracking-wider min-w-[150px]">
                                            Notes
                                        </th>
                                        <th className="px-2 py-2 text-left text-xs font-medium text-gray-500 uppercase tracking-wider min-w-[50px]">
                                            Actions
                                        </th>
                                    </tr>
                                </thead>
                                <tbody className="bg-white divide-y divide-gray-200">
                                    <tr className="bg-blue-50">
                                        <td className="px-3 py-2">
                                            <UncontrolledCell
                                                type="date"
                                                defaultValue={new Date().toISOString().split('T')[0]}
                                                inputRef={el => communityRowRefs.current.date = el}
                                                onBlur={() => { }}
                                            />
                                        </td>
                                        <td className="px-3 py-2">
                                            <select
                                                ref={el => communityRowRefs.current.communities_served = el}
                                                className="w-full px-1 py-1 text-xs border border-gray-300 focus:outline-none focus:ring-1 focus:ring-blue-500 focus:border-transparent"
                                            >
                                                <option value="">Select Community</option>
                                                {communities.map((community) => (
                                                    <option key={community.id} value={community.name}>
                                                        {community.name}
                                                    </option>
                                                ))}
                                            </select>
                                        </td>
                                        <td className="px-3 py-2">
                                            <UncontrolledCell
                                                type="number"
                                                defaultValue=""
                                                inputRef={el => communityRowRefs.current.families_helped = el}
                                                onBlur={() => { }}
                                                className="w-full px-1 py-1 text-xs border border-gray-300 focus:outline-none focus:ring-1 focus:ring-[#2CABE3] focus:border-transparent"
                                            />
                                        </td>
                                        <td className="px-3 py-2">
                                            <UncontrolledCell
                                                type="number"
                                                defaultValue=""
                                                inputRef={el => communityRowRefs.current.school_staff_helped = el}
                                                onBlur={() => { }}
                                                className="w-full px-1 py-1 text-xs border border-gray-300 focus:outline-none focus:ring-1 focus:ring-[#2CABE3] focus:border-transparent"
                                            />
                                        </td>
                                        <td className="px-3 py-2">
                                            <UncontrolledCell
                                                type="number"
                                                defaultValue=""
                                                inputRef={el => communityRowRefs.current.food_given_lb = el}
                                                onBlur={() => { }}
                                                className="w-full px-1 py-1 text-xs border border-gray-300 focus:outline-none focus:ring-1 focus:ring-[#2CABE3] focus:border-transparent"
                                            />
                                        </td>
                                        <td className="px-3 py-2">
                                            <UncontrolledCell
                                                defaultValue=""
                                                inputRef={el => communityRowRefs.current.notes = el}
                                                onBlur={() => { }}
                                            />
                                        </td>
                                        <td className="px-3 py-2">
                                            <Button
                                                variant="primary"
                                                size="sm"
                                                onClick={handleAddCommunityRow}
                                            >
                                                <i className="fas fa-plus"></i>
                                            </Button>
                                        </td>
                                    </tr>

                                    {communityData.map((row) => (
                                        <tr key={row.id} className="hover:bg-gray-50">
                                            <td className="px-3 py-2">
                                                <UncontrolledCell
                                                    type="date"
                                                    defaultValue={row.date}
                                                    onBlur={(val) => handleUpdateRow(row.id, 'date', val)}
                                                />
                                            </td>
                                            <td className="px-3 py-2">
                                                <select
                                                    value={row.communities_served || ''}
                                                    onChange={(e) => handleUpdateRow(row.id, 'communities_served', e.target.value)}
                                                className="w-full px-1 py-1 text-xs border border-gray-300 focus:outline-none focus:ring-1 focus:ring-blue-500 focus:border-transparent"
                                                >
                                                    <option value="">Select Community</option>
                                                    {communities.map((community) => (
                                                        <option key={community.id} value={community.name}>
                                                            {community.name}
                                                        </option>
                                                    ))}
                                                </select>
                                            </td>
                                            <td className="px-3 py-2">
                                                <UncontrolledCell
                                                    type="number"
                                                    defaultValue={row.families_helped || 0}
                                                    onBlur={(val) => handleUpdateRow(row.id, 'families_helped', val)}
                                                className="w-full px-1 py-1 text-xs border border-gray-300 focus:outline-none focus:ring-1 focus:ring-[#2CABE3] focus:border-transparent"
                                                />
                                            </td>
                                            <td className="px-3 py-2">
                                                <UncontrolledCell
                                                    type="number"
                                                    defaultValue={row.school_staff_helped || 0}
                                                    onBlur={(val) => handleUpdateRow(row.id, 'school_staff_helped', val)}
                                                className="w-full px-1 py-1 text-xs border border-gray-300 focus:outline-none focus:ring-1 focus:ring-[#2CABE3] focus:border-transparent"
                                                />
                                            </td>
                                            <td className="px-3 py-2">
                                                <UncontrolledCell
                                                    type="number"
                                                    defaultValue={row.food_given_lb || 0}
                                                    onBlur={(val) => handleUpdateRow(row.id, 'food_given_lb', val)}
                                                className="w-full px-1 py-1 text-xs border border-gray-300 focus:outline-none focus:ring-1 focus:ring-[#2CABE3] focus:border-transparent"
                                                />
                                            </td>
                                            <td className="px-3 py-2">
                                                <UncontrolledCell
                                                    defaultValue={row.notes || ''}
                                                    onBlur={(val) => handleUpdateRow(row.id, 'notes', val)}
                                                />
                                            </td>
                                            <td className="px-3 py-2">
                                                <Button
                                                    variant="danger"
                                                    size="sm"
                                                    onClick={() => handleDeleteRow(row.id)}
                                                >
                                                    <i className="fas fa-trash"></i>
                                                </Button>
                                            </td>
                                        </tr>
                                    ))}

                                    {communityData.length === 0 && (
                                        <tr>
                                            <td colSpan="9" className="px-6 py-8 text-center text-gray-500">
                                                No community entries yet. Add your first entry using the row above.
                                            </td>
                                        </tr>
                                    )}
                                </tbody>
                            </table>
                        </div>
                    </div>
                )}

                <div className="mt-6 bg-blue-50 border border-blue-200 rounded-lg p-4">
                    <h3 className="text-sm font-semibold text-blue-900 mb-2">
                        <i className="fas fa-info-circle mr-2"></i>
                        How to use this system
                    </h3>
                    <ul className="text-sm text-blue-800 space-y-1">
                        <li>• <strong>Organization Impact:</strong> Track food donations, food saved from waste, and meals provided by organizations</li>
                        <li>• <strong>Communities Served:</strong> Track families helped, schools served, and community impact metrics</li>
                        <li>• Switch between tabs to view and manage different types of impact data</li>
                        <li>• Fill in the colored row at the top to add a new entry, then click the + button</li>
                        <li>• Click on any cell to edit existing data - changes save automatically</li>
                        <li>• Use the trash icon to delete entries</li>
                        <li>• Export to CSV for backup or analysis</li>
                    </ul>
                </div>
            </div>
        </AdminLayout>
    );
}

export default ImpactDataEntry;
