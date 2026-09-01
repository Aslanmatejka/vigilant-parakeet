import React, { useState, useEffect, useCallback, useRef } from 'react';
import { useNavigate, useLocation } from 'react-router-dom';
import { useTutorial } from '../../utils/TutorialContext';

// ─── Step Definitions (8 steps) ─────────────────────────────────────
const STEPS = [
    // 1. Welcome
    {
        id: 'welcome',
        target: null,
        icon: 'fa-seedling',
        title: 'Welcome to DoGoods!',
        content: 'DoGoods connects families with free food and resources in Alameda County. Let\'s walk through the platform together — it only takes a minute.',
        placement: 'center',
        route: '/'
    },
    // 2. Sign Up
    {
        id: 'signup',
        target: '[data-tutorial="signup-btn"]',
        icon: 'fa-user-plus',
        title: 'Sign Up',
        content: 'Create a free account or sign in to access your dashboard, claim food, and connect with your community. You\'ll need an approval number from your school in order to sign up.',
        placement: 'bottom',
        route: '/'
    },
    // 3. View Your Community
    {
        id: 'community',
        target: '[data-tutorial="communities-section"]',
        icon: 'fa-users',
        title: 'View Your Community',
        content: 'Select your community to see what All Good Living Foundation programs are offered in your school\'s community.',
        placement: 'bottom',
        route: '/'
    },
    // 4. Find Food
    {
        id: 'find-food',
        target: '[href="/find"]',
        icon: 'fa-search',
        title: 'Find Food',
        content: 'Browse available food shared by your community, and select items to feed your family.',
        placement: 'bottom',
        route: '/'
    },
    // 5. Claim Food
    {
        id: 'claim-food',
        target: null,
        icon: 'fa-hand-pointer',
        title: 'Claim Food',
        content: 'When you find something you need, click "Claim" to reserve it. You\'ll receive pickup details and can track your claim in your dashboard.',
        placement: 'center',
        route: null,
        image: 'https://images.unsplash.com/photo-1488459716781-31db52582fe9?w=400&h=200&fit=crop'
    },
    // 6. Pick Up Your Food
    {
        id: 'pickup',
        target: null,
        icon: 'fa-receipt',
        title: 'Pick Up Your Food',
        content: 'Your food is available in your school\'s community closet. Show the community manager at your school the receipt in your dashboard, and pick up the items you claimed.',
        placement: 'center',
        route: null
    },
    // 7. Resources
    {
        id: 'resources',
        target: null,
        icon: 'fa-book-open',
        title: 'Resources',
        content: 'Stay up to date on All Good Living Foundation\'s events and programs, and learn about our partners and impact.',
        placement: 'center',
        route: '/',
        highlightMultiple: ['[href="/impact-story"]', '[href="/sponsors"]']
    },
    // 8. You're All Set
    {
        id: 'complete',
        target: null,
        icon: 'fa-check-circle',
        title: 'You\'re All Set!',
        content: 'You now know how to navigate DoGoods. Click the help button (?) in the header anytime to restart this tour.',
        placement: 'center',
        route: null
    }
];

// ─── Component ──────────────────────────────────────────────────────
function Tutorial() {
    const {
        isTutorialOpen,
        currentStepIndex,
        closeTutorial,
        completeTutorial,
        nextStep,
        prevStep,
        goToStep,
    } = useTutorial();

    const navigate = useNavigate();
    const location = useLocation();
    const [highlightRect, setHighlightRect] = useState(null);
    const [multiHighlightRects, setMultiHighlightRects] = useState([]);
    const tooltipRef = useRef(null);
    const resizeTimerRef = useRef(null);

    const steps = STEPS;
    const currentStep = steps[currentStepIndex] || steps[0];
    const isFirstStep = currentStepIndex === 0;
    const isLastStep = currentStepIndex === steps.length - 1;

    // Highlight target element(s)
    const updateHighlight = useCallback(() => {
        if (!isTutorialOpen) {
            setHighlightRect(null);
            setMultiHighlightRects([]);
            return;
        }

        // Multi-highlight for Resources step
        if (currentStep?.highlightMultiple) {
            const rects = currentStep.highlightMultiple
                .map(sel => document.querySelector(sel))
                .filter(Boolean)
                .map(el => {
                    const rect = el.getBoundingClientRect();
                    return {
                        top: rect.top - 6,
                        left: rect.left - 6,
                        width: rect.width + 12,
                        height: rect.height + 12
                    };
                });
            setMultiHighlightRects(rects);
            setHighlightRect(null);
            if (rects.length > 0) {
                document.querySelector(currentStep.highlightMultiple[0])?.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
            }
            return;
        }

        setMultiHighlightRects([]);

        if (!currentStep?.target) {
            setHighlightRect(null);
            return;
        }
        const el = document.querySelector(currentStep.target);
        if (el) {
            const rect = el.getBoundingClientRect();
            setHighlightRect({
                top: rect.top - 8,
                left: rect.left - 8,
                width: rect.width + 16,
                height: rect.height + 16
            });
            el.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
        } else {
            setHighlightRect(null);
        }
    }, [isTutorialOpen, currentStep]);

    useEffect(() => {
        updateHighlight();
        // Also recalculate on resize/scroll
        const handleReposition = () => {
            clearTimeout(resizeTimerRef.current);
            resizeTimerRef.current = setTimeout(updateHighlight, 100);
        };
        window.addEventListener('resize', handleReposition);
        window.addEventListener('scroll', handleReposition, true);
        return () => {
            window.removeEventListener('resize', handleReposition);
            window.removeEventListener('scroll', handleReposition, true);
            clearTimeout(resizeTimerRef.current);
        };
    }, [updateHighlight]);

    // Navigate to required route if step requests it
    useEffect(() => {
        if (!isTutorialOpen || !currentStep?.route) return;
        if (location.pathname !== currentStep.route) {
            navigate(currentStep.route);
        }
    }, [isTutorialOpen, currentStep, location.pathname, navigate]);

    if (!isTutorialOpen) return null;

    const handleNext = () => {
        if (isLastStep) {
            completeTutorial();
        } else {
            nextStep();
        }
    };

    const handlePrevious = () => {
        if (!isFirstStep) prevStep();
    };

    const handleSkip = () => {
        closeTutorial();
    };

    // Tooltip positioning
    const getTooltipStyle = () => {
        if (!highlightRect || currentStep?.placement === 'center') {
            return {
                position: 'fixed',
                top: '50%',
                left: '50%',
                transform: 'translate(-50%, -50%)',
                maxWidth: '520px',
                width: '92%'
            };
        }

        const style = {
            position: 'fixed',
            maxWidth: '420px',
            width: '92%',
            zIndex: 10001
        };

        const viewH = window.innerHeight;
        const viewW = window.innerWidth;
        const spaceBelow = viewH - (highlightRect.top + highlightRect.height);
        const spaceAbove = highlightRect.top;

        // Prefer below, then above, then center
        if (spaceBelow > 200) {
            style.top = `${highlightRect.top + highlightRect.height + 16}px`;
            style.left = `${Math.min(Math.max(highlightRect.left + highlightRect.width / 2, 220), viewW - 220)}px`;
            style.transform = 'translateX(-50%)';
        } else if (spaceAbove > 200) {
            style.bottom = `${viewH - highlightRect.top + 16}px`;
            style.left = `${Math.min(Math.max(highlightRect.left + highlightRect.width / 2, 220), viewW - 220)}px`;
            style.transform = 'translateX(-50%)';
        } else {
            style.top = '50%';
            style.left = '50%';
            style.transform = 'translate(-50%, -50%)';
        }

        return style;
    };

    // ─── Main tutorial UI ───────────────────────────────────────────
    // Build an SVG overlay with cutout holes so highlighted elements are fully visible
    const hasAnyCutout = highlightRect || multiHighlightRects.length > 0;

    return (
        <>
            {/* Dark overlay — uses SVG mask to cut transparent holes for spotlighted elements */}
            {hasAnyCutout ? (
                <svg className="fixed inset-0 w-full h-full z-[9999]" onClick={handleSkip} style={{ pointerEvents: 'auto' }}>
                    <defs>
                        <mask id="tutorial-mask">
                            {/* White = visible (dark overlay shows), black = hidden (cutout) */}
                            <rect x="0" y="0" width="100%" height="100%" fill="white" />
                            {highlightRect && (
                                <rect
                                    x={highlightRect.left}
                                    y={highlightRect.top}
                                    width={highlightRect.width}
                                    height={highlightRect.height}
                                    rx="12"
                                    fill="black"
                                />
                            )}
                            {multiHighlightRects.map((rect, i) => (
                                <rect
                                    key={i}
                                    x={rect.left}
                                    y={rect.top}
                                    width={rect.width}
                                    height={rect.height}
                                    rx="12"
                                    fill="black"
                                />
                            ))}
                        </mask>
                    </defs>
                    <rect x="0" y="0" width="100%" height="100%" fill="rgba(0,0,0,0.6)" mask="url(#tutorial-mask)" />
                </svg>
            ) : (
                <div className="fixed inset-0 bg-black/60 z-[9999] transition-opacity" onClick={handleSkip} />
            )}

            {/* Spotlight border ring (single) */}
            {highlightRect && (
                <div
                    className="fixed pointer-events-none z-[10000] tutorial-spotlight"
                    style={{
                        top: `${highlightRect.top}px`,
                        left: `${highlightRect.left}px`,
                        width: `${highlightRect.width}px`,
                        height: `${highlightRect.height}px`,
                        border: '3px solid #2CABE3',
                        borderRadius: '12px',
                        boxShadow: '0 0 30px rgba(44, 171, 227, 0.4)',
                    }}
                />
            )}

            {/* Spotlight border rings (multiple — Resources step) */}
            {multiHighlightRects.map((rect, i) => (
                <div
                    key={i}
                    className="fixed pointer-events-none z-[10000] tutorial-spotlight"
                    style={{
                        top: `${rect.top}px`,
                        left: `${rect.left}px`,
                        width: `${rect.width}px`,
                        height: `${rect.height}px`,
                        border: '3px solid #2CABE3',
                        borderRadius: '12px',
                        boxShadow: '0 0 20px rgba(44, 171, 227, 0.4)',
                    }}
                />
            ))}

            {/* Tooltip card */}
            <div
                ref={tooltipRef}
                className="bg-white rounded-2xl shadow-2xl z-[10001] animate-fadeIn overflow-hidden"
                style={getTooltipStyle()}
            >
                {/* Icon header bar */}
                <div className="bg-gradient-to-r from-[#2CABE3] to-[#1b8dbf] px-6 py-4 flex items-center gap-3">
                    <div className="w-10 h-10 rounded-full bg-white/20 flex items-center justify-center">
                        <i className={`fas ${currentStep.icon || 'fa-info-circle'} text-white text-lg`}></i>
                    </div>
                    <div className="flex-grow">
                        <h3 className="text-lg font-bold text-white">{currentStep.title}</h3>
                    </div>
                    <button
                        onClick={handleSkip}
                        className="text-white/70 hover:text-white transition-colors"
                        aria-label="Close tutorial"
                    >
                        <i className="fas fa-times text-lg"></i>
                    </button>
                </div>

                <div className="p-6">
                    {/* Optional image (Claim Food step) */}
                    {currentStep.image && (
                        <div className="mb-4 rounded-xl overflow-hidden border border-gray-100">
                            <img src={currentStep.image} alt={currentStep.title} className="w-full h-40 object-cover" />
                        </div>
                    )}

                    <p className="text-gray-600 leading-relaxed mb-5">{currentStep.content}</p>

                    {/* Step dots */}
                    <div className="flex items-center justify-center gap-1.5 mb-5">
                        {steps.map((_, i) => (
                            <button
                                key={i}
                                onClick={() => goToStep(i)}
                                className={`rounded-full transition-all duration-300 ${
                                    i === currentStepIndex
                                        ? 'w-6 h-2.5 bg-[#2CABE3]'
                                        : i < currentStepIndex
                                        ? 'w-2.5 h-2.5 bg-[#2CABE3]/40'
                                        : 'w-2.5 h-2.5 bg-gray-200'
                                }`}
                                aria-label={`Go to step ${i + 1}`}
                            />
                        ))}
                    </div>

                    {/* Progress text */}
                    <div className="text-xs text-gray-400 text-center mb-4">
                        Step {currentStepIndex + 1} of {steps.length}
                    </div>

                    {/* Actions */}
                    <div className="flex items-center justify-between">
                        <button
                            onClick={handleSkip}
                            className="text-gray-400 hover:text-gray-600 text-sm font-medium transition-colors"
                        >
                            Skip
                        </button>
                        <div className="flex gap-2">
                            {!isFirstStep && (
                                <button
                                    onClick={handlePrevious}
                                    className="px-4 py-2 border border-gray-200 rounded-xl hover:bg-gray-50 font-medium text-sm text-gray-700 transition-colors"
                                >
                                    <i className="fas fa-arrow-left mr-1 text-xs"></i>
                                    Back
                                </button>
                            )}
                            <button
                                onClick={handleNext}
                                className="px-5 py-2 bg-[#2CABE3] text-white rounded-xl hover:bg-[#1b8dbf] font-medium text-sm transition-colors shadow-sm"
                            >
                                {isLastStep ? (
                                    <>Finish <i className="fas fa-check ml-1 text-xs"></i></>
                                ) : (
                                    <>Next <i className="fas fa-arrow-right ml-1 text-xs"></i></>
                                )}
                            </button>
                        </div>
                    </div>
                </div>
            </div>

            <style>{tutorialStyles}</style>
        </>
    );
}

const tutorialStyles = `
    @keyframes fadeIn {
        from { opacity: 0; transform: translateY(10px); }
        to   { opacity: 1; transform: translateY(0); }
    }
    .animate-fadeIn {
        animation: fadeIn 0.25s ease-out;
    }
    .tutorial-spotlight {
        animation: spotlightPulse 2s ease-in-out infinite;
    }
    @keyframes spotlightPulse {
        0%, 100% { box-shadow: 0 0 0 9999px rgba(0,0,0,0.55), 0 0 30px rgba(44,171,227,0.4); }
        50%      { box-shadow: 0 0 0 9999px rgba(0,0,0,0.55), 0 0 40px rgba(44,171,227,0.6); }
    }
`;

export default Tutorial;
