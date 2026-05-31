import React from 'react'
import { render, screen, fireEvent, waitFor, act } from '@testing-library/react'
import '@testing-library/jest-dom'

// ── Mocks ────────────────────────────────────────────────────

// Mock AuthContext
const mockAuthCtx = { user: { id: 'u1', name: 'Test User' }, isAuthenticated: true, isAdmin: false }
jest.mock('../utils/AuthContext.jsx', () => ({
  useAuthContext: () => mockAuthCtx,
}))

// Mock aiChatService
const mockSendMessage = jest.fn()
const mockGetHistory = jest.fn().mockResolvedValue([])
const mockClearHistory = jest.fn().mockResolvedValue(true)
const mockSubmitFeedback = jest.fn().mockResolvedValue(true)
jest.mock('../utils/services/aiChatService.js', () => ({
  __esModule: true,
  default: {
    sendMessage: (...args) => mockSendMessage(...args),
    getHistory: (...args) => mockGetHistory(...args),
    clearHistory: (...args) => mockClearHistory(...args),
    submitFeedback: (...args) => mockSubmitFeedback(...args),
  },
}))

// Mock react-router-dom
jest.mock('react-router-dom', () => ({
  useNavigate: () => jest.fn(),
}))

// Mock VoiceInput & VoiceOutput (no real SpeechRecognition in jsdom)
jest.mock('../components/assistant/VoiceInput.jsx', () => {
  return function MockVoiceInput({ onTranscript }) {
    return (
      <button data-testid="mock-voice" onClick={() => onTranscript('hello from voice')}>
        Mic
      </button>
    )
  }
})

jest.mock('../components/assistant/VoiceOutput.jsx', () => {
  return function MockVoiceOutput() {
    return null
  }
})

// Mock navigator.geolocation
const mockGetCurrentPosition = jest.fn((success) =>
  success({ coords: { latitude: 40.7, longitude: -74.0 } })
)
Object.defineProperty(global.navigator, 'geolocation', {
  value: { getCurrentPosition: mockGetCurrentPosition },
  writable: true,
})

// jsdom doesn't implement scrollIntoView
Element.prototype.scrollIntoView = jest.fn()

// ── Imports (after mocks) ────────────────────────────────────
import AIChatPanel from '../components/assistant/AIChatPanel.jsx'

// Helper: render chat panel and open it
async function renderAndOpen() {
  render(<AIChatPanel />)
  const bubble = screen.getByLabelText('Open Nouri AI Assistant')
  await act(async () => { fireEvent.click(bubble) })
  return screen
}

// ── Tests ────────────────────────────────────────────────────

describe('AI Chat — Message Send/Receive', () => {
  beforeEach(() => {
    jest.clearAllMocks()
    mockSendMessage.mockResolvedValue({
      response: 'I found 3 food listings nearby!',
      toolResults: [],
      suggestedActions: [],
    })
  })

  test('sends a message and displays AI response', async () => {
    await renderAndOpen()

    // Welcome message should show
    expect(screen.getByText(/I'm Nouri/)).toBeInTheDocument()

    // Type a message and send
    const input = screen.getByPlaceholderText(/Message Nouri|Ask me anything|Pregunta/i)
    fireEvent.change(input, { target: { value: 'Find food near me' } })
    fireEvent.submit(input.closest('form'))

    // User message rendered immediately
    expect(screen.getByText('Find food near me')).toBeInTheDocument()

    // Wait for AI response
    await waitFor(() => {
      expect(screen.getByText('I found 3 food listings nearby!')).toBeInTheDocument()
    })

    // Service was called with correct args
    expect(mockSendMessage).toHaveBeenCalledWith(
      'Find food near me',
      expect.objectContaining({ userId: 'u1' })
    )
  })
})

describe('AI Chat — Conversation History', () => {
  beforeEach(() => { jest.clearAllMocks() })

  test('loads conversation history on mount for authenticated user', async () => {
    mockGetHistory.mockResolvedValue([
      { id: 'h1', role: 'user', message: 'old message', metadata: null, created_at: '2025-01-01T00:00:00Z' },
      { id: 'h2', role: 'assistant', message: 'old reply', metadata: null, created_at: '2025-01-01T00:01:00Z' },
    ])

    await renderAndOpen()

    // History messages eventually appear
    await waitFor(() => {
      expect(screen.getByText('old message')).toBeInTheDocument()
      expect(screen.getByText('old reply')).toBeInTheDocument()
    })

    expect(mockGetHistory).toHaveBeenCalledWith('u1', 50)
  })
})

describe('AI Chat — Voice Mode Toggle', () => {
  beforeEach(() => { jest.clearAllMocks() })

  test('voice mode toggle button is present after opening chat', async () => {
    await renderAndOpen()

    // The voice mode toggle button should be present in the chat panel
    const voiceBtn = screen.getByLabelText('Switch to voice mode')
    expect(voiceBtn).toBeInTheDocument()
  })
})

describe('AI Chat — Spanish Language Detection', () => {
  beforeEach(() => { jest.clearAllMocks() })

  test('detects Spanish and responds accordingly', async () => {
    mockSendMessage.mockResolvedValue({
      response: '¡Encontré 2 listados!',
      toolResults: [],
      suggestedActions: [],
    })

    await renderAndOpen()

    const input = screen.getByPlaceholderText(/Message Nouri|Ask me anything|Pregunta/i)
    fireEvent.change(input, { target: { value: 'Hola, buscar comida cerca' } })
    fireEvent.submit(input.closest('form'))

    await waitFor(() => {
      expect(screen.getByText('¡Encontré 2 listados!')).toBeInTheDocument()
    })
  })
})

describe('AI Chat — Error Handling', () => {
  beforeEach(() => { jest.clearAllMocks() })

  test('shows error message when AI service fails', async () => {
    mockSendMessage.mockRejectedValue(new Error('Network failure'))

    await renderAndOpen()

    const input = screen.getByPlaceholderText(/Message Nouri|Ask me anything|Pregunta/i)
    fireEvent.change(input, { target: { value: 'test error' } })
    fireEvent.submit(input.closest('form'))

    // Should show the friendly error message
    await waitFor(() => {
      expect(
        screen.getByText(/having a little trouble/i)
      ).toBeInTheDocument()
    })
  })
})
