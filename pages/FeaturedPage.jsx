import React, { useState, useEffect } from 'react';
import { useNavigate, Link } from 'react-router-dom';
import supabase from '../utils/supabaseClient';
import { reportError } from '../utils/helpers';
import { useAuthContext } from '../utils/AuthContext';

function FeaturedPage() {
    const { isAdmin } = useAuthContext();
    const navigate = useNavigate();
    const [featured, setFeatured] = useState([]);
    const [loading, setLoading] = useState(true);
    const [selectedStory, setSelectedStory] = useState(null);

    useEffect(() => {
        loadFeatured();
    }, []);

    const loadFeatured = async () => {
        setLoading(true);
        try {
            const { data, error } = await supabase
                .from('impact_stories')
                .select('*')
                .eq('type', 'featured')
                .eq('is_active', true)
                .order('display_order');

            if (error) {
                console.error('Error loading featured stories:', error);
                reportError(error, { context: 'Featured page load' });
            }
            setFeatured(data || []);
        } catch (error) {
            console.error('Error loading featured stories:', error);
            reportError(error, { context: 'Featured page load' });
        } finally {
            setLoading(false);
        }
    };

    if (loading) {
        return (
            <div className="flex items-center justify-center min-h-screen">
                <div className="animate-spin rounded-full h-16 w-16 border-b-2 border-blue-600"></div>
            </div>
        );
    }

    // ── Detail View ──
    if (selectedStory) {
        return (
            <div className="min-h-screen bg-gradient-to-b from-[#2CABE3]/5 via-white to-emerald-50/40">
                {/* Admin Manage Button */}
                {isAdmin && (
                    <button
                        onClick={() => navigate('/admin/impact-content')}
                        className="fixed bottom-8 right-8 z-40 bg-gradient-to-r from-blue-600 to-blue-700 text-white px-6 py-3 rounded-full font-semibold shadow-2xl hover:shadow-xl transition-all transform hover:scale-105"
                    >
                        ✏️ Manage Content
                    </button>
                )}

                <article className="max-w-4xl mx-auto px-4 sm:px-6 lg:px-8 py-12">
                    {/* Back button */}
                    <button
                        onClick={() => setSelectedStory(null)}
                        className="mb-8 text-gray-700 hover:text-blue-600 transition-colors flex items-center gap-2 font-semibold"
                    >
                        <span>←</span>
                        <span>Back to Blog</span>
                    </button>

                    {/* Hero image */}
                    {selectedStory.image_url && (
                        <img
                            src={selectedStory.image_url}
                            alt={selectedStory.title}
                            className="w-full h-72 md:h-96 object-cover rounded-2xl shadow-lg mb-8"
                            onError={(e) => { e.target.onerror = null; e.target.src = 'https://images.unsplash.com/photo-1488521787991-ed7bbaae773c?q=80&w=800&auto=format&fit=crop'; }}
                        />
                    )}

                    {/* Meta */}
                    <div className="flex flex-wrap items-center gap-3 mb-4">
                        <span className="px-3 py-1 bg-blue-100 text-blue-700 text-xs font-semibold rounded-full uppercase tracking-wide">Blog</span>
                        {selectedStory.created_at && (
                            <span className="text-sm text-gray-400">
                                {new Date(selectedStory.created_at).toLocaleDateString('en-US', { year: 'numeric', month: 'long', day: 'numeric' })}
                            </span>
                        )}
                    </div>

                    {/* Title */}
                    <h1 className="text-3xl md:text-4xl font-bold text-gray-900 mb-6">{selectedStory.title}</h1>

                    {/* Attribution */}
                    {selectedStory.attribution && (
                        <p className="text-gray-500 mb-8 text-lg">
                            By <strong>{selectedStory.attribution}</strong>
                            {selectedStory.organization && <span> &middot; {selectedStory.organization}</span>}
                        </p>
                    )}

                    {/* Content */}
                    {selectedStory.quote && (
                        <div className="bg-gray-50 border-l-4 border-[#2CABE3] rounded-r-xl p-6 mb-8">
                            <p className="text-lg text-gray-700 leading-relaxed italic">&ldquo;{selectedStory.quote}&rdquo;</p>
                        </div>
                    )}

                    {selectedStory.description && (
                        <p className="text-lg text-gray-600 leading-relaxed mb-8">{selectedStory.description}</p>
                    )}

                    {/* Stats */}
                    {selectedStory.stats && (
                        <div className="bg-primary-50 rounded-xl p-5 mb-8">
                            <p className="text-primary-800 font-medium">📊 {selectedStory.stats}</p>
                        </div>
                    )}

                    {/* Organization info */}
                    {selectedStory.organization && (
                        <div className="flex items-center gap-2 text-sm text-gray-500 mb-8">
                            <span>🏢 {selectedStory.organization}</span>
                        </div>
                    )}

                    {/* Bottom nav */}
                    <div className="border-t pt-8 flex justify-between items-center">
                        <button
                            onClick={() => setSelectedStory(null)}
                            className="text-blue-600 hover:text-blue-800 font-semibold flex items-center gap-2"
                        >
                            ← All Blog Posts
                        </button>
                        <Link to="/impact-story" className="text-gray-500 hover:text-gray-700 font-medium">
                            Impact Story →
                        </Link>
                    </div>
                </article>
            </div>
        );
    }

    // ── Cards Grid View (default) ──
    return (
        <div className="min-h-screen bg-gradient-to-b from-[#2CABE3]/5 via-white to-emerald-50/40">
            {/* Admin Manage Button */}
            {isAdmin && (
                <button
                    onClick={() => navigate('/admin/impact-content')}
                    className="fixed bottom-8 right-8 z-40 bg-gradient-to-r from-blue-600 to-blue-700 text-white px-6 py-3 rounded-full font-semibold shadow-2xl hover:shadow-xl transition-all transform hover:scale-105"
                >
                    ✏️ Manage Content
                </button>
            )}

            {/* Hero */}
            <header className="relative overflow-hidden">
                <div className="absolute inset-0 -z-10" aria-hidden="true">
                    <div className="absolute -top-24 -left-24 w-96 h-96 rounded-full bg-[#2CABE3]/15 blur-3xl" />
                    <div className="absolute top-10 -right-24 w-96 h-96 rounded-full bg-emerald-300/20 blur-3xl" />
                </div>
                <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 pt-16 pb-12 sm:pt-20 sm:pb-16">
                    <button
                        onClick={() => navigate('/impact-story')}
                        className="mb-6 text-gray-600 hover:text-[#2CABE3] transition-colors flex items-center gap-2 text-sm font-medium"
                    >
                        <i className="fas fa-arrow-left text-[10px]" aria-hidden="true" />
                        Back to Impact Story
                    </button>
                    <div className="text-center">
                        <span className="inline-flex items-center px-3 py-1 rounded-full bg-[#2CABE3]/10 text-[#2CABE3] text-xs font-semibold mb-5 ring-1 ring-[#2CABE3]/20">
                            <i className="fas fa-star mr-2" aria-hidden="true"></i>
                            Featured Stories
                        </span>
                        <h1 className="text-4xl sm:text-5xl lg:text-6xl font-bold text-gray-900 mb-5 tracking-tight">
                            Community{" "}
                            <span className="bg-gradient-to-r from-[#2CABE3] to-emerald-500 bg-clip-text text-transparent">
                                Blog
                            </span>
                        </h1>
                        <p className="text-base sm:text-lg text-gray-600 max-w-2xl mx-auto leading-relaxed">
                            Highlighting the most impactful stories from our community &mdash; milestones, achievements, and moments that inspire.
                        </p>
                    </div>
                </div>
            </header>

            {/* Blog Cards Grid */}
            <section className="py-16">
                <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
                    {featured.length === 0 ? (
                        <div className="text-center py-16">
                            <p className="text-gray-500 text-lg">No blog posts yet. Check back soon!</p>
                        </div>
                    ) : (
                        <div className="grid sm:grid-cols-2 lg:grid-cols-3 gap-8">
                            {featured.map((story) => (
                                <div
                                    key={story.id}
                                    onClick={() => setSelectedStory(story)}
                                    className="bg-white rounded-2xl shadow-lg overflow-hidden cursor-pointer group hover:shadow-xl transition-all duration-300 hover:-translate-y-1"
                                >
                                    <div className="relative overflow-hidden">
                                        <img
                                            src={story.image_url || 'https://images.unsplash.com/photo-1488521787991-ed7bbaae773c?q=80&w=800&auto=format&fit=crop'}
                                            alt={story.title}
                                            className="w-full h-52 object-cover group-hover:scale-105 transition-transform duration-300"
                                            onError={(e) => { e.target.onerror = null; e.target.src = 'https://images.unsplash.com/photo-1488521787991-ed7bbaae773c?q=80&w=800&auto=format&fit=crop'; }}
                                        />
                                        <div className="absolute inset-0 bg-gradient-to-t from-black/30 to-transparent opacity-0 group-hover:opacity-100 transition-opacity duration-300 flex items-end justify-center pb-4">
                                            <span className="text-white font-semibold text-sm bg-[#2CABE3]/90 px-4 py-2 rounded-full">Read More →</span>
                                        </div>
                                    </div>
                                    <div className="p-5">
                                        <h3 className="text-lg font-bold text-gray-900 group-hover:text-blue-600 transition-colors line-clamp-2">{story.title}</h3>
                                        {story.created_at && (
                                            <p className="text-xs text-gray-400 mt-2">
                                                {new Date(story.created_at).toLocaleDateString('en-US', { year: 'numeric', month: 'long', day: 'numeric' })}
                                            </p>
                                        )}
                                    </div>
                                </div>
                            ))}
                        </div>
                    )}
                </div>
            </section>

            {/* CTA Section */}
            <section className="py-16 bg-gradient-to-br from-primary-50 to-primary-100">
                <div className="max-w-4xl mx-auto px-4 sm:px-6 lg:px-8 text-center">
                    <h2 className="text-4xl font-bold text-gray-900 mb-6">Be Part of Our Story</h2>
                    <p className="text-lg text-gray-700 mb-8">
                        Every meal shared, every pound of food saved — it all starts with you.
                    </p>
                    <div className="flex flex-col sm:flex-row gap-4 justify-center">
                        <Link to="/signup" className="bg-[#2CABE3] text-white px-8 py-4 rounded-xl font-bold text-lg hover:opacity-90 transition-all shadow-lg">
                            Join the Platform
                        </Link>
                        <Link to="/donate" className="bg-primary-600 text-white px-8 py-4 rounded-xl font-bold text-lg hover:opacity-90 transition-all shadow-lg">
                            Support Our Mission
                        </Link>
                    </div>
                </div>
            </section>
        </div>
    );
}

export default FeaturedPage;
