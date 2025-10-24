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
        fetchImpact();

        const subscription = impactService.subscribeToImpactUpdates(() => {
            fetchImpact();
        });

        return () => {
            impactService.unsubscribeFromImpactUpdates(subscription);
        };
    }, []);

    const fetchImpact = async () => {
        try {
            setLoading(true);
            const data = await impactService.getAggregatedImpact();
            setImpact(data);
            setError(null);
        } catch (err) {
            console.error('Error fetching impact data:', err);
            setError(err.message);
        } finally {
            setLoading(false);
        }
    };

    return { impact, loading, error, refetch: fetchImpact };
}
