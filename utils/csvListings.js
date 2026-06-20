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
        `Expected columns: title, quantity, unit, category (and optionally: description, expiry_date, location, dietary_tags, allergens)`,
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
    if (obj.expiry_date) row.expiry_date = obj.expiry_date.slice(0, 40)
    if (obj.location) row.location = obj.location.slice(0, 200)
    if (obj.dietary_tags) row.dietary_tags = parseListField(obj.dietary_tags)
    if (obj.allergens) row.allergens = parseListField(obj.allergens)
    rows.push(row)
  }

  return { rows, errors, headers: rawHeaders, delimiter }
}

/**
 * Generate and trigger a download of the CSV template file.
 */
export function downloadCsvTemplate() {
  const headers = ['title', 'quantity', 'unit', 'category', 'description', 'expiry_date', 'dietary_tags', 'allergens', 'location']
  const examples = [
    ['Fresh Apples', '10', 'lbs', 'produce', 'Crisp Fuji apples from local farm', '2026-06-10', 'vegan,gluten-free', '', '123 Main St'],
    ['Whole Wheat Bread', '5', 'loaves', 'bakery', 'Freshly baked today', '2026-05-31', 'vegetarian', 'gluten', ''],
    ['Canned Beans', '20', 'cans', 'pantry', 'Black beans, unopened', '2027-01-01', 'vegan,gluten-free', '', ''],
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
  }
}

export const VALID_LISTING_CATEGORIES = VALID_CATEGORIES
