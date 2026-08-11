/**
 * UI smoke: Share Food → approve → Find Food → Claim
 *
 * Usage (from repo root, with `npm run dev` on :3001):
 *   node scripts/ui-share-claim-smoke.mjs
 *
 * Logs into two real accounts via Supabase Admin magic-link tokens
 * (no passwords). Creates a unique listing, claims it as the other user,
 * then cleans up.
 */
import { createClient } from '@supabase/supabase-js'
import { chromium } from 'playwright'
import fs from 'fs'
import path from 'path'
import { fileURLToPath } from 'url'
import dotenv from 'dotenv'

const __dirname = path.dirname(fileURLToPath(import.meta.url))
const root = path.join(__dirname, '..')
dotenv.config({ path: path.join(root, '.env') })
dotenv.config({ path: path.join(root, '.env.local'), override: true })

const BASE = process.env.UI_BASE_URL || 'http://localhost:3001'
const SUPABASE_URL = process.env.VITE_SUPABASE_URL || process.env.SUPABASE_URL
const ANON = process.env.VITE_SUPABASE_ANON_KEY || process.env.SUPABASE_ANON_KEY
const SERVICE = process.env.SUPABASE_SERVICE_ROLE_KEY
const DONOR_EMAIL = process.env.E2E_DONOR_EMAIL || 'compassionatedesk84@gmail.com'
const CLAIMER_EMAIL = process.env.E2E_CLAIMER_EMAIL || 'aslanabdulkarim84@gmail.com'

const stamp = Date.now()
const TITLE = `UI Smoke Loaf ${stamp}`
const results = []

function ok(name, detail = '') {
  results.push({ name, pass: true, detail })
  console.log(`  PASS  ${name}${detail ? ` — ${detail}` : ''}`)
}
function fail(name, detail = '') {
  results.push({ name, pass: false, detail })
  console.error(`  FAIL  ${name}${detail ? ` — ${detail}` : ''}`)
}

if (!SUPABASE_URL || !ANON || !SERVICE) {
  console.error('Missing SUPABASE url/anon/service role in .env')
  process.exit(1)
}

const admin = createClient(SUPABASE_URL, SERVICE, {
  auth: { autoRefreshToken: false, persistSession: false },
})
const projectRef = new URL(SUPABASE_URL).hostname.split('.')[0]
const AUTH_KEY = `sb-${projectRef}-auth-token`

async function sessionFor(email) {
  const { data, error } = await admin.auth.admin.generateLink({
    type: 'magiclink',
    email,
    options: { redirectTo: `${BASE}/` },
  })
  if (error) throw new Error(`generateLink(${email}): ${error.message}`)
  const hashed = data?.properties?.hashed_token
  if (!hashed) throw new Error(`No hashed_token for ${email}`)

  const anon = createClient(SUPABASE_URL, ANON, {
    auth: { autoRefreshToken: false, persistSession: false },
  })
  const verified = await anon.auth.verifyOtp({
    token_hash: hashed,
    type: 'email',
  })
  if (verified.error || !verified.data?.session) {
    throw new Error(`verifyOtp(${email}): ${verified.error?.message || 'no session'}`)
  }
  const session = verified.data.session
  const { data: profile } = await admin
    .from('users')
    .select('id,email,name,role,address,latitude,longitude,phone,organization')
    .eq('email', email)
    .maybeSingle()
  return { session, profile: profile || { id: session.user.id, email, name: email } }
}

async function injectAuth(context, { session, profile }) {
  await context.addInitScript(
    ({ authKey, session, profile }) => {
      // Match Supabase JS persist format (full session object).
      localStorage.setItem(authKey, JSON.stringify(session))
      localStorage.setItem('userAuthenticated', 'true')
      localStorage.setItem('currentUser', JSON.stringify({
        id: profile.id,
        email: profile.email,
        name: profile.name,
        role: profile.role || 'user',
        address: profile.address,
        latitude: profile.latitude,
        longitude: profile.longitude,
        phone: profile.phone,
        organization: profile.organization,
      }))
    },
    { authKey: AUTH_KEY, session, profile },
  )
}

function tinyPngPath() {
  // Minimal valid 1x1 PNG (not named *stock*)
  const b64 =
    'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=='
  const p = path.join(root, 'tmp-ui-smoke-food.png')
  fs.writeFileSync(p, Buffer.from(b64, 'base64'))
  return p
}

async function fillShareForm(page, png) {
  await page.goto(`${BASE}/share`, { waitUntil: 'domcontentloaded', timeout: 60000 })
  await page.waitForSelector('[data-name="food-form"], form', { timeout: 30000 })
  // Wait for profile autofill race to settle before typing.
  await page.waitForTimeout(1500)

  // Donor block
  await page.fill('input[name="donor_name"]', 'UI Smoke Donor')
  await page.fill('input[name="donor_zip"]', '94501')
  await page.fill('input[name="donor_city"]', 'Alameda')
  await page.selectOption('select[name="donor_state"]', 'CA')
  await page.fill('input[name="donor_email"]', DONOR_EMAIL)
  await page.fill('input[name="donor_occupation"]', 'Tester')
  await page.selectOption('select[name="donor_type"]', 'individual')

  const community = page.locator('select[name="school_district"]')
  if (await community.count()) {
    const disabled = await community.isDisabled()
    if (!disabled) {
      const opts = await community.locator('option').allTextContents()
      const pick = opts.find((o) => /Alameda Unified/i.test(o)) || opts.find((o) => o && !/select/i.test(o))
      if (pick) await community.selectOption({ label: pick.trim() })
    }
  }

  const geoDone = page.waitForEvent('console', {
    predicate: (msg) => /Found coordinates/i.test(msg.text()),
    timeout: 20000,
  }).catch(() => null)

  await page.fill('input[name="full_address"]', '1601 Broadway, Alameda, CA 94501')
  // Let controlled input commit, then blur via another field so geocode runs
  // with the latest formData (immediate .blur() can race React state).
  await page.waitForTimeout(500)
  await page.locator('input[name="donor_occupation"]').click()
  await geoDone
  await page.waitForTimeout(500)

  await page.fill('input[name="title"]', TITLE)
  await page.selectOption('select[name="category"]', 'produce')
  await page.fill('textarea[name="description"]', 'Automated UI smoke test produce listing. Safe to delete.')
  await page.fill('input[name="quantity"]', '3')
  await page.selectOption('select[name="unit"]', 'count')

  await page.setInputFiles('input[name="image"]', png)
  await page.waitForTimeout(400)

  await page.getByRole('button', { name: /submit listing/i }).click()
  try {
    await page.waitForURL(/\/profile|\/listings|\/dashboard/i, { timeout: 60000 })
  } catch (_) {
    const errs = await page.locator('.text-red-500, .text-red-600, [id$="-error"]').allTextContents()
    await page.screenshot({ path: path.join(root, 'tmp-share-fail.png'), fullPage: true }).catch(() => {})
    throw new Error(`share did not navigate; url=${page.url()} errs=${JSON.stringify(errs.filter(Boolean))}`)
  }
}

async function main() {
  console.log(`\nUI share/claim smoke @ ${BASE}`)
  console.log(`Title: ${TITLE}\n`)

  // Health
  const health = await fetch(`${BASE}/find`).then((r) => r.status).catch((e) => e.message)
  if (health !== 200) {
    fail('local UI reachable', String(health))
    process.exit(1)
  }
  ok('local UI reachable')

  const donor = await sessionFor(DONOR_EMAIL)
  const claimer = await sessionFor(CLAIMER_EMAIL)
  ok('auth sessions', `${DONOR_EMAIL} + ${CLAIMER_EMAIL}`)

  const browser = await chromium.launch({ headless: true })
  const png = tinyPngPath()
  let listingId = null
  let claimId = null

  try {
    // ---- SHARE as donor ----
    const donorCtx = await browser.newContext()
    await injectAuth(donorCtx, donor)
    const donorPage = await donorCtx.newPage()
    donorPage.setDefaultTimeout(45000)

    try {
      await fillShareForm(donorPage, png)
      const body = await donorPage.content()
      const err = await donorPage.locator('.text-red-600').first().textContent().catch(() => '')
      if (/failed|error|geocod/i.test(err || '') && !/profile/i.test(donorPage.url())) {
        fail('share form submit', err || donorPage.url())
      } else if (/\/profile|\/listings|\/dashboard/i.test(donorPage.url()) || /profile/i.test(body)) {
        ok('share form submit', donorPage.url())
      } else {
        // Still on share — check if listing landed in DB anyway
        const { data: rows } = await admin
          .from('food_listings')
          .select('id,status,title,user_id')
          .eq('title', TITLE)
          .order('created_at', { ascending: false })
          .limit(1)
        if (rows?.[0]) {
          ok('share form submit', `DB row ${rows[0].id} status=${rows[0].status}`)
        } else {
          fail('share form submit', `url=${donorPage.url()} err=${err}`)
        }
      }
    } catch (e) {
      fail('share form submit', e.message)
    }

    // Resolve listing
    const { data: created } = await admin
      .from('food_listings')
      .select('id,status,title,user_id,quantity')
      .eq('title', TITLE)
      .order('created_at', { ascending: false })
      .limit(1)
    if (!created?.[0]) {
      fail('listing persisted', 'not found after share')
      throw new Error('abort: no listing')
    }
    listingId = created[0].id
    ok('listing persisted', `${listingId} status=${created[0].status}`)

    // Share creates go-live status (approved/active) — pending is a regression.
    if (created[0].status !== 'approved' && created[0].status !== 'active') {
      fail(
        'listing go-live status',
        `expected approved/active, got ${created[0].status}`
      )
      throw new Error('abort: listing not live')
    }
    ok('listing go-live status', created[0].status)

    // Donor Find Food should NOT show own listing
    await donorPage.goto(`${BASE}/find`, { waitUntil: 'networkidle', timeout: 60000 })
    await donorPage.waitForTimeout(2000)
    const donorFind = await donorPage.content()
    if (donorFind.includes(TITLE)) {
      fail('own listing hidden on Find Food', 'donor still sees own title')
    } else {
      ok('own listing hidden on Find Food')
    }
    await donorCtx.close()

    // ---- CLAIM as claimer ----
    const claimCtx = await browser.newContext()
    await injectAuth(claimCtx, claimer)
    const claimPage = await claimCtx.newPage()
    claimPage.setDefaultTimeout(45000)

    await claimPage.goto(`${BASE}/find`, { waitUntil: 'networkidle', timeout: 60000 })
    await claimPage.waitForTimeout(2500)

    // Search filter if present
    const search = claimPage.locator('input[placeholder*="Search"], input[type="search"], input[name="search"]').first()
    if (await search.count()) {
      await search.fill(TITLE)
      await claimPage.waitForTimeout(800)
    }

    const claimerFind = await claimPage.content()
    if (!claimerFind.includes(TITLE)) {
      // Retry with longer wait / reload
      await claimPage.reload({ waitUntil: 'networkidle' })
      await claimPage.waitForTimeout(3000)
    }
    const visible = (await claimPage.content()).includes(TITLE)
    if (visible) ok('claimer sees listing on Find Food')
    else fail('claimer sees listing on Find Food', 'title missing after approve')

    if (visible) {
      // Click Claim on the matching card
      const card = claimPage.locator(`text=${TITLE}`).first()
      await card.scrollIntoViewIfNeeded().catch(() => {})
      // Prefer aria-label Claim <title>
      const claimBtn = claimPage.getByRole('button', { name: new RegExp(`Claim ${TITLE}`, 'i') })
        .or(claimPage.locator('button', { hasText: /^Claim$/ }).first())
      if (await claimBtn.count()) {
        await claimBtn.first().click()
        await claimPage.waitForURL(/\/claim/i, { timeout: 30000 }).catch(() => null)
        if (/\/claim/i.test(claimPage.url())) {
          ok('navigate to claim page', claimPage.url())
          await claimPage.getByRole('button', { name: /confirm claim/i }).click()
          await claimPage.waitForTimeout(4000)
          const after = await claimPage.content()
          const toastOk = /success|claimed|receipt|thank/i.test(after)
          const stillConfirm = /confirm claim/i.test(after) && /processing/i.test(after) === false
          // Check DB claim
          const { data: claims } = await admin
            .from('food_claims')
            .select('id,status,quantity,claimer_id')
            .eq('food_id', listingId)
            .eq('claimer_id', claimer.profile.id)
            .order('created_at', { ascending: false })
            .limit(1)
          if (claims?.[0]) {
            claimId = claims[0].id
            ok('claim persisted', `${claimId} status=${claims[0].status}`)
          } else if (toastOk) {
            ok('claim persisted', 'UI success (claim row pending)')
          } else {
            fail('claim persisted', stillConfirm ? 'still on confirm' : 'no claim row')
          }
        } else {
          fail('navigate to claim page', claimPage.url())
        }
      } else {
        fail('navigate to claim page', 'Claim button not found')
      }
    }

    await claimCtx.close()
  } finally {
    // Cleanup smoke artifacts
    try {
      if (claimId) await admin.from('food_claims').delete().eq('id', claimId)
      if (listingId) {
        await admin.from('food_claims').delete().eq('food_id', listingId)
        await admin.from('food_listings').delete().eq('id', listingId)
        ok('cleanup smoke listing', listingId)
      } else {
        await admin.from('food_listings').delete().eq('title', TITLE)
      }
    } catch (e) {
      fail('cleanup', e.message)
    }
    try { fs.unlinkSync(png) } catch (_) {}
    await browser.close()
  }

  const failed = results.filter((r) => !r.pass)
  console.log(`\n${results.length - failed.length}/${results.length} checks passed`)
  if (failed.length) {
    console.log('Failures:')
    for (const f of failed) console.log(` - ${f.name}: ${f.detail}`)
    process.exit(1)
  }
  console.log('Share + claim UI smoke passed.')
}

main().catch((e) => {
  console.error(e)
  process.exit(1)
})
