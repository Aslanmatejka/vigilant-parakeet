import React from "react";
import { useNavigate } from "react-router-dom";

function PrivacyPolicy() {
    const navigate = useNavigate();

    return (
            <div className="min-h-screen bg-gradient-to-b from-[#2CABE3]/5 via-white to-emerald-50/40">
                {/* Hero */}
                <header className="relative overflow-hidden">
                    <div className="absolute inset-0 -z-10" aria-hidden="true">
                        <div className="absolute -top-24 -left-24 w-96 h-96 rounded-full bg-[#2CABE3]/15 blur-3xl" />
                        <div className="absolute top-10 -right-24 w-96 h-96 rounded-full bg-emerald-300/20 blur-3xl" />
                    </div>
                    <div className="max-w-4xl mx-auto px-4 sm:px-6 lg:px-8 pt-16 pb-12 sm:pt-20 sm:pb-16">
                        <div className="text-center">
                            <span className="inline-flex items-center px-3 py-1 rounded-full bg-[#2CABE3]/10 text-[#2CABE3] text-xs font-semibold mb-5 ring-1 ring-[#2CABE3]/20">
                                <i className="fas fa-shield-halved mr-2" aria-hidden="true"></i>
                                Legal
                            </span>
                            <h1 id="privacy-policy-title" className="text-4xl sm:text-5xl lg:text-6xl font-bold text-gray-900 mb-5 tracking-tight">
                                Privacy{" "}
                                <span className="bg-gradient-to-r from-[#2CABE3] to-emerald-500 bg-clip-text text-transparent">
                                    Policy
                                </span>
                            </h1>
                            <p className="text-base sm:text-lg text-gray-600 max-w-2xl mx-auto leading-relaxed">
                                How we collect, use, and protect your information.
                            </p>
                        </div>
                    </div>
                </header>

                <main
                    data-name="privacy-policy"
                    className="max-w-4xl mx-auto pb-12 px-4"
                    role="main"
                    aria-labelledby="privacy-policy-title"
                >
                <article className="prose prose-cyan max-w-none">
                    <p 
                        className="text-gray-600 mb-6"
                        role="contentinfo"
                    >
                        Last Updated: January 15, 2024
                    </p>
                    
                    <p className="mb-6">
                        ShareFoods ("we", "our", or "us") is committed to protecting your privacy. This Privacy Policy explains how we collect, 
                        use, disclose, and safeguard your information when you use our website, mobile application, and services 
                        (collectively, the "Platform"). Please read this Privacy Policy carefully. By using the Platform, you consent 
                        to the data practices described in this statement.
                    </p>
                    
                    <section aria-labelledby="information-collection">
                        <h2 
                            id="information-collection"
                            className="text-2xl font-semibold text-gray-900 mt-8 mb-4"
                        >
                            1. Information We Collect
                        </h2>
                        
                        <section aria-labelledby="personal-information">
                            <h3 
                                id="personal-information"
                                className="text-xl font-semibold text-gray-800 mt-4 mb-2"
                            >
                                1.1 Personal Information
                            </h3>
                            <p>
                                We may collect personal information that you voluntarily provide to us when you:
                            </p>
                            <ul 
                                className="list-disc pl-6 mb-4"
                                role="list"
                            >
                                <li>Register for an account</li>
                                <li>Create or update your user profile</li>
                                <li>Post food listings</li>
                                <li>Communicate with other users</li>
                                <li>Contact our customer support</li>
                                <li>Participate in surveys or promotions</li>
                            </ul>
                            <p>
                                This information may include:
                            </p>
                            <ul 
                                className="list-disc pl-6 mb-4"
                                role="list"
                            >
                                <li>Name</li>
                                <li>Email address</li>
                                <li>Phone number</li>
                                <li>Physical address or general location</li>
                                <li>Profile picture</li>
                                <li>Organization information (if applicable)</li>
                            </ul>
                        </section>
                        
                        <section aria-labelledby="usage-information">
                            <h3 
                                id="usage-information"
                                className="text-xl font-semibold text-gray-800 mt-4 mb-2"
                            >
                                1.2 Usage Information
                            </h3>
                            <p>
                                We automatically collect certain information about your device and how you interact with our Platform, including:
                            </p>
                            <ul 
                                className="list-disc pl-6 mb-4"
                                role="list"
                            >
                                <li>IP address</li>
                                <li>Device type and operating system</li>
                                <li>Browser type</li>
                                <li>Pages viewed and features used</li>
                                <li>Time spent on the Platform</li>
                                <li>Referring website or application</li>
                                <li>Geographic location (with your permission)</li>
                            </ul>
                        </section>
                        
                        <section aria-labelledby="cookies-information">
                            <h3 
                                id="cookies-information"
                                className="text-xl font-semibold text-gray-800 mt-4 mb-2"
                            >
                                1.3 Cookies and Similar Technologies
                            </h3>
                            <p>
                                We use cookies, web beacons, and similar technologies to collect information about your browsing activities. 
                                For more information about our use of cookies, please see our{' '}
                                <button
                                    onClick={() => navigate('/cookies')}
                                    className="text-primary-600 hover:text-primary-700 underline focus:outline-none focus:ring-2 focus:ring-primary-500"
                                >
                                    Cookie Policy
                                </button>.
                            </p>
                        </section>
                    </section>
                    
                    <section aria-labelledby="information-usage">
                        <h2 
                            id="information-usage"
                            className="text-2xl font-semibold text-gray-900 mt-8 mb-4"
                        >
                            2. How We Use Your Information
                        </h2>
                        <p>
                            We may use the information we collect for various purposes, including to:
                        </p>
                        <ul 
                            className="list-disc pl-6 mb-4"
                            role="list"
                        >
                            <li>Provide, maintain, and improve the Platform</li>
                            <li>Process and manage your account registration</li>
                            <li>Facilitate food sharing and trading between users</li>
                            <li>Communicate with you about your account, updates, or promotional offers</li>
                            <li>Respond to your inquiries and provide customer support</li>
                            <li>Monitor and analyze usage patterns and trends</li>
                            <li>Protect the security and integrity of the Platform</li>
                            <li>Comply with legal obligations</li>
                            <li>Enforce our Terms of Service and other policies</li>
                        </ul>
                    </section>
                    
                    <section aria-labelledby="information-sharing">
                        <h2 
                            id="information-sharing"
                            className="text-2xl font-semibold text-gray-900 mt-8 mb-4"
                        >
                            3. How We Share Your Information
                        </h2>
                        <p>
                            We may share your information in the following circumstances:
                        </p>
                        
                        <section aria-labelledby="sharing-users">
                            <h3 
                                id="sharing-users"
                                className="text-xl font-semibold text-gray-800 mt-4 mb-2"
                            >
                                3.1 With Other Users
                            </h3>
                            <p>
                                When you create a food listing or interact with another user, certain information from your profile 
                                (such as your name, profile picture, and general location) will be visible to other users. 
                                Direct messaging features may also share your communications with the intended recipient.
                            </p>
                        </section>
                        
                        <section aria-labelledby="sharing-providers">
                            <h3 
                                id="sharing-providers"
                                className="text-xl font-semibold text-gray-800 mt-4 mb-2"
                            >
                                3.2 With Service Providers
                            </h3>
                            <p>
                                We may share your information with third-party service providers who perform services on our behalf, 
                                such as hosting, data analysis, payment processing, customer service, and marketing assistance.
                            </p>
                        </section>
                        
                        <section aria-labelledby="sharing-legal">
                            <h3 
                                id="sharing-legal"
                                className="text-xl font-semibold text-gray-800 mt-4 mb-2"
                            >
                                3.3 For Legal Reasons
                            </h3>
                            <p>
                                We may disclose your information if required to do so by law or in response to valid requests by public authorities 
                                (e.g., a court or government agency). We may also disclose your information to protect the rights, property, 
                                or safety of ShareFoods, our users, or others.
                            </p>
                        </section>
                        
                        <section aria-labelledby="sharing-business">
                            <h3 
                                id="sharing-business"
                                className="text-xl font-semibold text-gray-800 mt-4 mb-2"
                            >
                                3.4 Business Transfers
                            </h3>
                            <p>
                                If ShareFoods is involved in a merger, acquisition, or sale of all or a portion of its assets, your information 
                                may be transferred as part of that transaction. We will notify you via email and/or a prominent notice on our 
                                Platform of any change in ownership or uses of your information.
                            </p>
                        </section>
                    </section>
                    
                    <section aria-labelledby="data-security">
                        <h2 
                            id="data-security"
                            className="text-2xl font-semibold text-gray-900 mt-8 mb-4"
                        >
                            4. Data Security
                        </h2>
                        <p>
                            We implement appropriate technical and organizational measures to protect the security of your personal information. 
                            However, please be aware that no method of transmission over the Internet or method of electronic storage is 100% secure. 
                            While we strive to use commercially acceptable means to protect your personal information, we cannot guarantee its absolute security.
                        </p>
                    </section>
                    
                    <section aria-labelledby="privacy-rights">
                        <h2 
                            id="privacy-rights"
                            className="text-2xl font-semibold text-gray-900 mt-8 mb-4"
                        >
                            5. Your Privacy Rights
                        </h2>
                        <p>
                            Depending on your location, you may have certain rights regarding your personal information, such as:
                        </p>
                        <ul 
                            className="list-disc pl-6 mb-4"
                            role="list"
                        >
                            <li>Access to your personal information</li>
                            <li>Correction of inaccurate or incomplete information</li>
                            <li>Deletion of your personal information</li>
                            <li>Restriction or objection to the processing of your information</li>
                            <li>Data portability</li>
                            <li>Withdrawal of consent</li>
                        </ul>
                        <p>
                            To exercise these rights, please contact us using the information provided in the "Contact Us" section below.
                        </p>
                    </section>
                    
                    <section aria-labelledby="childrens-privacy">
                        <h2 
                            id="childrens-privacy"
                            className="text-2xl font-semibold text-gray-900 mt-8 mb-4"
                        >
                            6. Children's Privacy
                        </h2>
                        <p>
                            The Platform is not intended for children under the age of 16. We do not knowingly collect personal information 
                            from children under 16. If you are a parent or guardian and believe that your child has provided us with personal 
                            information, please contact us so that we can delete the information.
                        </p>
                    </section>
                    
                    <section aria-labelledby="policy-changes">
                        <h2 
                            id="policy-changes"
                            className="text-2xl font-semibold text-gray-900 mt-8 mb-4"
                        >
                            7. Changes to This Privacy Policy
                        </h2>
                        <p>
                            We may update this Privacy Policy from time to time. The updated version will be indicated by an updated 
                            "Last Updated" date and will be effective as soon as it is accessible. We encourage you to review this 
                            Privacy Policy periodically to stay informed about how we are protecting your information.
                        </p>
                    </section>
                    
                    <section 
                        aria-labelledby="contact-us"
                        className="mt-8"
                    >
                        <h2 
                            id="contact-us"
                            className="text-2xl font-semibold text-gray-900 mb-4"
                        >
                            8. Contact Us
                        </h2>
                        <p>
                            If you have questions or concerns about this Privacy Policy or our data practices, please contact us at:
                        </p>
                        <address className="not-italic">
                            <p>
                                Email:{' '}
                                <a 
                                    href={`mailto:privacy@sharefoods.com`}
                                    className="text-primary-600 hover:text-primary-700"
                                    aria-label="Send email to privacy team"
                                >
                                    privacy@sharefoods.com
                                </a>
                                <br />
                                Address: 123 Main Street, City, State, ZIP<br />
                                Phone:{' '}
                                <a 
                                    href={`tel:1234567890`}
                                    className="text-primary-600 hover:text-primary-700"
                                    aria-label="Call privacy team"
                                >
                                    (123) 456-7890
                                </a>
                            </p>
                        </address>
                    </section>
                </article>
            </main>
            </div>
    );
}

export default PrivacyPolicy;
