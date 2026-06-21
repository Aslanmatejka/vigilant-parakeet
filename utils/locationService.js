const DEFAULT_RADIUS = 10; // Default radius in kilometers

class LocationService {
    constructor() {
        this.currentPosition = null;
        this.watchId = null;
        // Fan-out set: every consumer that called startWatchingPosition gets
        // its callback invoked on each browser position event. Without this,
        // the second simultaneous consumer of useGeoLocation was silently
        // dropped because the singleton watchId early-returned and never
        // registered the new callback.
        this.watchCallbacks = new Set();
    }

    async requestLocationPermission() {
        try {
            if (!navigator.geolocation) {
                throw new Error('Geolocation is not supported by your browser');
            }
            
            const permission = await navigator.permissions.query({ name: 'geolocation' });
            return permission.state;
        } catch (error) {
            console.error('Error requesting location permission:', error);
            throw error;
        }
    }

    async getCurrentPosition() {
        return new Promise((resolve, reject) => {
            navigator.geolocation.getCurrentPosition(
                (position) => {
                    this.currentPosition = {
                        latitude: position.coords.latitude,
                        longitude: position.coords.longitude
                    };
                    resolve(this.currentPosition);
                },
                (error) => {
                    console.error('Error getting location:', error);
                    reject(error);
                },
                {
                    enableHighAccuracy: true,
                    timeout: 15000,
                    maximumAge: 60000
                }
            );
        });
    }

    startWatchingPosition(callback) {
        if (typeof callback !== 'function') return;
        this.watchCallbacks.add(callback);
        // Replay the last known position so a freshly-mounted consumer
        // doesn't have to wait for the next GPS update before rendering.
        if (this.currentPosition) {
            try { callback(this.currentPosition); } catch (_) { /* swallow */ }
        }
        if (this.watchId !== null) return; // Already watching; new callback joins fan-out.

        this.watchId = navigator.geolocation.watchPosition(
            (position) => {
                this.currentPosition = {
                    latitude: position.coords.latitude,
                    longitude: position.coords.longitude
                };
                // Snapshot the Set so a callback that unsubscribes itself
                // mid-iteration doesn't mutate what we're iterating over.
                for (const cb of [...this.watchCallbacks]) {
                    try { cb(this.currentPosition); } catch (_) { /* one bad consumer shouldn't break others */ }
                }
            },
            (error) => {
                console.error('Error watching location:', error);
            },
            {
                enableHighAccuracy: true,
                timeout: 15000,
                maximumAge: 60000
            }
        );
    }

    stopWatchingPosition(callback) {
        if (callback) {
            this.watchCallbacks.delete(callback);
        } else {
            // Legacy no-arg form: clear everything. Keeps the previous
            // behavior of stop-meaning-stop-all so any caller that hasn't
            // been migrated yet still works.
            this.watchCallbacks.clear();
        }
        // Only release the underlying browser watch when no consumer is
        // still listening \u2014 otherwise a component unmount used to clear
        // the watch out from under the other consumers still on screen.
        if (this.watchCallbacks.size === 0 && this.watchId !== null) {
            navigator.geolocation.clearWatch(this.watchId);
            this.watchId = null;
        }
    }

    calculateDistance(lat1, lon1, lat2, lon2) {
        const R = 6371; // Earth's radius in kilometers
        const dLat = this.toRad(lat2 - lat1);
        const dLon = this.toRad(lon2 - lon1);
        const a = 
            Math.sin(dLat/2) * Math.sin(dLat/2) +
            Math.cos(this.toRad(lat1)) * Math.cos(this.toRad(lat2)) * 
            Math.sin(dLon/2) * Math.sin(dLon/2);
        const c = 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1-a));
        return R * c;
    }

    toRad(degrees) {
        return degrees * (Math.PI/180);
    }

    isWithinRadius(userLocation, itemLocation, radius = DEFAULT_RADIUS) {
        const distance = this.calculateDistance(
            userLocation.latitude,
            userLocation.longitude,
            itemLocation.latitude,
            itemLocation.longitude
        );
        return distance <= radius;
    }
}

export const locationService = new LocationService();
