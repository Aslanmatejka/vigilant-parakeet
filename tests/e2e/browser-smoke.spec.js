// @ts-check
import { test, expect } from '@playwright/test'

test.describe('static routes load without crashing', () => {
  test('login page renders email field', async ({ page }) => {
    const errors = []
    page.on('pageerror', (err) => errors.push(err.message))
    await page.goto('/login')
    await expect(page.locator('input[name="email"], input[type="email"]').first()).toBeVisible()
    expect(errors).toEqual([])
  })

  test('signup page renders', async ({ page }) => {
    const errors = []
    page.on('pageerror', (err) => errors.push(err.message))
    await page.goto('/signup')
    await expect(page.locator('input[name="email"], input[type="email"]').first()).toBeVisible()
    expect(errors).toEqual([])
  })

  test('how-it-works page renders content', async ({ page }) => {
    const errors = []
    page.on('pageerror', (err) => errors.push(err.message))
    await page.goto('/how-it-works')
    await expect(page.locator('body')).toContainText(/how|food|share|community/i)
    expect(errors).toEqual([])
  })

  test('find-food route loads shell', async ({ page }) => {
    const errors = []
    page.on('pageerror', (err) => errors.push(err.message))
    await page.goto('/find-food')
    await page.waitForLoadState('networkidle')
    await expect(page.locator('body')).toBeVisible()
    expect(errors).toEqual([])
  })
})
