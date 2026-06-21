/**
 * Insights Fallback Layer (real self-healing)
 * --------------------------------------------
 * When the AI backend is unreachable, we don't just retry — we actually
 * recover the user experience by:
 *
 *   1. Serving the last good payload from localStorage (stale-while-revalidate)
 *   2. Computing genuine, accurate insights directly from Supabase
 *      (profile completion + activity-based suggestions) so the user still
 *      sees something useful and truthful, not a placeholder.
 *
 * Only deterministic, rules-based logic — no AI call required.
 */

import supabase from '../supabaseClient.js'

const CACHE_PREFIX = 'dogoods:insights:'
const CACHE_TTL_MS = 5 * 60 * 1000 // 5 minutes — stale data is still shown but refresh kicks off

const keyFor = (userId) => `${CACHE_PREFIX}${userId}`

// ---------------------------------------------------------------------------
// Cache (localStorage)
// ---------------------------------------------------------------------------
export function getCachedInsights(userId) {
    if (!userId || typeof window === 'undefined') return null
    try {
        const raw = window.localStorage.getItem(keyFor(userId))
        if (!raw) return null
        const parsed = JSON.parse(raw)
        if (!parsed?.payload) return null
        const fresh = Date.now() - (parsed.savedAt || 0) < CACHE_TTL_MS
        return { payload: parsed.payload, fresh, savedAt: parsed.savedAt }
    } catch (_) {
        return null
    }
}

export function cacheInsights(userId, payload) {
    if (!userId || typeof window === 'undefined' || !payload) return
    try {
        window.localStorage.setItem(
            keyFor(userId),
            JSON.stringify({ payload, savedAt: Date.now() })
        )
    } catch (_) {
        /* quota / private mode — ignore */
    }
}

export function clearCachedInsights(userId) {
    if (!userId || typeof window === 'undefined') return
    try {
        window.localStorage.removeItem(keyFor(userId))
    } catch (_) {
        /* ignore */
    }
}

/**
 * Wipe every cached insights payload across all users on this device.
 * Called from the SIGNED_OUT auth listener below so a previous user's
 * profile-completion / activity counts don't briefly flash for the next
 * person to sign in on the same browser.
 */
function clearAllCachedInsights() {
    if (typeof window === 'undefined') return
    try {
        const keys = []
        for (let i = 0; i < window.localStorage.length; i++) {
            const k = window.localStorage.key(i)
            if (k && k.startsWith(CACHE_PREFIX)) keys.push(k)
        }
        for (const k of keys) window.localStorage.removeItem(k)
    } catch (_) {
        /* quota / private mode — ignore */
    }
}

// Evict cached insights when the user signs out so the next session on this
// device starts clean. Guarded so test mocks (which only stub a subset of
// supabase.auth) don't blow up at import time.
if (typeof supabase?.auth?.onAuthStateChange === 'function') {
    supabase.auth.onAuthStateChange((event) => {
        if (event === 'SIGNED_OUT') clearAllCachedInsights()
    })
}

// ---------------------------------------------------------------------------
// Local insight computation — queries Supabase directly
// ---------------------------------------------------------------------------

/** Profile fields required for a "complete" profile, per role. */
const PROFILE_FIELDS = {
    donor:      ['name', 'phone', 'address', 'avatar_url'],
    recipient:  ['name', 'phone', 'address', 'dietary_restrictions'],
    volunteer:  ['name', 'phone', 'address', 'avatar_url'],
    dispatcher: ['name', 'phone', 'address', 'avatar_url'],
    organizer:  ['name', 'phone', 'address', 'avatar_url'],
    sponsor:    ['name', 'phone', 'avatar_url'],
    admin:      [],
}

const FIELD_LABELS = {
    name: 'your name',
    phone: 'a phone number',
    address: 'your address',
    avatar_url: 'a profile photo',
    dietary_restrictions: 'dietary preferences',
}

const FIELD_ROUTES = {
    name: '/settings',
    phone: '/settings',
    address: '/settings',
    avatar_url: '/profile',
    dietary_restrictions: '/settings',
}

function profileStats(role, userRow) {
    const fields = PROFILE_FIELDS[role] || PROFILE_FIELDS.recipient
    if (!fields.length) return { pct: null, missing: [] }
    const missing = fields.filter((f) => {
        const v = userRow?.[f]
        return v === null || v === undefined || (typeof v === 'string' && v.trim() === '')
    })
    const pct = Math.round(((fields.length - missing.length) / fields.length) * 100)
    return { pct, missing }
}

function resolveRole(userRow, roleHint) {
    if (userRow?.is_admin) return 'admin'
    const raw = (roleHint || userRow?.community_role || 'recipient').toLowerCase()
    const allowed = ['admin', 'donor', 'recipient', 'volunteer', 'dispatcher', 'organizer', 'sponsor']
    if (!allowed.includes(raw)) return 'recipient'
    return raw
}

/**
 * Compute insights from real Supabase data without hitting the AI backend.
 *
 * @param {string} userId
 * @param {string|null} roleHint
 * @returns {Promise<object>} same shape as the backend /api/ai/insights response
 */
export async function computeLocalInsights(userId, roleHint = null) {
    const nowIso = new Date().toISOString()

    // 1. Fetch the user profile
    let userRow = {}
    try {
        const { data } = await supabase
            .from('users')
            .select('id,name,is_admin,community_role,address,phone,avatar_url,dietary_restrictions,sms_opt_in')
            .eq('id', userId)
            .maybeSingle()
        userRow = data || {}
    } catch (_) { /* keep empty */ }

    const role = resolveRole(userRow, roleHint)
    const { pct, missing } = profileStats(role, userRow)

    // 2. Build profile-gap insights (the same shape the backend uses)
    const gapInsights = missing.map((f) => ({
        id: `profile_${f}`,
        title: `Add ${FIELD_LABELS[f] || f.replace(/_/g, ' ')}`,
        message: 'Completing your profile helps the community trust and reach you faster.',
        priority: 'medium',
        icon: 'user-pen',
        source: 'profile_gap',
        action: { label: 'Update profile', href: FIELD_ROUTES[f] || '/settings' },
    }))

    // 3. Fetch activity in parallel (best-effort — tolerate failures)
    const [claimsRes, listingsRes, notifsRes] = await Promise.allSettled([
        supabase
            .from('food_claims')
            .select('id,status,created_at')
            .eq('claimer_id', userId)
            .order('created_at', { ascending: false })
            .limit(50),
        supabase
            .from('food_listings')
            .select('id,status,created_at,expiry_date,pickup_by')
            .eq('user_id', userId)
            .order('created_at', { ascending: false })
            .limit(50),
        supabase
            .from('notifications')
            .select('id,read,created_at')
            .eq('user_id', userId)
            .eq('read', false)
            .limit(20),
    ])

    const claims = claimsRes.status === 'fulfilled' ? (claimsRes.value.data || []) : []
    const listings = listingsRes.status === 'fulfilled' ? (listingsRes.value.data || []) : []
    const unreadNotifs = notifsRes.status === 'fulfilled' ? (notifsRes.value.data || []).length : 0

    const pendingClaims = claims.filter((c) => c.status === 'pending').length
    const approvedClaims = claims.filter((c) => c.status === 'approved').length
    const activeListings = listings.filter((l) => l.status === 'approved' || l.status === 'active').length
    const pendingListings = listings.filter((l) => l.status === 'pending').length

    // Flag listings expiring within ~36 h so donors see "expiring soon"
    // alerts for items expiring TOMORROW (not just today). Using end-of-day
    // local time as the cutoff with a 24h window meant a listing expiring
    // tomorrow (delta ≈ 30h) was silently excluded right when the donor
    // needed the nudge most.
    //
    // new Date('YYYY-MM-DD') without 'T00:00:00' is UTC midnight, which in
    // Pacific time is the previous afternoon — making listings appear expired
    // ~7 hours early.
    const soonMs = 36 * 60 * 60 * 1000
    const expiringSoon = listings.filter((l) => {
        if (!l.expiry_date || (l.status !== 'approved' && l.status !== 'active')) return false
        const expiryLocal = new Date(l.expiry_date + 'T00:00:00')
        expiryLocal.setHours(23, 59, 59, 999)
        const delta = expiryLocal.getTime() - Date.now()
        return delta > 0 && delta < soonMs
    }).length

    // 4. Build activity insights per role
    const activityInsights = []

    if (unreadNotifs > 0) {
        activityInsights.push({
            id: 'unread_notifications',
            title: `${unreadNotifs} unread notification${unreadNotifs === 1 ? '' : 's'}`,
            message: 'You have updates waiting — check your inbox to stay current.',
            priority: 'medium',
            icon: 'bell',
            source: 'activity',
            action: { label: 'View notifications', href: '/notifications' },
        })
    }

    if (role === 'admin') {
        activityInsights.push({
            id: 'admin_overview',
            title: 'Review the platform overview',
            message: 'Check pending approvals, recent reports, and community health from the admin dashboard.',
            priority: 'medium',
            icon: 'gauge-high',
            source: 'activity',
            action: { label: 'Open admin dashboard', href: '/admin' },
        })
    } else if (role === 'donor') {
        if (expiringSoon > 0) {
            activityInsights.push({
                id: 'donor_expiring',
                title: `${expiringSoon} listing${expiringSoon === 1 ? '' : 's'} expiring soon`,
                message: 'Promote pickup or extend the window so this food still reaches someone.',
                priority: 'high',
                icon: 'clock',
                source: 'activity',
                action: { label: 'Review my listings', href: '/listings' },
            })
        }
        if (activeListings === 0) {
            activityInsights.push({
                id: 'donor_share',
                title: 'Share surplus food today',
                message: 'You have no active listings — a small donation can feed a neighbour.',
                priority: 'medium',
                icon: 'utensils',
                source: 'activity',
                action: { label: 'Share food', href: '/share' },
            })
        }
        if (pendingListings > 0) {
            activityInsights.push({
                id: 'donor_pending',
                title: `${pendingListings} listing${pendingListings === 1 ? '' : 's'} awaiting approval`,
                message: 'Admins are reviewing — you\'ll be notified once they go live.',
                priority: 'low',
                icon: 'hourglass-half',
                source: 'activity',
                action: { label: 'View status', href: '/listings' },
            })
        }
    } else {
        // recipient / volunteer / dispatcher / organizer / sponsor — generic helpful nudges
        if (pendingClaims > 0) {
            activityInsights.push({
                id: 'recipient_pending',
                title: `${pendingClaims} claim${pendingClaims === 1 ? '' : 's'} awaiting confirmation`,
                message: 'Donors usually respond within a few hours.',
                priority: 'low',
                icon: 'hourglass-half',
                source: 'activity',
                action: { label: 'Track claims', href: '/dashboard' },
            })
        }
        if (approvedClaims > 0) {
            activityInsights.push({
                id: 'recipient_pickup',
                title: `${approvedClaims} pickup${approvedClaims === 1 ? '' : 's'} ready`,
                message: 'Coordinate with the donor before the pickup window closes.',
                priority: 'high',
                icon: 'circle-check',
                source: 'activity',
                action: { label: 'See pickups', href: '/dashboard' },
            })
        }
        if (pendingClaims === 0 && approvedClaims === 0) {
            activityInsights.push({
                id: 'recipient_browse',
                title: 'Browse food available near you',
                message: 'Fresh listings are added every day — claim what your family needs.',
                priority: 'medium',
                icon: 'magnifying-glass',
                source: 'activity',
                action: { label: 'Find food', href: '/find' },
            })
        }
    }

    const headline = role === 'admin'
        ? 'Platform overview while AI is reconnecting'
        : 'Here\'s a quick summary while AI reconnects'

    return {
        role,
        headline,
        insights: [...gapInsights, ...activityInsights].slice(0, 6),
        profile_completion: pct,
        profile_gaps: gapInsights.map((g) => g.id),
        generated_at: nowIso,
        _degraded: true,
        _source: 'local',
    }
}
