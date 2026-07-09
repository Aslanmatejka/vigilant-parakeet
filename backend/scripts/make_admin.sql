-- Make aslanabdulkarim84@gmail.com an admin
UPDATE users 
SET role = 'admin' 
WHERE email = 'aslanabdulkarim84@gmail.com';

-- Verify the update
SELECT id, name, email, role 
FROM users 
WHERE email = 'aslanabdulkarim84@gmail.com';
