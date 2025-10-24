import { useState, useEffect } from 'react';
import impactService from '../impactService';

export function useImpact() {
    const [impact, setImpact] = useState({
        totalMeals: 0,
        foodSavedKg: 0,
        peopleHelped: 0,
        wasteReduced: 0,
        co2Saved: 0,
        volunteerHours: 0,
        partnerOrganizations: 0
    });
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState(null);

    useEffect(() => {
        console.log('[useImpact] Hook initialized, fetching initial data...');
        fetchImpact();

        const channel = impactService.subscribeToImpactUpdates((payload) => {
            console.log('[useImpact] 🔄 Real-time update triggered, refetching...', payload);
            fetchImpact();
        });

        return () => {
            console.log('[useImpact] Cleaning up subscription...');
            impactService.unsubscribeFromImpactUpdates(channel);
        };
    }, []);

    const fetchImpact = async () => {
        try {
            console.log('[useImpact] Fetching impact data...');
            setLoading(true);
            const data = await impactService.getAggregatedImpact();
            console.log('[useImpact] ✅ Impact data updated:', data);
            setImpact(data);
            setError(null);
        } catch (err) {
            console.error('[useImpact] ❌ Error fetching impact data:', err);
            setError(err.message);
        } finally {
            setLoading(false);
        }
    };

    return { impact, loading, error, refetch: fetchImpact };
}
