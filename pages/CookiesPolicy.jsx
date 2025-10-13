import ErrorBoundary from "../components/common/ErrorBoundary";

function CookiesPolicy() {
    try {
        return (
            <ErrorBoundary>
                <div 
                    data-name="cookies-policy" 
                    className="max-w-4xl mx-auto py-12 px-4"
                    role="main"
                    aria-labelledby="cookies-policy-title"
                >
                    <h1 
                        id="cookies-policy-title"
                        className="text-3xl font-bold text-gray-900 mb-8"
                    >
                        Cookie Policy
                    </h1>
                    
                    <div className="prose prose-green max-w-none">
                        <p className="text-gray-600 mb-6" aria-label="Last update date">
                            Last Updated: January 15, 2024
                        </p>
                        
                        <p className="mb-6">
                            This Cookie Policy explains how ShareFoods (&quot;we&quot;, &quot;our&quot;, or &quot;us&quot;) uses cookies and similar technologies 
                            to recognize you when you visit our website, mobile application, and services (collectively, the &quot;Platform&quot;). 
                            It explains what these technologies are and why we use them, as well as your rights to control our use of them.
                        </p>
                        
                        <h2 className="text-2xl font-semibold text-gray-900 mt-8 mb-4">1. What Are Cookies?</h2>
                        <p>
                            Cookies are small data files that are placed on your computer or mobile device when you visit a website. 
                            Cookies are widely used by website owners to make their websites work, or to work more efficiently, 
                            as well as to provide reporting information.
                        </p>
                        <p>
                            Cookies set by the website owner (in this case, ShareFoods) are called &quot;first-party cookies&quot;. 
                            Cookies set by parties other than the website owner are called &quot;third-party cookies&quot;. 
                            Third-party cookies enable third-party features or functionality to be provided on or through the website 
                            (e.g., advertising, interactive content, and analytics). The parties that set these third-party cookies 
                            can recognize your computer both when it visits the website in question and also when it visits certain other websites.
                        </p>
                        
                        <h2 className="text-2xl font-semibold text-gray-900 mt-8 mb-4">2. Why Do We Use Cookies?</h2>
                        <p>
                            We use first-party and third-party cookies for several reasons. Some cookies are required for technical reasons 
                            for our Platform to operate, and we refer to these as &quot;essential&quot; or &quot;strictly necessary&quot; cookies. 
                            Other cookies enable us to track and target the interests of our users to enhance the experience on our Platform. 
                            Third parties serve cookies through our Platform for advertising, analytics, and other purposes.
                        </p>
                        
                        <h2 className="text-2xl font-semibold text-gray-900 mt-8 mb-4">3. Types of Cookies We Use</h2>
                        <p>
                            The specific types of first and third-party cookies served through our Platform and the purposes they perform include:
                        </p>
                        
                        <h3 className="text-xl font-semibold text-gray-800 mt-4 mb-2">3.1 Strictly Necessary Cookies</h3>
                        <p>
                            These cookies are essential to provide you with services available through our Platform and to enable you to use some of its features. 
                            Without these cookies, the services that you have asked for cannot be provided, and we only use these cookies to provide you with those services.
                        </p>
                        
                        <h3 className="text-xl font-semibold text-gray-800 mt-4 mb-2">3.2 Functionality Cookies</h3>
                        <p>
                            These cookies allow our Platform to remember choices you make when you use our Platform, such as remembering your login details or language preferences. 
                            The purpose of these cookies is to provide you with a more personal experience and to avoid you having to re-enter your preferences every time you visit our Platform.
                        </p>
                        
                        <h3 className="text-xl font-semibold text-gray-800 mt-4 mb-2">3.3 Analytics and Performance Cookies</h3>
                        <p>
                            These cookies are used to collect information about traffic to our Platform and how users use our Platform. 
                            The information gathered does not identify any individual visitor. The information is aggregated and anonymous. 
                            It includes the number of visitors to our Platform, the websites that referred them to our Platform, 
                            the pages they visited on our Platform, what time of day they visited our Platform, whether they have visited our Platform before, 
                            and other similar information.
                        </p>
                        <p>
                            We use this information to help operate our Platform more efficiently, to gather broad demographic information, 
                            and to monitor the level of activity on our Platform. We use Google Analytics for this purpose. 
                            Google Analytics uses its own cookies. It is only used to improve how our Platform works.
                        </p>
                        
                        <h3 className="text-xl font-semibold text-gray-800 mt-4 mb-2">3.4 Social Media Cookies</h3>
                        <p>
                            These cookies are used when you share information using a social media sharing button or &quot;like&quot; button on our Platform, 
                            or when you link your account or engage with our content on or through a social networking website such as Facebook, Twitter, or Instagram. 
                            The social network will record that you have done this.
                        </p>
                        
                        <h2 className="text-2xl font-semibold text-gray-900 mt-8 mb-4">4. How Can You Control Cookies?</h2>
                        <p>
                            You have the right to decide whether to accept or reject cookies. You can exercise your cookie preferences by clicking on the appropriate opt-out links provided in the cookie banner that appears when you first visit our Platform.
                        </p>
                        <p>
                            You can also set or amend your web browser controls to accept or refuse cookies. If you choose to reject cookies, you may still use our Platform though your access to some functionality and areas of our Platform may be restricted. As the means by which you can refuse cookies through your web browser controls vary from browser to browser, you should visit your browser&apos;s help menu for more information.
                        </p>
                        <p>
                            In addition, most advertising networks offer you a way to opt out of targeted advertising. If you would like to find out more information, please visit {' '}
                            <a 
                                href="http://www.aboutads.info/choices/" 
                                className="text-green-600 hover:text-green-700" 
                                target="_blank" 
                                rel="noopener noreferrer"
                                aria-label="Visit About Ads Choices website (opens in new tab)"
                            >
                                http://www.aboutads.info/choices/
                            </a> or {' '}
                            <a 
                                href="http://www.youronlinechoices.com" 
                                className="text-green-600 hover:text-green-700" 
                                target="_blank" 
                                rel="noopener noreferrer"
                                aria-label="Visit Your Online Choices website (opens in new tab)"
                            >
                                http://www.youronlinechoices.com
                            </a>.
                        </p>
                        
                        <h2 className="text-2xl font-semibold text-gray-900 mt-8 mb-4">5. How Often Will We Update This Cookie Policy?</h2>
                        <p>
                            We may update this Cookie Policy from time to time in order to reflect, for example, changes to the cookies we use or for other operational, legal, or regulatory reasons. Please therefore revisit this Cookie Policy regularly to stay informed about our use of cookies and related technologies.
                        </p>
                        <p>
                            The date at the top of this Cookie Policy indicates when it was last updated.
                        </p>
                        
                        <h2 className="text-2xl font-semibold text-gray-900 mt-8 mb-4">6. Contact Us</h2>
                        <p>
                            If you have any questions about our use of cookies or other technologies, please contact us at:
                        </p>
                        <address className="not-italic">
                            Email: <a href="mailto:privacy@sharefoods.com" className="text-green-600 hover:text-green-700">privacy@sharefoods.com</a><br />
                            Address: 123 Main Street, City, State, ZIP<br />
                            Phone: <a href="tel:+11234567890" className="text-green-600 hover:text-green-700">(123) 456-7890</a>
                        </address>
                    </div>
                </div>
            </ErrorBoundary>
        );
        
    } catch (error) {
        console.error('CookiesPolicy page error:', error);
        return (
            <div className="text-center py-8">
                <i className="fas fa-exclamation-circle text-red-500 text-4xl mb-4"></i>
                <h2 className="text-xl font-bold mb-2">Something went wrong</h2>
                <p className="text-gray-600">We&apos;re sorry, but there was an error loading this page.</p>
                <button
                    onClick={() => window.location.reload()}
                    className="mt-4 px-4 py-2 bg-green-600 text-white rounded hover:bg-green-700"
                >
                    Reload Page
                </button>
            </div>
        );
    }
}

export default CookiesPolicy;
