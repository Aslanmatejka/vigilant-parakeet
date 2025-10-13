// Date formatting
export function formatDate(date) {
    try {
        return new Date(date).toLocaleDateString('en-US', {
            year: 'numeric',
            month: 'long',
            day: 'numeric'
        });
    } catch (error) {
        console.error('Date formatting error:', error);
        return date;
    }
}

// Time ago formatter
export function timeAgo(date) {
    try {
        const seconds = Math.floor((new Date() - new Date(date)) / 1000);
        const intervals = {
            year: 31536000,
            month: 2592000,
            week: 604800,
            day: 86400,
            hour: 3600,
            minute: 60,
            second: 1
        };

        for (const [unit, secondsInUnit] of Object.entries(intervals)) {
            const interval = Math.floor(seconds / secondsInUnit);
            if (interval >= 1) {
                return `${interval} ${unit}${interval === 1 ? '' : 's'} ago`;
            }
        }
        return 'just now';
    } catch (error) {
        console.error('Time ago formatting error:', error);
        return 'unknown time ago';
    }
}

// File size formatter
export function formatFileSize(bytes) {
    try {
        if (bytes === 0) return '0 Bytes';
        const k = 1024;
        const sizes = ['Bytes', 'KB', 'MB', 'GB'];
        const i = Math.floor(Math.log(bytes) / Math.log(k));
        return `${parseFloat((bytes / Math.pow(k, i)).toFixed(2))} ${sizes[i]}`;
    } catch (error) {
        console.error('File size formatting error:', error);
        return 'unknown size';
    }
}

// Input validation
export function validateEmail(email) {
    try {
        const re = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
        return re.test(email);
    } catch (error) {
        console.error('Email validation error:', error);
        return false;
    }
}

export function validatePhone(phone) {
    try {
        const re = /^\+?[\d\s-]{10,}$/;
        return re.test(phone);
    } catch (error) {
        console.error('Phone validation error:', error);
        return false;
    }
}

// Location distance calculator
export function calculateDistance(lat1, lon1, lat2, lon2) {
    try {
        const R = 6371; // Earth's radius in km
        const dLat = (lat2 - lat1) * Math.PI / 180;
        const dLon = (lon2 - lon1) * Math.PI / 180;
        const a = Math.sin(dLat/2) * Math.sin(dLat/2) +
                 Math.cos(lat1 * Math.PI / 180) * Math.cos(lat2 * Math.PI / 180) *
                 Math.sin(dLon/2) * Math.sin(dLon/2);
        const c = 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1-a));
        const distance = R * c;
        return distance.toFixed(1);
    } catch (error) {
        console.error('Distance calculation error:', error);
        return null;
    }
}

// Food expiration status
export function getExpirationStatus(expiryDate) {
    try {
        const now = new Date();
        const expiry = new Date(expiryDate);
        const daysUntilExpiry = Math.ceil((expiry - now) / (1000 * 60 * 60 * 24));

        if (daysUntilExpiry < 0) {
            return { status: 'Expired', days: Math.abs(daysUntilExpiry), color: 'red' };
        } else if (daysUntilExpiry <= 3) {
            return { status: 'Expires soon', days: daysUntilExpiry, color: 'yellow' };
        } else {
            return { status: 'Fresh', days: daysUntilExpiry, color: 'green' };
        }
    } catch (error) {
        console.error('Expiration status error:', error);
        return { status: 'Unknown', days: 0, color: 'gray' };
    }
}

// Error reporting
export function reportError(error, info = {}) {
    // In a real app, you would send this to a service like Sentry, LogRocket, etc.
    console.error("Caught an error:", error, info);
}

// Safe file download
export function safeDownload(blob, filename) {
    try {
        const url = window.URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.style.display = 'none';
        a.href = url;
        a.download = filename;
        document.body.appendChild(a);
a.click();
        window.URL.revokeObjectURL(url);
        document.body.removeChild(a);
    } catch (error) {
        console.error('Download error:', error);
        reportError(error);
    }
}
