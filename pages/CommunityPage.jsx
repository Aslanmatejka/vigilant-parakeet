import React from "react";
import SponsoredBy from "../components/common/SponsoredBy";
import Card from "../components/common/Card";
import Button from "../components/common/Button";
import Input from "../components/common/Input";
import Avatar from "../components/common/Avatar";
import { useAuth, useCommunityPosts } from "../utils/hooks/useSupabase";
import { reportError } from "../utils/helpers";

// Reusable Donate/Volunteer buttons
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

// Utility function to format dates
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

class ErrorBoundary extends React.Component {
    constructor(props) {
        super(props);
        this.state = { hasError: false };
    }

    static getDerivedStateFromError(/* error */) {
        return { hasError: true };
    }

    componentDidCatch(error, errorInfo) {
        reportError(error);
        console.error('Component Error:', error, errorInfo);
    }

    render() {
        if (this.state.hasError) {
            return (
                <div className="text-center py-8">
                    <i className="fas fa-exclamation-circle text-red-500 text-4xl mb-4"></i>
                    <h2 className="text-xl font-bold mb-2">Something went wrong</h2>
                    <p className="text-gray-600 mb-4">We're sorry, but there was an error loading this section.</p>
                    <Button onClick={() => window.location.reload()} variant="secondary">
                        Refresh Page
                    </Button>
                </div>
            );
        }

        return this.props.children;
    }
}

function LoadingComponent() {
    return (
        <div className="text-center py-8">
            <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-green-500"></div>
        </div>
    );
}

function CommunityPage() {
    try {
        const { user: authUser, isAuthenticated } = useAuth();
        const [selectedCategory, setSelectedCategory] = React.useState('all');
        
        const { 
            posts, 
            loading, 
            error, 
            createPost, 
            addComment, 
            likePost 
        } = useCommunityPosts(selectedCategory !== 'all' ? { category: selectedCategory } : {});
        
        const [newPost, setNewPost] = React.useState({ title: '', content: '', category: 'tips' });
        const [commentInputs, setCommentInputs] = React.useState({});
        const [likedPosts, setLikedPosts] = React.useState({});

        // Add loading state for individual actions
        const [actionLoading, setActionLoading] = React.useState({
            post: false,
            comment: null, // will store postId when commenting
            like: null, // will store postId when liking
        });

        const handleCreatePost = async (e) => {
            e.preventDefault();
            if (!newPost.title.trim() || !newPost.content.trim()) {
                alert('Please fill in both title and content');
                return;
            }

            if (!isAuthenticated) {
                alert('Please log in to create a post');
                return;
            }

            setActionLoading(prev => ({ ...prev, post: true }));
            try {
                await createPost({
                    title: newPost.title.trim(),
                    content: newPost.content.trim(),
                    category: newPost.category,
                    author: authUser
                });
                setNewPost({ title: '', content: '', category: 'tips' });
            } catch (error) {
                console.error('Create post error:', error);
                reportError(error);
                alert('Failed to create post. Please try again.');
            } finally {
                setActionLoading(prev => ({ ...prev, post: false }));
            }
        };

        const handleAddComment = async (postId) => {
            const comment = commentInputs[postId];
            if (!comment?.trim()) return;

            if (!isAuthenticated) {
                alert('Please log in to comment');
                return;
            }

            setActionLoading(prev => ({ ...prev, comment: postId }));
            try {
                await addComment(postId, {
                    content: comment.trim(),
                    author_id: authUser.id
                });
                setCommentInputs(prev => ({ ...prev, [postId]: '' }));
            } catch (error) {
                console.error('Add comment error:', error);
                reportError(error);
                alert('Failed to add comment. Please try again.');
            } finally {
                setActionLoading(prev => ({ ...prev, comment: null }));
            }
        };

        const handleLikePost = async (postId) => {
            if (!isAuthenticated) {
                alert('Please log in to like posts');
                return;
            }

            const isLiked = likedPosts[postId] || false;
            setActionLoading(prev => ({ ...prev, like: postId }));
            try {
                await likePost(postId, !isLiked);
                setLikedPosts(prev => ({ ...prev, [postId]: !isLiked }));
            } catch (error) {
                console.error('Like post error:', error);
                reportError(error);
                alert('Failed to like post. Please try again.');
            } finally {
                setActionLoading(prev => ({ ...prev, like: null }));
            }
        };

        const filteredPosts = posts.filter(post => 
            selectedCategory === 'all' || post.category === selectedCategory
        );

        return (
            <div className="max-w-6xl mx-auto py-8 px-4">
                {/* Forum/Blog Section */}
                <section className="mb-10">
                    <h2 className="text-2xl font-bold mb-4">Community Forum & Blog</h2>
                    {/* Create Post Form */}
                    <Card className="mb-6">
                        <form onSubmit={handleCreatePost} className="space-y-4">
                            <div className="flex flex-col md:flex-row gap-4">
                                <Input
                                    label="Title"
                                    name="title"
                                    value={newPost.title}
                                    onChange={e => setNewPost(prev => ({ ...prev, title: e.target.value }))}
                                    required
                                    maxLength={100}
                                    className="flex-1"
                                />
                                <select
                                    name="category"
                                    value={newPost.category}
                                    onChange={e => setNewPost(prev => ({ ...prev, category: e.target.value }))}
                                    className="border rounded px-3 py-2"
                                >
                                    <option value="tips">Tips</option>
                                    <option value="questions">Questions</option>
                                    <option value="stories">Stories</option>
                                </select>
                            </div>
                            <Input
                                label="Content"
                                name="content"
                                value={newPost.content}
                                onChange={e => setNewPost(prev => ({ ...prev, content: e.target.value }))}
                                required
                                multiline
                                rows={3}
                                maxLength={500}
                                className="w-full"
                            />
                            <Button type="submit" loading={actionLoading.post} disabled={actionLoading.post}>
                                {actionLoading.post ? "Posting..." : "Create Post"}
                            </Button>
                        </form>
                    </Card>

                    <div className="space-y-6">
                        {loading && <LoadingComponent />}
                        {error && (
                            <Card className="mb-6">
                                <div className="p-6 text-center">
                                    <i className="fas fa-exclamation-triangle text-red-500 text-4xl mb-4"></i>
                                    <h3 className="text-xl font-bold text-red-700 mb-2">Error Loading Posts</h3>
                                    <p className="text-gray-600 mb-4">There was an error loading the posts. Please try again later.</p>
                                    <Button onClick={() => window.location.reload()} variant="secondary">
                                        Retry
                                    </Button>
                                </div>
                            </Card>
                        )}

                        {!loading && !error && filteredPosts.length === 0 && (
                            <Card className="mb-6">
                                <div className="p-6 text-center">
                                    <i className="fas fa-comments text-gray-400 text-4xl mb-4"></i>
                                    <h3 className="text-xl font-bold text-gray-700 mb-2">No posts yet</h3>
                                    <p className="text-gray-600">
                                        {selectedCategory === 'all' 
                                            ? "Be the first to share something with the community!"
                                            : `No posts in the ${selectedCategory} category yet.`
                                        }
                                    </p>
                                </div>
                            </Card>
                        )}

                        <div className="space-y-6">
                            {filteredPosts.map(post => (
                                <Card key={post.id || post.objectId} className="overflow-hidden">
                                    <div className="p-6">
                                        {/* Post Header */}
                                        <div className="flex items-start space-x-4 mb-4">
                                            <Avatar 
                                                src={post.author?.avatar} 
                                                alt={post.author?.name}
                                                size="md"
                                            />
                                            <div className="flex-1">
                                                <div className="flex items-center space-x-2 mb-1">
                                                    <h4 className="font-bold text-gray-900">{post.author?.name}</h4>
                                                    <span className="px-2 py-1 bg-green-100 text-green-800 text-xs rounded-full capitalize">
                                                        {post.category}
                                                    </span>
                                                </div>
                                                <p className="text-sm text-gray-500">
                                                    {timeAgo(post.createdAt || post.date)}
                                                </p>
                                            </div>
                                        </div>

                                        {/* Post Content */}
                                        <h3 className="text-xl font-bold text-gray-900 mb-3">{post.title}</h3>
                                        <p className="text-gray-700 whitespace-pre-line mb-4">{post.content}</p>

                                        {/* Post Actions */}
                                        <div className="flex items-center space-x-4 pb-4 border-b border-gray-200">
                                            <Button
                                                variant="ghost"
                                                onClick={() => handleLikePost(post.id || post.objectId)}
                                                disabled={actionLoading.like === (post.id || post.objectId)}
                                                className={`flex items-center space-x-2 ${
                                                    likedPosts[post.id || post.objectId] || post.liked 
                                                        ? 'text-red-500' 
                                                        : 'text-gray-500'
                                                }`}
                                            >
                                                <i className={`fas fa-heart ${
                                                    likedPosts[post.id || post.objectId] || post.liked 
                                                        ? 'text-red-500' 
                                                        : 'text-gray-400'
                                                }`}></i>
                                                <span>{post.likes || 0}</span>
                                            </Button>
                                            <div className="flex items-center space-x-2 text-gray-500">
                                                <i className="fas fa-comment"></i>
                                                <span>{post.comments?.length || 0} comments</span>
                                            </div>
                                        </div>

                                        {/* Comments */}
                                        {post.comments && post.comments.length > 0 && (
                                            <div className="mt-4 space-y-3">
                                                {post.comments.map(comment => (
                                                    <div key={comment.id || comment.objectId} className="flex space-x-3">
                                                        <Avatar 
                                                            src={comment.author?.avatar} 
                                                            alt={comment.author?.name}
                                                            size="sm"
                                                        />
                                                        <div className="flex-1">
                                                            <div className="bg-gray-50 rounded-lg p-3">
                                                                <div className="flex items-center space-x-2 mb-1">
                                                                    <span className="font-semibold text-sm text-gray-900">
                                                                        {comment.author?.name}
                                                                    </span>
                                                                    <span className="text-xs text-gray-500">
                                                                        {timeAgo(comment.createdAt)}
                                                                    </span>
                                                                </div>
                                                                <p className="text-gray-700 text-sm">{comment.content}</p>
                                                            </div>
                                                        </div>
                                                    </div>
                                                ))}
                                            </div>
                                        )}

                                        {/* Add Comment */}
                                        {isAuthenticated && (
                                            <div className="mt-4 flex space-x-3">
                                                <Avatar 
                                                    src={authUser?.avatar} 
                                                    alt={authUser?.name}
                                                    size="sm"
                                                />
                                                <div className="flex-1 flex space-x-2">
                                                    <Input
                                                        placeholder="Add a comment..."
                                                        value={commentInputs[post.id || post.objectId] || ''}
                                                        onChange={(e) => setCommentInputs(prev => ({ 
                                                            ...prev, 
                                                            [post.id || post.objectId]: e.target.value 
                                                        }))}
                                                        onKeyPress={(e) => {
                                                            if (e.key === 'Enter') {
                                                                handleAddComment(post.id || post.objectId);
                                                            }
                                                        }}
                                                        className="flex-1"
                                                    />
                                                    <Button
                                                        onClick={() => handleAddComment(post.id || post.objectId)}
                                                        disabled={
                                                            actionLoading.comment === (post.id || post.objectId) ||
                                                            !commentInputs[post.id || post.objectId]?.trim()
                                                        }
                                                        size="sm"
                                                    >
                                                        {actionLoading.comment === (post.id || post.objectId) ? 'Adding...' : 'Post'}
                                                    </Button>
                                                </div>
                                            </div>
                                        )}
                                    </div>
                                </Card>
                            ))}
                        </div>
                    </div>
                </section>

                {/* Social Media Section */}
                <section className="mb-10">
                    <h2 className="text-2xl font-bold mb-4">Connect on Social Media</h2>
                    <div className="flex gap-4">
                        <a href="https://facebook.com/allgoodlivingfoundation" target="_blank" rel="noopener noreferrer" aria-label="Facebook" className="text-blue-600 hover:underline">Facebook</a>
                        <a href="https://instagram.com/allgoodlivingfoundation" target="_blank" rel="noopener noreferrer" aria-label="Instagram" className="text-pink-600 hover:underline">Instagram</a>
                        <a href="https://twitter.com/allgoodlivingfdn" target="_blank" rel="noopener noreferrer" aria-label="Twitter" className="text-blue-400 hover:underline">Twitter</a>
                    </div>
                </section>

                {/* Sponsor Section */}
                {/* REMOVE THIS SECTION TO AVOID DUPLICATE */}
                {/* <section className="mb-10">
                    <h2 className="text-2xl font-bold mb-4">Our Sponsors</h2>
                    <SponsoredBy />
                </section> */}

                {/* Donate & Volunteer Buttons */}
                <section className="mb-10">
                    <h2 className="text-2xl font-bold mb-4">Support the Community</h2>
                    <DonateVolunteerButtons />
                </section>
            </div>
        );
    } catch (error) {
        reportError(error);
        console.error('CommunityPage error:', error);
        return (
            <div className="max-w-6xl mx-auto py-8 px-4">
                <div className="text-center">
                    <i className="fas fa-exclamation-circle text-red-500 text-4xl mb-4"></i>
                    <h2 className="text-2xl font-bold mb-2">Something went wrong</h2>
                    <p className="text-gray-600 mb-4">We're sorry, but there was an error loading the community page.</p>
                    <Button onClick={() => window.location.reload()}>
                        Refresh Page
                    </Button>
                </div>
            </div>
        );
    }
}

export default function CommunityPageWithErrorBoundary() {
    return (
        <ErrorBoundary>
            <CommunityPage />
        </ErrorBoundary>
    );
}
