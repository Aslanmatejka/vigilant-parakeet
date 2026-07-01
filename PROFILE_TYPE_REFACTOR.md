# User Profile Type System Refactor

## Summary
Simplified the DoGoods app user profile type system from 6 roles to 3 core roles by removing volunteer, driver, dispatcher, and sponsor types. Users now select from: **Recipient**, **Donor**, or **Organizer**.

## Changes Made

### Database Migration
**File:** `supabase/migrations/20260628_simplify_community_roles.sql`
- Migrated existing `volunteer`, `driver`, `dispatcher` users to `organizer` role
- Updated CHECK constraint on `users.community_role` column to only allow: `donor`, `recipient`, `organizer`
- Updated column comment to reflect new role definitions

### Frontend Code Updates (8 files)

#### Core User Type System
1. **components/profile/UserTypeSelector.jsx**
   - Removed `VOLUNTEER: 'volunteer'` from `USER_TYPES` enum
   - Replaced with `ORGANIZER: 'organizer'`
   - Updated options array with organizer description: "Can coordinate food distributions"

2. **pages/UserSettings.jsx**
   - Removed dropdown options: `volunteer`, `driver`, `sponsor`
   - Kept: `donor`, `recipient`, `organizer`

3. **pages/admin/AdminBroadcasts.jsx**
   - Removed broadcast targeting options: `volunteer`, `driver`, `sponsor`
   - Kept: `donor`, `recipient`, `organizer`

#### Dashboard & Navigation
4. **pages/UserDashboard.jsx**
   - Replaced `isVolunteer` variable with `isOrganizer`
   - Changed condition from `role === 'volunteer' || role === 'driver' || role === 'dispatcher'` to `role === 'organizer'`
   - Updated quick actions for organizer role:
     * Distribution Events (was Pickup Routes)
     * Find Food (was See what needs delivering)
     * Near Me
   - Updated UI component visibility logic to use `isOrganizer`

5. **components/common/Header.jsx**
   - Replaced `isVolunteer` with `isOrganizer`
   - Updated navigation menu for organizers:
     * Distribution Events (was Pickup Routes)
     * Near Me

#### AI & Services
6. **components/assistant/RoleInsightsPanel.jsx**
   - Removed role labels: `volunteer`, `dispatcher`, `sponsor`
   - Kept: `donor`, `recipient`, `organizer`

7. **utils/services/insightsFallback.js**
   - Removed from `PROFILE_FIELDS`: `volunteer`, `dispatcher`, `sponsor`
   - Removed from `resolveRole()` allowed roles: `volunteer`, `dispatcher`, `sponsor`
   - Updated comment: "recipient / organizer" (was "recipient / volunteer / dispatcher / organizer / sponsor")

### What Was NOT Changed
The following references were intentionally left unchanged as they are not part of the user role system:

1. **External Marketing Links** (Footer, Header, ContactPage, CommunityPage)
   - Links to `https://allgoodlivingfoundation.org/volunteer-form`
   - `DonateVolunteerButtons` component name
   - These are for volunteer recruitment/marketing, not user roles

2. **Impact Metrics** (impactService.js, useImpact.js)
   - `volunteerHours` field for tracking volunteer hours worked
   - This is data analytics, not a role type

## Migration Impact

### For Existing Users
- Users with `community_role` set to `volunteer`, `driver`, or `dispatcher` will be automatically migrated to `organizer` when the migration runs
- No data loss - all user preferences and history preserved
- UI will show "Organizer" as their role type

### For New Users
- Signup/profile flows will only offer 3 role choices:
  1. **Recipient** - Receives food
  2. **Donor** - Shares food
  3. **Organizer** - Coordinates distributions

## Testing Recommendations

1. **Database Migration**
   - Run migration on local Supabase: `npm run supabase:reset` or apply migration manually
   - Verify CHECK constraint updated: `\d users` in psql
   - Verify existing volunteer/driver users migrated to organizer

2. **Frontend Testing**
   - Sign up as new user - verify only 3 role options shown
   - Test role switching in UserSettings - verify volunteer/driver removed
   - Test dashboard quick actions for each role type
   - Test header navigation for organizer role
   - Test admin broadcast targeting dropdown
   - Verify AI insights work for organizer role

3. **Regression Testing**
   - Verify donor workflows unaffected
   - Verify recipient workflows unaffected
   - Verify external volunteer recruitment links still work
   - Verify impact metrics (volunteer hours) still display

## Rollback Plan
If rollback is needed:
1. Revert migration: Drop new constraint, add old constraint with 6 roles
2. Revert frontend files (use git to restore previous versions)
3. No data migration needed - organizers can remain as organizers
