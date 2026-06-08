import React, { useState, useEffect } from 'react';
import PropTypes from 'prop-types';
import UrgencyService from '../../utils/urgencyService';

/**
 * UrgencyBadge Component
 * Displays urgency level and countdown timer for food listings with expiration deadlines
 * Updates in real-time to show accurate time remaining
 */
function UrgencyBadge({ foodListing, showCountdown = true, compact = false }) {
  const [urgencyInfo, setUrgencyInfo] = useState(null);

  useEffect(() => {
    // Initial calculation
    const updateUrgency = () => {
      const info = UrgencyService.getUrgencyInfo(foodListing);
      setUrgencyInfo(info);
    };

    updateUrgency();

    // Update every minute for accurate countdown
    const interval = setInterval(updateUrgency, 60000);

    return () => clearInterval(interval);
  }, [foodListing]);

  if (!urgencyInfo || urgencyInfo.urgencyLevel === 'none') {
    return null;
  }

  const { config, countdown, isExpired, shouldShowCountdown, urgencyLevel } = urgencyInfo;

  // Don't show if expired
  if (isExpired) {
    return null;
  }

  // Compact version (just icon and level)
  if (compact) {
    return (
      <div className={`inline-flex items-center gap-1 px-2 py-1 rounded-full text-xs font-medium ${config.badgeClass}`}>
        <span>{config.icon}</span>
        <span className="capitalize">{urgencyLevel}</span>
      </div>
    );
  }

  // Full version with countdown
  return (
    <div className={`rounded-lg border-2 p-3 ${config.bgClass} ${config.borderClass}`}>
      <div className="flex items-start justify-between gap-3">
        {/* Urgency indicator */}
        <div className="flex items-center gap-2">
          <span className="text-2xl" aria-label={config.label}>{config.icon}</span>
          <div>
            <div className={`font-semibold text-sm ${config.textClass}`}>
              {config.label}
            </div>
            {shouldShowCountdown && showCountdown && (
              <div className={`text-xs mt-0.5 ${config.textClass}`}>
                {countdown.text}
              </div>
            )}
          </div>
        </div>

        {/* Countdown badge */}
        {shouldShowCountdown && showCountdown && (
          <div className={`px-3 py-1 rounded-full ${config.badgeClass} font-bold text-sm whitespace-nowrap`}>
            {countdown.value > 0 && (
              <>
                {countdown.value}
                <span className="text-xs ml-0.5">
                  {countdown.unit === 'days' ? 'd' : countdown.unit === 'hours' ? 'h' : 'm'}
                </span>
              </>
            )}
          </div>
        )}
      </div>

      {/* Additional details for critical items */}
      {urgencyLevel === 'critical' && (
        <div className={`mt-2 text-xs ${config.textClass} font-medium`}>
          <i className="fas fa-exclamation-triangle mr-1" aria-hidden="true"></i>
          Act fast! This item expires very soon.
        </div>
      )}
    </div>
  );
}

UrgencyBadge.propTypes = {
  foodListing: PropTypes.shape({
    pickup_by: PropTypes.string,
    expiry_date: PropTypes.string,
    urgency_level: PropTypes.string
  }).isRequired,
  showCountdown: PropTypes.bool,
  compact: PropTypes.bool
};

/**
 * UrgencyIndicator Component
 * Minimal inline indicator for use in food cards/lists
 */
export function UrgencyIndicator({ foodListing }) {
  const urgencyInfo = UrgencyService.getUrgencyInfo(foodListing);

  if (!urgencyInfo || urgencyInfo.urgencyLevel === 'none' || urgencyInfo.isExpired) {
    return null;
  }

  const { config, countdown, urgencyLevel } = urgencyInfo;

  // Only show for urgent items in compact view
  if (urgencyLevel !== 'critical' && urgencyLevel !== 'high') {
    return null;
  }

  return (
    <div className={`inline-flex items-center gap-1.5 px-2 py-1 rounded-full text-xs font-semibold ${config.badgeClass}`}>
      <span>{config.icon}</span>
      <span>{countdown.text}</span>
    </div>
  );
}

UrgencyIndicator.propTypes = {
  foodListing: PropTypes.shape({
    pickup_by: PropTypes.string,
    expiry_date: PropTypes.string,
    urgency_level: PropTypes.string
  }).isRequired
};

/**
 * CountdownTimer Component
 * Real-time countdown display that updates every second (for critical items)
 */
export function CountdownTimer({ deadline }) {
  const [timeRemaining, setTimeRemaining] = useState('');
  const [isUrgent, setIsUrgent] = useState(false);

  useEffect(() => {
    if (!deadline) return;

    const updateTimer = () => {
      const deadlineDate = new Date(deadline);
      const seconds = UrgencyService.getSecondsRemaining(deadlineDate);
      const countdown = UrgencyService.formatCountdown(seconds);
      
      setTimeRemaining(countdown.text);
      setIsUrgent(seconds <= 6 * 60 * 60); // Less than 6 hours
    };

    updateTimer();

    // Update every second for critical items, every minute for others
    const interval = setInterval(updateTimer, isUrgent ? 1000 : 60000);

    return () => clearInterval(interval);
  }, [deadline, isUrgent]);

  if (!timeRemaining) return null;

  return (
    <div className={`inline-flex items-center gap-1 ${isUrgent ? 'text-red-600 font-bold animate-pulse' : 'text-gray-600'}`}>
      <i className="fas fa-clock text-xs" aria-hidden="true"></i>
      <span className="text-sm">{timeRemaining}</span>
    </div>
  );
}

CountdownTimer.propTypes = {
  deadline: PropTypes.string.isRequired
};

/**
 * ExpiryCountdown Component
 * Live color-coded countdown pill shown on every food card that has an expiry
 * or pickup deadline. Updates every minute (every second when < 1 hour left).
 */
export function ExpiryCountdown({ foodListing }) {
  const [display, setDisplay] = useState(null);
  const intervalRef = React.useRef(null);

  useEffect(() => {
    if (!foodListing) return;
    const deadline = UrgencyService.getDeadline(foodListing);
    if (!deadline) return;

    const tick = () => {
      const seconds = UrgencyService.getSecondsRemaining(deadline);
      if (seconds <= 0) {
        setDisplay(null);
        return;
      }

      const totalHours = Math.floor(seconds / 3600);
      const minutes = Math.floor((seconds % 3600) / 60);
      const days = Math.floor(totalHours / 24);
      const remHours = totalHours % 24;

      let text;
      if (days > 0) {
        text = remHours > 0 ? `${days}d ${remHours}h left` : `${days}d left`;
      } else if (totalHours > 0) {
        text = `${totalHours}h ${minutes}m left`;
      } else {
        text = `${minutes}m left`;
      }

      const urgency = seconds <= 6 * 3600  ? 'critical'
                    : seconds <= 24 * 3600 ? 'high'
                    : seconds <= 72 * 3600 ? 'medium'
                    : 'normal';

      setDisplay({ text, urgency });

      // Reschedule at appropriate frequency
      clearInterval(intervalRef.current);
      intervalRef.current = setInterval(tick, seconds < 3600 ? 1000 : 60000);
    };

    tick();
    return () => clearInterval(intervalRef.current);
  }, [foodListing]);

  if (!display) return null;

  const colorMap = {
    critical: 'bg-red-50 text-red-700 border-red-300',
    high:     'bg-orange-50 text-orange-700 border-orange-200',
    medium:   'bg-yellow-50 text-yellow-700 border-yellow-200',
    normal:   'bg-green-50 text-green-700 border-green-200',
  };

  return (
    <span
      className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-full border text-[10px] sm:text-xs font-semibold ${colorMap[display.urgency]} ${display.urgency === 'critical' ? 'animate-pulse' : ''}`}
      aria-label={`Expires in ${display.text}`}
    >
      <i className="fas fa-hourglass-half text-[9px] sm:text-[10px]" aria-hidden="true" />
      {display.text}
    </span>
  );
}

ExpiryCountdown.propTypes = {
  foodListing: PropTypes.shape({
    pickup_by: PropTypes.string,
    expiry_date: PropTypes.string,
  }).isRequired,
};

export default UrgencyBadge;
