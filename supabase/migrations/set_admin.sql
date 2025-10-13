-- Check and set admin status for your user
-- Run this in the Supabase SQL editor

-- Check your admin status
SELECT id, email, is_admin FROM users 
WHERE id = 'c4dcbd93-081e-4160-87eb-1d51d444413a';

-- If needed, update your user to be an admin
UPDATE users 
SET is_admin = true
WHERE id = 'c4dcbd93-081e-4160-87eb-1d51d444413a'
RETURNING id, email, is_admin;
