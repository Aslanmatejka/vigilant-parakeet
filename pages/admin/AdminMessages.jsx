import React from 'react';
import AdminLayout from './AdminLayout';
import dataService from '../../utils/dataService';
import Avatar from '../../components/common/Avatar';
import Button from '../../components/common/Button';

function AdminMessages() {
    const [conversations, setConversations] = React.useState([]);
    const [selectedConversation, setSelectedConversation] = React.useState(null);
    const [messages, setMessages] = React.useState([]);
    const [newMessage, setNewMessage] = React.useState('');
    const [loading, setLoading] = React.useState(true);
    const [sending, setSending] = React.useState(false);
    const [filter, setFilter] = React.useState('all'); // all, open, closed
    const messagesEndRef = React.useRef(null);

    const scrollToBottom = () => {
        messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
    };

    React.useEffect(() => {
        scrollToBottom();
    }, [messages]);

    React.useEffect(() => {
        loadConversations();

        // Unsubscribe from any previous subscription first
        dataService.unsubscribe('conversations');

        // Subscribe to conversation changes
        const subscription = dataService.subscribeToConversations((payload) => {
            if (payload.eventType === 'INSERT' || payload.eventType === 'UPDATE') {
                loadConversations();
            }
        });

        return () => {
            dataService.unsubscribe('conversations');
        };
    }, []);

    React.useEffect(() => {
        if (selectedConversation?.id) {
            loadMessages();

            // Unsubscribe from any previous subscription first
            dataService.unsubscribe(`messages_${selectedConversation.id}`);

            // Subscribe to messages for this conversation
            const subscription = dataService.subscribeToMessages(selectedConversation.id, (payload) => {
                if (payload.eventType === 'INSERT') {
                    setMessages(prev => {
                        // Check if we already have this message (optimistic update)
                        const exists = prev.some(m => m.id === payload.new.id);
                        if (exists) {
                            return prev; // Already have it
                        }

                        // Check if we have a temp message for this (replace it)
                        const hasTempMessage = prev.some(m => String(m.id).startsWith('temp-'));
                        if (hasTempMessage && payload.new.is_from_admin) {
                            // Replace temp message with real one
                            return prev.map(m =>
                                String(m.id).startsWith('temp-') ? payload.new : m
                            );
                        }

                        // Add new message
                        return [...prev, payload.new];
                    });
                    scrollToBottom();

                    // Mark non-admin messages as read
                    if (!payload.new.is_from_admin && !payload.new.read_at) {
                        dataService.markMessageAsRead(payload.new.id);
                    }
                }
            });

            return () => {
                dataService.unsubscribe(`messages_${selectedConversation.id}`);
            };
        }
    }, [selectedConversation?.id]);

    const loadConversations = async () => {
        try {
            setLoading(true);
            console.log('AdminMessages: Loading conversations...');
            const data = await dataService.getAdminConversations();
            console.log('AdminMessages: Received conversations data:', data);
            console.log('AdminMessages: Number of conversations:', data?.length || 0);
            setConversations(data);
        } catch (error) {
            console.error('AdminMessages: Failed to load conversations:', error);
            console.error('AdminMessages: Error details:', {
                message: error.message,
                code: error.code,
                details: error.details,
                hint: error.hint
            });
        } finally {
            setLoading(false);
        }
    };

    const loadMessages = async () => {
        try {
            const msgs = await dataService.getConversationMessages(selectedConversation.id);
            setMessages(msgs);

            // Mark unread messages as read (in parallel, not sequentially)
            const unreadMessages = msgs.filter(m => !m.is_from_admin && !m.read_at);
            if (unreadMessages.length > 0) {
                // Mark all unread messages in parallel instead of one by one
                await Promise.all(
                    unreadMessages.map(msg => dataService.markMessageAsRead(msg.id))
                );
            }
        } catch (error) {
            console.error('Failed to load messages:', error);
        }
    };

    const handleSendMessage = async (e) => {
        e.preventDefault();
        if (!newMessage.trim() || !selectedConversation?.id || sending) return;

        const messageText = newMessage.trim();
        const tempMessage = {
            id: 'temp-' + Date.now(),
            conversation_id: selectedConversation.id,
            message: messageText,
            is_from_admin: true,
            created_at: new Date().toISOString(),
            read_at: null
        };

        try {
            setSending(true);

            // Optimistic UI update - add message immediately
            setMessages(prev => [...prev, tempMessage]);
            setNewMessage('');

            console.log('Admin sending message:', {
                conversationId: selectedConversation.id,
                message: messageText,
                isFromAdmin: true
            });

            await dataService.sendMessage(selectedConversation.id, messageText, true);
            console.log('Message sent successfully');

            // Subscription will update with real message, no need to reload
        } catch (error) {
            console.error('Failed to send message:', error);
            console.error('Error details:', {
                message: error.message,
                code: error.code,
                details: error.details,
                hint: error.hint
            });

            // Remove optimistic message on error
            setMessages(prev => prev.filter(m => m.id !== tempMessage.id));
            setNewMessage(messageText); // Restore message text

            alert(`Failed to send message: ${error.message || 'Unknown error'}. Please try again.`);
        } finally {
            setSending(false);
        }
    };

    const handleCloseConversation = async (conversationId) => {
        try {
            await dataService.closeConversation(conversationId);
            await loadConversations();
            if (selectedConversation?.id === conversationId) {
                setSelectedConversation(null);
                setMessages([]);
            }
        } catch (error) {
            console.error('Failed to close conversation:', error);
            alert('Failed to close conversation. Please try again.');
        }
    };

    const handleReopenConversation = async (conversationId) => {
        try {
            await dataService.reopenConversation(conversationId);
            await loadConversations();
        } catch (error) {
            console.error('Failed to reopen conversation:', error);
            alert('Failed to reopen conversation. Please try again.');
        }
    };

    const filteredConversations = React.useMemo(() => {
        if (filter === 'all') return conversations;
        return conversations.filter(c => c.status === filter);
    }, [conversations, filter]);

    const getUnreadCount = (conversation) => {
        return conversation.unread_count || 0;
    };

    const getLastMessage = (conversation) => {
        if (!conversation.last_message) {
            return 'No messages yet';
        }
        const preview = conversation.last_message.message.substring(0, 50);
        return conversation.last_message.message.length > 50 ? `${preview}...` : preview;
    };

    return (
        <AdminLayout active="messages">
            <div className="h-[calc(100vh-4rem)] flex flex-col">
                <div className="mb-6">
                    <h1 className="text-2xl font-bold text-gray-900">Messages</h1>
                    <p className="text-gray-600 mt-1">Manage user conversations and support requests</p>
                </div>

                <div className="flex-1 grid grid-cols-12 gap-4 overflow-hidden">
                    {/* Conversations List */}
                    <div className="col-span-4 bg-white rounded-lg shadow-sm border border-gray-200 flex flex-col overflow-hidden">
                        {/* Filter Tabs */}
                        <div className="p-4 border-b border-gray-200">
                            <div className="flex space-x-2">
                                {[
                                    { value: 'all', label: 'All', icon: 'fa-inbox' },
                                    { value: 'open', label: 'Open', icon: 'fa-envelope-open' },
                                    { value: 'closed', label: 'Closed', icon: 'fa-check-circle' }
                                ].map(tab => (
                                    <button
                                        key={tab.value}
                                        onClick={() => setFilter(tab.value)}
                                        className={`flex-1 px-3 py-2 text-sm font-medium rounded-lg transition-colors ${
                                            filter === tab.value
                                                ? 'bg-[#2CABE3] text-white'
                                                : 'bg-gray-100 text-gray-700 hover:bg-gray-200'
                                        }`}
                                    >
                                        <i className={`fas ${tab.icon} mr-2`}></i>
                                        {tab.label}
                                    </button>
                                ))}
                            </div>
                        </div>

                        {/* Conversations */}
                        <div className="flex-1 overflow-y-auto">
                            {loading ? (
                                <div className="flex items-center justify-center h-full text-gray-500">
                                    <i className="fas fa-spinner fa-spin mr-2"></i>
                                    Loading conversations...
                                </div>
                            ) : filteredConversations.length === 0 ? (
                                <div className="flex flex-col items-center justify-center h-full text-gray-400 p-4">
                                    <i className="fas fa-inbox text-5xl mb-3"></i>
                                    <p className="text-sm">No conversations found</p>
                                </div>
                            ) : (
                                filteredConversations.map(conv => (
                                    <button
                                        key={conv.id}
                                        onClick={() => setSelectedConversation(conv)}
                                        className={`w-full p-4 border-b border-gray-100 hover:bg-gray-50 transition-colors text-left ${
                                            selectedConversation?.id === conv.id ? 'bg-[#2CABE3]/10' : ''
                                        }`}
                                    >
                                        <div className="flex items-start space-x-3">
                                            <Avatar
                                                src={conv.users?.avatar_url}
                                                alt={conv.users?.name}
                                                size="md"
                                            />
                                            <div className="flex-1 min-w-0">
                                                <div className="flex items-center justify-between mb-1">
                                                    <h3 className="text-sm font-semibold text-gray-900 truncate">
                                                        {conv.users?.name || conv.users?.email || 'Unknown User'}
                                                    </h3>
                                                    {getUnreadCount(conv) > 0 && (
                                                        <span className="ml-2 bg-[#2CABE3] text-white text-xs rounded-full px-2 py-0.5">
                                                            {getUnreadCount(conv)}
                                                        </span>
                                                    )}
                                                </div>
                                                <p className="text-xs text-gray-500 truncate mb-1">
                                                    {getLastMessage(conv)}
                                                </p>
                                                <div className="flex items-center space-x-2 text-xs">
                                                    <span className={`px-2 py-0.5 rounded ${
                                                        conv.status === 'open'
                                                            ? 'bg-[#2CABE3]/20 text-[#2CABE3]'
                                                            : 'bg-gray-100 text-gray-600'
                                                    }`}>
                                                        {conv.status}
                                                    </span>
                                                    <span className="text-gray-400">
                                                        {new Date(conv.last_message_at).toLocaleDateString()}
                                                    </span>
                                                </div>
                                            </div>
                                        </div>
                                    </button>
                                ))
                            )}
                        </div>
                    </div>

                    {/* Chat Area */}
                    <div className="col-span-8 bg-white rounded-lg shadow-sm border border-gray-200 flex flex-col overflow-hidden">
                        {selectedConversation ? (
                            <>
                                {/* Chat Header */}
                                <div className="p-4 border-b border-gray-200 flex items-center justify-between">
                                    <div className="flex items-center space-x-3">
                                        <Avatar
                                            src={selectedConversation.users?.avatar_url}
                                            alt={selectedConversation.users?.name}
                                            size="md"
                                        />
                                        <div>
                                            <h2 className="text-lg font-semibold text-gray-900">
                                                {selectedConversation.users?.name || 'Unknown User'}
                                            </h2>
                                            <p className="text-sm text-gray-500">{selectedConversation.users?.email}</p>
                                        </div>
                                    </div>
                                    <div className="flex items-center space-x-2">
                                        {selectedConversation.status === 'open' ? (
                                            <Button
                                                variant="secondary"
                                                size="sm"
                                                onClick={() => handleCloseConversation(selectedConversation.id)}
                                            >
                                                <i className="fas fa-check-circle mr-2"></i>
                                                Close Conversation
                                            </Button>
                                        ) : (
                                            <Button
                                                variant="primary"
                                                size="sm"
                                                onClick={() => handleReopenConversation(selectedConversation.id)}
                                            >
                                                <i className="fas fa-redo mr-2"></i>
                                                Reopen
                                            </Button>
                                        )}
                                    </div>
                                </div>

                                {/* Messages */}
                                <div className="flex-1 overflow-y-auto p-4 space-y-4 bg-gray-50">
                                    {messages.length === 0 ? (
                                        <div className="flex flex-col items-center justify-center h-full text-gray-400">
                                            <i className="fas fa-comments text-5xl mb-3"></i>
                                            <p className="text-sm">No messages in this conversation</p>
                                        </div>
                                    ) : (
                                        messages.map((msg, index) => (
                                            <div
                                                key={msg.id || index}
                                                className={`flex ${msg.is_from_admin ? 'justify-end' : 'justify-start'}`}
                                            >
                                                <div className={`flex items-start space-x-2 max-w-[70%] ${msg.is_from_admin ? 'flex-row-reverse space-x-reverse' : 'flex-row'}`}>
                                                    {!msg.is_from_admin && (
                                                        <Avatar
                                                            size="sm"
                                                            src={selectedConversation.users?.avatar_url}
                                                            alt={selectedConversation.users?.name}
                                                            className="flex-shrink-0 mt-1"
                                                        />
                                                    )}
                                                    <div className={`rounded-lg px-4 py-3 ${
                                                        msg.is_from_admin
                                                            ? 'bg-[#2CABE3] text-white'
                                                            : 'bg-white border border-gray-200'
                                                    }`}>
                                                        <p className="text-sm break-words whitespace-pre-wrap">{msg.message}</p>
                                                        <div className="flex items-center justify-between mt-2 text-xs">
                                                            <span className={msg.is_from_admin ? 'text-white/80' : 'text-gray-400'}>
                                                                {new Date(msg.created_at).toLocaleString()}
                                                            </span>
                                                            {msg.is_from_admin && (
                                                                <i className="fas fa-user-shield ml-2"></i>
                                                            )}
                                                        </div>
                                                    </div>
                                                    {msg.is_from_admin && (
                                                        <div className="w-8 h-8 bg-[#2CABE3] rounded-full flex items-center justify-center flex-shrink-0 mt-1">
                                                            <i className="fas fa-user-shield text-white text-xs"></i>
                                                        </div>
                                                    )}
                                                </div>
                                            </div>
                                        ))
                                    )}
                                    <div ref={messagesEndRef} />
                                </div>

                                {/* Message Input */}
                                <form onSubmit={handleSendMessage} className="p-4 border-t border-gray-200 bg-white">
                                    <div className="flex items-end space-x-2">
                                        <textarea
                                            value={newMessage}
                                            onChange={(e) => setNewMessage(e.target.value)}
                                            onKeyDown={(e) => {
                                                if (e.key === 'Enter' && !e.shiftKey) {
                                                    e.preventDefault();
                                                    handleSendMessage(e);
                                                }
                                            }}
                                            placeholder="Type your response... (Shift+Enter for new line)"
                                            className="flex-1 px-4 py-3 border border-gray-300 rounded-lg resize-none focus:outline-none focus:ring-2 focus:ring-primary-500 focus:border-transparent"
                                            rows="3"
                                            disabled={sending || selectedConversation.status === 'closed'}
                                        />
                                        <Button
                                            type="submit"
                                            variant="primary"
                                            disabled={!newMessage.trim() || sending || selectedConversation.status === 'closed'}
                                            className="self-end"
                                        >
                                            {sending ? (
                                                <><i className="fas fa-spinner fa-spin mr-2"></i>Sending...</>
                                            ) : (
                                                <><i className="fas fa-paper-plane mr-2"></i>Send</>
                                            )}
                                        </Button>
                                    </div>
                                    {selectedConversation.status === 'closed' && (
                                        <p className="text-xs text-gray-500 mt-2">
                                            <i className="fas fa-info-circle mr-1"></i>
                                            This conversation is closed. Reopen it to send messages.
                                        </p>
                                    )}
                                </form>
                            </>
                        ) : (
                            <div className="flex flex-col items-center justify-center h-full text-gray-400">
                                <i className="fas fa-comment-dots text-6xl mb-4"></i>
                                <h3 className="text-lg font-medium text-gray-500 mb-2">Select a Conversation</h3>
                                <p className="text-sm text-center max-w-md">
                                    Choose a conversation from the list to view messages and respond to users
                                </p>
                            </div>
                        )}
                    </div>
                </div>
            </div>
        </AdminLayout>
    );
}

export default AdminMessages;
