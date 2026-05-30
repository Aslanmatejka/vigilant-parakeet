/**
 * Automatic food image assignment for bulk CSV listings.
 *
 * Strategy (in priority order):
 *  1. Keyword match on the listing title (most specific)
 *  2. Category fallback pool — deterministically picked via title hash
 *     so the same CSV always produces the same images.
 *
 * All photo IDs are from Unsplash and are already used / verified
 * within this codebase (see scripts/add-sample-food-listings.js).
 */

const BASE = 'https://images.unsplash.com/photo-'
const PARAMS = '?w=400&q=80&auto=format&fit=crop'

const u = (id) => `${BASE}${id}${PARAMS}`

// ─── Keyword → image map (checked via substring, case-insensitive) ────────────
// Order matters — more specific keywords should come first.
const KEYWORD_IMAGES = [
  // Fruit
  [['apple', 'apples'], u('1619566636858-adf3ef46400b')],
  [['banana', 'bananas'], u('1571771894821-ce9b6c11b08e')],
  [['orange', 'citrus', 'lemon', 'lime', 'grapefruit'], u('1547514701-42782101795e')],
  [['strawberr', 'berr', 'blueberr', 'raspberr'], u('1464965911861-746a04b4bca6')],
  [['grape', 'grapes'], u('1537640538966-79f369143f8f')],
  [['peach', 'plum', 'apricot', 'nectarine'], u('1528825871115-3581a5387919')],
  [['mango', 'pineapple', 'papaya'], u('1550258987-190a2d41a8ba')],
  [['watermelon', 'melon', 'cantaloupe'], u('1563114773-84221bd62daa')],
  [['avocado'], u('1523049673857-eb18f1ddf950')],
  // Vegetables
  [['tomato', 'tomatoes'], u('1546470427-e26264be0b0d')],
  [['carrot', 'carrots'], u('1598170845058-32b9d6a5da37')],
  [['broccoli'], u('1459411621453-7b03977f4bfc')],
  [['lettuce', 'salad', 'greens', 'spinach', 'kale'], u('1540420773420-3366772f4999')],
  [['potato', 'potatoes', 'yam', 'sweet potato'], u('1518977676693-5ba7e0c27fb4')],
  [['onion', 'garlic'], u('1518977676693-5ba7e0c27fb4')],
  [['pepper', 'peppers', 'bell pepper'], u('1525609004556-c46c7d6cf023')],
  [['corn', 'zucchini', 'squash', 'cucumber'], u('1542838132-92c53300491e')],
  [['vegetable', 'vegetables', 'veggies', 'mixed veg', 'produce'], u('1542838132-92c53300491e')],
  // Bakery
  [['bread', 'loaf', 'loaves', 'sourdough', 'baguette'], u('1608198093002-ad4e005484ec')],
  [['muffin', 'cupcake', 'cake', 'pastry', 'croissant', 'danish'], u('1551024601-bec78aea704b')],
  [['cookie', 'cookies', 'brownie', 'donut'], u('1499636136210-6f4ee915583a')],
  [['bagel', 'roll', 'rolls', 'bun', 'buns'], u('1509440159596-0249088772ff')],
  [['tortilla', 'wrap', 'pita'], u('1621996659397-5b5e3f4e7d34')],
  // Dairy & eggs
  [['egg', 'eggs'], u('1582722872445-44dc5f7e3c8f')],
  [['milk', 'dairy', 'yogurt', 'yoghurt', 'cream', 'butter'], u('1563636619-e9143da7973b')],
  [['cheese'], u('1486297678162-eb2a19b0a32d')],
  // Meat & protein
  [['chicken', 'poultry', 'turkey'], u('1604908176997-125f25cc6f3d')],
  [['beef', 'steak', 'burger', 'ground beef', 'hamburger'], u('1558030006-da6fa8fb6f27')],
  [['pork', 'bacon', 'sausage', 'ham'], u('1529042410759-befb1204b468')],
  [['fish', 'salmon', 'tuna', 'seafood', 'shrimp'], u('1580476262798-bddd9f4b7369')],
  // Pantry / dry goods
  [['rice'], u('1586201375761-83865001e31c')],
  [['pasta', 'spaghetti', 'noodle', 'noodles'], u('1551462147-37885acc36f1')],
  [['bean', 'beans', 'lentil', 'lentils', 'chickpea'], u('1515543904431-90b4b23dc9bd')],
  [['soup', 'broth', 'stew', 'canned'], u('1593759608892-b0033064e78c')],
  [['oat', 'oatmeal', 'cereal', 'granola'], u('1606312619070-d48b4c652a52')],
  [['oil', 'olive oil', 'vegetable oil'], u('1474979266404-7f4b342668a3')],
  [['flour', 'sugar', 'salt', 'spice', 'condiment'], u('1556909211-36987daf7b4d')],
  [['coffee', 'tea', 'drink', 'juice', 'beverage'], u('1461023058943-362d6d1c2d0d')],
  [['snack', 'chip', 'chips', 'cracker', 'bar', 'bars'], u('1606312619070-d48b4c652a52')],
  // Prepared
  [['meal', 'ready', 'cooked', 'prepared', 'leftovers', 'dinner', 'lunch', 'breakfast'], u('1504674900247-0877df9cc836')],
  [['sandwich', 'wrap'], u('1528735602780-2552fd46c7f1')],
  [['salad'], u('1540420773420-3366772f4999')],
  [['soup'], u('1476718406336-4b0cf2c7f74e')],
]

// ─── Category fallback pools ────────────────────────────────────────────────
const CATEGORY_POOLS = {
  produce: [
    u('1542838132-92c53300491e'), // mixed veg
    u('1619566636858-adf3ef46400b'), // apples
    u('1571771894821-ce9b6c11b08e'), // bananas
    u('1547514701-42782101795e'), // citrus
    u('1553395572-0ef353fd1077'), // market produce
  ],
  bakery: [
    u('1608198093002-ad4e005484ec'), // bread
    u('1551024601-bec78aea704b'), // pastry
    u('1499636136210-6f4ee915583a'), // cookies
    u('1509440159596-0249088772ff'), // bagel
  ],
  dairy: [
    u('1628088062854-d1870b4553da'), // dairy bundle
    u('1582722872445-44dc5f7e3c8f'), // eggs
    u('1563636619-e9143da7973b'), // milk
    u('1486297678162-eb2a19b0a32d'), // cheese
  ],
  pantry: [
    u('1586201375761-83865001e31c'), // rice
    u('1593759608892-b0033064e78c'), // canned goods
    u('1551462147-37885acc36f1'), // pasta
    u('1606312619070-d48b4c652a52'), // granola
  ],
  meat: [
    u('1604908176997-125f25cc6f3d'), // chicken
    u('1558030006-da6fa8fb6f27'), // beef
    u('1580476262798-bddd9f4b7369'), // fish
  ],
  prepared: [
    u('1504674900247-0877df9cc836'), // cooked meal
    u('1476718406336-4b0cf2c7f74e'), // bowl of soup
    u('1540420773420-3366772f4999'), // salad
  ],
  other: [
    u('1512621776951-a57141f2eefd'), // fruit bowl
    u('1610832958506-aa56368176cf'), // produce market
    u('1498557850523-fd3d118b962e'), // food assortment
  ],
}

/**
 * Simple non-cryptographic string hash → stable integer.
 * Used so the same title always maps to the same pool image.
 */
function hashString(str) {
  let h = 0
  for (let i = 0; i < str.length; i++) {
    h = (Math.imul(31, h) + str.charCodeAt(i)) | 0
  }
  return Math.abs(h)
}

/**
 * Return a relevant Unsplash image URL for a listing row.
 * Checks keyword matches first, then falls back to the category pool.
 *
 * @param {{ title: string, category: string }} row
 * @returns {string} absolute image URL
 */
export function assignFoodImage(row) {
  const lower = String(row.title || '').toLowerCase()

  // 1. Keyword match (first wins)
  for (const [keywords, url] of KEYWORD_IMAGES) {
    if (keywords.some(kw => lower.includes(kw))) return url
  }

  // 2. Category pool with deterministic selection
  const pool = CATEGORY_POOLS[row.category] || CATEGORY_POOLS.other
  return pool[hashString(lower) % pool.length]
}

/**
 * Apply assignFoodImage to an array of listing rows in-place (mutates copies).
 * Only assigns an image when the row doesn't already have one.
 *
 * @param {object[]} rows
 * @returns {object[]} new array with image_url populated
 */
export function assignImagestoRows(rows) {
  return rows.map(row => ({
    ...row,
    image_url: row.image_url || assignFoodImage(row),
  }))
}
