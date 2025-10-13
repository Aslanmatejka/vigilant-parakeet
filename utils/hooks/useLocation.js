import { useState, useEffect } from 'react';
import { locationService } from '../locationService';

export function useGeoLocation() {
    const [location, setLocation] = useState(null);
    const [loading, setLoading] = useState(false);
    const [error, setError] = useState(null);
    const [watching, setWatching] = useState(false);

    useEffect(() => {
        // Check if we have permission when the hook is first used
        checkPermission();
        
        // Cleanup any watching when component unmounts
        return () => {
            if (watching) {
                locationService.stopWatchingPosition();
                setWatching(false);
            }
        };
    }, []);

    const checkPermission = async () => {
        try {
            const permissionStatus = await locationService.requestLocationPermission();
            if (permissionStatus === 'granted') {
                // If we already have permission, get the location
                getCurrentPosition();
            }
        } catch (err) {
            setError('Location permission check failed');
        }
    };

    const getCurrentPosition = async () => {
        setLoading(true);
        setError(null);
        
        try {
            const position = await locationService.getCurrentPosition();
            setLocation(position);
            startWatching(); // Start watching for location updates
        } catch (err) {
            setError('Unable to get your location. Please ensure location services are enabled.');
        } finally {
            setLoading(false);
        }
    };

    const startWatching = () => {
        if (!watching) {
            locationService.startWatchingPosition((position) => {
                setLocation(position);
            });
            setWatching(true);
        }
    };

    const enableLocation = async () => {
        try {
            const permissionStatus = await locationService.requestLocationPermission();
            if (permissionStatus === 'granted') {
                getCurrentPosition();
            } else {
                setError('Location permission denied. Please enable location services in your browser settings.');
            }
        } catch (err) {
            setError('Failed to enable location services');
        }
    };

    return {
        location,
        loading,
        error,
        enableLocation,
        refreshLocation: getCurrentPosition
    };
}
