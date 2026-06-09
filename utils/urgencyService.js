/**
 * Urgency Service
 * Calculates urgency levels and countdown timers for food listings based on expiration/pickup deadlines
 */

export const URGENCY_LEVELS = {
  CRITICAL: 'critical', // < 6 hours
  HIGH: 'high',         // < 24 hours
  MEDIUM: 'medium',     // < 72 hours (3 days)
  NORMAL: 'normal',     // > 72 hours
  NONE: 'none'          // No deadline or expired
};

export const URGENCY_CONFIG = {
  critical: {
    label: 'Critical - Expires Soon!',
    icon: '🚨',
    color: 'red',
    bgClass: 'bg-red-100',
    textClass: 'text-red-800',
    borderClass: 'border-red-300',
    badgeClass: 'bg-red-500 text-white',
    threshold: 6 * 60 * 60 // 6 hours in seconds
  },
  high: {
    label: 'High Priority - Expires Today',
    icon: '⚠️',
    color: 'orange',
    bgClass: 'bg-orange-100',
    textClass: 'text-orange-800',
    borderClass: 'border-orange-300',
    badgeClass: 'bg-orange-500 text-white',
    threshold: 24 * 60 * 60 // 24 hours
  },
  medium: {
    label: 'Moderate - Expires Soon',
    icon: '⏰',
    color: 'yellow',
    bgClass: 'bg-yellow-100',
    textClass: 'text-yellow-800',
    borderClass: 'border-yellow-300',
    badgeClass: 'bg-yellow-500 text-white',
    threshold: 72 * 60 * 60 // 72 hours (3 days)
  },
  normal: {
    label: 'Available',
    icon: '✓',
    color: 'green',
    bgClass: 'bg-primary-50',
    textClass: 'text-primary-700',
    borderClass: 'border-primary-200',
    badgeClass: 'bg-primary-500 text-white',
    threshold: Infinity
  },
  none: {
    label: 'No Deadline',
    icon: '−',
    color: 'gray',
    bgClass: 'bg-gray-50',
    textClass: 'text-gray-600',
    borderClass: 'border-gray-200',
    badgeClass: 'bg-gray-400 text-white',
    threshold: 0
  }
};

class UrgencyService {
  /**
   * Calculate urgency level based on pickup deadline or expiry date
   * @param {Object} foodListing - Food listing object
   * @returns {string} Urgency level (critical, high, medium, normal, none)
   */
  static calculateUrgencyLevel(foodListing) {
    if (!foodListing) return URGENCY_LEVELS.NONE;

    const deadline = this.getDeadline(foodListing);
    if (!deadline) return URGENCY_LEVELS.NONE;

    const secondsRemaining = this.getSecondsRemaining(deadline);
    
    if (secondsRemaining <= 0) {
      return URGENCY_LEVELS.NONE; // Expired
    } else if (secondsRemaining <= URGENCY_CONFIG.critical.threshold) {
      return URGENCY_LEVELS.CRITICAL;
    } else if (secondsRemaining <= URGENCY_CONFIG.high.threshold) {
      return URGENCY_LEVELS.HIGH;
    } else if (secondsRemaining <= URGENCY_CONFIG.medium.threshold) {
      return URGENCY_LEVELS.MEDIUM;
    } else {
      return URGENCY_LEVELS.NORMAL;
    }
  }

  /**
   * Get the deadline from food listing (pickup_by takes precedence over expiry_date)
   * @param {Object} foodListing - Food listing object
   * @returns {Date|null} Deadline date
   */
  static getDeadline(foodListing) {
    if (foodListing.pickup_by) {
      return new Date(foodListing.pickup_by);
    } else if (foodListing.expiry_date) {
      // Parse as LOCAL midnight so that setHours(23,59,59,999) lands at
      // end-of-day in the user's timezone. Without the 'T00:00:00' suffix,
      // new Date('YYYY-MM-DD') is treated as UTC midnight, making setHours
      // operate on the previous local day in Pacific time (off by 24 hours).
      const expiryDate = new Date(foodListing.expiry_date + 'T00:00:00');
      expiryDate.setHours(23, 59, 59, 999);
      return expiryDate;
    }
    return null;
  }

  /**
   * Calculate seconds remaining until deadline
   * @param {Date} deadline - Deadline date
   * @returns {number} Seconds remaining
   */
  static getSecondsRemaining(deadline) {
    if (!deadline) return 0;
    return Math.floor((deadline.getTime() - Date.now()) / 1000);
  }

  /**
   * Format countdown time in human-readable format
   * @param {number} seconds - Seconds remaining
   * @returns {Object} Formatted time with units
   */
  static formatCountdown(seconds) {
    if (seconds <= 0) {
      return { expired: true, text: 'Expired', value: 0, unit: '' };
    }

    const hours = Math.floor(seconds / 3600);
    const minutes = Math.floor((seconds % 3600) / 60);
    const days = Math.floor(hours / 24);

    if (days > 0) {
      const remainingHours = hours % 24;
      return {
        expired: false,
        text: remainingHours > 0 
          ? `${days}d ${remainingHours}h remaining` 
          : `${days} day${days > 1 ? 's' : ''} remaining`,
        value: days,
        unit: 'days',
        detailed: { days, hours: remainingHours, minutes }
      };
    } else if (hours > 0) {
      return {
        expired: false,
        text: minutes > 0 
          ? `${hours}h ${minutes}m remaining` 
          : `${hours} hour${hours > 1 ? 's' : ''} remaining`,
        value: hours,
        unit: 'hours',
        detailed: { hours, minutes }
      };
    } else {
      return {
        expired: false,
        text: `${minutes} minute${minutes !== 1 ? 's' : ''} remaining`,
        value: minutes,
        unit: 'minutes',
        detailed: { minutes }
      };
    }
  }

  /**
   * Get complete urgency information for a food listing
   * @param {Object} foodListing - Food listing object
   * @returns {Object} Complete urgency information
   */
  static getUrgencyInfo(foodListing) {
    const deadline = this.getDeadline(foodListing);
    const secondsRemaining = deadline ? this.getSecondsRemaining(deadline) : 0;
    const urgencyLevel = this.calculateUrgencyLevel(foodListing);
    const countdown = this.formatCountdown(secondsRemaining);
    const config = URGENCY_CONFIG[urgencyLevel];

    return {
      urgencyLevel,
      deadline,
      secondsRemaining,
      countdown,
      config,
      isExpired: countdown.expired,
      isUrgent: urgencyLevel === URGENCY_LEVELS.CRITICAL || urgencyLevel === URGENCY_LEVELS.HIGH,
      shouldShowCountdown: urgencyLevel !== URGENCY_LEVELS.NONE && !countdown.expired
    };
  }

  /**
   * Sort food listings by urgency (most urgent first)
   * @param {Array} listings - Array of food listings
   * @returns {Array} Sorted listings
   */
  static sortByUrgency(listings) {
    if (!listings || !Array.isArray(listings)) return [];

    const urgencyOrder = {
      [URGENCY_LEVELS.CRITICAL]: 0,
      [URGENCY_LEVELS.HIGH]: 1,
      [URGENCY_LEVELS.MEDIUM]: 2,
      [URGENCY_LEVELS.NORMAL]: 3,
      [URGENCY_LEVELS.NONE]: 4
    };

    return [...listings].sort((a, b) => {
      const urgencyA = this.calculateUrgencyLevel(a);
      const urgencyB = this.calculateUrgencyLevel(b);
      
      const orderA = urgencyOrder[urgencyA];
      const orderB = urgencyOrder[urgencyB];

      if (orderA !== orderB) {
        return orderA - orderB;
      }

      // If same urgency, sort by time remaining
      const deadlineA = this.getDeadline(a);
      const deadlineB = this.getDeadline(b);
      
      if (!deadlineA && !deadlineB) return 0;
      if (!deadlineA) return 1;
      if (!deadlineB) return -1;
      
      return deadlineA.getTime() - deadlineB.getTime();
    });
  }

  /**
   * Filter out expired listings
   * @param {Array} listings - Array of food listings
   * @returns {Array} Active listings
   */
  static filterExpired(listings) {
    if (!listings || !Array.isArray(listings)) return [];
    
    return listings.filter(listing => {
      const urgencyInfo = this.getUrgencyInfo(listing);
      return !urgencyInfo.isExpired;
    });
  }

  /**
   * Get only urgent listings (critical or high priority)
   * @param {Array} listings - Array of food listings
   * @returns {Array} Urgent listings
   */
  static getUrgentListings(listings) {
    if (!listings || !Array.isArray(listings)) return [];
    
    return listings.filter(listing => {
      const urgencyLevel = this.calculateUrgencyLevel(listing);
      return urgencyLevel === URGENCY_LEVELS.CRITICAL || urgencyLevel === URGENCY_LEVELS.HIGH;
    });
  }
}

export default UrgencyService;
