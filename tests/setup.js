import '@testing-library/jest-dom';
import 'whatwg-fetch';

// Mock fetch to prevent actual HTTP requests in tests
global.fetch = jest.fn(() =>
  Promise.resolve({
    ok: true,
    json: () => Promise.resolve({
      urgency: 'normal',
      value: 5,
      choices: [{ message: { content: JSON.stringify({ score: 8, reasoning: 'Test reasoning' }) } }]
    }),
  }),
);

// Mock window objects that might not exist in test environment
Object.defineProperty(window, 'DEEPSEEK_API_KEY', {
  writable: true,
  value: 'sk-test-key-for-testing'
});

// Clear all mocks before each test
beforeEach(() => {
  jest.clearAllMocks();
});
