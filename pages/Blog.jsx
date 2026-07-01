import React from 'react';
import { Link, useNavigate } from 'react-router-dom';
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
        <div data-name="blog" className="min-h-screen bg-gradient-to-b from-[#2CABE3]/5 via-white to-emerald-50/40">
            {/* Hero */}
            <header className="relative overflow-hidden">
                <div className="absolute inset-0 -z-10" aria-hidden="true">
                    <div className="absolute -top-24 -left-24 w-96 h-96 rounded-full bg-[#2CABE3]/15 blur-3xl" />
                    <div className="absolute top-10 -right-24 w-96 h-96 rounded-full bg-emerald-300/20 blur-3xl" />
                </div>
                <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 pt-16 pb-12 sm:pt-20 sm:pb-16">
                    <div className="text-center">
                        <span className="inline-flex items-center px-3 py-1 rounded-full bg-[#2CABE3]/10 text-[#2CABE3] text-xs font-semibold mb-5 ring-1 ring-[#2CABE3]/20">
                            <i className="fas fa-pen-nib mr-2" aria-hidden="true"></i>
                            ShareFoods Blog
                        </span>
                        <h1 className="text-4xl sm:text-5xl lg:text-6xl font-bold text-gray-900 mb-5 tracking-tight">
                            Stories from{" "}
                            <span className="bg-gradient-to-r from-[#2CABE3] to-emerald-500 bg-clip-text text-transparent">
                                our community
                            </span>
                        </h1>
                        <p className="text-base sm:text-lg text-gray-600 max-w-2xl mx-auto leading-relaxed">
                            Updates, insights, and stories from the people making food sharing possible.
                        </p>
                        <div className="mt-7 flex flex-wrap items-center justify-center gap-2 text-sm">
                            <span className="inline-flex items-center gap-2 px-4 py-1.5 rounded-full bg-gradient-to-r from-[#2CABE3] to-emerald-500 text-white font-medium shadow-md">
                                <i className="fas fa-pen-nib text-[10px]" aria-hidden="true" />
                                Blog
                            </span>
                            <Link to="/news" className="inline-flex items-center gap-2 px-4 py-1.5 rounded-full bg-white shadow-sm ring-1 ring-gray-200 text-gray-700 font-medium hover:text-[#2CABE3] transition">
                                <i className="fas fa-newspaper text-[10px]" aria-hidden="true" />
                                News
                            </Link>
                            <Link to="/testimonials" className="inline-flex items-center gap-2 px-4 py-1.5 rounded-full bg-white shadow-sm ring-1 ring-gray-200 text-gray-700 font-medium hover:text-[#2CABE3] transition">
                                <i className="fas fa-quote-left text-[10px]" aria-hidden="true" />
                                Testimonials
                            </Link>
                        </div>
                    </div>
                </div>
            </header>

            <main className="max-w-7xl mx-auto py-8 px-4">

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
                                ? 'bg-primary-600 text-white'
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
                                        <span className="px-3 py-1 text-sm font-medium text-primary-600 bg-primary-100 rounded-full">
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
            </main>
        </div>
    );
}

export default Blog;
