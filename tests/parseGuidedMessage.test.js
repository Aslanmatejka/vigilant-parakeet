import {
  parseGuidedStepHeader,
  stripGuidedHeader,
  simplifyGuideText,
  inferGuidedFieldFromText,
} from '../utils/nouriGuide/parseGuidedMessage'

describe('parseGuidedMessage', () => {
  test('parses English guided header', () => {
    const msg = 'GUIDED — STEP 2 of 5 (Share food) — Donor info\nEnter your name.'
    const parsed = parseGuidedStepHeader(msg)
    expect(parsed).not.toBeNull()
    expect(parsed.stepIndex).toBe(1)
    expect(parsed.stepTotal).toBe(5)
    expect(parsed.goalKey).toBe('share-food')
    expect(parsed.section).toBe('Donor info')
  })

  test('parses field token for highlight', () => {
    const msg = 'GUIDED — STEP 3 of 16 (SHARE FOOD) — Donor type [field:donor_type]:\nTap Donor Type.'
    const parsed = parseGuidedStepHeader(msg)
    expect(parsed?.fieldName).toBe('donor_type')
    expect(parsed?.stepIndex).toBe(2)
    expect(parsed?.section).toBe('Donor type')
  })

  test('infers field from headerless guided coaching', () => {
    const inferred = inferGuidedFieldFromText(
      "You got it! Tap City and type your city. Example: Alameda. Say done.",
      'share-food',
    )
    expect(inferred?.fieldName).toBe('donor_city')
    expect(inferred?.goalKey).toBe('share-food')
  })

  test('parses Spanish guided header', () => {
    const msg = 'GUIADO — PASO 1 de 3 (Buscar comida) — Búsqueda\nEscribe tu código postal.'
    const parsed = parseGuidedStepHeader(msg)
    expect(parsed?.goalKey).toBe('find-food')
    expect(parsed?.stepIndex).toBe(0)
  })

  test('stripGuidedHeader removes first line', () => {
    const msg = 'GUIDED — STEP 1 of 2 (Login) — Email\nType your email.'
    expect(stripGuidedHeader(msg)).toBe('Type your email.')
  })

  test('simplifyGuideText shortens when simple language on', () => {
    const long = 'One. Two. Three. Four. Five. Six.'
    const simplified = simplifyGuideText(long, true)
    expect(simplified.split('.').length).toBeLessThanOrEqual(5)
  })
})
