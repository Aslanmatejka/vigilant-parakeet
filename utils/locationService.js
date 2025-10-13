const DEFAULT_RADIUS = 10; // Default radius in kilometers

class LocationService {
    constructor() {
        this.currentPosition = null;
        this.watchId = null;
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
                    timeout: 5000,
                    maximumAge: 0
                }
            );
        });
    }

    startWatchingPosition(callback) {
        if (this.watchId) return;

        this.watchId = navigator.geolocation.watchPosition(
            (position) => {
                this.currentPosition = {
                    latitude: position.coords.latitude,
                    longitude: position.coords.longitude
                };
                callback(this.currentPosition);
            },
            (error) => {
                console.error('Error watching location:', error);
            },
            {
                enableHighAccuracy: true,
                timeout: 5000,
                maximumAge: 0
            }
        );
    }

    stopWatchingPosition() {
        if (this.watchId) {
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
