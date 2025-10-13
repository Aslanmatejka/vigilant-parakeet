import { Link } from 'react-router-dom';
import Card from '../components/common/Card';
import Avatar from '../components/common/Avatar';
import Button from '../components/common/Button';

import { useBlog } from '../utils/hooks/useSupabase';

const formatDate = (dateString) => {
    if (!dateString) return '';
    return new Date(dateString).toLocaleDateString('en-US', {
        year: 'numeric',
        month: 'long',
        day: 'numeric'
    });
};

function Blog() {
    const {
        posts,
        error
    } = useBlog();

    const [filter, setFilter] = React.useState('all');

    const filteredPosts = React.useMemo(() => {
        return posts.filter(post => {
            if (filter === 'all') return true;
            return post.category === filter;
        });
    }, [posts, filter]);

    const handleCategoryChange = (category) => {
        setFilter(category);
    };

    const handleRetry = () => {
        // Implement retry logic here
    };

    return (
        <div data-name="blog" className="max-w-7xl mx-auto py-12 px-4">
            <div className="text-center mb-16">
                <h1 className="text-4xl font-bold text-gray-900 mb-4">
                    ShareFoods Blog
                </h1>
                <p className="text-xl text-gray-600">
                    Stories, updates, and insights from our community
                </p>
            </div>

            <div 
                className="flex flex-wrap gap-4 mb-8"
                role="tablist"
                aria-label="Blog categories"
            >
                {['all', 'food-waste', 'success-stories', 'tips-tricks', 'community-news', 'events'].map((category) => (
                    <button
                        key={category}
                        onClick={() => handleCategoryChange(category)}
                        className={`
                            px-4 py-2 rounded-full text-sm font-medium
                            ${filter === category
                                ? 'bg-green-600 text-white'
                                : 'bg-gray-100 text-gray-600 hover:bg-gray-200'
                            }
                        `}
                        role="tab"
                        aria-selected={filter === category}
                        aria-controls={`${category.toLowerCase()}-posts`}
                    >
                        {category.replace(/-/g, ' ').replace(/\b\w/g, l => l.toUpperCase())}
                    </button>
                ))}
            </div>

            {error ? (
                <div className="text-center py-12">
                    <p className="text-red-600 mb-4">{error}</p>
                    <Button
                        variant="secondary"
                        onClick={handleRetry}
                    >
                        Try Again
                    </Button>
                </div>
            ) : (
                <>
                    <div 
                        className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-8"
                        role="tabpanel"
                        id={`${filter.toLowerCase()}-posts`}
                    >
                        {filteredPosts.map((post) => (
                            <Card
                                key={post.id}
                                className="overflow-hidden"
                                image={post.image_url}
                            >
                                <div className="p-6">
                                    <div className="flex items-center justify-between mb-4">
                                        <span className="px-3 py-1 text-sm font-medium text-green-600 bg-green-100 rounded-full">
                                            {post.category}
                                        </span>
                                        <time className="text-sm text-gray-500" dateTime={post.published_at}>
                                            {formatDate(post.published_at)}
                                        </time>
                                    </div>
                                    
                                    <h2 className="text-xl font-semibold mb-2">
                                        {post.title}
                                    </h2>
                                    <p className="text-gray-600 mb-4">
                                        {post.excerpt}
                                    </p>

                                    <div className="flex items-center justify-between">
                                        <div className="flex items-center space-x-3">
                                            <Avatar
                                                src={post.author?.avatar_url}
                                                alt={`${post.author?.name}'s avatar`}
                                                size="sm"
                                            />
                                            <span className="text-sm font-medium">
                                                {post.author?.name}
                                            </span>
                                        </div>
                                        <Link to={`/blog/${post.slug}`}>
                                            <Button
                                                variant="secondary"
                                                size="sm"
                                                aria-label={`Read more about ${post.title}`}
                                            >
                                                Read More
                                            </Button>
                                        </Link>
                                    </div>
                                </div>
                            </Card>
                        ))}
                    </div>

                    {!filteredPosts.length && (
                        <div className="text-center py-12">
                            <p className="text-gray-500">No blog posts found in this category.</p>
                        </div>
                    )}
                </>
            )}
        </div>
    );
}

export default Blog;
