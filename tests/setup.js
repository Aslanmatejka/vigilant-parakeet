import '@testing-library/jest-dom';
import 'whatwg-fetch';

// Avoid import.meta / missing env when AI modules pull in supabaseClient.
jest.mock('../utils/supabaseClient.js', () => ({
  __esModule: true,
  default: {
    auth: {
      getSession: jest.fn().mockResolvedValue({ data: { session: null } }),
    },
  },
}));

// dataService also reads import.meta.env, mock the surface used by the AI panel.
jest.mock('../utils/dataService.js', () => ({
  __esModule: true,
  default: {
    uploadFile: jest.fn().mockResolvedValue({ url: '' }),
    getFoodListings: jest.fn().mockResolvedValue([]),
    createFoodListing: jest.fn().mockResolvedValue({ id: 'mock' }),
  },
}));

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

// Clear all mocks before each test
beforeEach(() => {
  jest.clearAllMocks();
});
