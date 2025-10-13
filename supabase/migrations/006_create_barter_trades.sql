-- Create barter trades table
CREATE TABLE barter_trades (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    initiator_id UUID REFERENCES users(id) ON DELETE CASCADE,
    offered_listing_id UUID REFERENCES food_listings(id) ON DELETE SET NULL,
    requested_items JSONB NOT NULL, -- Array of requested items
    trade_type VARCHAR(20) DEFAULT 'direct' CHECK (trade_type IN ('direct', 'multi-item', 'open')),
    status VARCHAR(20) DEFAULT 'pending' CHECK (status IN ('pending', 'accepted', 'declined', 'completed', 'cancelled', 'counter_offered')),
    message TEXT,
    analysis JSONB, -- AI analysis results
    original_trade_id UUID REFERENCES barter_trades(id) ON DELETE SET NULL, -- For counter offers
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Create indexes for better performance
CREATE INDEX idx_barter_trades_initiator ON barter_trades(initiator_id);
CREATE INDEX idx_barter_trades_status ON barter_trades(status);
CREATE INDEX idx_barter_trades_trade_type ON barter_trades(trade_type);
CREATE INDEX idx_barter_trades_created_at ON barter_trades(created_at);
CREATE INDEX idx_barter_trades_offered_listing ON barter_trades(offered_listing_id);

-- Create trigger to update updated_at timestamp
CREATE OR REPLACE FUNCTION update_barter_trades_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trigger_update_barter_trades_updated_at
    BEFORE UPDATE ON barter_trades
    FOR EACH ROW
    EXECUTE FUNCTION update_barter_trades_updated_at();

-- Enable RLS (Row Level Security)
ALTER TABLE barter_trades ENABLE ROW LEVEL SECURITY;

-- Create RLS policies
CREATE POLICY "Users can view barter trades they are involved in" ON barter_trades
    FOR SELECT USING (
        initiator_id = auth.uid() OR
        EXISTS (
            SELECT 1 FROM food_listings fl 
            WHERE fl.id = offered_listing_id 
            AND fl.user_id = auth.uid()
        )
    );

CREATE POLICY "Users can create barter trades" ON barter_trades
    FOR INSERT WITH CHECK (initiator_id = auth.uid());

CREATE POLICY "Users can update their own barter trades" ON barter_trades
    FOR UPDATE USING (
        initiator_id = auth.uid() OR
        EXISTS (
            SELECT 1 FROM food_listings fl 
            WHERE fl.id = offered_listing_id 
            AND fl.user_id = auth.uid()
        )
    );

CREATE POLICY "Users can delete their own barter trades" ON barter_trades
    FOR DELETE USING (initiator_id = auth.uid());

-- Create function to notify on trade updates
CREATE OR REPLACE FUNCTION notify_barter_trade_update()
RETURNS TRIGGER AS $$
BEGIN
    -- Notify the initiator
    IF TG_OP = 'INSERT' THEN
        INSERT INTO notifications (user_id, type, title, message, data)
        VALUES (
            NEW.initiator_id,
            'trade_created',
            'Barter Trade Created',
            'Your barter trade offer has been posted.',
            jsonb_build_object('trade_id', NEW.id)
        );
    ELSIF TG_OP = 'UPDATE' AND OLD.status != NEW.status THEN
        -- Notify status changes
        INSERT INTO notifications (user_id, type, title, message, data)
        VALUES (
            NEW.initiator_id,
            'trade_status_update',
            'Trade Status Updated',
            'Your barter trade status has been updated to: ' || NEW.status,
            jsonb_build_object('trade_id', NEW.id, 'status', NEW.status)
        );
    END IF;
    
    RETURN COALESCE(NEW, OLD);
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trigger_notify_barter_trade_update
    AFTER INSERT OR UPDATE ON barter_trades
    FOR EACH ROW
    EXECUTE FUNCTION notify_barter_trade_update();

-- Add sample data for testing
INSERT INTO barter_trades (
    initiator_id,
    offered_listing_id,
    requested_items,
    trade_type,
    message,
    status
) VALUES (
    (SELECT id FROM users LIMIT 1),
    (SELECT id FROM food_listings WHERE listing_type = 'trade' LIMIT 1),
    '[
        {
            "title": "Fresh Tomatoes",
            "quantity": 2,
            "unit": "kg",
            "category": "produce",
            "description": "Ripe red tomatoes"
        },
        {
            "title": "Organic Lettuce",
            "quantity": 3,
            "unit": "heads",
            "category": "produce"
        }
    ]'::jsonb,
    'multi-item',
    'Looking to trade my homemade bread for fresh vegetables. These tomatoes and lettuce would be perfect for my family.',
    'pending'
);
