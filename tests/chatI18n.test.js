import {
  t,
  chatErrorMessage,
  getWelcomeCategories,
  getSuggestions,
  pickInitialChatLanguage,
  languageSwitchPrompt,
  welcomeGreeting,
  CHAT_UI_LANGUAGES,
} from '../utils/chatI18n'

describe('chatI18n', () => {
  test('supports five UI languages', () => {
    expect(CHAT_UI_LANGUAGES).toEqual(['en', 'es', 'fr', 'vi', 'zh'])
  })

  test('welcome categories for French', () => {
    const cats = getWelcomeCategories('fr')
    expect(cats.length).toBeGreaterThan(0)
    expect(cats[0].title).toMatch(/Pas sûr/i)
  })

  test('error messages localized', () => {
    expect(chatErrorMessage('timeout', 'vi')).toMatch(/thời gian/i)
    expect(chatErrorMessage('timeout', 'zh')).toMatch(/时间/)
  })

  test('language switch prompts', () => {
    expect(languageSwitchPrompt('fr')).toMatch(/français/i)
    expect(languageSwitchPrompt('zh')).toMatch(/中文/)
  })

  test('pickInitialChatLanguage honors preferred language', () => {
    expect(pickInitialChatLanguage(null, 'vi')).toBe('vi')
  })

  test('welcome greeting uses language', () => {
    expect(welcomeGreeting('zh', 'Sam')).toBe('你好，Sam！')
  })

  test('UI strings via t()', () => {
    expect(t('fr', 'retry')).toBe('Réessayer')
    expect(getSuggestions('vi').length).toBeGreaterThan(0)
  })
})
