import React from 'react';
import PropTypes from 'prop-types';

// Single brand color for all community building pins (map + cards).
export const COMMUNITY_PIN_COLOR = '#2563eb';

export function colorForCommunity(_id = null) {
    return COMMUNITY_PIN_COLOR;
}

export function getCommunityPinDimensions(count = 0) {
    const countStr = count > 0 ? String(count) : '';
    const dotR = 13;
    const badgeR = countStr.length >= 3 ? 11 : 9;
    const pad = badgeR + 2;
    const size = dotR * 2 + pad * 2;
    return { width: size, height: size };
}

/** SVG markup for Mapbox DOM markers (innerHTML). */
export function renderCommunityPinSvg({ communityId = null, count = 0, color = null } = {}) {
    const pinColor = color || colorForCommunity(communityId);
    const countStr = count > 0 ? String(count) : '';
    const dotR = 13;
    const badgeR = countStr.length >= 3 ? 11 : 9;
    const pad = badgeR + 2;
    const { width: svgW, height: svgH } = getCommunityPinDimensions(count);
    const dotCx = svgW / 2;
    const dotCy = svgH / 2;
    const badgeCx = dotCx + dotR - 2;
    const badgeCy = dotCy - dotR + 2;

    return `
        <svg xmlns="http://www.w3.org/2000/svg" width="${svgW}" height="${svgH}" viewBox="0 0 ${svgW} ${svgH}" style="display:block;overflow:visible;filter:drop-shadow(0 2px 3px rgba(0,0,0,0.3));">
            <rect x="${dotCx - 9}" y="${dotCy - 2}" width="18" height="14" rx="2"
                  fill="${pinColor}" stroke="#ffffff" stroke-width="2" />
            <rect x="${dotCx - 6}" y="${dotCy + 1}" width="4" height="4" rx="0.5" fill="#ffffff" opacity="0.9" />
            <rect x="${dotCx + 2}" y="${dotCy + 1}" width="4" height="4" rx="0.5" fill="#ffffff" opacity="0.9" />
            <polygon points="${dotCx - 11},${dotCy - 2} ${dotCx},${dotCy - 11} ${dotCx + 11},${dotCy - 2}"
                     fill="${pinColor}" stroke="#ffffff" stroke-width="2" stroke-linejoin="round" />
            ${count > 0 ? `
                <circle cx="${badgeCx}" cy="${badgeCy}" r="${badgeR}"
                        fill="#ef4444" stroke="#ffffff" stroke-width="1.75" />
                <text x="${badgeCx}" y="${badgeCy}" text-anchor="middle" dominant-baseline="central"
                      fill="#ffffff" font-family="system-ui,-apple-system,Segoe UI,Roboto,sans-serif"
                      font-weight="700" font-size="${countStr.length >= 3 ? 9 : 11}">${countStr}</text>
            ` : ''}
        </svg>
    `;
}

/** Inline community building pin for cards, legends, etc. */
function CommunityPinIcon({ communityId = null, size = 20, count = 0, className = '', title = null }) {
    const color = colorForCommunity(communityId);
    const showBadge = count > 0;
    const countStr = String(count);
    const badgeR = countStr.length >= 3 ? 4.5 : 3.5;

    return (
        <svg
            xmlns="http://www.w3.org/2000/svg"
            width={size}
            height={size}
            viewBox="0 0 48 48"
            className={`flex-shrink-0 ${className}`.trim()}
            aria-hidden={title ? undefined : true}
            role={title ? 'img' : undefined}
            aria-label={title || undefined}
            style={{ filter: 'drop-shadow(0 1px 2px rgba(0,0,0,0.25))' }}
        >
            <rect x="15" y="22" width="18" height="14" rx="2" fill={color} stroke="#ffffff" strokeWidth="2" />
            <rect x="18" y="25" width="4" height="4" rx="0.5" fill="#ffffff" opacity="0.9" />
            <rect x="26" y="25" width="4" height="4" rx="0.5" fill="#ffffff" opacity="0.9" />
            <polygon
                points="13,22 24,11 35,22"
                fill={color}
                stroke="#ffffff"
                strokeWidth="2"
                strokeLinejoin="round"
            />
            {showBadge && (
                <>
                    <circle cx="35" cy="13" r={badgeR} fill="#ef4444" stroke="#ffffff" strokeWidth="1.5" />
                    <text
                        x="35"
                        y="13"
                        textAnchor="middle"
                        dominantBaseline="central"
                        fill="#ffffff"
                        fontFamily="system-ui, -apple-system, Segoe UI, Roboto, sans-serif"
                        fontWeight="700"
                        fontSize={countStr.length >= 3 ? 6 : 7}
                    >
                        {countStr}
                    </text>
                </>
            )}
        </svg>
    );
}

CommunityPinIcon.propTypes = {
    communityId: PropTypes.oneOfType([PropTypes.string, PropTypes.number]),
    size: PropTypes.number,
    count: PropTypes.number,
    className: PropTypes.string,
    title: PropTypes.string,
};

export default CommunityPinIcon;
