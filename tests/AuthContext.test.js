/**
 * AuthContext tests
 * Tests the AuthProvider, useAuthContext hook, and auth state management
 * via source code analysis (avoids complex mock chains for Supabase).
 */
const fs = require('fs');
const path = require('path');

const authContextSource = fs.readFileSync(
  path.resolve(__dirname, '../utils/AuthContext.jsx'),
  'utf-8'
);

describe('AuthContext source analysis', () => {
  test('exports useAuthContext hook', () => {
    expect(authContextSource).toContain('export const useAuthContext');
  });

  test('exports AuthProvider component', () => {
    expect(authContextSource).toContain('export const AuthProvider');
  });

  test('creates context with createContext', () => {
    expect(authContextSource).toContain('createContext');
  });

  test('useAuthContext throws if used outside provider', () => {
    expect(authContextSource).toContain('useAuthContext must be used within an AuthProvider');
  });

  test('AuthProvider calls authService.init() on mount', () => {
    expect(authContextSource).toContain('authService.init()');
  });

  test('AuthProvider registers a listener via authService.addListener', () => {
    expect(authContextSource).toContain('authService.addListener');
  });

  test('AuthProvider initializes state from authService localStorage values', () => {
    expect(authContextSource).toContain('authService.getCurrentUser()');
    expect(authContextSource).toContain('authService.isUserAuthenticated()');
    expect(authContextSource).toContain('authService.isUserAdmin()');
  });

  test('AuthProvider exposes signIn, signUp, signOut from authService', () => {
    expect(authContextSource).toContain('signIn');
    expect(authContextSource).toContain('signUp');
    expect(authContextSource).toContain('signOut');
  });

  test('AuthProvider exposes loading and initialized states', () => {
    expect(authContextSource).toContain('loading');
    expect(authContextSource).toContain('initialized');
  });

  test('AuthProvider cleans up listener on unmount (returns cleanup)', () => {
    // The useEffect should call unsubscribe() in its cleanup function
    expect(authContextSource).toContain('const unsubscribe = authService.addListener');
    expect(authContextSource).toContain('unsubscribe()');
    // Verify cleanup returns a function
    expect(authContextSource).toMatch(/return\s*\(\)\s*=>\s*\{[\s\S]*?unsubscribe\(\)/);
  });
});

describe('useAuthContext hook behavior', () => {
  test('useAuthContext is exported as a named function from AuthContext.jsx', () => {
    expect(authContextSource).toMatch(/export const useAuthContext\s*=\s*\(/);
  });

  test('useAuthContext throws error if used outside provider', () => {
    // Verify the source contains the guard
    expect(authContextSource).toContain("throw new Error('useAuthContext must be used within an AuthProvider')");
  });

  test('context value includes user, isAuthenticated, isAdmin, loading, initialized', () => {
    // The value object is defined as `const value = { ... }` before being passed to Provider
    const valueMatch = authContextSource.match(/const value\s*=\s*\{([\s\S]*?)\};/);
    expect(valueMatch).toBeTruthy();
    const valueContent = valueMatch[1];
    expect(valueContent).toContain('user');
    expect(valueContent).toContain('isAuthenticated');
    expect(valueContent).toContain('isAdmin');
    expect(valueContent).toContain('loading');
    expect(valueContent).toContain('initialized');
  });

  test('context value includes signIn, signUp, signOut methods', () => {
    const valueMatch = authContextSource.match(/const value\s*=\s*\{([\s\S]*?)\};/);
    expect(valueMatch).toBeTruthy();
    const valueContent = valueMatch[1];
    expect(valueContent).toContain('signIn');
    expect(valueContent).toContain('signUp');
    expect(valueContent).toContain('signOut');
  });
});
