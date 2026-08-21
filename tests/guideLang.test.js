import { normalizeGuideLang, resolveGuideLang, ttsLangTag } from '../utils/guideLang'

describe('guideLang', () => {
  test('normalizeGuideLang maps variants', () => {
    expect(normalizeGuideLang('es-MX')).toBe('es')
    expect(normalizeGuideLang('fr-CA')).toBe('fr')
    expect(normalizeGuideLang('vi')).toBe('vi')
    expect(normalizeGuideLang('zh-CN')).toBe('zh')
    expect(normalizeGuideLang('unknown')).toBe('en')
  })

  test('resolveGuideLang prefers override then settings', () => {
    expect(resolveGuideLang('fr', 'en', 'en')).toBe('fr')
    expect(resolveGuideLang(null, 'vi', 'en')).toBe('vi')
    expect(resolveGuideLang(null, null, 'es')).toBe('es')
  })

  test('ttsLangTag returns BCP-47 tags', () => {
    expect(ttsLangTag('vi')).toBe('vi-VN')
    expect(ttsLangTag('zh')).toBe('zh-CN')
  })
})
