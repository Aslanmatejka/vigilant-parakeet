import React, { useState } from 'react';
import { Link } from 'react-router-dom';
import { toast } from 'react-toastify';
import supabase from '../utils/supabaseClient';

function ContactPage() {
    const [formData, setFormData] = useState({
        name: '',
        email: '',
        reason: '',
        message: ''
    });
    const [isSubmitting, setIsSubmitting] = useState(false);

    const handleChange = (e) => {
        setFormData({
            ...formData,
            [e.target.name]: e.target.value
        });
    };

    const handleSubmit = async (e) => {
        e.preventDefault();
        
        if (!formData.name || !formData.email || !formData.reason || !formData.message) {
            toast.error('Please fill in all fields');
            return;
        }

        setIsSubmitting(true);

        try {
            // Store contact form submission in database
            const { error } = await supabase
                .from('user_feedback')
                .insert({
                    feedback_type: formData.reason,
                    subject: `Contact from ${formData.name}`,
                    user_email: formData.email,
                    message: formData.message,
                    status: 'new',
                    priority: 'medium'
                });

            if (error) throw error;

            toast.success('Message sent successfully! We\'ll get back to you soon.');
            setFormData({ name: '', email: '', reason: '', message: '' });
        } catch (error) {
            console.error('Error submitting contact form:', error);
            toast.error('Failed to send message. Please try again or email us directly.');
        } finally {
            setIsSubmitting(false);
        }
    };

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
                            <i className="fas fa-envelope mr-2" aria-hidden="true"></i>
                            Get in Touch
                        </span>
                        <h1 className="text-4xl sm:text-5xl lg:text-6xl font-bold text-gray-900 mb-5 tracking-tight">
                            We&apos;d love to{" "}
                            <span className="bg-gradient-to-r from-[#2CABE3] to-emerald-500 bg-clip-text text-transparent">
                                hear from you
                            </span>
                        </h1>
                        <p className="text-base sm:text-lg text-gray-600 max-w-2xl mx-auto leading-relaxed">
                            Have a question or want to get involved? Reach out to the All Good Living Foundation.
                        </p>
                    </div>
                </div>
            </header>

            <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 pb-20">
            <div className="grid md:grid-cols-2 gap-8">
                {/* Contact Information */}
                <div className="space-y-6">
                    {/* Organization Info Card */}
                    <div className="bg-gradient-to-br from-cyan-50 to-cyan-100 rounded-2xl shadow-lg p-8 border border-cyan-200">
                        <h2 className="text-2xl font-bold text-gray-900 mb-6">
                            <i className="fas fa-building text-cyan-600 mr-2"></i>
                            All Good Living Foundation
                        </h2>

                        <div className="space-y-4">
                            {/* Phone */}
                            <div className="flex items-start gap-4">
                                <div className="flex-shrink-0 w-12 h-12 bg-cyan-600 rounded-full flex items-center justify-center">
                                    <i className="fas fa-phone text-white"></i>
                                </div>
                                <div>
                                    <h3 className="font-semibold text-gray-900 mb-1">Phone</h3>
                                    <a href="tel:510-522-6288" className="text-cyan-600 hover:text-cyan-700 font-medium">
                                        510-522-6288
                                    </a>
                                </div>
                            </div>

                            {/* Email */}
                            <div className="flex items-start gap-4">
                                <div className="flex-shrink-0 w-12 h-12 bg-cyan-600 rounded-full flex items-center justify-center">
                                    <i className="fas fa-envelope text-white"></i>
                                </div>
                                <div>
                                    <h3 className="font-semibold text-gray-900 mb-1">Email</h3>
                                    <a href="mailto:info@allgoodlivingfoundation.org" className="text-cyan-600 hover:text-cyan-700 font-medium break-all">
                                        info@allgoodlivingfoundation.org
                                    </a>
                                </div>
                            </div>

                            {/* Address */}
                            <div className="flex items-start gap-4">
                                <div className="flex-shrink-0 w-12 h-12 bg-cyan-600 rounded-full flex items-center justify-center">
                                    <i className="fas fa-map-marker-alt text-white"></i>
                                </div>
                                <div>
                                    <h3 className="font-semibold text-gray-900 mb-1">Address</h3>
                                    <a 
                                        href="https://www.google.com/maps/search/?api=1&query=1900+Thau+Way,+Alameda,+CA+94501"
                                        target="_blank"
                                        rel="noopener noreferrer"
                                        className="text-gray-700 hover:text-cyan-600"
                                    >
                                        1900 Thau Way<br />
                                        Alameda, CA 94501
                                    </a>
                                </div>
                            </div>

                            {/* Hours */}
                            <div className="flex items-start gap-4">
                                <div className="flex-shrink-0 w-12 h-12 bg-cyan-600 rounded-full flex items-center justify-center">
                                    <i className="fas fa-clock text-white"></i>
                                </div>
                                <div>
                                    <h3 className="font-semibold text-gray-900 mb-1">Hours</h3>
                                    <p className="text-gray-700">Monday - Friday</p>
                                    <p className="text-gray-700">9:00 AM - 3:00 PM</p>
                                </div>
                            </div>
                        </div>
                    </div>

                    {/* Action Buttons */}
                    <div className="grid grid-cols-2 gap-4">
                        <Link
                            to="/donate"
                            className="bg-cyan-600 hover:bg-cyan-700 text-white font-bold py-4 px-6 rounded-xl shadow-lg transition-all duration-300 transform hover:scale-105 text-center"
                        >
                            <i className="fas fa-heart mr-2"></i>
                            Donate
                        </Link>
                        <a
                            href="https://allgoodlivingfoundation.org/volunteer-form"
                            target="_blank"
                            rel="noopener noreferrer"
                            className="bg-blue-600 hover:bg-blue-700 text-white font-bold py-4 px-6 rounded-xl shadow-lg transition-all duration-300 transform hover:scale-105 text-center"
                        >
                            <i className="fas fa-hands-helping mr-2"></i>
                            Volunteer
                        </a>
                    </div>

                    {/* Map or additional info */}
                    <div className="bg-white rounded-2xl shadow-lg p-6 border border-gray-200">
                        <h3 className="font-bold text-gray-900 mb-3">
                            <i className="fas fa-info-circle text-cyan-600 mr-2"></i>
                            Get Involved
                        </h3>
                        <p className="text-gray-600 mb-3">
                            We&apos;re always looking for passionate individuals to help us reduce food waste and feed our community.
                        </p>
                        <ul className="space-y-2 text-gray-700">
                            <li className="flex items-center gap-2">
                                <i className="fas fa-check-circle text-cyan-600"></i>
                                <span>Volunteer with us</span>
                            </li>
                            <li className="flex items-center gap-2">
                                <i className="fas fa-check-circle text-cyan-600"></i>
                                <span>Make a donation</span>
                            </li>
                            <li className="flex items-center gap-2">
                                <i className="fas fa-check-circle text-cyan-600"></i>
                                <span>Become a sponsor</span>
                            </li>
                        </ul>
                    </div>
                </div>

                {/* Contact Form */}
                <div className="bg-white rounded-2xl shadow-lg p-8 border border-gray-200">
                    <h2 className="text-2xl font-bold text-gray-900 mb-6">
                        <i className="fas fa-paper-plane text-cyan-600 mr-2"></i>
                        Send Us a Message
                    </h2>

                    <form onSubmit={handleSubmit} className="space-y-6">
                        {/* Name */}
                        <div>
                            <label htmlFor="name" className="block text-sm font-semibold text-gray-700 mb-2">
                                Name <span className="text-red-500">*</span>
                            </label>
                            <input
                                type="text"
                                id="name"
                                name="name"
                                value={formData.name}
                                onChange={handleChange}
                                required
                                className="w-full px-4 py-3 border border-gray-300 rounded-lg focus:ring-2 focus:ring-cyan-500 focus:border-transparent"
                                placeholder="Your full name"
                            />
                        </div>

                        {/* Email */}
                        <div>
                            <label htmlFor="email" className="block text-sm font-semibold text-gray-700 mb-2">
                                Email Address <span className="text-red-500">*</span>
                            </label>
                            <input
                                type="email"
                                id="email"
                                name="email"
                                value={formData.email}
                                onChange={handleChange}
                                required
                                className="w-full px-4 py-3 border border-gray-300 rounded-lg focus:ring-2 focus:ring-cyan-500 focus:border-transparent"
                                placeholder="your.email@example.com"
                            />
                        </div>

                        {/* Reason */}
                        <div>
                            <label htmlFor="reason" className="block text-sm font-semibold text-gray-700 mb-2">
                                Reason for Contacting <span className="text-red-500">*</span>
                            </label>
                            <select
                                id="reason"
                                name="reason"
                                value={formData.reason}
                                onChange={handleChange}
                                required
                                className="w-full px-4 py-3 border border-gray-300 rounded-lg focus:ring-2 focus:ring-cyan-500 focus:border-transparent bg-white"
                            >
                                <option value="">Select a reason...</option>
                                <option value="technical_issue">Technical Issue</option>
                                <option value="suggestion">Suggestion</option>
                                <option value="question_feedback">Question / Other Feedback</option>
                            </select>
                        </div>

                        {/* Message */}
                        <div>
                            <label htmlFor="message" className="block text-sm font-semibold text-gray-700 mb-2">
                                Message <span className="text-red-500">*</span>
                            </label>
                            <textarea
                                id="message"
                                name="message"
                                value={formData.message}
                                onChange={handleChange}
                                required
                                rows="6"
                                className="w-full px-4 py-3 border border-gray-300 rounded-lg focus:ring-2 focus:ring-cyan-500 focus:border-transparent resize-none"
                                placeholder="Tell us what's on your mind..."
                            />
                        </div>

                        {/* Submit Button */}
                        <button
                            type="submit"
                            disabled={isSubmitting}
                            className="w-full bg-cyan-600 hover:bg-cyan-700 disabled:bg-gray-400 text-white font-bold py-4 px-6 rounded-lg shadow-lg transition-all duration-300 transform hover:scale-105 disabled:transform-none disabled:cursor-not-allowed"
                        >
                            {isSubmitting ? (
                                <>
                                    <i className="fas fa-spinner fa-spin mr-2"></i>
                                    Sending...
                                </>
                            ) : (
                                <>
                                    <i className="fas fa-paper-plane mr-2"></i>
                                    Send Message
                                </>
                            )}
                        </button>
                    </form>

                    <p className="text-sm text-gray-500 mt-4 text-center">
                        We typically respond within 1-2 business days
                    </p>
                </div>
            </div>
            </div>
        </div>
    );
}

export default ContactPage;
