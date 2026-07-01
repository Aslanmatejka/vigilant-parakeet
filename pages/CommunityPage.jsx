import React from "react";
import { Link } from 'react-router-dom';
import Card from "../components/common/Card";
import Button from "../components/common/Button";
import Avatar from "../components/common/Avatar";
import { useAuth } from "../utils/hooks/useSupabase";
import { reportError } from "../utils/helpers";
import dataService from '../utils/dataService';

export const DonateVolunteerButtons = ({ className = "" }) => (
    <div className={`flex flex-col md:flex-row gap-4 ${className}`}>
        <Link
            to="/donate"
            className="inline-block px-6 py-2 bg-[#2CABE3] text-white rounded-lg font-semibold shadow hover:opacity-90 focus:outline-none focus:ring-2 focus:ring-[#2CABE3]"
            aria-label="Donate to All Good Living Foundation"
        >
            Donate
        </Link>
        <a
            href="https://allgoodlivingfoundation.org/volunteer-form"
            target="_blank"
            rel="noopener noreferrer"
            className="inline-block px-6 py-2 bg-blue-600 text-white rounded-lg font-semibold shadow hover:bg-blue-700 focus:outline-none focus:ring-2 focus:ring-blue-400"
            aria-label="Volunteer with All Good Living Foundation"
        >
            Volunteer
        </a>
    </div>
);

const timeAgo = (date) => {
    const seconds = Math.floor((new Date() - new Date(date)) / 1000);

    let interval = seconds / 31536000;
    if (interval > 1) return Math.floor(interval) + " years ago";

    interval = seconds / 2592000;
    if (interval > 1) return Math.floor(interval) + " months ago";

    interval = seconds / 86400;
    if (interval > 1) return Math.floor(interval) + " days ago";

    interval = seconds / 3600;
    if (interval > 1) return Math.floor(interval) + " hours ago";

    interval = seconds / 60;
    if (interval > 1) return Math.floor(interval) + " minutes ago";

    return Math.floor(seconds) + " seconds ago";
};

function CommunityPage() {
    const { user: authUser, isAuthenticated } = useAuth();
    const [posts, setPosts] = React.useState([]);
    const [loading, setLoading] = React.useState(true);
    const [userLikes, setUserLikes] = React.useState([]);
    const [likingPost, setLikingPost] = React.useState(null);
    const [selectedType, setSelectedType] = React.useState('all');

    React.useEffect(() => {
        fetchPosts();
        if (authUser?.id) {
            fetchUserLikes();
        }

        const postsSubscription = dataService.subscribeToCommunityPosts(() => {
            console.log('Post change detected, refreshing...');
            setTimeout(() => fetchPosts(), 500);
        });

        const likesSubscription = dataService.subscribeToPostLikes(() => {
            console.log('Like change detected, refreshing...');
            setTimeout(() => {
                fetchPosts();
                if (authUser?.id) {
                    fetchUserLikes();
                }
            }, 500);
        });

        return () => {
            dataService.unsubscribe('community_posts');
            dataService.unsubscribe('post_likes');
        };
    }, [authUser?.id]);

    const fetchPosts = async () => {
        try {
            setLoading(true);
            const filters = selectedType !== 'all' ? { post_type: selectedType } : {};
            const data = await dataService.getCommunityPosts(filters);
            setPosts(data);
        } catch (error) {
            console.error('Error fetching posts:', error);
            reportError(error);
        } finally {
            setLoading(false);
        }
    };

    const fetchUserLikes = async () => {
        try {
            const likes = await dataService.getUserPostLikes(authUser.id);
            setUserLikes(likes);
        } catch (error) {
            console.error('Error fetching user likes:', error);
        }
    };

    const handleLike = async (postId) => {
        if (!isAuthenticated) {
            alert('Please log in to like posts');
            return;
        }

        setLikingPost(postId);
        try {
            console.log('Toggling like for post:', postId);
            const result = await dataService.togglePostLike(postId);
            console.log('Like toggle result:', result);

            setPosts(prevPosts => prevPosts.map(post => {
                if (post.id === postId) {
                    const isLiked = userLikes.includes(postId);
                    const newLikesCount = isLiked ? post.likes_count - 1 : post.likes_count + 1;
                    console.log(`Updating post ${postId} likes from ${post.likes_count} to ${newLikesCount}`);
                    return {
                        ...post,
                        likes_count: newLikesCount
                    };
                }
                return post;
            }));

            if (userLikes.includes(postId)) {
                setUserLikes(prev => prev.filter(id => id !== postId));
            } else {
                setUserLikes(prev => [...prev, postId]);
            }
        } catch (error) {
            console.error('Error toggling like:', error);
            reportError(error);
            alert('Failed to like post: ' + error.message);
        } finally {
            setLikingPost(null);
        }
    };

    const filteredPosts = selectedType === 'all'
        ? posts
        : posts.filter(post => post.post_type === selectedType);

    return (
        <div className="min-h-screen bg-gradient-to-b from-[#2CABE3]/5 via-white to-emerald-50/40">
            {/* Hero */}
            <header className="relative overflow-hidden">
                <div className="absolute inset-0 -z-10" aria-hidden="true">
                    <div className="absolute -top-24 -left-24 w-96 h-96 rounded-full bg-[#2CABE3]/15 blur-3xl" />
                    <div className="absolute top-10 -right-24 w-96 h-96 rounded-full bg-emerald-300/20 blur-3xl" />
                </div>
                <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 pt-16 pb-12 sm:pt-20 sm:pb-16">
                    <div className="text-center">
                        <span className="inline-flex items-center px-3 py-1 rounded-full bg-[#2CABE3]/10 text-[#2CABE3] text-xs font-semibold mb-5 ring-1 ring-[#2CABE3]/20">
                            <i className="fas fa-users mr-2" aria-hidden="true"></i>
                            Community Hub
                        </span>
                        <h1 className="text-4xl sm:text-5xl lg:text-6xl font-bold text-gray-900 mb-5 tracking-tight">
                            Community Forum{" "}
                            <span className="bg-gradient-to-r from-[#2CABE3] to-emerald-500 bg-clip-text text-transparent">
                                &amp; Stories
                            </span>
                        </h1>
                        <p className="text-base sm:text-lg text-gray-600 max-w-2xl mx-auto leading-relaxed">
                            Share your experiences, read testimonies, and stay connected with our food-rescue community.
                        </p>
                    </div>
                </div>
            </header>

            <div className="max-w-6xl mx-auto py-8 px-4">
            <section className="mb-10">
                <div className="flex justify-between items-center mb-6">
                    <h2 className="text-3xl font-bold text-gray-900">Community Forum & Testimonies</h2>
                    <div className="flex gap-2">
                        <Button
                            variant={selectedType === 'all' ? 'primary' : 'secondary'}
                            size="sm"
                            onClick={() => setSelectedType('all')}
                        >
                            All
                        </Button>
                        <Button
                            variant={selectedType === 'testimony' ? 'primary' : 'secondary'}
                            size="sm"
                            onClick={() => setSelectedType('testimony')}
                        >
                            Testimonies
                        </Button>
                        <Button
                            variant={selectedType === 'blog' ? 'primary' : 'secondary'}
                            size="sm"
                            onClick={() => setSelectedType('blog')}
                        >
                            Blog
                        </Button>
                        <Button
                            variant={selectedType === 'announcement' ? 'primary' : 'secondary'}
                            size="sm"
                            onClick={() => setSelectedType('announcement')}
                        >
                            Announcements
                        </Button>
                    </div>
                </div>

                {loading ? (
                    <div className="text-center py-12">
                        <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-[#2CABE3] mx-auto"></div>
                        <p className="mt-4 text-gray-600">Loading posts...</p>
                    </div>
                ) : filteredPosts.length === 0 ? (
                    <Card className="p-8 text-center">
                        <i className="fas fa-comments text-gray-400 text-5xl mb-4"></i>
                        <h3 className="text-xl font-bold text-gray-700 mb-2">No posts yet</h3>
                        <p className="text-gray-600">Check back soon for community updates and testimonies!</p>
                    </Card>
                ) : (
                    <div className="space-y-6">
                        {filteredPosts.map(post => (
                            <Card key={post.id} className="overflow-hidden hover:shadow-lg transition-shadow">
                                <div className="p-6">
                                    <div className="flex items-start space-x-4 mb-4">
                                        <Avatar
                                            src={post.users?.avatar_url}
                                            alt={post.users?.name || 'Admin'}
                                            size="md"
                                        />
                                        <div className="flex-1">
                                            <div className="flex items-center gap-2 mb-1">
                                                <h4 className="font-bold text-gray-900">{post.users?.name || 'Admin'}</h4>
                                                <span className={`px-2 py-1 text-xs font-semibold rounded-full ${
                                                    post.post_type === 'testimony' ? 'bg-purple-100 text-purple-800' :
                                                    post.post_type === 'blog' ? 'bg-blue-100 text-blue-800' :
                                                    post.post_type === 'announcement' ? 'bg-red-100 text-red-800' :
                                                    'bg-primary-100 text-primary-800'
                                                }`}>
                                                    {post.post_type}
                                                </span>
                                                {post.category && post.category !== 'general' && (
                                                    <span className="px-2 py-1 bg-gray-100 text-gray-700 text-xs rounded-full capitalize">
                                                        {post.category}
                                                    </span>
                                                )}
                                            </div>
                                            <p className="text-sm text-gray-500">
                                                {timeAgo(post.created_at)}
                                            </p>
                                        </div>
                                    </div>

                                    <h3 className="text-2xl font-bold text-gray-900 mb-3">{post.title}</h3>
                                    <p className="text-gray-700 whitespace-pre-line mb-4">{post.content}</p>

                                    {post.image_url && (
                                        <img
                                            src={post.image_url}
                                            alt={post.title}
                                            className="w-full max-h-96 object-cover rounded-lg mb-4"
                                        />
                                    )}

                                    <div className="flex items-center gap-4 pt-4 border-t border-gray-200">
                                        <Button
                                            variant="ghost"
                                            size="sm"
                                            onClick={() => handleLike(post.id)}
                                            disabled={likingPost === post.id}
                                            className={`flex items-center gap-2 ${
                                                userLikes.includes(post.id)
                                                    ? 'text-red-500'
                                                    : 'text-gray-500 hover:text-red-500'
                                            }`}
                                        >
                                            <i className={`fas fa-heart ${
                                                userLikes.includes(post.id) ? 'text-red-500' : ''
                                            }`}></i>
                                            <span className="font-semibold">{post.likes_count || 0}</span>
                                        </Button>
                                    </div>
                                </div>
                            </Card>
                        ))}
                    </div>
                )}
            </section>

            <section className="mb-10">
                <h2 className="text-2xl font-bold mb-4">Connect on Social Media</h2>
                <div className="flex gap-4">
                    <a href="https://www.facebook.com/allgoodlivingfoundation" target="_blank" rel="noopener noreferrer" aria-label="Facebook" className="text-blue-600 hover:underline">
                        <i className="fab fa-facebook text-2xl"></i> Facebook
                    </a>
                    <a href="https://www.instagram.com/aglfoundation" target="_blank" rel="noopener noreferrer" aria-label="Instagram" className="text-pink-600 hover:underline">
                        <i className="fab fa-instagram text-2xl"></i> Instagram
                    </a>
                </div>
            </section>

            <section className="mb-10">
                <h2 className="text-2xl font-bold mb-4">Support the Community</h2>
                <DonateVolunteerButtons />
            </section>
            </div>
        </div>
    );
}

export default CommunityPage;
