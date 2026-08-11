import { safeInternalRedirect } from '../utils/safeRedirect';

describe('safeInternalRedirect', () => {
  test('allows internal paths', () => {
    expect(safeInternalRedirect('/find')).toBe('/find');
    expect(safeInternalRedirect('/admin/listing-approvals')).toBe('/admin/listing-approvals');
    expect(safeInternalRedirect('/claim?food=1')).toBe('/claim?food=1');
  });

  test('rejects external and protocol-relative URLs', () => {
    expect(safeInternalRedirect('//evil.com')).toBe('/');
    expect(safeInternalRedirect('https://evil.com')).toBe('/');
    expect(safeInternalRedirect('javascript:alert(1)')).toBe('/');
  });

  test('falls back when empty', () => {
    expect(safeInternalRedirect(null)).toBe('/');
    expect(safeInternalRedirect('')).toBe('/');
  });
});
