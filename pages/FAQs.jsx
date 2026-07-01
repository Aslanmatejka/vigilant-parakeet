import React from 'react';
import { useNavigate } from 'react-router-dom';

function FAQs() {
    const navigate = useNavigate();
    const [openIndex, setOpenIndex] = React.useState(null);

    React.useEffect(() => {
        window.scrollTo(0, 0);
    }, []);

    const toggleAccordion = (index) => {
        setOpenIndex(openIndex === index ? null : index);
    };

    const faqs = [
        {
            category: "About Do Good Store",
            questions: [
                {
                    question: "What is Do Good Store?",
                    answer: "Do Good Store is a free, community-powered platform created by All Good Living Foundation (AGLF) that connects surplus food with families who need it. Restaurants, organizations, schools, and neighbors share extra food—and families can easily see what's available at their local school Community Closets. Less waste. More meals. Everybody wins."
                },
                {
                    question: "Who is Do Good Store for?",
                    answer: "Three main groups:\n\n• Sharers – Restaurants, organizations, schools, and community members with surplus food\n\n• Families – Those experiencing food insecurity who want to see what food is available nearby\n\n• Schools & Community Closets – Distribution points where donated food is made accessible to families"
                },
                {
                    question: "Is Do Good Store free to use?",
                    answer: "Yes. Completely free. No subscriptions. No hidden fees. No \"premium hunger\" tier."
                },
                {
                    question: "Who runs Do Good Store?",
                    answer: "Do Good Store is powered by All Good Living Foundation (AGLF), a nonprofit dedicated to ensuring no child or family goes without life's essentials."
                }
            ]
        },
        {
            category: "Sharing Food",
            questions: [
                {
                    question: "What kind of food can be shared?",
                    answer: "Sharers can list:\n\n• Fresh produce\n• Prepared foods (following food safety guidelines)\n• Packaged and nonperishable items\n• School-appropriate snacks and pantry staples\n\nIf it's safe, edible, and something you'd feed your own family—great. If not, it's a no."
                },
                {
                    question: "How does sharing food work?",
                    answer: "Sharers:\n\n1. Post available food on the app\n2. Select a nearby school or Community Closet\n3. Drop off food according to the provided guidelines\n\nAGLF helps coordinate distribution so food gets to families quickly and safely."
                },
                {
                    question: "Can restaurants and businesses participate regularly?",
                    answer: "Absolutely—and we love our repeat sharers. Businesses can:\n\n• Reduce food waste\n• Support local families\n• Show real community impact\n\nWe'll help make it easy and consistent."
                }
            ]
        },
        {
            category: "For Families",
            questions: [
                {
                    question: "How do families use Do Good Store?",
                    answer: "Families can:\n\n• View real-time food availability at their school or Community Closet\n• See what items were donated and when they're available\n• Pick up food discreetly and with dignity\n\nNo guesswork. No awkward conversations. Just access."
                },
                {
                    question: "Do families need to qualify or sign up?",
                    answer: "Access is typically provided through:\n\n• Partner schools\n• Community Closets\n• Referrals from AGLF or trusted community organizations\n\nSome locations may require simple verification to ensure food reaches those who need it most."
                },
                {
                    question: "Is this only for school families?",
                    answer: "Schools are a major access point, but not the only one. Community organizations and partner locations may also participate. Availability depends on local partnerships."
                }
            ]
        },
        {
            category: "Safety & Quality",
            questions: [
                {
                    question: "Is the food safe?",
                    answer: "Yes. AGLF follows food safety guidelines and works only with responsible sharers. Clear labeling, handling instructions, and drop-off standards are part of the process."
                }
            ]
        },
        {
            category: "Community Impact",
            questions: [
                {
                    question: "Does Do Good Store replace food pantries?",
                    answer: "No. It complements them. Do Good Store focuses on surplus food recovery and real-time sharing, helping fill gaps between traditional pantry schedules and increasing access to fresh food."
                },
                {
                    question: "How does this help the community long-term?",
                    answer: "• Less food waste\n• More fresh food access\n• Stronger school-community connections\n• Families supported where they already are\n\nIt's local. It's efficient. And it works."
                }
            ]
        },
        {
            category: "Get Involved",
            questions: [
                {
                    question: "How can I get involved?",
                    answer: "• Share surplus food\n• Encourage a restaurant or organization to join\n• Volunteer with AGLF\n• Spread the word\n\nDoing good is contagious—catch it."
                }
            ]
        }
    ];

    return (
        <div className="min-h-screen bg-gradient-to-b from-[#2CABE3]/5 via-white to-emerald-50/40">
            {/* Hero */}
            <header className="relative overflow-hidden">
                <div className="absolute inset-0 -z-10" aria-hidden="true">
                    <div className="absolute -top-24 -left-24 w-96 h-96 rounded-full bg-[#2CABE3]/15 blur-3xl" />
                    <div className="absolute top-10 -right-24 w-96 h-96 rounded-full bg-emerald-300/20 blur-3xl" />
                </div>
                <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 pt-16 pb-12 sm:pt-20 sm:pb-16">
                    <div className="text-center">
                        <span className="inline-flex items-center px-3 py-1 rounded-full bg-[#2CABE3]/10 text-[#2CABE3] text-xs font-semibold mb-5 ring-1 ring-[#2CABE3]/20">
                            <i className="fas fa-circle-question mr-2" aria-hidden="true"></i>
                            Help Center
                        </span>
                        <h1 className="text-4xl sm:text-5xl lg:text-6xl font-bold text-gray-900 mb-5 tracking-tight">
                            Got questions?{" "}
                            <span className="bg-gradient-to-r from-[#2CABE3] to-emerald-500 bg-clip-text text-transparent">
                                We&apos;ve got answers
                            </span>
                        </h1>
                        <p className="text-base sm:text-lg text-gray-600 max-w-2xl mx-auto leading-relaxed">
                            Find answers to common questions about the Do Good Store and All Good Living Foundation
                        </p>
                    </div>
                </div>
            </header>

            {/* FAQs Content */}
            <div className="container mx-auto px-4 py-12">
                <div className="max-w-4xl mx-auto">
                    {faqs.map((category, categoryIndex) => (
                        <div key={categoryIndex} className="mb-12">
                            <h2 className="text-2xl font-bold text-gray-900 mb-6 flex items-center gap-3">
                                <span className="w-1 h-8 bg-gradient-to-b from-primary-500 to-primary-700 rounded"></span>
                                {category.category}
                            </h2>
                            
                            <div className="space-y-4">
                                {category.questions.map((faq, questionIndex) => {
                                    const globalIndex = `${categoryIndex}-${questionIndex}`;
                                    const isOpen = openIndex === globalIndex;
                                    
                                    return (
                                        <div
                                            key={questionIndex}
                                            className="bg-white rounded-lg shadow-md overflow-hidden hover:shadow-lg transition-shadow"
                                        >
                                            <button
                                                onClick={() => toggleAccordion(globalIndex)}
                                                className="w-full px-6 py-4 text-left flex items-center justify-between gap-4 hover:bg-gray-50 transition-colors"
                                            >
                                                <span className="font-semibold text-gray-900 flex-1">
                                                    {faq.question}
                                                </span>
                                                <i
                                                    className={`fas fa-chevron-${isOpen ? 'up' : 'down'} text-primary-600 transition-transform`}
                                                ></i>
                                            </button>
                                            
                                            {isOpen && (
                                                <div className="px-6 py-4 bg-gray-50 border-t border-gray-200">
                                                    <p className="text-gray-700 leading-relaxed whitespace-pre-line">
                                                        {faq.answer}
                                                    </p>
                                                </div>
                                            )}
                                        </div>
                                    );
                                })}
                            </div>
                        </div>
                    ))}

                    {/* Still Have Questions Section */}
                    <div className="mt-16 bg-gradient-to-r from-primary-600 to-primary-800 rounded-2xl p-8 text-white text-center">
                        <h3 className="text-2xl font-bold mb-4">Still Have Questions?</h3>
                        <p className="text-primary-100 mb-6 max-w-2xl mx-auto">
                            Can&apos;t find what you&apos;re looking for? Our team is here to help!
                        </p>
                        <div className="flex flex-col sm:flex-row gap-4 justify-center">
                            <a
                                href="mailto:info@allgoodlivingfoundation.org"
                                className="bg-white text-primary-600 px-6 py-3 rounded-lg font-semibold hover:bg-primary-50 transition-colors inline-flex items-center justify-center gap-2"
                            >
                                <i className="fas fa-envelope"></i>
                                Email Us
                            </a>
                            <a
                                href="tel:510-522-6288"
                                className="bg-white text-primary-600 px-6 py-3 rounded-lg font-semibold hover:bg-primary-50 transition-colors inline-flex items-center justify-center gap-2"
                            >
                                <i className="fas fa-phone"></i>
                                Call Us
                            </a>
                        </div>
                    </div>
                </div>
            </div>
        </div>
    );
}

export default FAQs;
