import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import AIAssistant from '../components/assistant/AIAssistant';

// Mock the utilities
jest.mock('../utils/deepseekChat', () => ({
    deepseekChat: jest.fn(),
    streamDeepseekChat: jest.fn(),
    testDeepseekConnection: jest.fn()
}));

jest.mock('../utils/aiAgent', () => ({
    getRecipeSuggestions: jest.fn(),
    getStorageTips: jest.fn()
}));

jest.mock('../utils/helpers', () => ({
    reportError: jest.fn()
}));

jest.mock('../utils/config', () => ({
    getApiConfig: jest.fn(() => ({
        DEEPSEEK: {
            API_KEY: 'test-key',
            API_ENDPOINT: 'https://api.deepseek.com/v1',
            MODELS: { CHAT: 'deepseek-chat' }
        }
    }))
}));

describe('AI Assistant', () => {
    const mockOnClose = jest.fn();

    beforeEach(() => {
        jest.clearAllMocks();
    });

    describe('Rendering', () => {
        test('renders assistant when open', () => {
            render(<AIAssistant isOpen={true} onClose={mockOnClose} />);
            
            expect(screen.getByText('Nourish Assistant')).toBeInTheDocument();
            expect(screen.getByPlaceholderText('Ask me anything...')).toBeInTheDocument();
        });

        test('does not render when closed', () => {
            render(<AIAssistant isOpen={false} onClose={mockOnClose} />);
            
            expect(screen.queryByText('Nourish Assistant')).not.toBeInTheDocument();
        });

        test('shows initial message', () => {
            render(<AIAssistant isOpen={true} onClose={mockOnClose} />);
            
            expect(screen.getByText(/Hi! I'm Nourish/)).toBeInTheDocument();
        });

        test('shows quick questions when conversation is new', () => {
            render(<AIAssistant isOpen={true} onClose={mockOnClose} />);
            
            expect(screen.getByText('How do I find food near me?')).toBeInTheDocument();
            expect(screen.getByText('What can I make with tomatoes and basil?')).toBeInTheDocument();
        });
    });

    describe('Connection Status', () => {
        test('shows checking status initially', () => {
            render(<AIAssistant isOpen={true} onClose={mockOnClose} />);
            
            expect(screen.getByText('Checking...')).toBeInTheDocument();
        });

        test('shows connected status when API is available', async () => {
            const { testDeepseekConnection } = require('../utils/deepseekChat');
            testDeepseekConnection.mockResolvedValue(true);

            render(<AIAssistant isOpen={true} onClose={mockOnClose} />);
            
            await waitFor(() => {
                expect(screen.getByText('Connected')).toBeInTheDocument();
            });
        });

        test('shows disconnected status when API is unavailable', async () => {
            const { testDeepseekConnection } = require('../utils/deepseekChat');
            testDeepseekConnection.mockResolvedValue(false);

            render(<AIAssistant isOpen={true} onClose={mockOnClose} />);
            
            await waitFor(() => {
                expect(screen.getByText('Disconnected')).toBeInTheDocument();
            });
        });
    });

    describe('Message Handling', () => {
        test('sends user message', async () => {
            const { streamDeepseekChat } = require('../utils/deepseekChat');
            streamDeepseekChat.mockResolvedValue();

            render(<AIAssistant isOpen={true} onClose={mockOnClose} />);
            
            const input = screen.getByPlaceholderText('Ask me anything...');
            const sendButton = screen.getByRole('button', { name: /paper-plane/i });

            fireEvent.change(input, { target: { value: 'Hello AI' } });
            fireEvent.click(sendButton);

            await waitFor(() => {
                expect(screen.getByText('Hello AI')).toBeInTheDocument();
            });
        });

        test('handles streaming response', async () => {
            const { streamDeepseekChat } = require('../utils/deepseekChat');
            let onChunkCallback;
            streamDeepseekChat.mockImplementation((messages, onChunk) => {
                onChunkCallback = onChunk;
                return Promise.resolve();
            });

            render(<AIAssistant isOpen={true} onClose={mockOnClose} />);
            
            const input = screen.getByPlaceholderText('Ask me anything...');
            fireEvent.change(input, { target: { value: 'Test message' } });
            fireEvent.submit(input);

            await waitFor(() => {
                expect(streamDeepseekChat).toHaveBeenCalled();
            });

            // Simulate streaming chunks
            if (onChunkCallback) {
                onChunkCallback('Hello');
                onChunkCallback(' there');
                onChunkCallback('!');
            }

            await waitFor(() => {
                expect(screen.getByText('Hello there!')).toBeInTheDocument();
            });
        });

        test('handles special commands (recipes)', async () => {
            const { getRecipeSuggestions } = require('../utils/aiAgent');
            getRecipeSuggestions.mockResolvedValue({
                recipes: [
                    {
                        name: 'Tomato Basil Pasta',
                        ingredients: ['tomatoes', 'basil', 'pasta'],
                        instructions: 'Cook pasta and mix with tomatoes and basil',
                        prepTime: '10 minutes',
                        cookTime: '15 minutes'
                    }
                ]
            });

            render(<AIAssistant isOpen={true} onClose={mockOnClose} />);
            
            const input = screen.getByPlaceholderText('Ask me anything...');
            fireEvent.change(input, { target: { value: 'recipe for tomatoes and basil' } });
            fireEvent.submit(input);

            await waitFor(() => {
                expect(screen.getByText(/Here are some recipe suggestions/)).toBeInTheDocument();
                expect(screen.getByText(/Tomato Basil Pasta/)).toBeInTheDocument();
            });
        });

        test('handles special commands (storage tips)', async () => {
            const { getStorageTips } = require('../utils/aiAgent');
            getStorageTips.mockResolvedValue({
                food: 'lettuce',
                tips: ['Keep in refrigerator', 'Wrap in paper towel'],
                shelfLife: { refrigerator: '1 week' }
            });

            render(<AIAssistant isOpen={true} onClose={mockOnClose} />);
            
            const input = screen.getByPlaceholderText('Ask me anything...');
            fireEvent.change(input, { target: { value: 'how to store lettuce' } });
            fireEvent.submit(input);

            await waitFor(() => {
                expect(screen.getByText(/Storage tips for lettuce/)).toBeInTheDocument();
                expect(screen.getByText(/Keep in refrigerator/)).toBeInTheDocument();
            });
        });
    });

    describe('UI Interactions', () => {
        test('quick questions populate input', () => {
            render(<AIAssistant isOpen={true} onClose={mockOnClose} />);
            
            const quickQuestion = screen.getByText('How do I find food near me?');
            fireEvent.click(quickQuestion);

            const input = screen.getByPlaceholderText('Ask me anything...');
            expect(input.value).toBe('How do I find food near me?');
        });

        test('copy message functionality', async () => {
            const mockClipboard = {
                writeText: jest.fn().mockResolvedValue()
            };
            Object.assign(navigator, { clipboard: mockClipboard });

            render(<AIAssistant isOpen={true} onClose={mockOnClose} />);
            
            // Add a message first
            const input = screen.getByPlaceholderText('Ask me anything...');
            fireEvent.change(input, { target: { value: 'Test message' } });
            fireEvent.submit(input);

            await waitFor(() => {
                const copyButton = screen.getByTitle('Copy message');
                fireEvent.click(copyButton);
            });

            expect(mockClipboard.writeText).toHaveBeenCalled();
        });

        test('export conversation functionality', () => {
            const mockCreateElement = jest.fn();
            const mockClick = jest.fn();
            const mockDownload = jest.fn();
            const mockHref = jest.fn();
            
            mockCreateElement.mockReturnValue({
                click: mockClick,
                download: mockDownload,
                href: mockHref
            });

            document.createElement = mockCreateElement;
            URL.createObjectURL = jest.fn(() => 'blob:url');
            URL.revokeObjectURL = jest.fn();

            render(<AIAssistant isOpen={true} onClose={mockOnClose} />);
            
            const exportButton = screen.getByTitle('Export conversation');
            fireEvent.click(exportButton);

            expect(mockCreateElement).toHaveBeenCalledWith('a');
            expect(mockClick).toHaveBeenCalled();
        });

        test('clear conversation functionality', () => {
            render(<AIAssistant isOpen={true} onClose={mockOnClose} />);
            
            // Add a message first
            const input = screen.getByPlaceholderText('Ask me anything...');
            fireEvent.change(input, { target: { value: 'Test message' } });
            fireEvent.submit(input);

            const clearButton = screen.getByTitle('Clear conversation');
            fireEvent.click(clearButton);

            // Should only show the initial message
            expect(screen.getByText(/Hi! I'm Nourish/)).toBeInTheDocument();
            expect(screen.queryByText('Test message')).not.toBeInTheDocument();
        });

        test('close assistant functionality', () => {
            render(<AIAssistant isOpen={true} onClose={mockOnClose} />);
            
            const closeButton = screen.getByLabelText('Close assistant');
            fireEvent.click(closeButton);

            expect(mockOnClose).toHaveBeenCalled();
        });
    });

    describe('Error Handling', () => {
        test('handles API errors gracefully', async () => {
            const { streamDeepseekChat } = require('../utils/deepseekChat');
            streamDeepseekChat.mockRejectedValue(new Error('API Error'));

            render(<AIAssistant isOpen={true} onClose={mockOnClose} />);
            
            const input = screen.getByPlaceholderText('Ask me anything...');
            fireEvent.change(input, { target: { value: 'Test message' } });
            fireEvent.submit(input);

            await waitFor(() => {
                expect(screen.getByText(/I'm sorry, I'm having trouble/)).toBeInTheDocument();
            });
        });

        test('shows error message when API fails', async () => {
            const { streamDeepseekChat } = require('../utils/deepseekChat');
            streamDeepseekChat.mockRejectedValue(new Error('Network error'));

            render(<AIAssistant isOpen={true} onClose={mockOnClose} />);
            
            const input = screen.getByPlaceholderText('Ask me anything...');
            fireEvent.change(input, { target: { value: 'Test message' } });
            fireEvent.submit(input);

            await waitFor(() => {
                expect(screen.getByText('Network error')).toBeInTheDocument();
            });
        });
    });

    describe('Accessibility', () => {
        test('has proper ARIA labels', () => {
            render(<AIAssistant isOpen={true} onClose={mockOnClose} />);
            
            expect(screen.getByLabelText('Close assistant')).toBeInTheDocument();
            expect(screen.getByPlaceholderText('Ask me anything...')).toBeInTheDocument();
        });

        test('input is focused when assistant opens', () => {
            render(<AIAssistant isOpen={true} onClose={mockOnClose} />);
            
            const input = screen.getByPlaceholderText('Ask me anything...');
            expect(input).toHaveFocus();
        });
    });
});