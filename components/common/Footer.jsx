import React from 'react';
import PropTypes from 'prop-types';
import { reportError } from '../../utils/helpers';

function Footer({ 
    className = '',
    mainLinks = [
        { label: 'How It Works', path: '/how-it-works' },
        { label: 'Share Food', path: '/share' },
        { label: 'Find Food', path: '/find' },

    ],
    communityLinks = [
        { label: '', path: '/blog' },
        { label: '', path: '/success' },

        { label: 'Community Hub', path: '/community' }
    ],
    legalLinks = [
        { label: 'Terms of Service', path: '/terms' },
        { label: 'Privacy Policy', path: '/privacy' },
        { label: 'Cookie Policy', path: '/cookies' }
    ],
    socialLinks = [
        { label: 'Facebook', icon: 'facebook-f', url: 'https://facebook.com/dogoods' },
        { label: 'Twitter', icon: 'twitter', url: 'https://twitter.com/dogoods' },
        { label: 'Instagram', icon: 'instagram', url: 'https://instagram.com/dogoods' },
        { label: 'LinkedIn', icon: 'linkedin-in', url: 'https://linkedin.com/company/dogoods' }
    ]
}) {
    return (
        <footer 
            data-name="footer" 
            className={`bg-gray-900 text-white ${className}`}
            role="contentinfo"
            aria-label="Site footer"
        >
            <div className="container mx-auto px-4 py-12">
                <div className="grid grid-cols-1 md:grid-cols-4 gap-8">
                    {/* About Section */}
                    <div data-name="footer-about">
                        <a 
                            href="/" 
                            className="flex items-center mb-4"
                            aria-label="Go to homepage"
                        >
                            <div className="h-10 w-10 bg-green-600 rounded-full flex items-center justify-center text-white" aria-hidden="true">
                                <i className="fas fa-seedling text-xl"></i>
                            </div>
                            <span className="ml-2 text-xl font-semibold">DoGoods</span>
                        </a>
                        <p className="text-gray-400">
                            Reducing food waste and fighting hunger through community-driven food sharing.
                        </p>
                    </div>

                    {/* Quick Links Section */}
                    <nav data-name="footer-links" aria-label="Quick links">
                        <h3 className="text-lg font-semibold mb-4" id="quick-links-title">Quick Links</h3>
                        <ul 
                            className="space-y-2"
                            aria-labelledby="quick-links-title"
                            role="menu"
                        >
                            {mainLinks.map((link, index) => (
                                <li key={`main-${index}`} role="none">
                                    <a 
                                        href={link.path}
                                        className="text-gray-400 hover:text-white transition-colors duration-200 focus:outline-none focus:ring-2 focus:ring-green-500 focus:ring-offset-2 focus:ring-offset-gray-900 rounded"
                                        role="menuitem"
                                    >
                                        {link.label}
                                    </a>
                                </li>
                            ))}
                        </ul>
                    </nav>

                    {/* Community Section */}
                    <nav data-name="footer-community" aria-label="Community links">
                        <h3 className="text-lg font-semibold mb-4" id="community-links-title">Community</h3>
                        <ul 
                            className="space-y-2"
                            aria-labelledby="community-links-title"
                            role="menu"
                        >
                            {communityLinks.map((link, index) => (
                                <li key={`community-${index}`} role="none">
                                    <a 
                                        href={link.path}
                                        className="text-gray-400 hover:text-white transition-colors duration-200 focus:outline-none focus:ring-2 focus:ring-green-500 focus:ring-offset-2 focus:ring-offset-gray-900 rounded"
                                        role="menuitem"
                                    >
                                        {link.label}
                                    </a>
                                </li>
                            ))}
                        </ul>
                    </nav>

                    {/* Legal & Social Section */}
                    <div data-name="footer-legal-social">
                        {/* Legal Links */}
                        <nav aria-label="Legal links">
                            <h3 className="text-lg font-semibold mb-4" id="legal-links-title">Legal</h3>
                            <ul 
                                className="space-y-2 mb-6"
                                aria-labelledby="legal-links-title"
                                role="menu"
                            >
                                {legalLinks.map((link, index) => (
                                    <li key={`legal-${index}`} role="none">
                                        <a 
                                            href={link.path}
                                            className="text-gray-400 hover:text-white transition-colors duration-200 focus:outline-none focus:ring-2 focus:ring-green-500 focus:ring-offset-2 focus:ring-offset-gray-900 rounded"
                                            role="menuitem"
                                        >
                                            {link.label}
                                        </a>
                                    </li>
                                ))}
                            </ul>
                        </nav>

                        {/* Social Links */}
                        <nav aria-label="Social media links">
                            <h3 className="text-lg font-semibold mb-4" id="social-links-title">Follow Us</h3>
                            <ul 
                                className="flex space-x-4"
                                aria-labelledby="social-links-title"
                                role="menu"
                            >
                                {socialLinks.map((link, index) => (
                                    <li key={`social-${index}`} role="none">
                                        <a 
                                            href={link.url}
                                            target="_blank"
                                            rel="noopener noreferrer"
                                            className="text-gray-400 hover:text-white transition-colors duration-200 focus:outline-none focus:ring-2 focus:ring-green-500 focus:ring-offset-2 focus:ring-offset-gray-900 rounded p-2"
                                            role="menuitem"
                                            aria-label={`Follow us on ${link.label}`}
                                        >
                                            <i className={`fab fa-${link.icon} text-lg`} aria-hidden="true"></i>
                                        </a>
                                    </li>
                                ))}
                            </ul>
                        </nav>
                    </div>
                </div>

                {/* Bottom Section */}
                <div className="border-t border-gray-800 mt-8 pt-8">
                    <div className="flex flex-col md:flex-row justify-between items-center">
                        <p className="text-gray-400 text-sm">
                            © {new Date().getFullYear()} DoGoods. All rights reserved.
                        </p>
                        <div className="mt-4 md:mt-0">
                            <p className="text-gray-400 text-sm">
                                Made with <i className="fas fa-heart text-red-500" aria-hidden="true"></i> for the community
                            </p>
                        </div>
                    </div>
                </div>
            </div>
        </footer>
    );
}

Footer.propTypes = {
    className: PropTypes.string,
    mainLinks: PropTypes.arrayOf(
        PropTypes.shape({
            label: PropTypes.string.isRequired,
            path: PropTypes.string.isRequired
        })
    ),
    communityLinks: PropTypes.arrayOf(
        PropTypes.shape({
            label: PropTypes.string.isRequired,
            path: PropTypes.string.isRequired
        })
    ),
    legalLinks: PropTypes.arrayOf(
        PropTypes.shape({
            label: PropTypes.string.isRequired,
            path: PropTypes.string.isRequired
        })
    ),
    socialLinks: PropTypes.arrayOf(
        PropTypes.shape({
            label: PropTypes.string.isRequired,
            icon: PropTypes.string.isRequired,
            url: PropTypes.string.isRequired
        })
    )
};

export default Footer;
