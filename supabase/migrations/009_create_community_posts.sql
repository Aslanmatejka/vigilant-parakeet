-- Create community_posts table for community discussions
CREATE TABLE community_posts (
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

-- Create indexes for better performance
CREATE INDEX idx_community_posts_author ON community_posts(author_id);
CREATE INDEX idx_community_posts_category ON community_posts(category);
CREATE INDEX idx_community_posts_created_at ON community_posts(created_at);

-- Create trigger to update updated_at timestamp
CREATE OR REPLACE FUNCTION update_community_posts_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trigger_update_community_posts_updated_at
    BEFORE UPDATE ON community_posts
    FOR EACH ROW
    EXECUTE FUNCTION update_community_posts_updated_at();

-- Enable RLS (Row Level Security)
ALTER TABLE community_posts ENABLE ROW LEVEL SECURITY;

-- Create RLS policies
CREATE POLICY "Anyone can view community posts" ON community_posts
    FOR SELECT USING (true);

CREATE POLICY "Authenticated users can create community posts" ON community_posts
    FOR INSERT TO authenticated WITH CHECK (author_id = auth.uid());

CREATE POLICY "Users can update their own community posts" ON community_posts
    FOR UPDATE TO authenticated USING (author_id = auth.uid());

CREATE POLICY "Users can delete their own community posts" ON community_posts
    FOR DELETE TO authenticated USING (author_id = auth.uid());

-- Create community_comments table for post comments
CREATE TABLE community_comments (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    post_id UUID REFERENCES community_posts(id) ON DELETE CASCADE,
    author_id UUID REFERENCES users(id) ON DELETE CASCADE,
    content TEXT NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Create indexes for comments
CREATE INDEX idx_community_comments_post ON community_comments(post_id);
CREATE INDEX idx_community_comments_author ON community_comments(author_id);
CREATE INDEX idx_community_comments_created_at ON community_comments(created_at);

-- Enable RLS for comments
ALTER TABLE community_comments ENABLE ROW LEVEL SECURITY;

-- Create RLS policies for comments
CREATE POLICY "Anyone can view community comments" ON community_comments
    FOR SELECT USING (true);

CREATE POLICY "Authenticated users can create community comments" ON community_comments
    FOR INSERT TO authenticated WITH CHECK (author_id = auth.uid());

CREATE POLICY "Users can update their own community comments" ON community_comments
    FOR UPDATE TO authenticated USING (author_id = auth.uid());

CREATE POLICY "Users can delete their own community comments" ON community_comments
    FOR DELETE TO authenticated USING (author_id = auth.uid());

-- Create function to update post comment count
CREATE OR REPLACE FUNCTION update_post_comments_count()
RETURNS TRIGGER AS $$
BEGIN
    IF TG_OP = 'INSERT' THEN
        UPDATE community_posts 
        SET comments_count = comments_count + 1 
        WHERE id = NEW.post_id;
        RETURN NEW;
    ELSIF TG_OP = 'DELETE' THEN
        UPDATE community_posts 
        SET comments_count = comments_count - 1 
        WHERE id = OLD.post_id;
        RETURN OLD;
    END IF;
    RETURN NULL;
END;
$$ LANGUAGE plpgsql;

-- Create triggers to update comment count
CREATE TRIGGER trigger_update_comments_count_insert
    AFTER INSERT ON community_comments
    FOR EACH ROW
    EXECUTE FUNCTION update_post_comments_count();

CREATE TRIGGER trigger_update_comments_count_delete
    AFTER DELETE ON community_comments
    FOR EACH ROW
    EXECUTE FUNCTION update_post_comments_count();

-- Create community_post_likes table for post likes
CREATE TABLE community_post_likes (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    post_id UUID REFERENCES community_posts(id) ON DELETE CASCADE,
    user_id UUID REFERENCES users(id) ON DELETE CASCADE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    UNIQUE(post_id, user_id)
);

-- Create indexes for likes
CREATE INDEX idx_community_post_likes_post ON community_post_likes(post_id);
CREATE INDEX idx_community_post_likes_user ON community_post_likes(user_id);

-- Enable RLS for likes
ALTER TABLE community_post_likes ENABLE ROW LEVEL SECURITY;

-- Create RLS policies for likes
CREATE POLICY "Anyone can view community post likes" ON community_post_likes
    FOR SELECT USING (true);

CREATE POLICY "Authenticated users can like posts" ON community_post_likes
    FOR INSERT TO authenticated WITH CHECK (user_id = auth.uid());

CREATE POLICY "Users can unlike their own likes" ON community_post_likes
    FOR DELETE TO authenticated USING (user_id = auth.uid());

-- Create function to update post likes count
CREATE OR REPLACE FUNCTION update_post_likes_count()
RETURNS TRIGGER AS $$
BEGIN
    IF TG_OP = 'INSERT' THEN
        UPDATE community_posts 
        SET likes_count = likes_count + 1 
        WHERE id = NEW.post_id;
        RETURN NEW;
    ELSIF TG_OP = 'DELETE' THEN
        UPDATE community_posts 
        SET likes_count = likes_count - 1 
        WHERE id = OLD.post_id;
        RETURN OLD;
    END IF;
    RETURN NULL;
END;
$$ LANGUAGE plpgsql;

-- Create triggers to update likes count
CREATE TRIGGER trigger_update_likes_count_insert
    AFTER INSERT ON community_post_likes
    FOR EACH ROW
    EXECUTE FUNCTION update_post_likes_count();

CREATE TRIGGER trigger_update_likes_count_delete
    AFTER DELETE ON community_post_likes
    FOR EACH ROW
    EXECUTE FUNCTION update_post_likes_count();
