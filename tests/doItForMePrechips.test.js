import { inferChipsFromResponse } from '../utils/inferSuggestionChips.js'
import { resolveInputChips } from '../utils/suggestionChips.js'

function labels(chips) {
  return chips.map((c) => c.label)
}

function joined(chips) {
  return labels(chips).join(' ').toLowerCase()
}

function expectChips(text, need, forbid = []) {
  const infer = inferChipsFromResponse(text)
  const j = joined(infer)
  expect(infer.length).toBeGreaterThan(0)
  expect(need.some((n) => j.includes(n.toLowerCase()))).toBe(true)
  forbid.forEach((f) => expect(j).not.toContain(f.toLowerCase()))
}

describe('Do-it-for-me prechips match each AI response', () => {
  test('food + qty', () => {
    expectChips(
      'What food do you want to share, and how much do you have?',
      ['5 apples'],
      ['Tomorrow', 'Still sealed'],
    )
  })

  test('quantity', () => {
    expectChips('How many loaves?', ['Just 1', '3 of them'], ['Still sealed'])
  })

  test('community', () => {
    expectChips(
      'Your profile is linked to Ruby Bridges Elementary CC. Use that one?',
      ['Ruby', 'different school'],
      ['Yes, post it'],
    )
  })

  test('expiry', () => {
    expectChips('When does it expire?', ['Tomorrow'], ['Still sealed'])
  })

  test('description', () => {
    expectChips(
      'Please add a short description for recipients.',
      ['sealed'],
      ['Tomorrow', 'Attach a photo'],
    )
    expectChips('Description?', ['sealed'], ['Tomorrow'])
  })

  test('photo', () => {
    expectChips(
      'Please attach a photo of the food — required before I can post.',
      ['attach a photo'],
      ['sealed', 'skip'],
    )
  })

  test('post confirm', () => {
    expectChips(
      'Ready to post 3 loaves under Alameda Unified, with photo. Shall I post it?',
      ['Yes, post it'],
      ['Attach a photo', 'No allergen'],
    )
  })

  test('post confirm with allergen recap does not show allergen chips', () => {
    expectChips(
      'Ready to post — no allergens noted. Does this look right?',
      ['Yes, post it'],
      ['No allergen', 'Still sealed'],
    )
  })

  test('post confirm without photo nudges attach', () => {
    expectChips(
      'Ready to post: 100 boxes under Alameda Unified. Shall I post these now?',
      ['Attach a photo'],
      ['Yes, post it'],
    )
  })

  test('resolveInputChips replaces stale qty chips on expiry turn', () => {
    const stale = [{ label: '1', message: '1' }, { label: '3', message: '3' }, { label: '5', message: '5' }]
    const resolved = resolveInputChips(stale, 'en', null, {
      allowLazy: false,
      responseText: 'When does it expire?',
    })
    expect(labels(resolved).some((l) => /tomorrow/i.test(l))).toBe(true)
    expect(labels(resolved).every((l) => /^[135]|10$/.test(l))).toBe(false)
  })

  test('resolveInputChips keeps description chips on description ask', () => {
    const backend = [
      { label: 'Still sealed in the original packaging', message: 'Still sealed in the original packaging' },
      { label: 'Homemade and kept refrigerated', message: 'Homemade and kept refrigerated' },
      { label: 'Assorted leftovers in containers', message: 'Assorted leftovers in containers' },
    ]
    const resolved = resolveInputChips(backend, 'en', null, {
      allowLazy: false,
      responseText: 'Description?',
    })
    expect(labels(resolved).some((l) => /sealed|homemade/i.test(l))).toBe(true)
  })
})
