import React from "react";
import Card from "../components/common/Card";
import Button from "../components/common/Button";
import Avatar from "../components/common/Avatar";
import { useAuth } from "../utils/hooks/useSupabase";
import { reportError } from "../utils/helpers";
import dataService from '../utils/dataService';

export const DonateVolunteerButtons = ({ className = "" }) => (
    <div className={`flex flex-col md:flex-row gap-4 ${className}`}>
        <a
            href="https://allgoodlivingfoundation.org/donate"
            target="_blank"
            rel="noopener noreferrer"
            className="inline-block px-6 py-2 bg-green-600 text-white rounded-lg font-semibold shadow hover:bg-green-700 focus:outline-none focus:ring-2 focus:ring-green-400"
            aria-label="Donate to All Good Living Foundation"
        >
            Donate
        </a>
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
            await dataService.togglePostLike(postId);

            setPosts(prevPosts => prevPosts.map(post => {
                if (post.id === postId) {
                    const isLiked = userLikes.includes(postId);
                    return {
                        ...post,
                        likes_count: isLiked ? post.likes_count - 1 : post.likes_count + 1
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
        } finally {
            setLikingPost(null);
        }
    };

    const filteredPosts = selectedType === 'all'
        ? posts
        : posts.filter(post => post.post_type === selectedType);

    return (
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
                        <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-green-600 mx-auto"></div>
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
                                                    'bg-green-100 text-green-800'
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
                    <a href="https://facebook.com/allgoodlivingfoundation" target="_blank" rel="noopener noreferrer" aria-label="Facebook" className="text-blue-600 hover:underline">
                        <i className="fab fa-facebook text-2xl"></i> Facebook
                    </a>
                    <a href="https://instagram.com/allgoodlivingfoundation" target="_blank" rel="noopener noreferrer" aria-label="Instagram" className="text-pink-600 hover:underline">
                        <i className="fab fa-instagram text-2xl"></i> Instagram
                    </a>
                    <a href="https://twitter.com/allgoodlivingfdn" target="_blank" rel="noopener noreferrer" aria-label="Twitter" className="text-blue-400 hover:underline">
                        <i className="fab fa-twitter text-2xl"></i> Twitter
                    </a>
                </div>
            </section>

            <section className="mb-10">
                <h2 className="text-2xl font-bold mb-4">Support the Community</h2>
                <DonateVolunteerButtons />
            </section>
        </div>
    );
}

export default CommunityPage;
