import React, { useState, useEffect } from 'react';
import { useNavigate, Link } from 'react-router-dom';
import supabase from '../utils/supabaseClient';
import { reportError } from '../utils/helpers';
import { useAuthContext } from '../utils/AuthContext';

function ImpactStory() {
    const { isAdmin } = useAuthContext();
    const navigate = useNavigate();
    const [stories, setStories] = useState([]);
    const [gallery, setGallery] = useState([]);
    const [loading, setLoading] = useState(true);
    const [selectedStory, setSelectedStory] = useState(null);
    const [expandedGalleryId, setExpandedGalleryId] = useState(null);

    // Newsletter form state
    const [newsletterSuccess, setNewsletterSuccess] = useState(false);
    const [newsletterError, setNewsletterError] = useState('');
    const [isSubmitting, setIsSubmitting] = useState(false);
    const newsletterTimerRef = React.useRef(null);

    useEffect(() => {
        loadContent();
        window.scrollTo(0, 0);
        return () => {
            if (newsletterTimerRef.current) clearTimeout(newsletterTimerRef.current);
        };
    }, []);

    const loadContent = async () => {
        setLoading(true);
        try {
            const [storiesRes, galleryRes] = await Promise.all([
                supabase.from('impact_stories').select('*').eq('is_active', true).order('display_order'),
                supabase.from('impact_gallery').select('*').eq('is_active', true).order('display_order')
            ]);
            setStories(storiesRes.data || []);
            setGallery(galleryRes.data || []);
        } catch (error) {
            console.error('Error loading content:', error);
            reportError(error);
        } finally {
            setLoading(false);
        }
    };

    const toggleGalleryExpand = (id) => {
        setExpandedGalleryId(expandedGalleryId === id ? null : id);
    };

    const handleNewsletterSubmit = async (e) => {
        e.preventDefault();
        setIsSubmitting(true);
        setNewsletterError('');
        setNewsletterSuccess(false);

        const formData = new FormData(e.target);
        const data = {
            first_name: formData.get('firstName'),
            last_name: formData.get('lastName'),
            email: formData.get('email'),
            consent: formData.get('consent') === 'on',
            source: 'impact-story-page'
        };

        const emailRegex = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
        if (!emailRegex.test(data.email)) {
            setNewsletterError('Please enter a valid email address.');
            setIsSubmitting(false);
            return;
        }

        try {
            const { data: existing } = await supabase
                .from('newsletter_subscriptions')
                .select('email, is_active')
                .eq('email', data.email)
                .maybeSingle();

            if (existing) {
                if (existing.is_active) {
                    setNewsletterError('This email is already subscribed!');
                    setIsSubmitting(false);
                    return;
                } else {
                    await supabase
                        .from('newsletter_subscriptions')
                        .update({
                            is_active: true,
                            subscribed_at: new Date().toISOString(),
                            first_name: data.first_name,
                            last_name: data.last_name,
                            consent: data.consent
                        })
                        .eq('email', data.email);
                }
            } else {
                await supabase.from('newsletter_subscriptions').insert([data]);
            }

            setNewsletterSuccess(true);
            if (newsletterTimerRef.current) clearTimeout(newsletterTimerRef.current);
            newsletterTimerRef.current = setTimeout(() => setNewsletterSuccess(false), 5000);
            e.target.reset();
        } catch (error) {
            console.error('Error submitting newsletter:', error);
            setNewsletterError('Something went wrong. Please try again.');
        } finally {
            setIsSubmitting(false);
        }
    };

    const featuredStories = stories
        .filter(s => s.type === 'featured')
        .sort((a, b) => new Date(b.created_at) - new Date(a.created_at));

    if (loading) {
        return (
            <div className="flex items-center justify-center min-h-screen">
                <div className="animate-spin rounded-full h-16 w-16 border-b-2 border-blue-600"></div>
            </div>
        );
    }

    // ── Blog Detail View ──
    if (selectedStory) {
        return (
            <div className="min-h-screen bg-gray-50">
                {isAdmin && (
                    <button
                        onClick={() => navigate('/admin/impact-content')}
                        className="fixed bottom-8 right-8 z-40 bg-gradient-to-r from-blue-600 to-blue-700 text-white px-6 py-3 rounded-full font-semibold shadow-2xl hover:shadow-xl transition-all transform hover:scale-105"
                    >
                        &#9999;&#65039; Manage Content
                    </button>
                )}

                <article className="max-w-4xl mx-auto px-4 sm:px-6 lg:px-8 py-12">
                    <button
                        onClick={() => setSelectedStory(null)}
                        className="mb-8 text-gray-700 hover:text-blue-600 transition-colors flex items-center gap-2 font-semibold"
                    >
                        <span>&larr;</span>
                        <span>Back to Impact Story</span>
                    </button>

                    {selectedStory.image_url && (
                        <img
                            src={selectedStory.image_url}
                            alt={selectedStory.title}
                            className="w-full max-h-[28rem] object-contain rounded-2xl shadow-lg mb-8 bg-gray-100"
                            onError={(e) => { e.target.onerror = null; e.target.src = 'https://images.unsplash.com/photo-1488521787991-ed7bbaae773c?q=80&w=800&auto=format&fit=crop'; }}
                        />
                    )}

                    <div className="flex flex-wrap items-center gap-3 mb-4">
                        <span className="px-3 py-1 bg-blue-100 text-blue-700 text-xs font-semibold rounded-full uppercase tracking-wide">Blog</span>
                        {selectedStory.created_at && (
                            <span className="text-sm text-gray-400">
                                {new Date(selectedStory.created_at).toLocaleDateString('en-US', { year: 'numeric', month: 'long', day: 'numeric' })}
                            </span>
                        )}
                    </div>

                    <h1 className="text-3xl md:text-4xl font-bold text-gray-900 mb-6">{selectedStory.title}</h1>

                    {selectedStory.attribution && (
                        <p className="text-gray-500 mb-8 text-lg">
                            By <strong>{selectedStory.attribution}</strong>
                            {selectedStory.organization && <span> &middot; {selectedStory.organization}</span>}
                        </p>
                    )}

                    {selectedStory.quote && (
                        <div className="bg-gray-50 border-l-4 border-[#2CABE3] rounded-r-xl p-6 mb-8">
                            <p className="text-lg text-gray-700 leading-relaxed italic">&ldquo;{selectedStory.quote}&rdquo;</p>
                        </div>
                    )}

                    {selectedStory.description && (
                        <p className="text-lg text-gray-600 leading-relaxed mb-8">{selectedStory.description}</p>
                    )}

                    {selectedStory.stats && (
                        <div className="bg-primary-50 rounded-xl p-5 mb-8">
                            <p className="text-primary-800 font-medium">&#128202; {selectedStory.stats}</p>
                        </div>
                    )}

                    {selectedStory.organization && (
                        <div className="flex items-center gap-2 text-sm text-gray-500 mb-8">
                            <span>&#127970; {selectedStory.organization}</span>
                        </div>
                    )}

                    <div className="border-t pt-8 flex justify-between items-center">
                        <button
                            onClick={() => setSelectedStory(null)}
                            className="text-blue-600 hover:text-blue-800 font-semibold flex items-center gap-2"
                        >
                            &larr; Back to Impact Story
                        </button>
                        <Link to="/news" className="text-gray-500 hover:text-gray-700 font-medium">
                            News &rarr;
                        </Link>
                    </div>
                </article>
            </div>
        );
    }

    // ── Main Page ──
    return (
        <div className="min-h-screen bg-gradient-to-b from-[#2CABE3]/5 via-white to-emerald-50/40 -mx-6 md:-mx-10 -my-6 md:-my-10">
            <style>{`
                @keyframes fadeIn {
                    from { opacity: 0; transform: translateY(20px); }
                    to { opacity: 1; transform: translateY(0); }
                }
                .fade-in { animation: fadeIn 0.8s ease-out forwards; }
                @keyframes riseUp {
                    from { opacity: 0; transform: translateY(40px); }
                    to { opacity: 1; transform: translateY(0); }
                }
                .rise-up { opacity: 0; animation: riseUp 0.6s ease-out forwards; }
            `}</style>

            {/* Admin Edit Button */}
            {isAdmin && (
                <button
                    onClick={() => navigate('/admin/impact-content')}
                    className="fixed bottom-8 right-8 z-40 bg-gradient-to-r from-blue-600 to-blue-700 text-white px-6 py-3 rounded-full font-semibold shadow-2xl hover:shadow-xl transition-all transform hover:scale-105"
                >
                    &#9999;&#65039; Manage Content
                </button>
            )}

            {/* Hero Section */}
            <header className="relative overflow-hidden">
                {/* Decorative gradient blobs */}
                <div className="absolute inset-0 -z-10" aria-hidden="true">
                    <div className="absolute -top-24 -left-24 w-96 h-96 rounded-full bg-[#2CABE3]/15 blur-3xl" />
                    <div className="absolute top-10 -right-24 w-96 h-96 rounded-full bg-emerald-300/20 blur-3xl" />
                </div>

                <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 pt-16 pb-12 sm:pt-20 sm:pb-16">
                    <div className="text-center">
                        <span className="inline-flex items-center px-3 py-1 rounded-full bg-[#2CABE3]/10 text-[#2CABE3] text-xs font-semibold mb-5 ring-1 ring-[#2CABE3]/20">
                            <i className="fas fa-seedling mr-2" aria-hidden="true"></i>
                            Real Stories, Real Impact
                        </span>
                        <h1 className="text-4xl sm:text-5xl lg:text-6xl font-bold text-gray-900 mb-5 tracking-tight">
                            Our Impact{" "}
                            <span className="bg-gradient-to-r from-[#2CABE3] to-emerald-500 bg-clip-text text-transparent">
                                Story
                            </span>
                        </h1>
                        <p className="text-base sm:text-lg text-gray-600 max-w-2xl mx-auto leading-relaxed">
                            Connecting good food to families in need through smart technology and community care
                        </p>
                        <div className="mt-7 flex flex-wrap items-center justify-center gap-2 text-sm">
                            <button
                                onClick={() => document.getElementById('blog-section')?.scrollIntoView({ behavior: 'smooth' })}
                                className="inline-flex items-center gap-2 px-4 py-1.5 rounded-full bg-white shadow-sm ring-1 ring-gray-200 text-gray-700 font-medium hover:text-[#2CABE3] transition"
                            >
                                <i className="fas fa-pen-nib text-[10px]" aria-hidden="true" />
                                Blog
                            </button>
                            <Link
                                to="/news"
                                className="inline-flex items-center gap-2 px-4 py-1.5 rounded-full bg-white shadow-sm ring-1 ring-gray-200 text-gray-700 font-medium hover:text-[#2CABE3] transition"
                            >
                                <i className="fas fa-newspaper text-[10px]" aria-hidden="true" />
                                News
                            </Link>
                            <Link
                                to="/testimonials"
                                className="inline-flex items-center gap-2 px-4 py-1.5 rounded-full bg-white shadow-sm ring-1 ring-gray-200 text-gray-700 font-medium hover:text-[#2CABE3] transition"
                            >
                                <i className="fas fa-quote-left text-[10px]" aria-hidden="true" />
                                Testimonials
                            </Link>
                        </div>
                    </div>
                </div>
            </header>

            {/* ── Blog / Featured Cards (Default Section) ── */}
            <section id="blog-section" className="py-16 bg-white">
                <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
                    <h2 className="text-3xl font-bold text-gray-900 mb-2">Blog</h2>
                    <p className="text-gray-500 mb-8">Our latest stories, updates, and community highlights</p>

                    {featuredStories.length === 0 ? (
                        <div className="text-center py-12">
                            <p className="text-gray-400 text-lg">No blog posts yet. Check back soon!</p>
                        </div>
                    ) : (
                        <div className="flex flex-col gap-8 max-w-4xl mx-auto">
                            {featuredStories.map((story, index) => (
                                <div
                                    key={story.id}
                                    onClick={() => setSelectedStory(story)}
                                    className="rise-up bg-white rounded-2xl shadow-lg overflow-hidden cursor-pointer group hover:shadow-xl transition-all duration-300 hover:-translate-y-1 border border-gray-100 flex flex-col md:flex-row"
                                    style={{ animationDelay: `${index * 0.12}s` }}
                                >
                                    <div className="relative overflow-hidden md:w-80 shrink-0">
                                        <img
                                            src={story.image_url || 'https://images.unsplash.com/photo-1488521787991-ed7bbaae773c?q=80&w=800&auto=format&fit=crop'}
                                            alt={story.title}
                                            className="w-full h-52 md:h-full object-cover group-hover:scale-105 transition-transform duration-300"
                                            onError={(e) => { e.target.onerror = null; e.target.src = 'https://images.unsplash.com/photo-1488521787991-ed7bbaae773c?q=80&w=800&auto=format&fit=crop'; }}
                                        />
                                        <div className="absolute inset-0 bg-gradient-to-t from-black/30 to-transparent opacity-0 group-hover:opacity-100 transition-opacity duration-300 flex items-end justify-center pb-4">
                                            <span className="text-white font-semibold text-sm bg-[#2CABE3]/90 px-4 py-2 rounded-full">Read More &rarr;</span>
                                        </div>
                                    </div>
                                    <div className="p-6 flex flex-col justify-center">
                                        {story.created_at && (
                                            <p className="text-xs text-gray-400 mb-2 uppercase tracking-wide font-medium">
                                                {new Date(story.created_at).toLocaleDateString('en-US', { year: 'numeric', month: 'long', day: 'numeric' })}
                                            </p>
                                        )}
                                        <h3 className="text-xl font-bold text-gray-900 group-hover:text-blue-600 transition-colors mb-2">{story.title}</h3>
                                        {story.quote && (
                                            <p className="text-gray-500 line-clamp-3 text-sm leading-relaxed">{story.quote}</p>
                                        )}
                                        <span className="mt-4 text-[#2CABE3] font-semibold text-sm group-hover:underline">Read More &rarr;</span>
                                    </div>
                                </div>
                            ))}
                        </div>
                    )}

                    {featuredStories.length > 0 && (
                        <div className="text-center mt-10">
                            <Link to="/featured" className="inline-block bg-[#2CABE3] text-white px-8 py-3 rounded-xl font-semibold hover:opacity-90 transition-all shadow-md">
                                View All Blog Posts &rarr;
                            </Link>
                        </div>
                    )}
                </div>
            </section>

            {/* ── Gallery Section ── */}
            {gallery.length > 0 && (
                <section className="py-20 bg-white">
                    <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
                        <h2 className="text-3xl font-bold text-gray-900 mb-2">Gallery</h2>
                        <p className="text-gray-500 mb-8">Moments from our community</p>
                        <div className="grid grid-cols-1 md:grid-cols-3 gap-8">
                            {gallery.map((item) => (
                                <div key={item.id} className="group">
                                    <div
                                        className="cursor-pointer relative overflow-hidden rounded-2xl"
                                        onClick={() => toggleGalleryExpand(item.id)}
                                    >
                                        <img
                                            src={item.image_url}
                                            alt={item.title}
                                            className="rounded-2xl shadow-lg w-full h-64 object-cover group-hover:scale-105 transition-transform duration-300"
                                        />
                                        <div className="absolute inset-0 bg-gradient-to-t from-black/40 to-transparent opacity-0 group-hover:opacity-100 transition-opacity duration-300 flex items-end justify-center pb-4 rounded-2xl">
                                            <span className="text-white font-semibold text-sm bg-[#2CABE3]/90 px-4 py-2 rounded-full">
                                                {expandedGalleryId === item.id ? 'Hide Details' : 'View Details'}
                                            </span>
                                        </div>
                                    </div>
                                    <h3 className="text-xl font-bold text-gray-900 mt-4 mb-2">{item.title}</h3>
                                    {expandedGalleryId === item.id && (
                                        <div className="mt-2 bg-gray-50 rounded-xl p-4 border border-gray-200 animate-[fadeIn_0.3s_ease-out]">
                                            {item.description && (
                                                <p className="text-gray-600 leading-relaxed mb-3">{item.description}</p>
                                            )}
                                            {item.category && (
                                                <span className="inline-block px-3 py-1 bg-purple-100 text-purple-700 text-xs font-semibold rounded-full">{item.category}</span>
                                            )}
                                        </div>
                                    )}
                                    {expandedGalleryId !== item.id && item.description && (
                                        <p className="text-gray-600 line-clamp-2">{item.description}</p>
                                    )}
                                </div>
                            ))}
                        </div>
                    </div>
                </section>
            )}

            {/* ── CTA Section ── */}
            <section className="py-20 bg-gradient-to-br from-primary-50 to-blue-50">
                <div className="max-w-4xl mx-auto px-4 sm:px-6 lg:px-8 text-center">
                    <h2 className="text-4xl md:text-5xl font-bold text-gray-900 mb-6">Be Part of Our Story</h2>
                    <p className="text-xl text-gray-600 mb-10">
                        Every meal shared, every pound of food saved, every life touched&mdash;it all starts with you.
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

            {/* ── Newsletter Section ── */}
            <section className="py-20 bg-white">
                <div className="max-w-3xl mx-auto px-4 sm:px-6 lg:px-8">
                    <div className="text-center mb-10">
                        <h2 className="text-3xl font-bold text-gray-900 mb-4">Stay Updated on Our Impact</h2>
                        <p className="text-gray-600">
                            Subscribe to our newsletter for inspiring stories, impact updates, and ways to get involved in fighting food waste.
                        </p>
                    </div>
                    <form onSubmit={handleNewsletterSubmit} className="bg-gray-50 rounded-2xl p-8 shadow-lg">
                        {newsletterSuccess && (
                            <div className="mb-6 p-4 bg-primary-100 border border-primary-400 text-primary-700 rounded-lg">
                                &#10003; Successfully subscribed! Check your email for confirmation.
                            </div>
                        )}
                        {newsletterError && (
                            <div className="mb-6 p-4 bg-red-100 border border-red-400 text-red-700 rounded-lg">
                                {newsletterError}
                            </div>
                        )}
                        <div className="grid grid-cols-1 md:grid-cols-2 gap-4 mb-4">
                            <input type="text" name="firstName" placeholder="First Name *" required className="px-4 py-3 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent" />
                            <input type="text" name="lastName" placeholder="Last Name *" required className="px-4 py-3 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent" />
                        </div>
                        <input type="email" name="email" placeholder="Email Address *" required className="w-full px-4 py-3 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent mb-4" />
                        <label className="flex items-start mb-4 text-sm text-gray-600">
                            <input type="checkbox" name="consent" required className="mt-1 mr-2" />
                            <span>I agree to receive updates and newsletters from DoGoods. You can unsubscribe at any time.</span>
                        </label>
                        <button type="submit" disabled={isSubmitting} className="w-full bg-[#2CABE3] text-white px-6 py-3 rounded-lg font-bold hover:opacity-90 transition-all disabled:opacity-50">
                            {isSubmitting ? 'Subscribing...' : 'Subscribe to Newsletter'}
                        </button>
                    </form>
                </div>
            </section>
        </div>
    );
}

export default ImpactStory;
