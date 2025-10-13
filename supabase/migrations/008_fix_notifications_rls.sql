-- Fix notifications RLS policy - add missing INSERT policy
-- The notifications table had RLS enabled but was missing an INSERT policy
-- This was causing "new row violates row-level security policy" errors

-- Add INSERT policy for notifications
-- Allow system/triggers to insert notifications for any user
CREATE POLICY "System can create notifications" ON notifications FOR INSERT WITH CHECK (true);

-- Also allow authenticated users to create notifications (for potential future features)
CREATE POLICY "Authenticated users can create notifications" ON notifications FOR INSERT 
WITH CHECK (auth.role() = 'authenticated');
