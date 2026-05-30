import React from 'react';
import { useAuthContext } from '../../utils/AuthContext';
import dataService from '../../utils/dataService';
import Avatar from '../common/Avatar';

function UserChatWidget() {
    const { user, isAuthenticated } = useAuthContext();
    const [isOpen, setIsOpen] = React.useState(false);
    const [conversation, setConversation] = React.useState(null);
    const [messages, setMessages] = React.useState([]);
    const [newMessage, setNewMessage] = React.useState('');
    const [loading, setLoading] = React.useState(false);
    const [sending, setSending] = React.useState(false);
    const messagesEndRef = React.useRef(null);

    const scrollToBottom = () => {
        messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
    };

    React.useEffect(() => {
        scrollToBottom();
    }, [messages]);

    React.useEffect(() => {
        if (isOpen && isAuthenticated && user?.id) {
            loadConversation();
        }
    }, [isOpen, isAuthenticated, user?.id]);

    React.useEffect(() => {
        if (conversation?.id) {
            loadMessages();

            // Unsubscribe from any previous subscription first
            dataService.unsubscribe(`messages_${conversation.id}`);

            // Subscribe to real-time updates
            const subscription = dataService.subscribeToMessages(conversation.id, (payload) => {
                if (payload.eventType === 'INSERT') {
                    setMessages(prev => {
                        // Check if we already have this message (optimistic update)
                        const exists = prev.some(m => m.id === payload.new.id);
                        if (exists) {
                            return prev; // Already have it
                        }

                        // Check if we have a temp message for this (replace it)
                        const hasTempMessage = prev.some(m => String(m.id).startsWith('temp-'));
                        if (hasTempMessage && !payload.new.is_from_admin) {
                            // Replace temp message with real one
                            return prev.map(m =>
                                String(m.id).startsWith('temp-') ? payload.new : m
                            );
                        }

                        // Add new message
                        return [...prev, payload.new];
                    });
                    scrollToBottom();
                }
            });

            return () => {
                dataService.unsubscribe(`messages_${conversation.id}`);
            };
        }
    }, [conversation?.id]);

    const loadConversation = async () => {
        try {
            setLoading(true);
            console.log('Loading conversation for user:', user.id);
            const conv = await dataService.getOrCreateConversation(user.id);
            console.log('Conversation loaded:', conv);
            setConversation(conv);
        } catch (error) {
            console.error('Failed to load conversation:', error);
            alert('Failed to load conversation. Please refresh the page and try again.');
        } finally {
            setLoading(false);
        }
    };

    const loadMessages = async () => {
        try {
            const msgs = await dataService.getConversationMessages(conversation.id);
            setMessages(msgs);
        } catch (error) {
            console.error('Failed to load messages:', error);
        }
    };

    const handleSendMessage = async (e) => {
        e.preventDefault();
        console.log('Send message clicked:', { newMessage, conversationId: conversation?.id, sending });

        if (!newMessage.trim() || !conversation?.id || sending) {
            console.log('Send blocked:', {
                hasMessage: !!newMessage.trim(),
                hasConversation: !!conversation?.id,
                isSending: sending
            });
            return;
        }

        const messageText = newMessage.trim();

        try {
            setSending(true);

            // Optimistic UI update - add message immediately
            const tempMessage = {
                id: 'temp-' + Date.now(),
                conversation_id: conversation.id,
                message: messageText,
                is_from_admin: false,
                created_at: new Date().toISOString(),
                read_at: null
            };
            setMessages(prev => [...prev, tempMessage]);
            setNewMessage('');

            console.log('Sending message to conversation:', conversation.id);
            await dataService.sendMessage(conversation.id, messageText, false);
            console.log('Message sent successfully');

            // Subscription will update with real message, no need to reload
        } catch (error) {
            console.error('Failed to send message:', error);
            console.error('Error details:', {
                message: error.message,
                code: error.code,
                details: error.details
            });

            // Remove optimistic message on error
            setMessages(prev => prev.filter(m => m.id !== tempMessage.id));
            setNewMessage(messageText); // Restore message text

            alert(`Failed to send message: ${error.message || 'Unknown error'}. Please try again.`);
        } finally {
            setSending(false);
        }
    };

    if (!isAuthenticated) {
        return null;
    }

    return (
        <>
            {/* Chat Button (icon-only) */}
            <button
                onClick={() => setIsOpen(!isOpen)}
                className="fixed bottom-6 right-24 z-40 w-10 h-10 text-gray-600 hover:text-blue-600 bg-white/80 hover:bg-white rounded-full shadow-md hover:shadow-lg transition-all duration-200 flex items-center justify-center"
                aria-label="Open chat with admin"
                title="Chat with admin"
            >
                {isOpen ? (
                    <i className="fas fa-times text-base"></i>
                ) : (
                    <span className="relative inline-flex">
                        <i className="fas fa-comments text-base"></i>
                        {/* Notification badge if there are unread admin messages */}
                        {messages.some(m => m.is_from_admin && !m.read_at) && (
                            <span className="absolute -top-1 -right-1 w-2.5 h-2.5 bg-red-500 rounded-full border border-white"></span>
                        )}
                    </span>
                )}
            </button>

            {/* Chat Window */}
            {isOpen && (
                <div className="fixed bottom-24 right-24 z-40 w-96 max-w-[calc(100vw-3rem)] bg-white rounded-lg shadow-2xl flex flex-col overflow-hidden border border-gray-200">
                    {/* Header */}
                    <div className="bg-blue-600 text-white px-4 py-3 flex items-center justify-between">
                        <div className="flex items-center space-x-2">
                            <div className="w-8 h-8 bg-blue-700 rounded-full flex items-center justify-center">
                                <i className="fas fa-headset text-sm"></i>
                            </div>
                            <div>
                                <h3 className="font-semibold text-sm">Chat with Admin</h3>
                                <p className="text-xs text-blue-100">We're here to help!</p>
                            </div>
                        </div>
                        <button
                            onClick={() => setIsOpen(false)}
                            className="text-white hover:text-primary-100 transition-colors"
                            aria-label="Close chat"
                        >
                            <i className="fas fa-times"></i>
                        </button>
                    </div>

                    {/* Messages Area */}
                    <div className="flex-1 overflow-y-auto p-4 space-y-3 bg-gray-50 max-h-96 min-h-[300px]">
                        {loading ? (
                            <div className="flex items-center justify-center h-full">
                                <div className="text-gray-500">
                                    <i className="fas fa-spinner fa-spin mr-2"></i>
                                    Loading conversation...
                                </div>
                            </div>
                        ) : messages.length === 0 ? (
                            <div className="flex flex-col items-center justify-center h-full text-center text-gray-500">
                                <i className="fas fa-comments text-4xl mb-3 text-gray-300"></i>
                                <p className="text-sm">No messages yet</p>
                                <p className="text-xs mt-1">Send a message to start the conversation</p>
                            </div>
                        ) : (
                            messages.map((msg, index) => (
                                <div
                                    key={msg.id || index}
                                    className={`flex ${msg.is_from_admin ? 'justify-start' : 'justify-end'}`}
                                >
                                    <div className={`flex items-start space-x-2 max-w-[80%] ${msg.is_from_admin ? 'flex-row' : 'flex-row-reverse space-x-reverse'}`}>
                                        {msg.is_from_admin && (
                                            <div className="w-8 h-8 bg-blue-600 rounded-full flex items-center justify-center flex-shrink-0 mt-1">
                                                <i className="fas fa-user-shield text-white text-xs"></i>
                                            </div>
                                        )}
                                        <div className={`rounded-lg px-4 py-2 ${msg.is_from_admin ? 'bg-white border border-gray-200' : 'bg-blue-600 text-white'}`}>
                                            <p className="text-sm break-words">{msg.message}</p>
                                            <p className={`text-xs mt-1 ${msg.is_from_admin ? 'text-gray-400' : 'text-blue-100'}`}>
                                                {new Date(msg.created_at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
                                            </p>
                                        </div>
                                        {!msg.is_from_admin && (
                                            <Avatar size="sm" src={user?.avatar_url} alt={user?.name} className="flex-shrink-0 mt-1" />
                                        )}
                                    </div>
                                </div>
                            ))
                        )}
                        <div ref={messagesEndRef} />
                    </div>

                    {/* Input Area */}
                    <form onSubmit={handleSendMessage} className="border-t border-gray-200 p-3 bg-white">
                        <div className="flex items-center space-x-2">
                            <input
                                type="text"
                                value={newMessage}
                                onChange={(e) => setNewMessage(e.target.value)}
                                placeholder="Type your message..."
                                className="flex-1 px-3 py-2 border border-gray-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-primary-500 focus:border-transparent"
                                disabled={sending || loading}
                            />
                            <button
                                type="submit"
                                disabled={!newMessage.trim() || sending || loading}
                                className="px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 transition-colors disabled:opacity-50 disabled:cursor-not-allowed flex items-center space-x-1"
                            >
                                {sending ? (
                                    <i className="fas fa-spinner fa-spin"></i>
                                ) : (
                                    <>
                                        <i className="fas fa-paper-plane"></i>
                                        <span className="text-sm">Send</span>
                                    </>
                                )}
                            </button>
                        </div>
                    </form>
                </div>
            )}
        </>
    );
}

export default UserChatWidget;
