/**
 * Form voice guide opt-in — engine gates TTS on formVoiceGuideEnabled.
 */
import {
  clearGuideState,
  setNouriA11yPrefs,
  startFormGuide,
  syncGuideFromFormField,
  getNouriGuideState,
  replayGuide,
} from '../utils/nouriGuide/engine'

const speakMock = jest.fn()

class MockSpeechSynthesisUtterance {
  constructor(text) {
    this.text = text
    this.lang = ''
    this.rate = 1
    this.voice = null
    this.onstart = null
    this.onend = null
    this.onerror = null
  }
}

beforeEach(() => {
  clearGuideState()
  setNouriA11yPrefs({
    preferTextOverVoice: false,
    formVoiceGuideEnabled: false,
    simpleLanguage: false,
    alwaysShowCaptions: true,
    preferredLanguage: 'en',
  })
  speakMock.mockClear()
  global.SpeechSynthesisUtterance = MockSpeechSynthesisUtterance
  global.window.speechSynthesis = {
    cancel: jest.fn(),
    getVoices: () => [{ lang: 'en-US', name: 'Test' }],
    speak: speakMock,
    addEventListener: jest.fn(),
    removeEventListener: jest.fn(),
  }
})

describe('nouriGuide form voice opt-in', () => {
  it('does not speak on form welcome when formVoiceGuideEnabled is off', () => {
    startFormGuide(
      { formId: 'share-food', welcomeMessage: 'Welcome to share food', hints: {} },
      { lang: 'en' },
    )
    const s = getNouriGuideState()
    expect(s.source).toBe('form')
    expect(s.text).toContain('Welcome')
    expect(s.isSpeaking).toBe(false)
    expect(speakMock).not.toHaveBeenCalled()
  })

  it('speaks on form welcome when formVoiceGuideEnabled is on', () => {
    jest.useFakeTimers()
    setNouriA11yPrefs({ formVoiceGuideEnabled: true })
    startFormGuide(
      { formId: 'share-food', welcomeMessage: 'Welcome to share food', hints: {} },
      { lang: 'en' },
    )
    jest.runAllTimers()
    expect(speakMock).toHaveBeenCalled()
    jest.useRealTimers()
  })

  it('does not speak on field focus when formVoiceGuideEnabled is off', () => {
    syncGuideFromFormField(
      {
        formId: 'share-food',
        fieldName: 'title',
        label: 'Title',
        text: 'What food are you sharing?',
        hints: { title: 'What food are you sharing?' },
      },
      { lang: 'en' },
    )
    expect(getNouriGuideState().fieldName).toBe('title')
    expect(speakMock).not.toHaveBeenCalled()
  })

  it('speaks on field focus when formVoiceGuideEnabled is on', () => {
    jest.useFakeTimers()
    setNouriA11yPrefs({ formVoiceGuideEnabled: true })
    syncGuideFromFormField(
      {
        formId: 'share-food',
        fieldName: 'title',
        label: 'Title',
        text: 'What food are you sharing?',
        hints: { title: 'What food are you sharing?' },
      },
      { lang: 'en' },
    )
    jest.runAllTimers()
    expect(speakMock).toHaveBeenCalled()
    jest.useRealTimers()
  })

  it('blocks replay on forms when formVoiceGuideEnabled is off', () => {
    startFormGuide(
      { formId: 'share-food', welcomeMessage: 'Welcome', hints: {} },
      { lang: 'en' },
    )
    speakMock.mockClear()
    replayGuide({ lang: 'en' })
    expect(speakMock).not.toHaveBeenCalled()
  })

  it('respects preferTextOverVoice over formVoiceGuideEnabled', () => {
    setNouriA11yPrefs({ formVoiceGuideEnabled: true, preferTextOverVoice: true })
    startFormGuide(
      { formId: 'share-food', welcomeMessage: 'Welcome', hints: {} },
      { lang: 'en' },
    )
    expect(speakMock).not.toHaveBeenCalled()
  })
})
