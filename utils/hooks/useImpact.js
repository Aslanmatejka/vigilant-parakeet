import { useState, useEffect, useRef, useCallback } from 'react';
import impactService from '../impactService';

export function useImpact() {
    const [impact, setImpact] = useState({
        totalMealsProvided: 0,
        foodSavedFromWaste: 0,
        foodProvided: 0,
        peopleHelped: 0,
        schoolsServed: 0,
        nonprofitsHelped: 0,
        wasteReduced: 0,
        co2Saved: 0,
        volunteerHours: 0
    });
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState(null);
    // Don't flip `loading` back on for background realtime refreshes \u2014 the
    // home/Success page would otherwise flash a spinner every time an
    // admin edits an impact row.
    const hasLoadedRef = useRef(false);
    const refetchTimerRef = useRef(null);

    const fetchImpact = useCallback(async () => {
        try {
            if (!hasLoadedRef.current) setLoading(true);
            const data = await impactService.getAggregatedImpact();
            setImpact(data);
            setError(null);
            hasLoadedRef.current = true;
        } catch (err) {
            console.error('[useImpact] Error fetching impact data:', err);
            setError(err.message);
        } finally {
            setLoading(false);
        }
    }, []);

    useEffect(() => {
        fetchImpact();

        // Debounce realtime refetches so a bulk-import burst (e.g. 100 rows
        // changing in 200ms) collapses into a single round-trip instead of
        // 100 parallel fetches that all overwrite each other.
        const scheduleRefetch = () => {
            clearTimeout(refetchTimerRef.current);
            refetchTimerRef.current = setTimeout(() => { fetchImpact(); }, 400);
        };

        const channel = impactService.subscribeToImpactUpdates(scheduleRefetch);

        return () => {
            clearTimeout(refetchTimerRef.current);
            impactService.unsubscribeFromImpactUpdates(channel);
        };
    }, [fetchImpact]);

    return { impact, loading, error, refetch: fetchImpact };
}
