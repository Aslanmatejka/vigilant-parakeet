import React from 'react';

const ContentModeration = () => {
  const mockContent = [
    {
      id: 1,
      type: 'listing',
      title: 'Fresh Organic Vegetables',
      image: 'https://images.unsplash.com/photo-1566385101042-1a0aa0c1268c?ixlib=rb-1.2.1&auto=format&fit=crop&w=800&q=60',
      content: 'Fresh organic vegetables from local farm',
      status: 'pending',
      createdAt: '2024-01-15'
    },
    {
      id: 2,
      type: 'listing',
      title: 'Fresh Herbs',
      image: 'https://images.unsplash.com/photo-1600231915619-bcfb0bd75ad6?ixlib=rb-1.2.1&auto=format&fit=crop&w=800&q=60',
      content: 'Organic fresh herbs from my garden',
      status: 'pending',
      createdAt: '2024-01-14'
    },
    {
      id: 3,
      type: 'listing',
      title: 'Homemade Sourdough',
      image: 'https://images.unsplash.com/photo-1586444248902-2f64eddc13df?ixlib=rb-1.2.1&auto=format&fit=crop&w=800&q=60',
      content: 'Freshly baked sourdough bread',
      status: 'pending',
      createdAt: '2024-01-13'
    }
  ];

  return (
    <div className="p-6">
      <h1 className="text-2xl font-bold mb-6">Content Moderation</h1>
      
      <div className="bg-white rounded-lg shadow overflow-hidden">
        <div className="px-6 py-4 border-b border-gray-200">
          <h2 className="text-lg font-semibold">Pending Content</h2>
        </div>
        
        <div className="divide-y divide-gray-200">
          {mockContent.map(item => (
            <div key={item.id} className="p-6">
              <div className="flex items-start space-x-4">
                <img 
                  src={item.image} 
                  alt={item.title}
                  className="w-16 h-16 rounded object-cover"
                />
                <div className="flex-1">
                  <div className="flex items-center justify-between">
                    <h3 className="text-lg font-medium">{item.title}</h3>
                    <span className="inline-flex px-2 py-1 text-xs font-semibold rounded-full bg-yellow-100 text-yellow-800">
                      {item.status}
                    </span>
                  </div>
                  <p className="text-gray-600 mt-1">{item.content}</p>
                  <p className="text-sm text-gray-500 mt-2">Posted: {item.createdAt}</p>
                </div>
              </div>
              
              <div className="mt-4 flex space-x-2">
                <button className="px-4 py-2 bg-green-600 text-white rounded hover:bg-green-700">
                  Approve
                </button>
                <button className="px-4 py-2 bg-red-600 text-white rounded hover:bg-red-700">
                  Reject
                </button>
                <button className="px-4 py-2 bg-gray-600 text-white rounded hover:bg-gray-700">
                  Flag for Review
                </button>
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
};

export default ContentModeration; 