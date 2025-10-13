-- Drop tables in correct order to avoid FK issues
DROP TABLE IF EXISTS distribution_registrations CASCADE;
DROP TABLE IF EXISTS distribution_events CASCADE;
DROP TABLE IF EXISTS trades CASCADE;
DROP TABLE IF EXISTS user_badges CASCADE;
DROP TABLE IF EXISTS user_stats CASCADE;
DROP TABLE IF EXISTS notifications CASCADE;
DROP TABLE IF EXISTS community_comments CASCADE;
DROP TABLE IF EXISTS community_posts CASCADE;
DROP TABLE IF EXISTS food_claims CASCADE;
DROP TABLE IF EXISTS food_listings CASCADE;
DROP TABLE IF EXISTS users CASCADE;

-- ENUM types (safe drop before create)
DROP TYPE IF EXISTS user_role;
CREATE TYPE user_role AS ENUM ('user', 'admin', 'moderator');
DROP TYPE IF EXISTS user_status;
CREATE TYPE user_status AS ENUM ('active', 'suspended', 'inactive');
DROP TYPE IF EXISTS account_type;
CREATE TYPE account_type AS ENUM ('individual', 'business', 'nonprofit');
DROP TYPE IF EXISTS listing_type;
CREATE TYPE listing_type AS ENUM ('donation');
DROP TYPE IF EXISTS listing_status;
CREATE TYPE listing_status AS ENUM ('pending', 'approved', 'declined', 'active', 'completed', 'expired', 'cancelled');
DROP TYPE IF EXISTS food_category;
CREATE TYPE food_category AS ENUM ('produce', 'bakery', 'dairy', 'pantry', 'meat', 'prepared', 'other');
DROP TYPE IF EXISTS claim_status;
CREATE TYPE claim_status AS ENUM ('pending', 'approved', 'declined');

-- USERS TABLE FIRST
CREATE TABLE IF NOT EXISTS users (
    id UUID PRIMARY KEY REFERENCES auth.users(id) ON DELETE CASCADE,
    email VARCHAR(255) UNIQUE NOT NULL,
    name VARCHAR(255) NOT NULL,
    avatar_url TEXT,
    phone VARCHAR(20),
    organization VARCHAR(255),
    bio TEXT,
    location VARCHAR(255),
    account_type account_type DEFAULT 'individual',
    role user_role DEFAULT 'user',
    status user_status DEFAULT 'active',
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);
    -- Add is_admin column to users table for admin flag
    ALTER TABLE users ADD COLUMN IF NOT EXISTS is_admin BOOLEAN DEFAULT FALSE;
-- Set aslanabdulkarim84@gmail.com as admin
UPDATE users SET is_admin = TRUE WHERE email = 'aslanabdulkarim84@gmail.com';

-- USER STATS
CREATE TABLE IF NOT EXISTS user_stats (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id UUID REFERENCES users(id) ON DELETE CASCADE,
    total_donations INTEGER DEFAULT 0,
    total_food_saved DECIMAL(10,2) DEFAULT 0,
    total_impact_score INTEGER DEFAULT 0,
    last_updated TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS user_badges (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id UUID REFERENCES users(id) ON DELETE CASCADE,
    badge_name VARCHAR(100) NOT NULL,
    badge_description TEXT,
    badge_icon VARCHAR(50),
    earned_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);
-- Remove duplicate and unsafe DROP TYPE statements
DROP FUNCTION IF EXISTS update_updated_at_column() CASCADE;
DROP FUNCTION IF EXISTS update_community_posts_updated_at();
DROP FUNCTION IF EXISTS notify_declined_submission();
DROP FUNCTION IF EXISTS notify_claim_status_change();
-- Enable necessary extensions
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "pgcrypto";



CREATE TABLE IF NOT EXISTS users (
    id UUID PRIMARY KEY REFERENCES auth.users(id) ON DELETE CASCADE,
    email VARCHAR(255) UNIQUE NOT NULL,
    name VARCHAR(255) NOT NULL,
    avatar_url TEXT,
    phone VARCHAR(20),
    organization VARCHAR(255),
    bio TEXT,
    location VARCHAR(255),
    account_type account_type DEFAULT 'individual',
    role user_role DEFAULT 'user',
    status user_status DEFAULT 'active',
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Function to handle new user registration
CREATE OR REPLACE FUNCTION handle_new_user()
RETURNS TRIGGER
SECURITY DEFINER 
SET search_path = public
LANGUAGE plpgsql
AS $$
DECLARE
    new_user_id UUID;
BEGIN
    -- Store the new user's ID
    new_user_id := NEW.id;
    
    -- Create user profile with proper error handling
    BEGIN
        INSERT INTO public.users (
            id,
            email,
            name,
            avatar_url,
            account_type,
            role,
            status
        ) VALUES (
            new_user_id,
            NEW.email,
            COALESCE(NEW.raw_user_meta_data->>'name', NEW.email),
            COALESCE(
                NEW.raw_user_meta_data->>'avatar_url',
                'https://ui-avatars.com/api/?name=' || COALESCE(NEW.raw_user_meta_data->>'name', 'User') || '&background=random'
            ),
            COALESCE(NEW.raw_user_meta_data->>'account_type', 'individual')::account_type,
            'user'::user_role,
            'active'::user_status
        );
    EXCEPTION WHEN OTHERS THEN
        RAISE LOG 'Error creating user profile: %', SQLERRM;
        RETURN NEW;
    END;

    -- Create user stats with proper error handling
    BEGIN
        INSERT INTO public.user_stats (
            user_id,
            total_donations,
            total_food_saved,
            total_impact_score
        ) VALUES (
            new_user_id,
            0,
            0.0,
            0
        );
    EXCEPTION WHEN OTHERS THEN
        RAISE LOG 'Error creating user stats: %', SQLERRM;
    END;

    -- Create initial welcome badge
    BEGIN
        INSERT INTO public.user_badges (
            user_id,
            badge_name,
            badge_description,
            badge_icon
        ) VALUES (
            new_user_id,
            'Welcome',
            'First login badge',
            'star'
        );
    EXCEPTION WHEN OTHERS THEN
        RAISE LOG 'Error creating welcome badge: %', SQLERRM;
    END;

    RETURN NEW;
END;
$$;

-- Create the trigger on auth.users
DROP TRIGGER IF EXISTS on_auth_user_created ON auth.users;
CREATE TRIGGER on_auth_user_created
    AFTER INSERT ON auth.users
    FOR EACH ROW EXECUTE FUNCTION handle_new_user();

-- FOOD LISTINGS
CREATE TABLE IF NOT EXISTS food_listings (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id UUID REFERENCES users(id) ON DELETE CASCADE,
    title VARCHAR(255) NOT NULL,
    description TEXT,
    image_url TEXT,
    quantity DECIMAL(10,2) NOT NULL,
    unit VARCHAR(50) NOT NULL,
    category food_category NOT NULL,
    listing_type listing_type NOT NULL,
    status listing_status DEFAULT 'pending',
    expiry_date DATE,
    location VARCHAR(255),
    donor_name VARCHAR(255),
    donor_email VARCHAR(255),
    donor_phone VARCHAR(50),
    donor_city VARCHAR(255),
    donor_state VARCHAR(100),
    donor_zip VARCHAR(20),
    donor_occupation VARCHAR(255),
    donor_type VARCHAR(50),
    latitude DECIMAL(10,8),
    longitude DECIMAL(11,8),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- INCREMENT IMPACT SCORE ON FOOD SHARE
CREATE OR REPLACE FUNCTION increment_impact_on_food_share()
RETURNS TRIGGER AS $$
BEGIN
    UPDATE user_stats
    SET total_impact_score = total_impact_score + 1
    WHERE user_id = NEW.user_id;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trigger_increment_impact_on_food_share ON food_listings;
CREATE TRIGGER trigger_increment_impact_on_food_share
AFTER INSERT ON food_listings
FOR EACH ROW EXECUTE FUNCTION increment_impact_on_food_share();

-- FOOD CLAIMS
CREATE TABLE IF NOT EXISTS food_claims (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    food_id UUID REFERENCES food_listings(id) ON DELETE CASCADE,
    claimer_id UUID REFERENCES users(id) ON DELETE CASCADE,
    requester_name VARCHAR(255) NOT NULL,
    requester_email VARCHAR(255),
    requester_phone VARCHAR(20),
    school_district VARCHAR(100),
    school VARCHAR(100),
    school_contact VARCHAR(100),
    school_contact_email VARCHAR(100),
    school_contact_phone VARCHAR(20),
    category VARCHAR(50),
    dietary_restrictions VARCHAR(200),
    members_count INTEGER,
    pickup_time TIME,
    pickup_place VARCHAR(100),
    pickup_contact VARCHAR(100),
    dropoff_time TIME,
    dropoff_place VARCHAR(100),
    dropoff_contact VARCHAR(100),
    status claim_status DEFAULT 'pending',
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- COMMUNITY POSTS
CREATE TABLE IF NOT EXISTS community_posts (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    title VARCHAR(255) NOT NULL,
    content TEXT NOT NULL,
    category VARCHAR(100) DEFAULT 'general',
    author_id UUID REFERENCES users(id) ON DELETE CASCADE,
    likes_count INTEGER DEFAULT 0,
    comments_count INTEGER DEFAULT 0,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);
CREATE TABLE IF NOT EXISTS community_comments (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    post_id UUID REFERENCES community_posts(id) ON DELETE CASCADE,
    author_id UUID REFERENCES users(id) ON DELETE CASCADE,
    content TEXT NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- NOTIFICATIONS
CREATE TABLE IF NOT EXISTS notifications (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id UUID REFERENCES users(id) ON DELETE CASCADE,
    title VARCHAR(255) NOT NULL,
    message TEXT NOT NULL,
    type VARCHAR(50) NOT NULL,
    read BOOLEAN DEFAULT FALSE,
    data JSONB,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- USER STATS
CREATE TABLE IF NOT EXISTS user_stats (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id UUID REFERENCES users(id) ON DELETE CASCADE,
    total_donations INTEGER DEFAULT 0,
    total_food_saved DECIMAL(10,2) DEFAULT 0,
    total_impact_score INTEGER DEFAULT 0,
    last_updated TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- USER BADGES
CREATE TABLE IF NOT EXISTS user_badges (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id UUID REFERENCES users(id) ON DELETE CASCADE,
    badge_name VARCHAR(100) NOT NULL,
    badge_description TEXT,
    badge_icon VARCHAR(50),
    earned_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- FOOD DISTRIBUTION EVENTS
CREATE TABLE IF NOT EXISTS distribution_events (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    title VARCHAR(255) NOT NULL,
    description TEXT,
    location VARCHAR(255) NOT NULL,
    latitude DECIMAL(10,8),
    longitude DECIMAL(11,8),
    event_date DATE NOT NULL,
    start_time TIME NOT NULL,
    end_time TIME NOT NULL,
    capacity INTEGER,
    registered_count INTEGER DEFAULT 0,
    status VARCHAR(50) DEFAULT 'scheduled',
    created_by UUID REFERENCES users(id),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);
CREATE TABLE IF NOT EXISTS distribution_registrations (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    event_id UUID REFERENCES distribution_events(id) ON DELETE CASCADE,
    user_id UUID REFERENCES users(id) ON DELETE CASCADE,
    registered_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    attended BOOLEAN DEFAULT FALSE,
    UNIQUE(event_id, user_id)
);

-- INDEXES
CREATE INDEX idx_users_email ON users(email);
-- UPDATE EXISTING BACKEND: Remove trade-related schema
ALTER TABLE user_stats DROP COLUMN IF EXISTS total_trades;
DROP TABLE IF EXISTS trades;
DROP TYPE IF EXISTS trade_status;
CREATE INDEX idx_users_status ON users(status);
CREATE INDEX idx_food_listings_user_id ON food_listings(user_id);
CREATE INDEX idx_food_listings_status ON food_listings(status);
CREATE INDEX idx_food_listings_category ON food_listings(category);
CREATE INDEX idx_food_listings_location ON food_listings(location);
CREATE INDEX idx_notifications_user_id ON notifications(user_id);
CREATE INDEX idx_notifications_read ON notifications(read);
CREATE INDEX idx_community_posts_author ON community_posts(author_id);
CREATE INDEX idx_community_posts_category ON community_posts(category);
CREATE INDEX idx_community_posts_created_at ON community_posts(created_at);
CREATE INDEX idx_community_comments_post ON community_comments(post_id);

-- TRIGGERS & FUNCTIONS
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ language 'plpgsql';
CREATE TRIGGER update_users_updated_at BEFORE UPDATE ON users FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
CREATE TRIGGER update_food_listings_updated_at BEFORE UPDATE ON food_listings FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
CREATE TRIGGER update_distribution_events_updated_at BEFORE UPDATE ON distribution_events FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
CREATE OR REPLACE FUNCTION update_community_posts_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;
CREATE TRIGGER trigger_update_community_posts_updated_at BEFORE UPDATE ON community_posts FOR EACH ROW EXECUTE FUNCTION update_community_posts_updated_at();

-- NOTIFY ON DECLINED FOOD SUBMISSION
CREATE OR REPLACE FUNCTION notify_declined_submission()
RETURNS TRIGGER AS $$
BEGIN
    IF NEW.status = 'declined' AND OLD.status <> 'declined' THEN
        INSERT INTO notifications (user_id, title, message, type, data)
        VALUES (
            NEW.user_id,
            'Food Submission Not Approved',
            'Your food submission was not approved by the admin. Please review the guidelines and try again.',
            'submission_declined',
            jsonb_build_object('listing_id', NEW.id)
        );
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;
DROP TRIGGER IF EXISTS trigger_notify_declined_submission ON food_listings;
CREATE TRIGGER trigger_notify_declined_submission AFTER UPDATE ON food_listings FOR EACH ROW EXECUTE FUNCTION notify_declined_submission();

-- NOTIFY ON CLAIM STATUS CHANGE
CREATE OR REPLACE FUNCTION notify_claim_status_change()
RETURNS TRIGGER AS $$
BEGIN
    IF NEW.status = 'approved' AND OLD.status <> 'approved' THEN
        INSERT INTO notifications (user_id, title, message, type, data)
        VALUES (
            NEW.claimer_id,
            'Food Claim Approved',
            'Your claim for food has been approved! Please check your email for pickup details.',
            'claim_approved',
            jsonb_build_object('claim_id', NEW.id, 'food_id', NEW.food_id)
        );
    ELSIF NEW.status = 'declined' AND OLD.status <> 'declined' THEN
        INSERT INTO notifications (user_id, title, message, type, data)
        VALUES (
            NEW.claimer_id,
            'Food Claim Not Approved',
            'Your claim for food was not approved. Please try again or contact support for more info.',
            'claim_declined',
            jsonb_build_object('claim_id', NEW.id, 'food_id', NEW.food_id)
        );
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;
DROP TRIGGER IF EXISTS trigger_notify_claim_status_change ON food_claims;
CREATE TRIGGER trigger_notify_claim_status_change AFTER UPDATE ON food_claims FOR EACH ROW EXECUTE FUNCTION notify_claim_status_change();

-- RLS POLICIES (add more as needed)
ALTER TABLE users ENABLE ROW LEVEL SECURITY;

-- Drop existing policies to avoid conflicts
DROP POLICY IF EXISTS "Users can create their own profile" ON users;
DROP POLICY IF EXISTS "Allow system trigger to create user profile" ON users;
DROP POLICY IF EXISTS "Users can view own profile" ON users;
DROP POLICY IF EXISTS "Users can update own profile" ON users;
DROP POLICY IF EXISTS "Allow trigger to create profile" ON users;

-- Create new policies
CREATE POLICY "Allow trigger to create profile"
ON users FOR INSERT
WITH CHECK (true);

CREATE POLICY "Users can view own profile"
ON users FOR SELECT
USING (auth.uid() = id);

CREATE POLICY "Users can update own profile"
ON users FOR UPDATE
USING (auth.uid() = id);

CREATE POLICY "Admins can view all profiles"
ON users FOR SELECT
USING ((auth.jwt() ->> 'is_admin')::boolean = true);

CREATE POLICY "Users can view their own profile" ON users
FOR SELECT
USING (auth.uid() = id);
-- NOTE: Admin access to all users is not possible via subquery in RLS due to recursion errors.
-- For admin access, use JWT custom claims or an external admin table. Only allow users to view their own profile.

ALTER TABLE food_listings ENABLE ROW LEVEL SECURITY;
ALTER TABLE user_stats ENABLE ROW LEVEL SECURITY;
CREATE POLICY "Users can create their own stats" ON user_stats
FOR INSERT
WITH CHECK (auth.uid() = user_id);
-- NOTE: Admin access to all stats is not possible via subquery in RLS due to recursion errors.
-- For admin access, use JWT custom claims or an external admin table. Only allow users to view their own stats.
CREATE POLICY "Users can view their own stats" ON user_stats FOR SELECT USING (auth.uid() = user_id);

ALTER TABLE user_badges ENABLE ROW LEVEL SECURITY;
-- Allow users to insert their own badges
CREATE POLICY "Users can create their own badges" ON user_badges
FOR INSERT
WITH CHECK (auth.uid() = user_id);
ALTER TABLE distribution_events ENABLE ROW LEVEL SECURITY;
ALTER TABLE distribution_registrations ENABLE ROW LEVEL SECURITY;
ALTER TABLE notifications ENABLE ROW LEVEL SECURITY;
ALTER TABLE community_posts ENABLE ROW LEVEL SECURITY;
ALTER TABLE community_comments ENABLE ROW LEVEL SECURITY;
ALTER TABLE food_claims ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Anyone can view approved listings" ON food_listings FOR SELECT USING (status = 'approved');
CREATE POLICY "Users can view own listings" ON food_listings FOR SELECT USING (auth.uid() = user_id);
CREATE POLICY "Admins can view all listings" ON food_listings FOR SELECT USING ((auth.jwt() ->> 'is_admin')::boolean = true);
CREATE POLICY "Users can create listings" ON food_listings FOR INSERT WITH CHECK (auth.uid() = user_id);
CREATE POLICY "Users can update own listings" ON food_listings FOR UPDATE USING (auth.uid() = user_id);
CREATE POLICY "Admins can update any listing" ON food_listings FOR UPDATE USING ((auth.jwt() ->> 'is_admin')::boolean = true);

CREATE POLICY "Users can view own claims" ON food_claims FOR SELECT USING (auth.uid() = claimer_id);
CREATE POLICY "Users can create claims" ON food_claims FOR INSERT WITH CHECK (auth.uid() = claimer_id);
-- NOTE: Admin access to all claims is not possible via subquery in RLS due to recursion errors.
-- For admin access, use JWT custom claims or an external admin table. Only allow users to update their own claims.
CREATE POLICY "Users can update own claims" ON food_claims FOR UPDATE USING (auth.uid() = claimer_id);

-- Enable RLS and allow authenticated users to insert notifications
ALTER TABLE notifications ENABLE ROW LEVEL SECURITY;
CREATE POLICY "Allow insert for authenticated users" ON notifications FOR INSERT TO authenticated WITH CHECK (true);

-- Add more policies as needed for other tables

-- Grant necessary permissions
GRANT USAGE ON SCHEMA public TO postgres, anon, authenticated, service_role;
GRANT ALL ON ALL TABLES IN SCHEMA public TO postgres, anon, authenticated, service_role;
GRANT ALL ON ALL SEQUENCES IN SCHEMA public TO postgres, anon, authenticated, service_role;
