import supabase from './supabaseClient';

class ImpactService {
    async getAggregatedImpact() {
        try {
            const { data, error } = await supabase
                .from('impact_data')
                .select('*');

            if (error) throw error;

            if (!data || data.length === 0) {
                return {
                    totalMeals: 0,
                    foodSavedKg: 0,
                    peopleHelped: 0,
                    wasteReduced: 0,
                    co2Saved: 0,
                    volunteerHours: 0,
                    partnerOrganizations: 0
                };
            }

            const aggregated = data.reduce((acc, entry) => ({
                totalMeals: acc.totalMeals + (parseFloat(entry.meals_provided) || 0),
                foodSavedKg: acc.foodSavedKg + (parseFloat(entry.food_saved_kg) || 0),
                peopleHelped: acc.peopleHelped + (parseInt(entry.people_helped) || 0),
                wasteReduced: acc.wasteReduced + (parseFloat(entry.waste_diverted_kg) || 0),
                co2Saved: acc.co2Saved + (parseFloat(entry.co2_reduced_kg) || 0),
                volunteerHours: acc.volunteerHours + (parseFloat(entry.volunteer_hours) || 0),
                partnerOrganizations: Math.max(acc.partnerOrganizations, parseInt(entry.partner_organizations) || 0)
            }), {
                totalMeals: 0,
                foodSavedKg: 0,
                peopleHelped: 0,
                wasteReduced: 0,
                co2Saved: 0,
                volunteerHours: 0,
                partnerOrganizations: 0
            });

            return aggregated;
        } catch (error) {
            console.error('Error fetching aggregated impact:', error);
            return {
                totalMeals: 0,
                foodSavedKg: 0,
                peopleHelped: 0,
                wasteReduced: 0,
                co2Saved: 0,
                volunteerHours: 0,
                partnerOrganizations: 0
            };
        }
    }

    async getImpactByDateRange(startDate, endDate) {
        try {
            const { data, error } = await supabase
                .from('impact_data')
                .select('*')
                .gte('date', startDate)
                .lte('date', endDate)
                .order('date', { ascending: true });

            if (error) throw error;
            return data || [];
        } catch (error) {
            console.error('Error fetching impact by date range:', error);
            return [];
        }
    }

    subscribeToImpactUpdates(callback) {
        const subscription = supabase
            .channel('impact-updates')
            .on(
                'postgres_changes',
                {
                    event: '*',
                    schema: 'public',
                    table: 'impact_data'
                },
                (payload) => {
                    console.log('Impact data changed:', payload);
                    callback(payload);
                }
            )
            .subscribe();

        return subscription;
    }

    unsubscribeFromImpactUpdates(subscription) {
        if (subscription) {
            supabase.removeChannel(subscription);
        }
    }
}

export default new ImpactService();
