import React from 'react';
import Button from '../../components/common/Button';
import Input from '../../components/common/Input';
import Card from '../../components/common/Card';
import dataService from '../../utils/dataService';
import { reportError } from '../../utils/helpers';
import AdminLayout from './AdminLayout';

function AdminContentManagement() {
    const [posts, setPosts] = React.useState([]);
    const [loading, setLoading] = React.useState(true);
    const [showForm, setShowForm] = React.useState(false);
    const [editingPost, setEditingPost] = React.useState(null);
    const [formData, setFormData] = React.useState({
        title: '',
        content: '',
        category: 'general',
        post_type: 'testimony',
        image_url: ''
    });
    const [imageFile, setImageFile] = React.useState(null);
    const [submitting, setSubmitting] = React.useState(false);

    React.useEffect(() => {
        fetchPosts();

        const postsSubscription = dataService.subscribeToCommunityPosts(() => {
            console.log('Post change detected, refreshing...');
            fetchPosts();
        });

        return () => {
            dataService.unsubscribe('community_posts');
        };
    }, []);

    const fetchPosts = async () => {
        try {
            setLoading(true);
            const data = await dataService.getCommunityPosts();
            setPosts(data);
        } catch (error) {
            console.error('Error fetching posts:', error);
            reportError(error);
        } finally {
            setLoading(false);
        }
    };

    const handleInputChange = (e) => {
        const { name, value } = e.target;
        setFormData(prev => ({ ...prev, [name]: value }));
    };

    const handleImageChange = (e) => {
        const file = e.target.files[0];
        if (file) {
            setImageFile(file);
        }
    };

    const handleSubmit = async (e) => {
        e.preventDefault();
        setSubmitting(true);

        try {
            let imageUrl = formData.image_url;

            if (imageFile) {
                const { url } = await dataService.uploadFile(imageFile, 'food-images');
                imageUrl = url;
            }

            const postData = {
                ...formData,
                image_url: imageUrl
            };

            if (editingPost) {
                await dataService.updateCommunityPost(editingPost.id, postData);
            } else {
                await dataService.createCommunityPost(postData);
            }

            setFormData({
                title: '',
                content: '',
                category: 'general',
                post_type: 'testimony',
                image_url: ''
            });
            setImageFile(null);
            setEditingPost(null);
            setShowForm(false);
            await fetchPosts();
        } catch (error) {
            console.error('Error saving post:', error);
            reportError(error);
            alert('Failed to save post: ' + error.message);
        } finally {
            setSubmitting(false);
        }
    };

    const handleEdit = (post) => {
        setEditingPost(post);
        setFormData({
            title: post.title,
            content: post.content,
            category: post.category || 'general',
            post_type: post.post_type || 'testimony',
            image_url: post.image_url || ''
        });
        setShowForm(true);
    };

    const handleDelete = async (postId) => {
        if (!confirm('Are you sure you want to delete this post?')) return;

        try {
            await dataService.deleteCommunityPost(postId);
            await fetchPosts();
        } catch (error) {
            console.error('Error deleting post:', error);
            reportError(error);
            alert('Failed to delete post');
        }
    };

    const handleCancel = () => {
        setShowForm(false);
        setEditingPost(null);
        setFormData({
            title: '',
            content: '',
            category: 'general',
            post_type: 'testimony',
            image_url: ''
        });
        setImageFile(null);
    };

    return (
        <AdminLayout active="posts">
            <div className="max-w-6xl mx-auto p-6">
            <div className="flex justify-between items-center mb-6">
                <h1 className="text-3xl font-bold text-gray-900">Content Management</h1>
                <Button
                    onClick={() => setShowForm(!showForm)}
                    variant="primary"
                >
                    <i className="fas fa-plus mr-2"></i>
                    {showForm ? 'Cancel' : 'Create Post'}
                </Button>
            </div>

            {showForm && (
                <Card className="mb-6 p-6">
                    <h2 className="text-xl font-bold mb-4">
                        {editingPost ? 'Edit Post' : 'Create New Post'}
                    </h2>
                    <form onSubmit={handleSubmit} className="space-y-4">
                        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                            <Input
                                label="Title"
                                name="title"
                                value={formData.title}
                                onChange={handleInputChange}
                                required
                                maxLength={255}
                            />
                            <div>
                                <label className="block text-sm font-medium text-gray-700 mb-1">
                                    Post Type
                                </label>
                                <select
                                    name="post_type"
                                    value={formData.post_type}
                                    onChange={handleInputChange}
                                    className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-green-500"
                                    required
                                >
                                    <option value="testimony">Testimony</option>
                                    <option value="blog">Blog</option>
                                    <option value="forum">Forum Post</option>
                                    <option value="announcement">Announcement</option>
                                </select>
                            </div>
                        </div>

                        <div>
                            <label className="block text-sm font-medium text-gray-700 mb-1">
                                Category
                            </label>
                            <select
                                name="category"
                                value={formData.category}
                                onChange={handleInputChange}
                                className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-green-500"
                            >
                                <option value="general">General</option>
                                <option value="tips">Tips</option>
                                <option value="stories">Stories</option>
                                <option value="questions">Questions</option>
                                <option value="news">News</option>
                            </select>
                        </div>

                        <Input
                            label="Content"
                            name="content"
                            value={formData.content}
                            onChange={handleInputChange}
                            multiline
                            rows={6}
                            required
                        />

                        <div>
                            <label className="block text-sm font-medium text-gray-700 mb-1">
                                Upload Image
                            </label>
                            <input
                                type="file"
                                accept="image/*"
                                onChange={handleImageChange}
                                className="w-full px-3 py-2 border border-gray-300 rounded-lg"
                            />
                            {formData.image_url && !imageFile && (
                                <div className="mt-2">
                                    <img
                                        src={formData.image_url}
                                        alt="Current"
                                        className="h-32 w-auto rounded-lg"
                                    />
                                </div>
                            )}
                        </div>

                        <div className="flex gap-3">
                            <Button
                                type="submit"
                                variant="primary"
                                disabled={submitting}
                            >
                                {submitting ? 'Saving...' : editingPost ? 'Update Post' : 'Create Post'}
                            </Button>
                            <Button
                                type="button"
                                variant="secondary"
                                onClick={handleCancel}
                            >
                                Cancel
                            </Button>
                        </div>
                    </form>
                </Card>
            )}

            <div className="space-y-4">
                {loading ? (
                    <div className="text-center py-8">
                        <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-green-600 mx-auto"></div>
                        <p className="mt-4 text-gray-600">Loading posts...</p>
                    </div>
                ) : posts.length === 0 ? (
                    <Card className="p-8 text-center">
                        <i className="fas fa-inbox text-gray-400 text-4xl mb-4"></i>
                        <p className="text-gray-600">No posts yet. Create your first post!</p>
                    </Card>
                ) : (
                    posts.map(post => (
                        <Card key={post.id} className="p-6">
                            <div className="flex justify-between items-start mb-4">
                                <div className="flex-1">
                                    <div className="flex items-center gap-2 mb-2">
                                        <h3 className="text-xl font-bold text-gray-900">{post.title}</h3>
                                        <span className={`px-2 py-1 text-xs font-semibold rounded-full ${
                                            post.post_type === 'testimony' ? 'bg-purple-100 text-purple-800' :
                                            post.post_type === 'blog' ? 'bg-blue-100 text-blue-800' :
                                            post.post_type === 'announcement' ? 'bg-red-100 text-red-800' :
                                            'bg-green-100 text-green-800'
                                        }`}>
                                            {post.post_type}
                                        </span>
                                        <span className="px-2 py-1 text-xs bg-gray-100 text-gray-700 rounded-full">
                                            {post.category}
                                        </span>
                                    </div>
                                    <p className="text-gray-700 whitespace-pre-line">{post.content}</p>
                                    {post.image_url && (
                                        <img
                                            src={post.image_url}
                                            alt={post.title}
                                            className="mt-4 h-48 w-auto rounded-lg"
                                        />
                                    )}
                                    <div className="mt-3 flex items-center gap-4 text-sm text-gray-500">
                                        <span><i className="fas fa-heart text-red-500"></i> {post.likes_count || 0} likes</span>
                                        <span><i className="fas fa-calendar"></i> {new Date(post.created_at).toLocaleDateString()}</span>
                                        <span><i className="fas fa-user"></i> {post.users?.name || 'Admin'}</span>
                                    </div>
                                </div>
                                <div className="flex gap-2 ml-4">
                                    <Button
                                        variant="secondary"
                                        size="sm"
                                        onClick={() => handleEdit(post)}
                                    >
                                        <i className="fas fa-edit"></i>
                                    </Button>
                                    <Button
                                        variant="danger"
                                        size="sm"
                                        onClick={() => handleDelete(post.id)}
                                    >
                                        <i className="fas fa-trash"></i>
                                    </Button>
                                </div>
                            </div>
                        </Card>
                    ))
                )}
            </div>
        </div>
        </AdminLayout>
    );
}

export default AdminContentManagement;
