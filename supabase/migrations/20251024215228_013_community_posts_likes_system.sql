/*
  # Community Posts Likes System

  1. Changes
    - Create `post_likes` table to track individual user likes
    - Add `image_url` column to `community_posts` for testimony images
    - Add `post_type` column to distinguish between testimonies, forum posts, and blogs
    - Update RLS policies to restrict post creation to admins only
    - Allow all authenticated users to like posts

  2. Security
    - Enable RLS on `post_likes` table
    - Only admins can create, update, delete posts
    - All users can view posts
    - Authenticated users can like/unlike posts
    - Users can view their own likes

  3. Real-time Support
    - Designed for real-time subscriptions
    - Likes count updated via triggers
*/

-- Create post_type enum
DO $$ BEGIN
  CREATE TYPE post_type AS ENUM ('testimony', 'forum', 'blog', 'announcement');
EXCEPTION
  WHEN duplicate_object THEN null;
END $$;

-- Add columns to community_posts if they don't exist
DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM information_schema.columns
    WHERE table_name = 'community_posts' AND column_name = 'image_url'
  ) THEN
    ALTER TABLE community_posts ADD COLUMN image_url TEXT;
  END IF;

  IF NOT EXISTS (
    SELECT 1 FROM information_schema.columns
    WHERE table_name = 'community_posts' AND column_name = 'post_type'
  ) THEN
    ALTER TABLE community_posts ADD COLUMN post_type post_type DEFAULT 'forum';
  END IF;

  IF NOT EXISTS (
    SELECT 1 FROM information_schema.columns
    WHERE table_name = 'community_posts' AND column_name = 'published'
  ) THEN
    ALTER TABLE community_posts ADD COLUMN published BOOLEAN DEFAULT true;
  END IF;
END $$;

-- Create post_likes table
CREATE TABLE IF NOT EXISTS post_likes (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  post_id UUID REFERENCES community_posts(id) ON DELETE CASCADE NOT NULL,
  user_id UUID REFERENCES users(id) ON DELETE CASCADE NOT NULL,
  created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
  UNIQUE(post_id, user_id)
);

-- Create index for better performance
CREATE INDEX IF NOT EXISTS idx_post_likes_post_id ON post_likes(post_id);
CREATE INDEX IF NOT EXISTS idx_post_likes_user_id ON post_likes(user_id);

-- Function to update likes count
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
    SET likes_count = GREATEST(likes_count - 1, 0)
    WHERE id = OLD.post_id;
    RETURN OLD;
  END IF;
  RETURN NULL;
END;
$$ LANGUAGE plpgsql;

-- Create trigger for likes count
DROP TRIGGER IF EXISTS trigger_update_post_likes_count ON post_likes;
CREATE TRIGGER trigger_update_post_likes_count
AFTER INSERT OR DELETE ON post_likes
FOR EACH ROW EXECUTE FUNCTION update_post_likes_count();

-- Enable RLS
ALTER TABLE post_likes ENABLE ROW LEVEL SECURITY;

-- Drop existing policies on community_posts if they exist
DROP POLICY IF EXISTS "Anyone can view published posts" ON community_posts;
DROP POLICY IF EXISTS "Authenticated users can create posts" ON community_posts;
DROP POLICY IF EXISTS "Users can update own posts" ON community_posts;
DROP POLICY IF EXISTS "Users can delete own posts" ON community_posts;

-- RLS Policies for community_posts
-- All users can view published posts
CREATE POLICY "Anyone can view published posts"
  ON community_posts FOR SELECT
  USING (published = true);

-- Only admins can create posts
CREATE POLICY "Admins can create posts"
  ON community_posts FOR INSERT
  TO authenticated
  WITH CHECK (
    EXISTS (
      SELECT 1 FROM users
      WHERE users.id = auth.uid()
      AND (users.role = 'admin' OR users.is_admin = true)
    )
  );

-- Only admins can update posts
CREATE POLICY "Admins can update posts"
  ON community_posts FOR UPDATE
  TO authenticated
  USING (
    EXISTS (
      SELECT 1 FROM users
      WHERE users.id = auth.uid()
      AND (users.role = 'admin' OR users.is_admin = true)
    )
  );

-- Only admins can delete posts
CREATE POLICY "Admins can delete posts"
  ON community_posts FOR DELETE
  TO authenticated
  USING (
    EXISTS (
      SELECT 1 FROM users
      WHERE users.id = auth.uid()
      AND (users.role = 'admin' OR users.is_admin = true)
    )
  );

-- RLS Policies for post_likes
-- Users can view all likes
CREATE POLICY "Anyone can view likes"
  ON post_likes FOR SELECT
  USING (true);

-- Authenticated users can like posts
CREATE POLICY "Authenticated users can like posts"
  ON post_likes FOR INSERT
  TO authenticated
  WITH CHECK (auth.uid() = user_id);

-- Users can unlike their own likes
CREATE POLICY "Users can delete own likes"
  ON post_likes FOR DELETE
  TO authenticated
  USING (auth.uid() = user_id);