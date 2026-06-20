import React from 'react';
import { Link } from 'react-router-dom';
import PropTypes from 'prop-types';
import { reportError } from '../../utils/helpers';

function Footer({
    className = ''
}) {
    return (
        <footer
            data-name="footer"
            className={`bg-[#D9E1F1] text-gray-900 ${className}`}
            role="contentinfo"
            aria-label="Site footer"
        >
            <div className="container mx-auto px-6 lg:px-12 py-16">
                <div className="grid grid-cols-1 md:grid-cols-3 gap-12 lg:gap-16">
                    {/* About Section - Left Column */}
                    <div data-name="footer-about" className="md:col-span-1">
                        <a
                            href="/"
                            className="inline-block mb-6"
                            aria-label="Go to homepage"
                        >
                            <img
                                src="/dogoodlogo.png"
                                alt="All Good Living Foundation Logo"
                                className="h-16 w-auto"
                            />
                        </a>
                        <p className="text-gray-700 text-sm leading-relaxed mb-8">
                            All Good Living Foundation is the community's safety net and spirit lifter, rolling up its sleeves to support students and families who are facing the most challenging moments of their lives. From school-based Community Closets to food access programs and youth-centered initiatives, the foundation brings practical help, dignity, and genuine connection to Alameda, Oakland, and other surrounding areas. It's simple: when our neighbors struggle, AGLF shows up — and keeps showing up — to make sure no one is left behind.
                        </p>

                        {/* Social Links */}
                        <div className="flex space-x-3">
                            <a
                                href="https://www.instagram.com/aglfoundation"
                                target="_blank"
                                rel="noopener noreferrer"
                                className="w-10 h-10 rounded-full bg-[#2CABE3] hover:opacity-90 flex items-center justify-center transition-all duration-200"
                                aria-label="Follow us on Instagram"
                            >
                                <i className="fab fa-instagram text-white text-lg" aria-hidden="true"></i>
                            </a>
                            <a
                                href="https://www.facebook.com/allgoodlivingfoundation"
                                target="_blank"
                                rel="noopener noreferrer"
                                className="w-10 h-10 rounded-full bg-[#2CABE3] hover:opacity-90 flex items-center justify-center transition-all duration-200"
                                aria-label="Follow us on Facebook"
                            >
                                <i className="fab fa-facebook-f text-white text-lg" aria-hidden="true"></i>
                            </a>
                        </div>
                    </div>

                    {/* Platform Section - Middle Column */}
                    <div data-name="footer-platform" className="md:col-span-1">
                        <h3 className="text-xl font-semibold mb-6 text-gray-900">Platform</h3>
                        <nav aria-label="Platform links">
                            <ul className="space-y-4">
                                <li>
                                    <a
                                        href="/find"
                                        className="text-gray-700 hover:text-gray-900 transition-colors duration-200 flex items-center group"
                                    >
                                        <i className="fas fa-search text-gray-600 group-hover:text-gray-900 mr-3" aria-hidden="true"></i>
                                        <span>Find Food</span>
                                    </a>
                                </li>
                                {/* TEMPORARILY DISABLED
                                <li>
                                    <a
                                        href="/share"
                                        className="text-gray-700 hover:text-gray-900 transition-colors duration-200 flex items-center group"
                                    >
                                        <i className="fas fa-heart text-gray-600 group-hover:text-gray-900 mr-3" aria-hidden="true"></i>
                                        <span>Share Food</span>
                                    </a>
                                </li>
                                */}
                                <li>
                                    <a
                                        href="https://allgoodlivingfoundation.org/volunteer-form"
                                        target="_blank"
                                        rel="noopener noreferrer"
                                        className="text-gray-700 hover:text-gray-900 transition-colors duration-200 flex items-center group"
                                    >
                                        <i className="fas fa-users text-gray-600 group-hover:text-gray-900 mr-3" aria-hidden="true"></i>
                                        <span>Volunteer</span>
                                    </a>
                                </li>
                                <li>
                                    <Link
                                        to="/donate"
                                        className="text-gray-700 hover:text-gray-900 transition-colors duration-200 flex items-center group"
                                    >
                                        <i className="fas fa-hand-holding-heart text-gray-600 group-hover:text-gray-900 mr-3" aria-hidden="true"></i>
                                        <span>Donate</span>
                                    </Link>
                                </li>
                                <li>
                                    <a
                                        href="/faqs"
                                        className="text-gray-700 hover:text-gray-900 transition-colors duration-200 flex items-center group"
                                    >
                                        <i className="fas fa-question-circle text-gray-600 group-hover:text-gray-900 mr-3" aria-hidden="true"></i>
                                        <span>FAQs</span>
                                    </a>
                                </li>
                                <li>
                                    <a
                                        href="/impact-story"
                                        className="text-gray-700 hover:text-gray-900 transition-colors duration-200 flex items-center group"
                                    >
                                        <i className="fas fa-seedling text-gray-600 group-hover:text-gray-900 mr-3" aria-hidden="true"></i>
                                        <span>Impact Story</span>
                                    </a>
                                </li>
                                <li>
                                    <a
                                        href="/recipes"
                                        className="text-gray-700 hover:text-gray-900 transition-colors duration-200 flex items-center group"
                                    >
                                        <i className="fas fa-utensils text-gray-600 group-hover:text-gray-900 mr-3" aria-hidden="true"></i>
                                        <span>Recipes</span>
                                    </a>
                                </li>
                                <li>
                                    <a
                                        href="/sponsors"
                                        className="text-gray-700 hover:text-gray-900 transition-colors duration-200 flex items-center group"
                                    >
                                        <i className="fas fa-handshake text-gray-600 group-hover:text-gray-900 mr-3" aria-hidden="true"></i>
                                        <span>Partners</span>
                                    </a>
                                </li>
                            </ul>
                        </nav>
                    </div>

                    {/* Contact Section - Right Column */}
                    <div data-name="footer-contact" className="md:col-span-1">
                        <h3 className="text-xl font-semibold mb-6 text-gray-900">Contact</h3>
                        <ul className="space-y-4">
                            <li>
                                <a
                                    href="mailto:info@allgoodlivingfoundation.org"
                                    className="text-gray-700 hover:text-gray-900 transition-colors duration-200 flex items-center group"
                                >
                                    <i className="fas fa-envelope text-gray-600 group-hover:text-gray-900 mr-3" aria-hidden="true"></i>
                                    <span className="break-all">info@allgoodlivingfoundation.org</span>
                                </a>
                            </li>
                            <li>
                                <a
                                    href="tel:510-522-6288"
                                    className="text-gray-700 hover:text-gray-900 transition-colors duration-200 flex items-center group"
                                >
                                    <i className="fas fa-phone text-gray-600 group-hover:text-gray-900 mr-3" aria-hidden="true"></i>
                                    <span>510-522-6288</span>
                                </a>
                            </li>
                            <li className="flex items-start group">
                                <i className="fas fa-map-marker-alt text-gray-600 group-hover:text-gray-900 mr-3 mt-1" aria-hidden="true"></i>
                                <a
                                    href="https://maps.google.com/?q=1900+Thau+Way,+Alameda,+CA+94501"
                                    target="_blank"
                                    rel="noopener noreferrer"
                                    className="text-gray-700 hover:text-gray-900 transition-colors duration-200"
                                >
                                    1900 Thau Way, Alameda, CA 94501
                                </a>
                            </li>
                        </ul>
                    </div>
                </div>

                {/* Bottom Section */}
                <div className="border-t border-gray-400 mt-12 pt-8">
                    <div className="flex flex-col md:flex-row justify-between items-center text-sm text-gray-600">
                        <p>© {new Date().getFullYear()} All Good Living Foundation. All rights reserved.</p>
                        <div className="flex gap-6 mt-4 md:mt-0">
                            <a href="/privacy" className="hover:text-gray-900 transition-colors">Privacy Policy</a>
                            <a href="/terms" className="hover:text-gray-900 transition-colors">Terms of Service</a>
                            <a href="/cookies" className="hover:text-gray-900 transition-colors">Cookie Policy</a>
                        </div>
                    </div>
                </div>
            </div>
        </footer>
    );
}

Footer.propTypes = {
    className: PropTypes.string
};

export default Footer;
