-- Create blog_posts table referenced by pages/Blog.jsx via dataService.getBlogPosts().
-- Without this table the Blog page always errored silently showing no posts.
CREATE TABLE IF NOT EXISTS blog_posts (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    author_id UUID REFERENCES users(id) ON DELETE SET NULL,
    title TEXT NOT NULL,
    slug TEXT UNIQUE NOT NULL,
    excerpt TEXT,
    content TEXT,
    category TEXT DEFAULT 'general',
    tags TEXT[],
    image_url TEXT,
    published BOOLEAN DEFAULT false,
    published_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now()
);

ALTER TABLE blog_posts ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Anyone can read published blog posts"
    ON blog_posts FOR SELECT
    USING (published = true);

CREATE POLICY "Admins can manage blog posts"
    ON blog_posts FOR ALL
    USING (EXISTS (SELECT 1 FROM users WHERE id = (SELECT auth.uid()) AND is_admin = true));
