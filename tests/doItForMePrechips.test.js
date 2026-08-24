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
    expectChips('How many loaves?', ['1', '3', '5'], ['Still sealed'])
  })

  test('community', () => {
    expectChips(
      'Your profile is linked to Ruby Bridges Elementary CC. Use that one?',
      ['Ruby', 'Different community'],
      ['Yes, post it'],
    )
  })

  test('expiry', () => {
    expectChips('When does it expire?', ['Tomorrow'], ['Still sealed'])
  })

  test('description', () => {
    expectChips(
      'Please add a short description for recipients.',
      ['Still sealed'],
      ['Tomorrow', 'Attach a photo'],
    )
    expectChips('Description?', ['Still sealed'], ['Tomorrow'])
  })

  test('photo', () => {
    expectChips(
      'Please attach a photo of the food — required before I can post.',
      ['Attach a photo'],
      ['Still sealed', 'skip'],
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
      { label: 'Still sealed', message: 'Still sealed' },
      { label: 'Homemade, refrigerated', message: 'Homemade, refrigerated' },
      { label: 'Assorted leftovers', message: 'Assorted leftovers' },
    ]
    const resolved = resolveInputChips(backend, 'en', null, {
      allowLazy: false,
      responseText: 'Description?',
    })
    expect(labels(resolved).some((l) => /sealed|homemade/i.test(l))).toBe(true)
  })

  test('description before photo narration', () => {
    expectChips(
      'Please add a short description for recipients. After that I will need a photo.',
      ['Still sealed'],
      ['Attach a photo'],
    )
  })

  test('description beats how many in same sentence', () => {
    expectChips(
      'Please add a short description — no need to say how many portions.',
      ['Still sealed'],
      ['1', '3', '5'],
    )
  })

  test('stale allergen chips replaced on expiry turn', () => {
    const stale = [
      { label: 'No allergens', message: 'No allergens' },
      { label: 'Dairy', message: 'Dairy' },
      { label: 'Nuts', message: 'Nuts' },
    ]
    const resolved = resolveInputChips(stale, 'en', null, {
      allowLazy: false,
      responseText: 'When does it expire?',
    })
    expect(labels(resolved).some((l) => /tomorrow/i.test(l))).toBe(true)
    expect(labels(resolved).some((l) => /allergen|dairy|nuts/i.test(l))).toBe(false)
  })

  test('stale food chips replaced on allergen turn', () => {
    const stale = [
      { label: '5 apples', message: '5 apples' },
      { label: '2 loaves of bread', message: '2 loaves of bread' },
    ]
    const resolved = resolveInputChips(stale, 'en', null, {
      allowLazy: false,
      responseText: 'Does this contain nuts, dairy, eggs, soy, or wheat?',
    })
    expect(labels(resolved).some((l) => /allergen|gluten|dairy|nuts/i.test(l))).toBe(true)
    expect(labels(resolved).some((l) => /apples|loaves/i.test(l))).toBe(false)
  })

  test('stale post chips replaced on food ask', () => {
    const stale = [
      { label: 'Yes, post it', message: 'Yes, post it' },
      { label: 'Wait, edit it', message: 'Wait, edit it' },
      { label: 'Cancel', message: 'Cancel' },
    ]
    const resolved = resolveInputChips(stale, 'en', null, {
      allowLazy: false,
      responseText: 'What food do you want to share, and how much do you have?',
    })
    expect(labels(resolved).some((l) => /apples|bread|vegetable/i.test(l))).toBe(true)
    expect(labels(resolved).some((l) => /yes, post it/i.test(l))).toBe(false)
  })

  test('stale fork chips stripped on qty ask', () => {
    const stale = [
      { label: 'Open the form', message: 'Open the form' },
      { label: 'Do it for me', message: 'Do it for me' },
      { label: 'Guide me step by step', message: 'Guide me step by step' },
    ]
    const resolved = resolveInputChips(stale, 'en', null, {
      allowLazy: false,
      responseText: 'How many would you like to share?',
    })
    expect(labels(resolved).some((l) => /^(1|2|3|5|10)$/.test(l))).toBe(true)
    expect(labels(resolved).some((l) => /do it for me|open the form/i.test(l))).toBe(false)
  })

  test('address look good is not post confirm', () => {
    const infer = inferChipsFromResponse(
      'Should I use your profile address 1423 Park St? Does that look good?',
    )
    const j = joined(infer)
    expect(j).not.toContain('yes, post it')
    expect(
      /saved address|different address|don'?t have|use that/i.test(j),
    ).toBe(true)
  })
})
