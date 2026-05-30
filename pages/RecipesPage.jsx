import React, { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { reportError } from '../utils/helpers';
import { useAuthContext } from '../utils/AuthContext';
import AIRecipePanel from '../components/food/AIRecipePanel';

function RecipesPage() {
    const { isAdmin } = useAuthContext();
    const navigate = useNavigate();
    const [recipes, setRecipes] = useState([]);
    const [loading, setLoading] = useState(true);
    const [expandedId, setExpandedId] = useState(null);

    useEffect(() => {
        window.scrollTo(0, 0);
        loadRecipes();
    }, []);

    const loadRecipes = async () => {
        setLoading(true);
        try {
            const supabaseUrl = import.meta.env.VITE_SUPABASE_URL;
            const supabaseKey = import.meta.env.VITE_SUPABASE_ANON_KEY;

            const controller = new AbortController();
            const timeout = setTimeout(() => controller.abort(), 10000);

            const res = await fetch(
                `${supabaseUrl}/rest/v1/impact_recipes?is_active=eq.true&order=created_at.desc`,
                {
                    headers: {
                        'apikey': supabaseKey,
                        'Authorization': `Bearer ${supabaseKey}`,
                    },
                    signal: controller.signal
                }
            );
            clearTimeout(timeout);

            if (!res.ok) throw new Error(`Failed to load recipes: ${res.status}`);
            const data = await res.json();
            setRecipes(data || []);
        } catch (error) {
            console.error('Error loading recipes:', error);
            reportError(error);
        } finally {
            setLoading(false);
        }
    };

    const getYouTubeId = (url) => {
        if (!url) return null;
        const match = url.match(/(?:youtu\.be\/|youtube\.com\/(?:embed\/|v\/|watch\?v=|shorts\/))([^?&/#]+)/);
        return match ? match[1] : null;
    };

    const getThumbnail = (recipe) => {
        if (recipe.thumbnail_url) return recipe.thumbnail_url;
        const id = getYouTubeId(recipe.youtube_url);
        return id ? `https://img.youtube.com/vi/${id}/hqdefault.jpg` : null;
    };

    if (loading) {
        return (
            <div className="flex items-center justify-center min-h-screen">
                <div className="animate-spin rounded-full h-16 w-16 border-b-2 border-red-500"></div>
            </div>
        );
    }

    return (
        <div className="min-h-screen bg-gray-50">
            <style>{`
                @keyframes riseUp {
                    from { opacity: 0; transform: translateY(40px); }
                    to { opacity: 1; transform: translateY(0); }
                }
                .rise-up { opacity: 0; animation: riseUp 0.6s ease-out forwards; }
            `}</style>

            {/* Expanded Video Modal */}
            {expandedId && (() => {
                const recipe = recipes.find(r => r.id === expandedId);
                const videoId = recipe ? getYouTubeId(recipe.youtube_url) : null;
                if (!recipe || !videoId) return null;
                return (
                    <div
                        className="fixed inset-0 z-50 flex items-center justify-center bg-black/80 backdrop-blur-sm"
                        onClick={() => setExpandedId(null)}
                    >
                        <div
                            className="relative w-full max-w-5xl mx-4 aspect-video rounded-2xl overflow-hidden shadow-2xl"
                            onClick={(e) => e.stopPropagation()}
                        >
                            <iframe
                                src={`https://www.youtube.com/embed/${videoId}?autoplay=1`}
                                className="w-full h-full"
                                allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture"
                                allowFullScreen
                                title={recipe.title}
                            />
                            <button
                                onClick={() => setExpandedId(null)}
                                className="absolute top-3 right-3 w-10 h-10 bg-black/60 hover:bg-black/80 text-white rounded-full flex items-center justify-center transition-colors text-xl font-bold"
                            >
                                ✕
                            </button>
                        </div>
                        <p className="absolute bottom-8 text-white text-lg font-semibold text-center w-full px-4 drop-shadow-lg">{recipe.title}</p>
                    </div>
                );
            })()}

            {/* Admin Button */}
            {isAdmin && (
                <button
                    onClick={() => navigate('/admin/impact-content')}
                    className="fixed bottom-8 right-8 z-40 bg-gradient-to-r from-blue-600 to-blue-700 text-white px-6 py-3 rounded-full font-semibold shadow-2xl hover:shadow-xl transition-all transform hover:scale-105"
                >
                    ✏️ Manage Content
                </button>
            )}

            {/* Hero */}
            <section className="bg-gradient-to-br from-red-50 to-orange-100 py-20">
                <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
                    <div className="text-center">
                        <h1 className="text-5xl md:text-6xl font-bold text-gray-900 mb-6">
                            🍳 Community Recipes
                        </h1>
                        <p className="text-xl text-gray-700 max-w-3xl mx-auto">
                            Delicious recipes from our community — learn to cook with rescued food and reduce waste in your kitchen.
                        </p>
                    </div>
                </div>
            </section>

            {/* Recipes Grid */}
            <section className="py-16">
                <div className="max-w-6xl mx-auto px-4 sm:px-6 lg:px-8">
                    <AIRecipePanel className="mb-10" />
                    {recipes.length === 0 ? (
                        <div className="text-center py-20">
                            <p className="text-gray-500 text-lg">No recipes yet. Check back soon!</p>
                        </div>
                    ) : (
                        <div className="grid sm:grid-cols-2 lg:grid-cols-3 gap-8">
                            {recipes.map((recipe, index) => {
                                return (
                                    <div
                                        key={recipe.id}
                                        className="rise-up bg-white rounded-2xl shadow-lg overflow-hidden hover:shadow-xl transition-all duration-300 hover:-translate-y-1 border border-gray-100"
                                        style={{ animationDelay: `${index * 0.1}s` }}
                                    >
                                        {/* Video / Thumbnail */}
                                        <div className="relative aspect-video bg-gray-900">
                                            <div
                                                className="w-full h-full cursor-pointer group relative"
                                                onClick={() => setExpandedId(recipe.id)}
                                            >
                                                <img
                                                    src={getThumbnail(recipe)}
                                                    alt={recipe.title}
                                                    className="w-full h-full object-cover group-hover:brightness-75 transition-all duration-300"
                                                    onError={(e) => { e.target.onerror = null; e.target.src = 'https://images.unsplash.com/photo-1556909114-f6e7ad7d3136?q=80&w=800&auto=format&fit=crop'; }}
                                                />
                                                {/* Play button overlay */}
                                                <div className="absolute inset-0 flex items-center justify-center">
                                                    <div className="w-16 h-16 bg-red-600 rounded-full flex items-center justify-center shadow-xl group-hover:scale-110 transition-transform">
                                                        <svg className="w-7 h-7 text-white ml-1" fill="currentColor" viewBox="0 0 24 24">
                                                            <path d="M8 5v14l11-7z"/>
                                                        </svg>
                                                    </div>
                                                </div>
                                            </div>
                                        </div>

                                        {/* Info */}
                                        <div className="p-5">
                                            <h3 className="text-lg font-bold text-gray-900 mb-2 line-clamp-2">{recipe.title}</h3>
                                            {recipe.description && (
                                                <p className="text-gray-500 text-sm line-clamp-3 leading-relaxed">{recipe.description}</p>
                                            )}
                                            {recipe.created_at && (
                                                <p className="text-xs text-gray-400 mt-3">
                                                    {new Date(recipe.created_at).toLocaleDateString('en-US', { year: 'numeric', month: 'long', day: 'numeric' })}
                                                </p>
                                            )}
                                        </div>
                                    </div>
                                );
                            })}
                        </div>
                    )}
                </div>
            </section>
        </div>
    );
}

export default RecipesPage;
