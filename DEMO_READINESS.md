# Boss demo readiness (2026-07-16)

## Live
- Frontend: https://dogoods.store
- Backend health: `GET https://dogoods-backend-production.up.railway.app/api/ai/health`
- Listing approval: **ON** (`platform_settings.require_listing_approval = true`)
- Warehouse community id: **1** (`Do Good Warehouse`) — shared across schools

## Recommended 8-minute walkthrough
1. **Admin** → Listing Approvals — show empty queue or approve any pending.
2. **School user A** (approval code for school X) → Share Food — banner says awaiting approval; submit → toast → Profile → Pending.
3. **Admin** → approve that listing.
4. **School user A** → Find Food — listing appears; claim works.
5. **School user B** (different school) → Find Food — does **not** see school X food.
6. **Nouri** → “I’m hungry” / “share bread” — search scoped; share says awaiting approval (not “live”).
7. **Settings** → Community / School label is read-only.

## Do not click during demo (or explain first)
- Admin Settings fields other than “Require approval” (preview-only; labeled).
- Other schools’ community pages while logged in as a different school (shows Members only).
- Blog / Success stories (thin content).

## Demo accounts checklist
- [ ] Admin account with `is_admin=true`
- [ ] User at school A with `community_id` set + `community_role` (donor or recipient)
- [ ] User at school B with different `community_id`
- [ ] Fresh approval code for signup demo (optional)

## Fixed in this pass
- Share form copy respects approval toggle; community locked to signup school
- Post-share goes to Pending listings with toast
- Claim blocks other communities; CAS uses live qty
- Legal/how-it-works pages public
- Map community pins scoped; community page members-only message
- Nouri multi-share no longer says “are live” when pending
- Claim community guard fails closed on lookup errors
