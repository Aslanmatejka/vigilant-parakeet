-- Re-enable RLS with better policies
ALTER TABLE barter_trades ENABLE ROW LEVEL SECURITY;

-- Drop existing policies
DROP POLICY IF EXISTS "Users can view barter trades they are involved in" ON barter_trades;
DROP POLICY IF EXISTS "Users can create barter trades" ON barter_trades;
DROP POLICY IF EXISTS "Users can update their own barter trades" ON barter_trades;
DROP POLICY IF EXISTS "Users can delete their own barter trades" ON barter_trades;

-- Create more permissive policies for testing
CREATE POLICY "Allow authenticated users to view all barter trades" ON barter_trades
    FOR SELECT TO authenticated USING (true);

CREATE POLICY "Allow authenticated users to create barter trades" ON barter_trades
    FOR INSERT TO authenticated WITH CHECK (initiator_id = auth.uid());

CREATE POLICY "Allow authenticated users to update their own barter trades" ON barter_trades
    FOR UPDATE TO authenticated USING (initiator_id = auth.uid());

CREATE POLICY "Allow authenticated users to delete their own barter trades" ON barter_trades
    FOR DELETE TO authenticated USING (initiator_id = auth.uid());
