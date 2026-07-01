import React, { useState, useEffect, useRef, useCallback } from 'react';
import { useNavigate, Link } from 'react-router-dom';
import supabase from '../utils/supabaseClient';
import { reportError } from '../utils/helpers';

function TestimonialsPage() {
    const navigate = useNavigate();
    const [testimonials, setTestimonials] = useState([]);
    const [loading, setLoading] = useState(true);
    const [current, setCurrent] = useState(0);

    // Touch / drag state
    const trackRef = useRef(null);
    const dragging = useRef(false);
    const startX = useRef(0);
    const currentTranslate = useRef(0);
    const prevTranslate = useRef(0);
    const animFrame = useRef(null);

    useEffect(() => {
        window.scrollTo(0, 0);
        loadTestimonials();
    }, []);

    const loadTestimonials = async () => {
        setLoading(true);
        try {
            const { data, error } = await supabase
                .from('impact_stories')
                .select('*')
                .eq('type', 'testimonial')
                .eq('is_active', true)
                .order('display_order');

            if (error) throw error;
            setTestimonials(data || []);
        } catch (error) {
            console.error('Error loading testimonials:', error);
            reportError(error);
        } finally {
            setLoading(false);
        }
    };

    const total = testimonials.length;

    const goTo = useCallback((idx) => {
        if (total === 0) return;
        let next = idx;
        if (next < 0) next = total - 1;
        if (next >= total) next = 0;
        setCurrent(next);
    }, [total]);

    const prev = () => goTo(current - 1);
    const next = () => goTo(current + 1);

    // Keyboard navigation
    useEffect(() => {
        const handleKey = (e) => {
            if (e.key === 'ArrowLeft') prev();
            if (e.key === 'ArrowRight') next();
        };
        window.addEventListener('keydown', handleKey);
        return () => window.removeEventListener('keydown', handleKey);
    }, [current, total]);

    // ── Touch / pointer helpers ──
    const getClientX = (e) => (e.touches ? e.touches[0].clientX : e.clientX);

    const onDragStart = (e) => {
        dragging.current = true;
        startX.current = getClientX(e);
        prevTranslate.current = -current * 100;
        if (trackRef.current) trackRef.current.style.transition = 'none';
    };

    const onDragMove = (e) => {
        if (!dragging.current) return;
        const dx = getClientX(e) - startX.current;
        const containerWidth = trackRef.current?.parentElement?.offsetWidth || 1;
        const pct = (dx / containerWidth) * 100;
        currentTranslate.current = prevTranslate.current + pct;
        if (trackRef.current) {
            trackRef.current.style.transform = `translateX(${currentTranslate.current}%)`;
        }
    };

    const onDragEnd = () => {
        if (!dragging.current) return;
        dragging.current = false;
        const moved = currentTranslate.current - prevTranslate.current;
        if (trackRef.current) trackRef.current.style.transition = 'transform 0.4s cubic-bezier(.4,0,.2,1)';

        if (moved < -12) next();
        else if (moved > 12) prev();
        else {
            // snap back
            if (trackRef.current) trackRef.current.style.transform = `translateX(${-current * 100}%)`;
        }
    };

    return (
        <div className="min-h-screen bg-gradient-to-b from-[#2CABE3]/5 via-white to-emerald-50/40">
            <style>{`
                @keyframes fadeSlideIn {
                    from { opacity: 0; transform: translateY(20px); }
                    to   { opacity: 1; transform: translateY(0); }
                }
                .fade-slide { animation: fadeSlideIn 0.6s ease-out forwards; }
            `}</style>

            {/* Hero */}
            <header className="relative overflow-hidden">
                <div className="absolute inset-0 -z-10" aria-hidden="true">
                    <div className="absolute -top-24 -left-24 w-96 h-96 rounded-full bg-[#2CABE3]/15 blur-3xl" />
                    <div className="absolute top-10 -right-24 w-96 h-96 rounded-full bg-emerald-300/20 blur-3xl" />
                </div>
                <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 pt-16 pb-12 sm:pt-20 sm:pb-16">
                    <div className="text-center">
                        <span className="inline-flex items-center px-3 py-1 rounded-full bg-[#2CABE3]/10 text-[#2CABE3] text-xs font-semibold mb-5 ring-1 ring-[#2CABE3]/20">
                            <i className="fas fa-quote-left mr-2" aria-hidden="true"></i>
                            Community Voices
                        </span>
                        <h1 className="text-4xl sm:text-5xl lg:text-6xl font-bold text-gray-900 mb-5 tracking-tight">
                            Community{" "}
                            <span className="bg-gradient-to-r from-[#2CABE3] to-emerald-500 bg-clip-text text-transparent">
                                Testimonials
                            </span>
                        </h1>
                        <p className="text-base sm:text-lg text-gray-600 max-w-2xl mx-auto leading-relaxed">
                            Real testimonials from real people making a difference in our communities
                        </p>
                        <div className="mt-7 flex flex-wrap items-center justify-center gap-2 text-sm">
                            <Link to="/impact-story" onClick={(e) => { e.preventDefault(); navigate('/impact-story'); setTimeout(() => document.getElementById('blog-section')?.scrollIntoView({ behavior: 'smooth' }), 300); }} className="inline-flex items-center gap-2 px-4 py-1.5 rounded-full bg-white shadow-sm ring-1 ring-gray-200 text-gray-700 font-medium hover:text-[#2CABE3] transition">
                                <i className="fas fa-pen-nib text-[10px]" aria-hidden="true" />
                                Blog
                            </Link>
                            <Link to="/news" className="inline-flex items-center gap-2 px-4 py-1.5 rounded-full bg-white shadow-sm ring-1 ring-gray-200 text-gray-700 font-medium hover:text-[#2CABE3] transition">
                                <i className="fas fa-newspaper text-[10px]" aria-hidden="true" />
                                News
                            </Link>
                            <span className="inline-flex items-center gap-2 px-4 py-1.5 rounded-full bg-gradient-to-r from-[#2CABE3] to-emerald-500 text-white font-medium shadow-md">
                                <i className="fas fa-quote-left text-[10px]" aria-hidden="true" />
                                Testimonials
                            </span>
                        </div>
                    </div>
                </div>
            </header>

            <div className="container mx-auto px-4 py-12">
                {/* Swipeable Carousel */}
                <div className="max-w-3xl mx-auto">
                    {loading ? (
                        <div className="text-center py-20">
                            <div className="inline-block animate-spin rounded-full h-12 w-12 border-b-2 border-blue-600"></div>
                        </div>
                    ) : total === 0 ? (
                        <div className="text-center py-20">
                            <p className="text-gray-500 text-lg">No testimonials yet. Check back soon!</p>
                        </div>
                    ) : (
                        <>
                            {/* Carousel viewport */}
                            <div
                                className="relative overflow-hidden rounded-3xl select-none touch-pan-y"
                                onMouseDown={onDragStart}
                                onMouseMove={onDragMove}
                                onMouseUp={onDragEnd}
                                onMouseLeave={onDragEnd}
                                onTouchStart={onDragStart}
                                onTouchMove={onDragMove}
                                onTouchEnd={onDragEnd}
                            >
                                {/* Track */}
                                <div
                                    ref={trackRef}
                                    className="flex transition-transform duration-400 ease-[cubic-bezier(.4,0,.2,1)]"
                                    style={{ transform: `translateX(${-current * 100}%)` }}
                                >
                                    {testimonials.map((item) => (
                                        <div
                                            key={item.id}
                                            className="w-full shrink-0 px-2"
                                        >
                                            <div className="bg-white rounded-3xl shadow-xl p-10 md:p-14 flex flex-col items-center text-center min-h-[320px] justify-center">
                                                <div className="text-6xl text-[#2CABE3] mb-4 leading-none select-none">&ldquo;</div>
                                                <p className="text-gray-600 leading-relaxed text-lg md:text-xl italic mb-8 max-w-2xl">
                                                    {item.quote}
                                                </p>
                                                <h3 className="text-xl font-bold text-gray-900 mb-1">{item.title}</h3>
                                                <p className="text-sm text-gray-500">
                                                    <strong>&mdash; {item.attribution}{item.organization && `, ${item.organization}`}</strong>
                                                </p>
                                            </div>
                                        </div>
                                    ))}
                                </div>

                                {/* Arrow buttons */}
                                {total > 1 && (
                                    <>
                                        <button
                                            onClick={prev}
                                            className="absolute left-3 top-1/2 -translate-y-1/2 bg-white/90 hover:bg-white text-gray-700 hover:text-[#2CABE3] w-11 h-11 rounded-full shadow-lg flex items-center justify-center transition-all z-10"
                                            aria-label="Previous testimonial"
                                        >
                                            <svg className="w-5 h-5" fill="none" stroke="currentColor" strokeWidth={2.5} viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" d="M15 19l-7-7 7-7" /></svg>
                                        </button>
                                        <button
                                            onClick={next}
                                            className="absolute right-3 top-1/2 -translate-y-1/2 bg-white/90 hover:bg-white text-gray-700 hover:text-[#2CABE3] w-11 h-11 rounded-full shadow-lg flex items-center justify-center transition-all z-10"
                                            aria-label="Next testimonial"
                                        >
                                            <svg className="w-5 h-5" fill="none" stroke="currentColor" strokeWidth={2.5} viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" d="M9 5l7 7-7 7" /></svg>
                                        </button>
                                    </>
                                )}
                            </div>

                            {/* Dot indicators */}
                            {total > 1 && (
                                <div className="flex justify-center gap-2 mt-8">
                                    {testimonials.map((_, i) => (
                                        <button
                                            key={i}
                                            onClick={() => goTo(i)}
                                            className={`w-3 h-3 rounded-full transition-all duration-300 ${
                                                i === current
                                                    ? 'bg-[#2CABE3] w-8'
                                                    : 'bg-gray-300 hover:bg-gray-400'
                                            }`}
                                            aria-label={`Go to testimonial ${i + 1}`}
                                        />
                                    ))}
                                </div>
                            )}

                            {/* Counter */}
                            {total > 1 && (
                                <p className="text-center text-sm text-gray-400 mt-4">
                                    {current + 1} / {total}
                                </p>
                            )}
                        </>
                    )}
                </div>
            </div>
        </div>
    );
}

export default TestimonialsPage;
