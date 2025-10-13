import { Link } from "react-router-dom";
import ErrorBoundary from "../components/common/ErrorBoundary";

function TermsOfServiceContent() {
    const lastUpdated = "January 15, 2024";
    const contactInfo = {
        email: "legal@sharefoods.com",
        address: "123 Main Street, City, State, ZIP",
        phone: "(123) 456-7890"
    };

    return (
        <div data-name="terms-of-service" className="max-w-4xl mx-auto py-12 px-4">
            <nav aria-label="Breadcrumb" className="mb-4">
                <ol className="flex text-sm">
                    <li>
                        <Link to="/" className="text-green-600 hover:text-green-700">Home</Link>
                        <span className="mx-2 text-gray-500">/</span>
                    </li>
                    <li className="text-gray-500" aria-current="page">Terms of Service</li>
                </ol>
            </nav>

            <main>
                <h1 className="text-3xl font-bold text-gray-900 mb-8">Terms of Service</h1>
                
                <div className="prose prose-green max-w-none">
                    <p className="text-gray-600 mb-6">
                        Last Updated: {lastUpdated}
                    </p>
                    
                    <section aria-labelledby="introduction">
                        <h2 id="introduction" className="text-2xl font-semibold text-gray-900 mt-8 mb-4">1. Introduction</h2>
                        <p>
                            Welcome to ShareFoods. These Terms of Service ("Terms") govern your use of the ShareFoods platform, 
                            including our website, mobile applications, and services (collectively, the "Platform"). 
                            By accessing or using the Platform, you agree to be bound by these Terms. 
                            If you do not agree to these Terms, please do not use the Platform.
                        </p>
                    </section>
                    
                    <section aria-labelledby="definitions">
                        <h2 id="definitions" className="text-2xl font-semibold text-gray-900 mt-8 mb-4">2. Definitions</h2>
                        <dl>
                            <dt><strong>"ShareFoods"</strong></dt>
                            <dd className="mb-2">refers to the company operating this platform.</dd>
                            
                            <dt><strong>"User"</strong></dt>
                            <dd className="mb-2">refers to any individual who accesses or uses the Platform.</dd>
                            
                            <dt><strong>"Donor"</strong></dt>
                            <dd className="mb-2">refers to a User who offers food items for donation or trade.</dd>
                            
                            <dt><strong>"Recipient"</strong></dt>
                            <dd className="mb-2">refers to a User who receives food items through the Platform.</dd>
                        </dl>
                    </section>
                    
                    <section aria-labelledby="registration">
                        <h2 id="registration" className="text-2xl font-semibold text-gray-900 mt-8 mb-4">3. Account Registration</h2>
                        <p>
                            To use certain features of the Platform, you must register for an account. You agree to provide accurate, 
                            current, and complete information during the registration process and to update such information to keep it 
                            accurate, current, and complete. You are responsible for safeguarding your password and for all activities 
                            that occur under your account.
                        </p>
                    </section>
                    
                    <section aria-labelledby="guidelines">
                        <h2 id="guidelines" className="text-2xl font-semibold text-gray-900 mt-8 mb-4">4. Food Sharing Guidelines</h2>
                        
                        <section aria-labelledby="food-safety">
                            <h3 id="food-safety" className="text-xl font-semibold text-gray-800 mt-4 mb-2">4.1 Food Safety</h3>
                            <p>
                                Donors must ensure that all food items offered are safe for consumption, properly stored, 
                                and handled according to food safety guidelines. ShareFoods reserves the right to remove any 
                                listings that do not comply with food safety standards.
                            </p>
                        </section>
                        
                        <section aria-labelledby="prohibited-items">
                            <h3 id="prohibited-items" className="text-xl font-semibold text-gray-800 mt-4 mb-2">4.2 Prohibited Items</h3>
                            <p>
                                The following items are prohibited from being shared on the Platform:
                            </p>
                            <ul className="list-disc pl-6 mb-4" role="list">
                                <li>Home-canned foods</li>
                                <li>Raw or undercooked meat, poultry, fish, or eggs</li>
                                <li>Food that has been previously served</li>
                                <li>Food that requires temperature control that has been out of temperature control for more than 2 hours</li>
                                <li>Alcoholic beverages</li>
                                <li>Any food that violates local health regulations</li>
                            </ul>
                        </section>
                        
                        <section aria-labelledby="listing-accuracy">
                            <h3 id="listing-accuracy" className="text-xl font-semibold text-gray-800 mt-4 mb-2">4.3 Accuracy of Listings</h3>
                            <p>
                                Donors must provide accurate descriptions of food items, including:
                            </p>
                            <ul className="list-disc pl-6 mb-4" role="list">
                                <li>Description of the item</li>
                                <li>Quantity available</li>
                                <li>Expiration or best-by date</li>
                                <li>Any allergen information</li>
                                <li>Storage conditions</li>
                            </ul>
                        </section>
                    </section>
                    
                    <section aria-labelledby="user-conduct">
                        <h2 id="user-conduct" className="text-2xl font-semibold text-gray-900 mt-8 mb-4">5. User Conduct</h2>
                        <p>
                            Users agree to:
                        </p>
                        <ul className="list-disc pl-6 mb-4" role="list">
                            <li>Treat other Users with respect and courtesy</li>
                            <li>Communicate honestly and promptly</li>
                            <li>Honor commitments made through the Platform</li>
                            <li>Not engage in any form of harassment, discrimination, or abusive behavior</li>
                            <li>Not use the Platform for any illegal or unauthorized purpose</li>
                        </ul>
                    </section>
                    
                    <section aria-labelledby="liability">
                        <h2 id="liability" className="text-2xl font-semibold text-gray-900 mt-8 mb-4">6. Liability Disclaimer</h2>
                        <p>
                            ShareFoods is a platform that connects food donors with recipients. We do not inspect, verify, 
                            or guarantee the safety, quality, or legality of food items shared through our Platform. 
                            Users acknowledge and agree that:
                        </p>
                        <ul className="list-disc pl-6 mb-4" role="list">
                            <li>ShareFoods is not responsible for the safety or quality of food items shared through the Platform</li>
                            <li>Users assume all risk associated with donating or receiving food items</li>
                            <li>ShareFoods is not liable for any illness, injury, or damages resulting from food shared through the Platform</li>
                            <li>Users should use their own judgment regarding the safety and suitability of food items</li>
                        </ul>
                    </section>
                    
                    <section aria-labelledby="intellectual-property">
                        <h2 id="intellectual-property" className="text-2xl font-semibold text-gray-900 mt-8 mb-4">7. Intellectual Property</h2>
                        <p>
                            The Platform and its original content, features, and functionality are owned by ShareFoods and are protected 
                            by international copyright, trademark, patent, trade secret, and other intellectual property or proprietary 
                            rights laws.
                        </p>
                    </section>
                    
                    <section aria-labelledby="termination">
                        <h2 id="termination" className="text-2xl font-semibold text-gray-900 mt-8 mb-4">8. Termination</h2>
                        <p>
                            ShareFoods may terminate or suspend your account and access to the Platform immediately, 
                            without prior notice or liability, for any reason whatsoever, including without limitation 
                            if you breach the Terms. Upon termination, your right to use the Platform will immediately cease.
                        </p>
                    </section>
                    
                    <section aria-labelledby="changes">
                        <h2 id="changes" className="text-2xl font-semibold text-gray-900 mt-8 mb-4">9. Changes to Terms</h2>
                        <p>
                            ShareFoods reserves the right to modify or replace these Terms at any time. If a revision is material, 
                            we will try to provide at least 30 days' notice prior to any new terms taking effect. 
                            What constitutes a material change will be determined at our sole discretion.
                        </p>
                    </section>
                    
                    <section aria-labelledby="governing-law">
                        <h2 id="governing-law" className="text-2xl font-semibold text-gray-900 mt-8 mb-4">10. Governing Law</h2>
                        <p>
                            These Terms shall be governed and construed in accordance with the laws of [Your Jurisdiction], 
                            without regard to its conflict of law provisions.
                        </p>
                    </section>
                    
                    <section aria-labelledby="contact">
                        <h2 id="contact" className="text-2xl font-semibold text-gray-900 mt-8 mb-4">11. Contact Us</h2>
                        <p>
                            If you have any questions about these Terms, please contact us at:
                        </p>
                        <address className="not-italic">
                            Email: <a href={`mailto:${contactInfo.email}`} className="text-green-600 hover:text-green-700">{contactInfo.email}</a><br />
                            Address: {contactInfo.address}<br />
                            Phone: <a href={`tel:${contactInfo.phone.replace(/[^\d+]/g, '')}`} className="text-green-600 hover:text-green-700">{contactInfo.phone}</a>
                        </address>
                    </section>
                </div>
            </main>
        </div>
    );
}

function TermsOfService() {
    return (
        <ErrorBoundary>
            <TermsOfServiceContent />
        </ErrorBoundary>
    );
}

export default TermsOfService;
