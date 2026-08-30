import {
  DEFAULT_A11Y_SETTINGS,
  mergeAccessibilitySettings,
  buildAccessibilityProfilePayload,
} from '../utils/accessibilityStorage'

describe('accessibilityStorage', () => {
  test('mergeAccessibilitySettings applies defaults', () => {
    const merged = mergeAccessibilitySettings({ largeText: true })
    expect(merged.largeText).toBe(true)
    expect(merged.preferredLanguage).toBe('en')
    expect(merged.smsGuideEnabled).toBe(false)
    expect(merged.formVoiceGuideEnabled).toBe(false)
  })

  test('mergeAccessibilitySettings normalizes unknown language', () => {
    const merged = mergeAccessibilitySettings({ preferredLanguage: 'xx' })
    expect(merged.preferredLanguage).toBe('en')
  })

  test('buildAccessibilityProfilePayload mirrors settings', () => {
    const payload = buildAccessibilityProfilePayload({
      ...DEFAULT_A11Y_SETTINGS,
      simpleLanguage: true,
      preferredLanguage: 'vi',
    })
    expect(payload.simpleLanguage).toBe(true)
    expect(payload.preferredLanguage).toBe('vi')
    expect(payload.easyMode).toBe(false)
    expect(payload.formVoiceGuideEnabled).toBe(false)
  })

  test('buildAccessibilityProfilePayload includes formVoiceGuideEnabled when on', () => {
    const payload = buildAccessibilityProfilePayload({
      ...DEFAULT_A11Y_SETTINGS,
      formVoiceGuideEnabled: true,
    })
    expect(payload.formVoiceGuideEnabled).toBe(true)
  })
})
