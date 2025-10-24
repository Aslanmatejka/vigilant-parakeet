import React from 'react';
import AdminLayout from './AdminLayout';
import dataService from '../../utils/dataService';
import supabase from '../../utils/supabaseClient';
import Button from '../../components/common/Button';

const ContentModeration = () => {
  const [content, setContent] = React.useState([]);
  const [loading, setLoading] = React.useState(true);
  const [filter, setFilter] = React.useState('all');

  React.useEffect(() => {
    fetchContent();

    const foodSubscription = supabase
      .channel('content-moderation-food')
      .on(
        'postgres_changes',
        {
          event: '*',
          schema: 'public',
          table: 'food_listings'
        },
        () => {
          console.log('Food listing changed, refreshing content...');
          fetchContent();
        }
      )
      .subscribe();

    const postsSubscription = supabase
      .channel('content-moderation-posts')
      .on(
        'postgres_changes',
        {
          event: '*',
          schema: 'public',
          table: 'community_posts'
        },
        () => {
          console.log('Post changed, refreshing content...');
          fetchContent();
        }
      )
      .subscribe();

    return () => {
      supabase.removeChannel(foodSubscription);
      supabase.removeChannel(postsSubscription);
    };
  }, [filter]);

  const fetchContent = async () => {
    try {
      setLoading(true);
      const [foodListings, communityPosts] = await Promise.all([
        dataService.getFoodListings({ status: 'pending' }),
        dataService.getCommunityPosts()
      ]);

      const allContent = [
        ...foodListings.map(item => ({
          id: item.id,
          type: 'food_listing',
          title: item.title || item.name,
          image: item.image_url,
          content: item.description,
          status: item.status,
          createdAt: item.created_at,
          data: item
        })),
        ...communityPosts.filter(post => !post.published).map(item => ({
          id: item.id,
          type: 'community_post',
          title: item.title,
          image: item.image_url,
          content: item.content,
          status: item.published ? 'published' : 'pending',
          createdAt: item.created_at,
          data: item
        }))
      ];

      const filtered = filter === 'all'
        ? allContent
        : allContent.filter(item => item.type === filter);

      setContent(filtered.sort((a, b) => new Date(b.createdAt) - new Date(a.createdAt)));
    } catch (error) {
      console.error('Error fetching content:', error);
      setContent([]);
    } finally {
      setLoading(false);
    }
  };

  const handleApprove = async (item) => {
    try {
      if (item.type === 'food_listing') {
        await dataService.updateFoodListingStatus(item.id, 'approved');
      } else if (item.type === 'community_post') {
        await dataService.updateCommunityPost(item.id, { published: true });
      }
      await fetchContent();
    } catch (error) {
      console.error('Error approving content:', error);
      alert('Failed to approve content');
    }
  };

  const handleReject = async (item) => {
    try {
      if (item.type === 'food_listing') {
        await dataService.updateFoodListingStatus(item.id, 'declined');
      } else if (item.type === 'community_post') {
        await dataService.deleteCommunityPost(item.id);
      }
      await fetchContent();
    } catch (error) {
      console.error('Error rejecting content:', error);
      alert('Failed to reject content');
    }
  };

  const handleFlag = async (item) => {
    alert(`Flagged ${item.type} "${item.title}" for review`);
  };

  return (
    <AdminLayout active="content">
    <div className="p-6">
      <div className="mb-6 flex justify-between items-center">
        <h1 className="text-2xl font-bold">Content Moderation</h1>
        <div className="flex gap-2">
          <Button
            variant={filter === 'all' ? 'primary' : 'secondary'}
            size="sm"
            onClick={() => setFilter('all')}
          >
            All
          </Button>
          <Button
            variant={filter === 'food_listing' ? 'primary' : 'secondary'}
            size="sm"
            onClick={() => setFilter('food_listing')}
          >
            Food Listings
          </Button>
          <Button
            variant={filter === 'community_post' ? 'primary' : 'secondary'}
            size="sm"
            onClick={() => setFilter('community_post')}
          >
            Posts
          </Button>
        </div>
      </div>

      <div className="bg-white rounded-lg shadow overflow-hidden">
        <div className="px-6 py-4 border-b border-gray-200">
          <h2 className="text-lg font-semibold">Pending Content ({content.length})</h2>
        </div>

        {loading ? (
          <div className="p-8 text-center">
            <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-green-600 mx-auto"></div>
            <p className="mt-4 text-gray-600">Loading content...</p>
          </div>
        ) : content.length === 0 ? (
          <div className="p-8 text-center">
            <i className="fas fa-check-circle text-green-500 text-4xl mb-4"></i>
            <p className="text-gray-600">No pending content to moderate</p>
          </div>
        ) : (
          <div className="divide-y divide-gray-200">
            {content.map(item => (
              <div key={`${item.type}-${item.id}`} className="p-6">
                <div className="flex items-start space-x-4">
                  {item.image && (
                    <img
                      src={item.image}
                      alt={item.title}
                      className="w-16 h-16 rounded object-cover"
                    />
                  )}
                  <div className="flex-1">
                    <div className="flex items-center justify-between mb-2">
                      <h3 className="text-lg font-medium">{item.title}</h3>
                      <div className="flex items-center gap-2">
                        <span className={`inline-flex px-2 py-1 text-xs font-semibold rounded-full ${
                          item.type === 'food_listing'
                            ? 'bg-blue-100 text-blue-800'
                            : 'bg-purple-100 text-purple-800'
                        }`}>
                          {item.type === 'food_listing' ? 'Food Listing' : 'Community Post'}
                        </span>
                        <span className="inline-flex px-2 py-1 text-xs font-semibold rounded-full bg-yellow-100 text-yellow-800">
                          {item.status}
                        </span>
                      </div>
                    </div>
                    <p className="text-gray-600 mt-1 line-clamp-2">{item.content}</p>
                    <p className="text-sm text-gray-500 mt-2">
                      Posted: {new Date(item.createdAt).toLocaleString()}
                    </p>
                  </div>
                </div>

                <div className="mt-4 flex space-x-2">
                  <Button
                    variant="primary"
                    size="sm"
                    onClick={() => handleApprove(item)}
                  >
                    <i className="fas fa-check mr-2"></i>
                    Approve
                  </Button>
                  <Button
                    variant="danger"
                    size="sm"
                    onClick={() => handleReject(item)}
                  >
                    <i className="fas fa-times mr-2"></i>
                    Reject
                  </Button>
                  <Button
                    variant="secondary"
                    size="sm"
                    onClick={() => handleFlag(item)}
                  >
                    <i className="fas fa-flag mr-2"></i>
                    Flag for Review
                  </Button>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
    </AdminLayout>
  );
};

export default ContentModeration;
