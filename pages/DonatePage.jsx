import React from 'react';

function DonatePage() {
    return (
        <div data-name="donate-page" className="min-h-screen bg-gradient-to-b from-[#2CABE3]/5 via-white to-emerald-50/40">
            {/* Hero */}
            <header className="relative overflow-hidden">
                <div className="absolute inset-0 -z-10" aria-hidden="true">
                    <div className="absolute -top-24 -left-24 w-96 h-96 rounded-full bg-[#2CABE3]/15 blur-3xl" />
                    <div className="absolute top-10 -right-24 w-96 h-96 rounded-full bg-emerald-300/20 blur-3xl" />
                </div>
                <div className="max-w-4xl mx-auto px-4 sm:px-6 lg:px-8 pt-16 pb-12 sm:pt-20 sm:pb-16">
                    <div className="text-center">
                        <span className="inline-flex items-center px-3 py-1 rounded-full bg-[#2CABE3]/10 text-[#2CABE3] text-xs font-semibold mb-5 ring-1 ring-[#2CABE3]/20">
                            <i className="fas fa-heart mr-2" aria-hidden="true"></i>
                            Support Our Mission
                        </span>
                        <h1 className="text-4xl sm:text-5xl lg:text-6xl font-bold text-gray-900 mb-5 tracking-tight">
                            Help us rescue{" "}
                            <span className="bg-gradient-to-r from-[#2CABE3] to-emerald-500 bg-clip-text text-transparent">
                                more food
                            </span>
                        </h1>
                        <p className="text-base sm:text-lg text-gray-600 max-w-2xl mx-auto leading-relaxed">
                            Your donation helps us reduce food waste and fight hunger in our communities. Every contribution makes a difference.
                        </p>
                    </div>
                </div>
            </header>

            <div className="max-w-4xl mx-auto px-4 sm:px-6 lg:px-8 pb-20">

            <div className="rounded-2xl overflow-hidden shadow-lg border border-cyan-100 bg-white" style={{ minHeight: '900px' }}>
                <iframe
                    src="https://donorbox.org/embed/school-donations-2"
                    name="donorbox"
                    seamless="seamless"
                    frameBorder="0"
                    scrolling="yes"
                    height="1200px"
                    width="100%"
                    style={{
                        maxWidth: '500px',
                        minWidth: '250px',
                        display: 'block',
                        margin: '0 auto',
                        border: 'none',
                    }}
                    allow="payment"
                    title="Donate to All Good Living Foundation"
                />
            </div>

            <div className="mt-8 text-center text-sm text-gray-500">
                <p>
                    Donations are securely processed through{' '}
                    <a
                        href="https://donorbox.org"
                        target="_blank"
                        rel="noopener noreferrer"
                        className="text-cyan-600 hover:underline"
                    >
                        Donorbox
                    </a>
                    . All Good Living Foundation is a registered nonprofit organization.
                </p>
            </div>
            </div>
        </div>
    );
}

export default DonatePage;
