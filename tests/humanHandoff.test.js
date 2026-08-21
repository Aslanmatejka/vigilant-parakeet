import {
  getGuideFailureCount,
  recordGuideFailure,
  recordGuideSuccess,
  shouldSuggestHumanHandoff,
  HUMAN_HANDOFF_THRESHOLD,
} from '../utils/nouriGuide/humanHandoff'

describe('humanHandoff', () => {
  beforeEach(() => {
    sessionStorage.clear()
  })

  test('increments failures and suggests handoff at threshold', () => {
    expect(getGuideFailureCount()).toBe(0)
    for (let i = 0; i < HUMAN_HANDOFF_THRESHOLD - 1; i += 1) {
      recordGuideFailure('test')
    }
    expect(shouldSuggestHumanHandoff()).toBe(false)
    recordGuideFailure('test')
    expect(shouldSuggestHumanHandoff()).toBe(true)
  })

  test('recordGuideSuccess resets counter', () => {
    recordGuideFailure('x')
    recordGuideFailure('x')
    recordGuideSuccess()
    expect(getGuideFailureCount()).toBe(0)
    expect(shouldSuggestHumanHandoff()).toBe(false)
  })
})
