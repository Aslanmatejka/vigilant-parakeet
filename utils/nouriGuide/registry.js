/**
 * Unified step registry — maps chat guided steps ↔ form DOM fields.
 * Mirrors backend _SHARE_GUIDED_UI / _REQUEST_GUIDED_UI / _FIND_GUIDED_UI indices.
 */

/** @typedef {{ fieldName?: string, section: string, label: string, dataGuideField?: string }} GuideStepMeta */

/** @typedef {{ formId: string, route: string, goal: string, welcome: string, steps: GuideStepMeta[] }} GoalRegistryEntry */

export const NOURI_GOALS = {
  'share-food': {
    formId: 'share-food',
    route: '/share',
    goal: 'share food',
    welcome:
      'Welcome! This form has two sections: donor information at the top, and food listing details below. Click or tap any field whenever you need help.',
    // Keep indices aligned with backend `_SHARE_GUIDED_UI` (one field per step).
    steps: [
      { section: 'Open Share Food', label: 'Open Share Food', fieldName: '' },
      { section: 'Your name', label: 'Name / Organization', fieldName: 'donor_name' },
      { section: 'Donor type', label: 'Donor Type', fieldName: 'donor_type' },
      { section: 'ZIP code', label: 'ZIP Code', fieldName: 'donor_zip' },
      { section: 'City', label: 'City', fieldName: 'donor_city' },
      { section: 'State', label: 'State', fieldName: 'donor_state' },
      { section: 'Community', label: 'Community', fieldName: 'school_district' },
      { section: 'Email or phone', label: 'Email', fieldName: 'donor_email' },
      { section: 'Pickup address', label: 'Pickup Address', fieldName: 'full_address' },
      { section: 'Food name', label: 'Food Name', fieldName: 'title' },
      { section: 'Category', label: 'Category', fieldName: 'category' },
      { section: 'Description', label: 'Description', fieldName: 'description' },
      { section: 'Quantity', label: 'Quantity', fieldName: 'quantity' },
      { section: 'Unit', label: 'Unit', fieldName: 'unit' },
      { section: 'Expiration', label: 'Expiration Date', fieldName: 'expiry_date' },
      { section: 'Photo & submit', label: 'Photo & Submit', fieldName: 'image' },
    ],
  },
  'request-food': {
    formId: 'request-food',
    route: '/request',
    goal: 'request food',
    welcome:
      "Welcome! I'll guide you step by step through your food request. Click or tap any field whenever you need help.",
    steps: [
      { section: 'Open Request Food', label: 'Food Needed', fieldName: 'title' },
      { section: 'Request form', label: 'Category & Quantity', fieldName: 'category' },
      { section: 'Request form', label: 'Community', fieldName: 'school_district' },
      { section: 'Request form', label: 'Contact Info', fieldName: 'requester_name' },
      { section: 'Submit request', label: 'Submit', fieldName: 'requester_email' },
    ],
  },
  'claim-food': {
    formId: 'claim-food',
    route: '/claim',
    goal: 'claim food',
    welcome:
      "Welcome! I'll guide you step by step through confirming your claim. Click or tap any field whenever you need help.",
    steps: [
      { section: 'Claim', label: 'Portions', dataGuideField: 'claimQty' },
    ],
  },
  'find-food': {
    formId: 'find-food',
    route: '/find',
    goal: 'find food',
    welcome: 'Browse available food listings or tell Nouri what you need.',
    steps: [
      { section: 'Open Find Food', label: 'Browse listings', fieldName: 'search' },
      { section: 'Find Food — search', label: 'Search', fieldName: 'search' },
      { section: 'Claim food', label: 'Claim', dataGuideField: 'claimQty' },
    ],
  },
  login: {
    formId: 'login',
    route: '/login',
    goal: 'sign in',
    welcome: 'Sign in with your email and password.',
    steps: [
      { section: 'Sign in', label: 'Email', fieldName: 'email' },
      { section: 'Sign in', label: 'Password', fieldName: 'password' },
    ],
  },
  signup: {
    formId: 'signup',
    route: '/signup',
    goal: 'sign up',
    welcome: 'Create your DoGoods account.',
    steps: [
      { section: 'Account', label: 'Name', fieldName: 'name' },
      { section: 'Account', label: 'Email', fieldName: 'email' },
      { section: 'Approval', label: 'Approval number', fieldName: 'approvalNumber' },
      { section: 'Security', label: 'Password', fieldName: 'password' },
      { section: 'Submit', label: 'Terms', fieldName: 'agreeToTerms' },
    ],
  },
  receipts: {
    formId: 'receipts',
    route: '/receipts',
    goal: 'receipts',
    welcome: 'View your food pickup receipts.',
    steps: [
      { section: 'Receipts', label: 'Filter tabs', dataGuideField: 'receiptsTabs' },
    ],
  },
  'bulk-upload': {
    formId: 'bulk-upload',
    route: '/listings',
    goal: 'bulk upload',
    welcome: 'Upload multiple listings with a CSV file.',
    steps: [
      { section: 'Upload', label: 'CSV file', fieldName: 'csvFile' },
      { section: 'Details', label: 'Location', fieldName: 'location' },
    ],
  },
}

/** @param {string} formId */
export function getGoalByFormId(formId) {
  return Object.values(NOURI_GOALS).find((g) => g.formId === formId) || null
}

/** @param {string} goalPhrase e.g. "share food" */
export function getGoalByPhrase(goalPhrase) {
  const t = (goalPhrase || '').toLowerCase()
  if (t.includes('share')) return NOURI_GOALS['share-food']
  if (t.includes('request')) return NOURI_GOALS['request-food']
  if (t.includes('claim')) return NOURI_GOALS['claim-food']
  if (t.includes('find')) return NOURI_GOALS['find-food']
  return null
}

/** @param {string} goalKey */
export function getStepMeta(goalKey, stepIndex) {
  const goal = NOURI_GOALS[goalKey]
  if (!goal) return null
  return goal.steps[stepIndex] || null
}

/** Resolve guided step index from a live form field name. */
export function getStepIndexForField(goalKey, fieldName) {
  const goal = NOURI_GOALS[goalKey]
  if (!goal || !fieldName) return -1
  // Prefer the first non-empty matching field (skip open step with blank fieldName).
  const idx = goal.steps.findIndex((s) => s.fieldName === fieldName)
  return idx
}

export function goalKeyFromFormId(formId) {
  const entry = Object.entries(NOURI_GOALS).find(([, g]) => g.formId === formId)
  return entry ? entry[0] : null
}

/** Map formId string to goal key (supports registry keys). */
export function resolveGoalKey(formId) {
  if (NOURI_GOALS[formId]) return formId
  return goalKeyFromFormId(formId)
}
