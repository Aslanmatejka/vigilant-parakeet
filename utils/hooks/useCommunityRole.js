import { useEffect, useState } from 'react'
import supabase from '../supabaseClient.js'
import { useAuthContext } from '../AuthContext.jsx'

// Returns the user's community_role, sourced from the DB on mount and refreshed
// whenever a `dogoods:community-role-changed` event fires. Falls back to the
// cached value on the auth user object so first paint isn't blank.
export function useCommunityRole() {
    const { user } = useAuthContext()
    const [role, setRole] = useState(() => user?.community_role || null)

    useEffect(() => {
        let cancelled = false
        if (!user?.id) { setRole(null); return }
        setRole(user.community_role || null)
        ;(async () => {
            try {
                const { data } = await supabase
                    .from('users')
                    .select('community_role')
                    .eq('id', user.id)
                    .single()
                if (!cancelled && data) setRole(data.community_role || null)
            } catch (_) { /* keep cached */ }
        })()
        const onChanged = (e) => {
            // Ignore malformed events with no detail \u2014 the old code would
            // setRole(null) on any stray dispatch, briefly wiping the user's
            // role until the next page reload re-fetched it.
            if (!e?.detail || typeof e.detail !== 'object') return
            if (e.detail.userId && e.detail.userId !== user.id) return
            setRole(e.detail.role ?? null)
        }
        window.addEventListener('dogoods:community-role-changed', onChanged)
        return () => {
            cancelled = true
            window.removeEventListener('dogoods:community-role-changed', onChanged)
        }
    }, [user?.id, user?.community_role])

    return String(role || '').toLowerCase()
}

export default useCommunityRole
