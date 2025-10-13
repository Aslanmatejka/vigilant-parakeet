import React, { useState, useEffect, useRef } from "react";
import PropTypes from 'prop-types';
import { useAI } from '../../utils/hooks/useSupabase';
import { streamDeepseekChat, testDeepseekConnection } from '../../utils/deepseekChat';


function AIAssistant({ 
    isOpen, 
    onClose,
    initialMessage = "Hi! I'm Nourish, your food sharing assistant. I can help you find food, suggest recipes for ingredients you have, provide food storage tips, or answer questions about ShareFoods. How can I help you today?"
}) {
    const { 
        isLoading: aiLoading, 
        error: aiError, 
        chatWithNourish, 
        getRecipeSuggestions, 
        getStorageTips 
    } = useAI();
    
    const [messages, setMessages] = useState([
        {
            role: 'assistant',
            content: initialMessage,
            timestamp: new Date().toISOString()
        }
    ]);
    const [userInput, setUserInput] = useState('');
    const [isLoading, setIsLoading] = useState(false);
    const [error, setError] = useState(null);
    
    const [isStreaming, setIsStreaming] = useState(false);
    const [connectionStatus, setConnectionStatus] = useState('checking');
    const messagesEndRef = useRef(null);
    const inputRef = useRef(null);

    useEffect(() => {
        scrollToBottom();
    }, [messages]);

    useEffect(() => {
        if (!isOpen) {
            // Use setTimeout to avoid state updates during unmounting
            setTimeout(() => {
                setError(null);
                setUserInput('');
                
                setIsStreaming(false);
            }, 0);
        } else {
            // Test connection when assistant opens
            testConnection();
        }
    }, [isOpen]);

    useEffect(() => {
        // Focus input when assistant opens
        if (isOpen && inputRef.current) {
            setTimeout(() => inputRef.current.focus(), 100);
        }
    }, [isOpen]);

    const testConnection = async () => {
        setConnectionStatus('checking');
        try {
            const isConnected = await testDeepseekConnection();
            setConnectionStatus(isConnected ? 'connected' : 'disconnected');
        } catch (error) {
            setConnectionStatus('disconnected');
        }
    };

    const scrollToBottom = () => {
        messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
    };

    const addMessage = (role, content) => {
        const newMessage = {
            role,
            content,
            timestamp: new Date().toISOString()
        };
        setMessages(prev => [...prev, newMessage]);
    };

    const updateLastMessage = (content) => {
        setMessages(prev => {
            const newMessages = [...prev];
            if (newMessages.length > 0) {
                newMessages[newMessages.length - 1] = {
                    ...newMessages[newMessages.length - 1],
                    content
                };
            }
            return newMessages;
        });
    };

    const formatResponse = (response) => {
        if (typeof response === 'string') {
            return response;
        }
        try {
            // Handle chat message responses
            if (response.content && response.type === 'text') {
                return response.content;
            }
            
            // Handle recipe suggestions
            if (response.recipes) {
                let formattedText = "Here are some recipe suggestions:\n\n";
                response.recipes.forEach((recipe, index) => {
                    formattedText += `${index + 1}. **${recipe.name}**\n`;
                    formattedText += `🥘 **Ingredients:** ${Array.isArray(recipe.ingredients) ? recipe.ingredients.join(', ') : recipe.ingredients}\n`;
                    formattedText += `📝 **Instructions:** ${recipe.instructions}\n`;
                    if (recipe.prepTime !== 'N/A') {
                        formattedText += `⏱️ **Time:** ${recipe.prepTime}`;
                        if (recipe.cookTime !== 'N/A') {
                            formattedText += ` (cooking: ${recipe.cookTime})`;
                        }
                        formattedText += '\n';
                    }
                    formattedText += '\n';
                });
                return formattedText;
            }

            // Handle storage tips
            if (response.food && response.tips) {
                let formattedText = `📦 **Storage Tips for ${response.food}:**\n\n`;
                const tips = Array.isArray(response.tips) ? response.tips : [response.tips];
                tips.forEach(tip => {
                    formattedText += `• ${tip}\n`;
                });
                if (response.shelfLife) {
                    formattedText += '\n⏳ **Shelf Life:**\n';
                    Object.entries(response.shelfLife).forEach(([location, duration]) => {
                        formattedText += `• ${location.charAt(0).toUpperCase() + location.slice(1)}: ${duration}\n`;
                    });
                }
                return formattedText;
            }

            // Default case for other types of responses
            return typeof response === 'string' ? response : response.content || JSON.stringify(response, null, 2);
        } catch (error) {
            console.error('Response formatting error:', error);
            return String(response);
        }
    };

    const handleSpecialCommands = async (input) => {
        const lowerInput = input.toLowerCase();
        if (lowerInput.includes('recipe') || lowerInput.includes('make with')) {
            const ingredients = input
                .toLowerCase()
                .replace(/recipe|make with|ingredients?|what can i make with/gi, '')
                .trim()
                .split(/[,s]+/)
                .filter(word => word.length > 2);
            if (ingredients.length > 0) {
                try {
                    const recipes = await getRecipeSuggestions(ingredients);
                    return formatResponse({ recipes });
                } catch (error) {
                    console.error('Recipe suggestion error:', error);
                    return "I'm sorry, I couldn't find recipe suggestions for those ingredients. Please try again with different ingredients.";
                }
            }
        }
        if (lowerInput.includes('store') || lowerInput.includes('storage') || lowerInput.includes('keep')) {
            const foodItem = input
                .toLowerCase()
                .replace(/how to store|storage tips for|how do i store|how to keep|keep fresh/gi, '')
                .trim();
            if (foodItem.length > 2) {
                try {
                    const tips = await getStorageTips(foodItem);
                    return formatResponse(tips);
                } catch (error) {
                    console.error('Storage tips error:', error);
                    return "I'm sorry, I couldn't find storage tips for that item. Please try again with a different food item.";
                }
            }
        }
        return null;
    };

    const handleStreamingResponse = async (input) => {
        try {
            // Prepare context from chat history
            const context = messages.slice(-5).map(msg => `${msg.role}: ${msg.content}`).join('\n');
            
            // Use the AI hook for non-streaming response
            const response = await chatWithNourish(input, context);
            
            // Format and add the response
            const formattedResponse = formatResponse(response);
            addMessage('assistant', formattedResponse);
            
        } catch (error) {
            console.error('AI chat error:', error);
            setError(error.message || "Failed to get response from AI.");
            addMessage('assistant', 
                "I'm sorry, I encountered an error while responding. Please try again."
            );
        }
    };

    const handleSendMessage = async (e) => {
        e.preventDefault();
        if (!userInput.trim() || isLoading || isStreaming) return;
        
        const input = userInput.trim();
        addMessage('user', input);
        setUserInput('');
        setIsLoading(true);
        setError(null);
        
        try {
            // Try special commands first (optional, can be removed if LLM handles all)
            const specialResponse = await handleSpecialCommands(input);
            if (specialResponse) {
                addMessage('assistant', specialResponse);
                setIsLoading(false);
                return;
            }

            // Use streaming for better UX
            await handleStreamingResponse(input);
        } catch (error) {
            console.error('AI assistant error:', error);
            setError(error.message || "Failed to get response. Please try again.");
            addMessage('assistant', 
                "I'm sorry, I'm having trouble processing your request right now. " +
                "Please try again later or try rephrasing your question."
            );
        } finally {
            setIsLoading(false);
        }
    };

    const handleQuickQuestion = (question) => {
        if (!isLoading && !isStreaming) {
            setUserInput(question);
            setError(null);
        }
    };

    const copyMessage = async (content) => {
        try {
            await navigator.clipboard.writeText(content);
            // You could add a toast notification here
        } catch (error) {
            console.error('Failed to copy message:', error);
        }
    };

    const exportConversation = () => {
        const conversation = messages.map(msg => 
            `${msg.role === 'user' ? 'You' : 'Nourish'}: ${msg.content}`
        ).join('\n\n');
        
        const blob = new Blob([conversation], { type: 'text/plain' });
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = `nourish-conversation-${new Date().toISOString().split('T')[0]}.txt`;
        a.click();
        URL.revokeObjectURL(url);
    };

    const clearConversation = () => {
        setMessages([
            {
                role: 'assistant',
                content: initialMessage,
                timestamp: new Date().toISOString()
            }
        ]);
        setError(null);
    };

    const formatTimestamp = (timestamp) => {
        return new Date(timestamp).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
    };

    const quickQuestions = [
        "How do I find food near me?",
        "What can I make with tomatoes and basil?",
        "How do I store leafy greens?",
        "How does ShareFoods work?"
    ];

    if (!isOpen) return null;

    return (
        <div data-name="ai-assistant" className="fixed inset-0 z-50 overflow-hidden flex items-center justify-center bg-black bg-opacity-50">
            <div className="bg-white rounded-lg shadow-xl w-full max-w-md mx-4 flex flex-col" style={{ maxHeight: '90vh' }}>
                {/* Header */}
                <div className="bg-green-600 text-white px-4 py-3 flex items-center justify-between rounded-t-lg">
                    <div className="flex items-center">
                        <div className="w-8 h-8 bg-white rounded-full flex items-center justify-center mr-3">
                            <i className="fas fa-robot text-green-600"></i>
                        </div>
                        <div>
                            <h3 className="font-bold">Nourish Assistant</h3>
                            <div className="flex items-center text-xs text-green-100">
                                <span className={`w-2 h-2 rounded-full mr-2 ${
                                    connectionStatus === 'connected' ? 'bg-green-300' : 
                                    connectionStatus === 'checking' ? 'bg-yellow-300' : 'bg-red-300'
                                }`}></span>
                                {connectionStatus === 'connected' ? 'Connected' : 
                                 connectionStatus === 'checking' ? 'Checking...' : 'Disconnected'}
                            </div>
                        </div>
                    </div>
                    <div className="flex items-center space-x-2">
                        <button 
                            onClick={exportConversation}
                            className="text-white hover:text-green-200 text-sm"
                            title="Export conversation"
                        >
                            <i className="fas fa-download"></i>
                        </button>
                        <button 
                            onClick={clearConversation}
                            className="text-white hover:text-green-200 text-sm"
                            title="Clear conversation"
                        >
                            <i className="fas fa-trash"></i>
                        </button>
                        <button 
                            onClick={onClose}
                            className="text-white hover:text-green-200"
                            aria-label="Close assistant"
                        >
                            <i className="fas fa-times"></i>
                        </button>
                    </div>
                </div>
                
                {/* Chat messages */}
                <div className="flex-1 overflow-y-auto p-4 space-y-4">
                    {messages.map((message, index) => (
                        <div
                            key={index}
                            className={`flex ${message.role === 'user' ? 'justify-end' : 'justify-start'}`}
                        >
                            <div className="relative group">
                                <div
                                    className={`max-w-xs lg:max-w-md px-4 py-2 rounded-lg ${
                                        message.role === 'user'
                                            ? 'bg-green-600 text-white'
                                            : 'bg-gray-100 text-gray-800'
                                    }`}
                                >
                                    <p className="whitespace-pre-wrap">{message.content}</p>
                                    <div className={`text-xs mt-1 ${
                                        message.role === 'user' ? 'text-green-200' : 'text-gray-500'
                                    }`}>
                                        {formatTimestamp(message.timestamp)}
                                    </div>
                                </div>
                                {message.role === 'assistant' && message.content && (
                                    <button
                                        onClick={() => copyMessage(message.content)}
                                        className="absolute -top-2 -right-2 bg-gray-200 hover:bg-gray-300 rounded-full p-1 opacity-0 group-hover:opacity-100 transition-opacity"
                                        title="Copy message"
                                    >
                                        <i className="fas fa-copy text-xs"></i>
                                    </button>
                                )}
                            </div>
                        </div>
                    ))}
                    
                    {isStreaming && currentStreamingMessage && (
                        <div className="flex justify-start">
                            <div className="bg-gray-100 text-gray-800 px-4 py-2 rounded-lg">
                                <p className="whitespace-pre-wrap">{currentStreamingMessage}</p>
                                <div className="text-xs text-gray-500 mt-1">
                                    {formatTimestamp(new Date().toISOString())} (typing...)
                                </div>
                            </div>
                        </div>
                    )}
                    
                    <div ref={messagesEndRef} />
                </div>

                {/* Quick questions */}
                {messages.length === 1 && (
                    <div className="px-4 pb-4">
                        <p className="text-sm text-gray-600 mb-3">Quick questions:</p>
                        <div className="flex flex-wrap gap-2">
                            {quickQuestions.map((question, index) => (
                                <button
                                    key={index}
                                    onClick={() => handleQuickQuestion(question)}
                                    className="text-xs bg-gray-100 hover:bg-gray-200 text-gray-700 px-3 py-1 rounded-full transition-colors"
                                >
                                    {question}
                                </button>
                            ))}
                        </div>
                    </div>
                )}

                {/* Error message */}
                {error && (
                    <div className="px-4 pb-4">
                        <div className="bg-red-50 border border-red-200 rounded-lg p-3">
                            <p className="text-sm text-red-700">{error}</p>
                        </div>
                    </div>
                )}

                {/* Input form */}
                <form onSubmit={handleSendMessage} className="p-4 border-t">
                    <div className="flex space-x-2">
                        <input
                            ref={inputRef}
                            type="text"
                            value={userInput}
                            onChange={(e) => setUserInput(e.target.value)}
                            placeholder="Ask me anything..."
                            className="flex-1 px-3 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-green-500 focus:border-transparent"
                            disabled={isLoading || isStreaming}
                        />
                        <button
                            type="submit"
                            disabled={!userInput.trim() || isLoading || isStreaming}
                            className="px-4 py-2 bg-green-600 text-white rounded-lg hover:bg-green-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
                        >
                            <i className="fas fa-paper-plane"></i>
                        </button>
                    </div>
                </form>
            </div>
        </div>
    );
}

AIAssistant.propTypes = {
    isOpen: PropTypes.bool.isRequired,
    onClose: PropTypes.func.isRequired,
    initialMessage: PropTypes.string
};

export default AIAssistant;
