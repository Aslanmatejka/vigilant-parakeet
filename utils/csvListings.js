/**
 * Tiny RFC-4180-ish CSV parser used by the AI chat bulk-listings upload.
 * Keeps the dependency footprint zero. Supports:
 *   - Quoted fields with embedded commas/semicolons/tabs, newlines, and "" escapes
 *   - Auto-detects delimiter: comma, semicolon, or tab
 *   - Header row required (case-insensitive)
 *   - Flexible column aliases (e.g. "qty" → quantity)
 *   - UTF-8 BOM stripping
 */

const VALID_CATEGORIES = new Set([
  'produce', 'bakery', 'dairy', 'pantry', 'meat', 'prepared', 'other',
])

const HEADER_ALIASES = {
  title: 'title',
  name: 'title',
  item: 'title',
  'food name': 'title',
  'food item': 'title',
  'item name': 'title',
  description: 'description',
  desc: 'description',
  notes: 'description',
  detail: 'description',
  quantity: 'quantity',
  qty: 'quantity',
  amount: 'quantity',
  count: 'quantity',
  number: 'quantity',
  unit: 'unit',
  units: 'unit',
  'unit of measure': 'unit',
  measure: 'unit',
  category: 'category',
  type: 'category',
  'food type': 'category',
  'food category': 'category',
  expiry_date: 'expiry_date',
  expiry: 'expiry_date',
  expires: 'expiry_date',
  'expiration date': 'expiry_date',
  'expiry date': 'expiry_date',
  'expires on': 'expiry_date',
  'best by': 'expiry_date',
  'use by': 'expiry_date',
  'best before': 'expiry_date',
  location: 'location',
  address: 'location',
  pickup_location: 'location',
  'pickup location': 'location',
  dietary_tags: 'dietary_tags',
  diet: 'dietary_tags',
  tags: 'dietary_tags',
  dietary: 'dietary_tags',
  'dietary restrictions': 'dietary_tags',
  allergens: 'allergens',
  allergy: 'allergens',
  allergies: 'allergens',
  'allergy info': 'allergens',
  community: 'community_name',
  community_name: 'community_name',
  'community name': 'community_name',
  school: 'community_name',
  'school name': 'community_name',
  'school/community': 'community_name',
  community_id: 'community_id',
  'community id': 'community_id',
  school_id: 'community_id',
}

const REQUIRED = ['title', 'quantity', 'unit', 'category']

/**
 * Strip UTF-8 BOM if present (Excel often adds \uFEFF to CSV exports).
 */
function stripBom(text) {
  return text.charCodeAt(0) === 0xFEFF ? text.slice(1) : text
}

/**
 * Detect the most likely field delimiter by counting occurrences in the first line.
 * Falls back to comma if nothing else scores higher.
 */
function detectDelimiter(firstLine) {
  const counts = {
    ',': (firstLine.match(/,/g) || []).length,
    ';': (firstLine.match(/;/g) || []).length,
    '\t': (firstLine.match(/\t/g) || []).length,
  }
  let best = ','
  let bestCount = 0
  for (const [delim, count] of Object.entries(counts)) {
    if (count > bestCount) { bestCount = count; best = delim }
  }
  return best
}

function splitRowsRespectingQuotes(text, delimiter) {
  const rows = []
  let field = ''
  let row = []
  let inQuotes = false
  for (let i = 0; i < text.length; i += 1) {
    const ch = text[i]
    if (inQuotes) {
      if (ch === '"') {
        if (text[i + 1] === '"') { field += '"'; i += 1 }
        else { inQuotes = false }
      } else {
        field += ch
      }
      continue
    }
    if (ch === '"') { inQuotes = true; continue }
    if (ch === delimiter) { row.push(field); field = ''; continue }
    if (ch === '\n' || ch === '\r') {
      if (ch === '\r' && text[i + 1] === '\n') i += 1
      row.push(field)
      if (row.some(c => c.trim() !== '')) rows.push(row)
      row = []
      field = ''
      continue
    }
    field += ch
  }
  if (field !== '' || row.length) {
    row.push(field)
    if (row.some(c => c.trim() !== '')) rows.push(row)
  }
  return rows
}

function normalizeHeaderName(h) {
  const key = String(h || '').trim().toLowerCase().replace(/\s+/g, ' ')
  return HEADER_ALIASES[key] || HEADER_ALIASES[key.replace(/\s+/g, '_')] || null
}

function parseListField(val) {
  if (!val) return []
  return String(val)
    .split(/[,;|]/)
    .map(s => s.trim())
    .filter(Boolean)
    .slice(0, 20)
}

/**
 * Accept an American-style expiry cell (MM/DD/YYYY, M/D/YY, M-D-YYYY) OR an
 * ISO YYYY-MM-DD passthrough. Returns ISO YYYY-MM-DD, or null when the input
 * is empty/unparseable so callers can fall through to their existing default
 * (sanitizeListingExpiry's category-based fill).
 *
 * Bulk CSV donors typing "9/1/2026" used to be silently overwritten with a
 * category default; parsing US dates here keeps their real expiry.
 */
export function parseAmericanDate(raw) {
  if (raw == null) return null
  const s = String(raw).trim()
  if (!s) return null
  const iso = s.match(/^(\d{4})-(\d{1,2})-(\d{1,2})$/)
  if (iso) {
    const y = Number(iso[1])
    const m = Number(iso[2])
    const d = Number(iso[3])
    if (isValidYmd(y, m, d)) return toIso(y, m, d)
    return null
  }
  const us = s.match(/^(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})$/)
  if (us) {
    const month = Number(us[1])
    const day = Number(us[2])
    let year = Number(us[3])
    if (year < 100) year += 2000
    if (isValidYmd(year, month, day)) return toIso(year, month, day)
    return null
  }
  return null
}

function isValidYmd(y, m, d) {
  if (!Number.isFinite(y) || !Number.isFinite(m) || !Number.isFinite(d)) return false
  if (y < 1900 || y > 2999) return false
  if (m < 1 || m > 12) return false
  if (d < 1 || d > 31) return false
  const dt = new Date(Date.UTC(y, m - 1, d))
  return (
    dt.getUTCFullYear() === y
    && dt.getUTCMonth() === m - 1
    && dt.getUTCDate() === d
  )
}

function toIso(y, m, d) {
  const mm = String(m).padStart(2, '0')
  const dd = String(d).padStart(2, '0')
  return `${y}-${mm}-${dd}`
}

/**
 * Parse a CSV blob of food listings.
 * Auto-detects delimiter (comma, semicolon, tab) and strips BOM.
 * @param {string} text - raw CSV text (header row required)
 * @returns {{ rows: object[], errors: string[], headers: string[], delimiter: string }}
 */
export function parseListingsCsv(text) {
  const errors = []
  if (!text || typeof text !== 'string') {
    return { rows: [], errors: ['Empty CSV file'], headers: [], delimiter: ',' }
  }

  // Strip BOM and leading/trailing whitespace
  const cleaned = stripBom(text).trim()
  if (!cleaned) {
    return { rows: [], errors: ['Empty CSV file'], headers: [], delimiter: ',' }
  }

  // Auto-detect delimiter from the first line
  const firstNewline = cleaned.search(/[\r\n]/)
  const firstLine = firstNewline === -1 ? cleaned : cleaned.slice(0, firstNewline)
  const delimiter = detectDelimiter(firstLine)

  const rawRows = splitRowsRespectingQuotes(cleaned, delimiter)

  if (rawRows.length < 1) {
    return { rows: [], errors: ['Empty CSV file'], headers: [], delimiter }
  }
  if (rawRows.length < 2) {
    return {
      rows: [],
      errors: [
        'Your CSV only has a header row — please add at least one data row below the headers.',
        `Expected columns: title, quantity, unit, category (and optionally: description, expiry_date, location, dietary_tags, allergens, community)`,
      ],
      headers: rawRows[0]?.map(h => h.trim()) || [],
      delimiter,
    }
  }

  const rawHeaders = rawRows[0].map(h => h.trim())
  const headerMap = rawHeaders.map(normalizeHeaderName)
  const headersFound = new Set(headerMap.filter(Boolean))
  const missingCols = REQUIRED.filter(req => !headersFound.has(req))
  if (missingCols.length) {
    const aliasHints = {
      title: '"title", "name", or "item"',
      quantity: '"quantity", "qty", or "amount"',
      unit: '"unit" or "units"',
      category: '"category" or "type"',
    }
    for (const col of missingCols) {
      errors.push(`Missing required column — use ${aliasHints[col]} (found: ${rawHeaders.join(', ')})`)
    }
    return { rows: [], errors, headers: rawHeaders, delimiter }
  }

  const rows = []
  for (let r = 1; r < rawRows.length; r += 1) {
    const cells = rawRows[r]
    const obj = {}
    headerMap.forEach((field, idx) => {
      if (!field) return
      obj[field] = (cells[idx] ?? '').trim()
    })
    if (!obj.title) {
      errors.push(`Row ${r + 1}: missing title — skipped`)
      continue
    }
    const qty = Number(obj.quantity)
    if (!Number.isFinite(qty) || qty <= 0) {
      errors.push(`Row ${r + 1}: invalid quantity "${obj.quantity}" — skipped`)
      continue
    }
    let category = String(obj.category || '').toLowerCase()
    if (!VALID_CATEGORIES.has(category)) category = 'other'
    const row = {
      title: obj.title.slice(0, 200),
      quantity: qty,
      unit: (obj.unit || 'items').slice(0, 40),
      category,
    }
    if (obj.description) row.description = obj.description.slice(0, 2000)
    if (obj.expiry_date) {
      // Donors typically write MM/DD/YYYY in a US-format spreadsheet;
      // convert to ISO here so the rest of the pipeline (sanitizeListingExpiry,
      // backend _normalize_expiry_date, DB) keeps its ISO contract.
      const usIso = parseAmericanDate(obj.expiry_date)
      row.expiry_date = (usIso || obj.expiry_date).slice(0, 40)
    }
    if (obj.location) row.location = obj.location.slice(0, 200)
    if (obj.dietary_tags) row.dietary_tags = parseListField(obj.dietary_tags)
    if (obj.allergens) row.allergens = parseListField(obj.allergens)
    // Per-row community — never discard. Recipients only see food for their
    // school (+ warehouse); wrong community_id at import looks like a leak.
    const rawCid = String(obj.community_id || '').trim()
    const rawCname = String(obj.community_name || '').trim()
    if (rawCid) {
      if (/^\d+$/.test(rawCid)) {
        row.community_id = rawCid.slice(0, 64)
      } else if (!rawCname) {
        // Non-numeric "community_id" cell is usually a school name.
        row.community_name = rawCid.slice(0, 200)
      } else {
        row.community_id = rawCid.slice(0, 64)
      }
    }
    if (rawCname) row.community_name = rawCname.slice(0, 200)
    rows.push(sanitizeListingExpiry(row))
  }

  return { rows, errors, headers: rawHeaders, delimiter }
}

/** YYYY-MM-DD for today + N days (local calendar). */
function datePlusDays(days) {
  const d = new Date()
  d.setDate(d.getDate() + days)
  const y = d.getFullYear()
  const m = String(d.getMonth() + 1).padStart(2, '0')
  const day = String(d.getDate()).padStart(2, '0')
  return `${y}-${m}-${day}`
}

/** MM/DD/YYYY for today + N days — used in the CSV template so donors see
 * the same format they'll type when editing the file in Excel/Sheets. */
function datePlusDaysUS(days) {
  const d = new Date()
  d.setDate(d.getDate() + days)
  const y = d.getFullYear()
  const m = String(d.getMonth() + 1).padStart(2, '0')
  const day = String(d.getDate()).padStart(2, '0')
  return `${m}/${day}/${y}`
}

/**
 * Suggested default expiry (days from today) by category when missing/past.
 * Find Food hides rows with expiry_date < today, so past dates look like
 * "only one listing posted".
 */
const CATEGORY_EXPIRY_DAYS = {
  produce: 5,
  bakery: 3,
  dairy: 7,
  meat: 3,
  prepared: 2,
  pantry: 180,
  other: 14,
}

/**
 * If expiry is missing or already past, replace with a category-based
 * future date so CSV imports remain visible on Find Food.
 *
 * @param {object} row
 * @returns {object}
 */
export function sanitizeListingExpiry(row) {
  if (!row || typeof row !== 'object') return row
  const today = datePlusDays(0)
  const raw = String(row.expiry_date || '').trim().slice(0, 10)
  if (raw && /^\d{4}-\d{2}-\d{2}$/.test(raw) && raw >= today) {
    return row
  }
  const cat = String(row.category || 'other').toLowerCase()
  const days = CATEGORY_EXPIRY_DAYS[cat] ?? CATEGORY_EXPIRY_DAYS.other
  return { ...row, expiry_date: datePlusDays(days) }
}

/**
 * Match a free-text community/school label to a community row.
 * Used after CSV parse so per-row names become community_id before publish.
 */
export function matchCommunityByName(query, communities) {
  const q = String(query || '').trim().toLowerCase()
  if (!q || !Array.isArray(communities) || !communities.length) return null
  const exact = communities.find(
    (c) => String(c?.name || '').trim().toLowerCase() === q,
  )
  if (exact) return exact
  const contains = communities.find((c) => {
    const name = String(c?.name || '').trim().toLowerCase()
    return name && (name.includes(q) || q.includes(name))
  })
  return contains || null
}

/**
 * Generate and trigger a download of the CSV template file.
 */
export function downloadCsvTemplate() {
  const headers = [
    'title', 'quantity', 'unit', 'category', 'description', 'expiry_date',
    'dietary_tags', 'allergens', 'location', 'community',
  ]
  // Keep example expiry dates in the future so the template itself is usable.
  // Dates are American MM/DD/YYYY — parseListingsCsv converts to ISO on
  // import, and ISO YYYY-MM-DD still works if a donor prefers it.
  // Different community names show that each row can target a different school.
  const examples = [
    ['Fresh Apples', '10', 'lbs', 'produce', 'Crisp Fuji apples from local farm', datePlusDaysUS(5), 'vegan,gluten-free', '', '', 'Do Good Warehouse'],
    ['Whole Wheat Bread', '5', 'loaves', 'bakery', 'Freshly baked today', datePlusDaysUS(3), 'vegetarian', 'gluten', '', ''],
    ['Canned Beans', '20', 'cans', 'pantry', 'Black beans, unopened', datePlusDaysUS(180), 'vegan,gluten-free', '', '', ''],
  ]
  const csvContent = [
    headers.join(','),
    ...examples.map(row => row.map(field => (field.includes(',') ? `"${field}"` : field)).join(',')),
  ].join('\r\n')

  const blob = new Blob([csvContent], { type: 'text/csv;charset=utf-8;' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = 'dogoods_listings_template.csv'
  document.body.appendChild(a)
  a.click()
  document.body.removeChild(a)
  URL.revokeObjectURL(url)
}

/**
 * Coerce a draft from /api/ai/vision-listing into a bulkCreateListings row.
 */
export function visionDraftToRow(draft) {
  if (!draft || !draft.title) return null
  return {
    title: String(draft.title).slice(0, 200),
    quantity: Number(draft.quantity) > 0 ? Number(draft.quantity) : 1,
    unit: String(draft.unit || 'items').slice(0, 40),
    category: VALID_CATEGORIES.has(draft.category) ? draft.category : 'other',
    description: draft.description ? String(draft.description).slice(0, 2000) : undefined,
    dietary_tags: Array.isArray(draft.dietary_tags) ? draft.dietary_tags : undefined,
    allergens: Array.isArray(draft.allergens) ? draft.allergens : undefined,
    image_url: draft.image_url ? String(draft.image_url).slice(0, 2000) : undefined,
    // Photo flow defaults — pickup address (from profile), suggested expiry
    // (category-based, user can override in preview), community membership.
    // Without these the listing publishes with no map pin, no freshness
    // hint, and no community attribution.
    location: draft.location ? String(draft.location).slice(0, 200) : undefined,
    expiry_date: draft.expiry_date ? String(draft.expiry_date).slice(0, 40) : undefined,
    community_id: draft.community_id ? String(draft.community_id).slice(0, 64) : undefined,
    community_name: draft.community_name ? String(draft.community_name).slice(0, 200) : undefined,
  }
}

export const VALID_LISTING_CATEGORIES = VALID_CATEGORIES
