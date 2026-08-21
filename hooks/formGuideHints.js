/**
 * Central hint maps for all guided forms/pages.
 */

export const SHARE_FOOD_WELCOME =
  'Welcome! This form has two sections: donor information at the top, and food listing details below. Click or tap any field whenever you need help.'

export const REQUEST_FOOD_WELCOME =
  "Welcome! I'll guide you step by step through your food request. Click or tap any field whenever you need help."

export const CLAIM_FOOD_WELCOME =
  "Welcome! I'll guide you step by step through confirming your claim. Click or tap any field whenever you need help."

export const LOGIN_WELCOME =
  'Welcome! Enter your email and password to sign in. Tap any field for help.'

export const SIGNUP_WELCOME =
  'Welcome! I will guide you through creating your account one step at a time.'

export const FIND_FOOD_WELCOME =
  'Browse food listings below. Use search and filters, or ask Nouri in chat to find something for you.'

export const RECEIPTS_WELCOME =
  'Your pickup receipts are listed here. Tap a tab to filter by status.'

export const BULK_UPLOAD_WELCOME =
  'Upload a CSV file with your food listings. I can guide you through each step.'

export const SHARE_FOOD_HINTS = {
  donor_name: { label: 'Name / Organization', text: 'Donor information. Enter your full name, or your organization name if you are donating on behalf of a group.' },
  donor_type: { label: 'Donor Type', text: 'Donor information. Choose Individual or Family for personal donations, or Organization for a business or group.' },
  donor_zip: { label: 'ZIP Code', text: 'Donor information. Enter the ZIP code for the pickup area.' },
  donor_city: { label: 'City', text: 'Donor information. Enter the city where recipients will pick up the food.' },
  donor_state: { label: 'State', text: 'Donor information. Select the state for the pickup location.' },
  school_district: { label: 'Community', text: 'Donor information. Choose the community or school this donation belongs to.' },
  donor_email: { label: 'Email', text: 'Donor information. Enter your email so recipients can reach you if needed.' },
  donor_phone: { label: 'Phone', text: 'Donor information. Optional — add a phone number if you want to be reachable by phone.' },
  full_address: { label: 'Pickup Address', text: 'Donor information. Enter the full street address where food will be picked up. We will locate it on the map.' },
  donor_occupation: { label: 'Occupation / Role', text: 'Donor information. Optional — your occupation or role, such as Teacher or Chef.' },
  title: { label: 'Food Name', text: 'Food listing. What are you donating? Enter a short name, like Apples, Rice, or Homemade Bread.' },
  category: { label: 'Category', text: 'Food listing. Select the food category, such as Fresh Produce, Dairy, or Bakery.' },
  description: { label: 'Description', text: 'Food listing. Describe the food — its condition, source, and anything recipients should know.' },
  quantity: { label: 'Quantity', text: 'Food listing. Enter how much food you have.' },
  unit: { label: 'Unit', text: 'Food listing. Choose the unit for the quantity, such as pounds, kilograms, or count.' },
  expiry_date: { label: 'Expiration Date', text: 'Food listing. Enter the expiration or best-before date so recipients know how fresh it is.' },
  pickup_by: { label: 'Pickup Deadline', text: 'Food listing. Optional — set a date and time by which the food must be picked up.' },
  dietary_tags: { label: 'Dietary Information', text: 'Food listing. Optional — check any dietary labels that apply, such as Vegetarian or Gluten-Free.' },
  allergens: { label: 'Allergens', text: 'Food listing. Optional — check all allergens present so recipients with restrictions stay safe.' },
  ingredients: { label: 'Ingredients', text: 'Food listing. Optional — list main ingredients if this is prepared or packaged food.' },
  image: { label: 'Photo', text: 'Food listing. Upload a real photo of the food — required before you can submit. Clear photos help recipients decide faster.' },
}

export const REQUEST_FOOD_HINTS = {
  title: { label: 'Food Needed', text: 'What food do you need? Enter the name or type, such as Rice or Fresh Vegetables.' },
  category: { label: 'Category', text: 'Select the category that best matches the food you are looking for.' },
  quantity: { label: 'Quantity', text: 'Enter how much you need.' },
  unit: { label: 'Unit', text: 'Choose the unit for your quantity, such as items, pounds, or bags.' },
  needed_by: { label: 'Needed By', text: 'Optional — enter the date you need this food by.' },
  school_district: { label: 'Community', text: 'Choose your school or community so nearby donors can see your request.' },
  description: { label: 'Details', text: 'Optional — add details like household size or why you need this food.' },
  dietary_notes: { label: 'Dietary Needs', text: 'Optional — list dietary needs such as gluten-free or nut allergy.' },
  requester_name: { label: 'Your Name', text: 'Contact information. Enter your name so donors know who the request is from.' },
  requester_email: { label: 'Email', text: 'Contact information. Enter your email so donors or admins can reach you.' },
  requester_phone: { label: 'Phone', text: 'Contact information. Optional — add a phone number if you prefer phone contact.' },
  full_address: { label: 'Pickup Area', text: 'Optional — enter your neighborhood or address to help donors near you.' },
}

export const CLAIM_FOOD_HINTS = {
  claimQty: { label: 'Portions', text: 'Use the plus and minus buttons to choose how many portions you want, then press Confirm Claim.' },
}

export const LOGIN_HINTS = {
  email: { label: 'Email', text: 'Enter the email address you used when you signed up.' },
  password: { label: 'Password', text: 'Enter your password. It must be at least 8 characters.' },
  rememberMe: { label: 'Remember me', text: 'Optional — keep you signed in on this device.' },
}

export const SIGNUP_HINTS = {
  name: { label: 'Full name', text: 'Enter your full name as you want it to appear in the app.' },
  email: { label: 'Email', text: 'Enter a valid email. You will need to confirm it before signing in.' },
  approvalNumber: { label: 'Approval number', text: 'Enter the code from your school community closet. Format: 3 letters and 6 digits, like RBE123456.' },
  phone: { label: 'Phone', text: 'Optional unless you want SMS alerts about claims and pickups.' },
  password: { label: 'Password', text: 'Choose a password at least 8 characters long.' },
  confirmPassword: { label: 'Confirm password', text: 'Type the same password again to confirm.' },
  agreeToTerms: { label: 'Terms', text: 'You must agree to the terms and conditions to create an account.' },
}

export const FIND_FOOD_HINTS = {
  search: { label: 'Search', text: 'Type what you are looking for, like rice, apples, or bread.' },
  category: { label: 'Category', text: 'Filter by food category to narrow results.' },
  sortBy: { label: 'Sort', text: 'Sort by expiring soon, nearest, or newest listings.' },
}

export const RECEIPTS_HINTS = {
  receiptsTabs: { label: 'Receipt filters', text: 'Choose All, Pending, Completed, or Expired to filter your receipts.' },
}

export const BULK_UPLOAD_HINTS = {
  csvFile: { label: 'CSV file', text: 'Upload a CSV with columns: title, description, quantity, unit, category, expiryDate.' },
  location: { label: 'Location', text: 'Optional default pickup location applied to rows in the CSV.' },
  notes: { label: 'Notes', text: 'Optional notes for this bulk upload batch.' },
}

/** @type {Record<string, { formId: string, welcome: string, hints: Record<string, { label: string, text: string }> }>} */
export const FORM_GUIDE_CONFIG = {
  'share-food': { formId: 'share-food', welcome: SHARE_FOOD_WELCOME, hints: SHARE_FOOD_HINTS },
  'request-food': { formId: 'request-food', welcome: REQUEST_FOOD_WELCOME, hints: REQUEST_FOOD_HINTS },
  'claim-food': { formId: 'claim-food', welcome: CLAIM_FOOD_WELCOME, hints: CLAIM_FOOD_HINTS },
  login: { formId: 'login', welcome: LOGIN_WELCOME, hints: LOGIN_HINTS },
  signup: { formId: 'signup', welcome: SIGNUP_WELCOME, hints: SIGNUP_HINTS },
  'find-food': { formId: 'find-food', welcome: FIND_FOOD_WELCOME, hints: FIND_FOOD_HINTS },
  receipts: { formId: 'receipts', welcome: RECEIPTS_WELCOME, hints: RECEIPTS_HINTS },
  'bulk-upload': { formId: 'bulk-upload', welcome: BULK_UPLOAD_WELCOME, hints: BULK_UPLOAD_HINTS },
}
