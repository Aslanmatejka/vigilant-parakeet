/**
 * Tests for sign-out functionality.
 * Verifies that:
 * 1. authService.signOut() clears state and localStorage
 * 2. useAuth listener updates synchronously (no setTimeout delay)
 * 3. Header handleLogout does NOT clear localStorage before signOut
 */

const fs = require('fs');
const path = require('path');

beforeEach(() => {
  localStorage.clear();
  jest.clearAllMocks();
});

describe('authService.signOut implementation', () => {
  const source = fs.readFileSync(
    path.resolve(__dirname, '../utils/authService.js'),
    'utf-8'
  );

  test('signOut calls supabase.auth.signOut before clearUser', () => {
    // In signOut(), supabase.auth.signOut() must come before this.clearUser()
    const signOutMethod = source.match(/async signOut\(\)[\s\S]*?return \{ success: true \}/);
    expect(signOutMethod).toBeTruthy();

    const body = signOutMethod[0];
    const supabaseSignOutPos = body.indexOf('supabase.auth.signOut()');
    const clearUserPos = body.indexOf('this.clearUser()');

    expect(supabaseSignOutPos).toBeGreaterThan(-1);
    expect(clearUserPos).toBeGreaterThan(-1);
    // supabase.auth.signOut() must come BEFORE clearUser()
    expect(supabaseSignOutPos).toBeLessThan(clearUserPos);
  });

  test('clearUser removes all expected localStorage keys', () => {
    // Match the clearUser method body up to the closing brace
    const clearUserMethod = source.match(/clearUser\(\) \{[\s\S]*?this\.notifyListeners\(\)[\s\S]*?^\s*\}/m);
    expect(clearUserMethod).toBeTruthy();

    const body = clearUserMethod[0];
    expect(body).toContain('localStorage.removeItem');
    expect(body).toContain('userAuthenticated');
    expect(body).toContain('currentUser');
    expect(body).toContain('adminAuthenticated');
    expect(body).toContain('adminUser');
  });

  test('signOut also removes Supabase auth token from localStorage', () => {
    // Match the full signOut method
    const signOutMethod = source.match(/async signOut\(\) \{[\s\S]*?return \{ success: true \}[\s\S]*?^\s*\}/m);
    expect(signOutMethod).toBeTruthy();
    expect(signOutMethod[0]).toContain('localStorage.removeItem(SUPABASE_AUTH_KEY)');
  });

  test('clearUser calls notifyListeners to propagate state change', () => {
    const clearUserMethod = source.match(/clearUser\(\)[\s\S]*?notifyListeners\(\)/);
    expect(clearUserMethod).toBeTruthy();
    expect(clearUserMethod[0]).toContain('this.notifyListeners()');
  });
});

describe('useAuth listener (no setTimeout)', () => {
  test('useSupabase listener callback does not use setTimeout', async () => {
    // Read the source and verify no setTimeout in listener
    const fs = require('fs');
    const path = require('path');
    const source = fs.readFileSync(
      path.resolve(__dirname, '../utils/hooks/useSupabase.js'),
      'utf-8'
    );

    // Find the addListener callback section
    const listenerMatch = source.match(/addListener\(\([\s\S]*?\)\)/);
    expect(listenerMatch).toBeTruthy();

    // The listener should NOT contain setTimeout
    expect(listenerMatch[0]).not.toContain('setTimeout');
  });
});

describe('Header handleLogout (no premature localStorage clear)', () => {
  test('Header does not clear localStorage before calling signOut', () => {
    const fs = require('fs');
    const path = require('path');
    const source = fs.readFileSync(
      path.resolve(__dirname, '../components/common/Header.jsx'),
      'utf-8'
    );

    // Find the handleLogout function in the try block (before signOut call)
    const handleLogoutMatch = source.match(/const handleLogout[\s\S]*?await signOut\(\)/);
    expect(handleLogoutMatch).toBeTruthy();

    const beforeSignOut = handleLogoutMatch[0];

    // Before signOut(), there should be NO localStorage.removeItem calls
    expect(beforeSignOut).not.toContain('localStorage.removeItem');
  });
});

describe('Header uses useAuthContext (not useAuth hook)', () => {
  test('Header imports useAuthContext from AuthContext', () => {
    const fs = require('fs');
    const path = require('path');
    const source = fs.readFileSync(
      path.resolve(__dirname, '../components/common/Header.jsx'),
      'utf-8'
    );

    expect(source).toContain('useAuthContext');
    expect(source).not.toContain("from \"../../utils/hooks/useSupabase\"");
  });
});

describe('AdminLayout uses authService signOut (not supabase directly)', () => {
  test('AdminLayout does not call supabase.auth.signOut() directly', () => {
    const fs = require('fs');
    const path = require('path');
    const source = fs.readFileSync(
      path.resolve(__dirname, '../pages/admin/AdminLayout.jsx'),
      'utf-8'
    );

    // Should NOT contain direct supabase.auth.signOut() call
    expect(source).not.toContain('supabase.auth.signOut()');
    // Should use signOut from context
    expect(source).toContain('await signOut()');
  });

  test('AdminLayout does not use setTimeout for navigation after logout', () => {
    const fs = require('fs');
    const path = require('path');
    const source = fs.readFileSync(
      path.resolve(__dirname, '../pages/admin/AdminLayout.jsx'),
      'utf-8'
    );

    const handleLogoutMatch = source.match(/const handleLogout[\s\S]*?navigate\(/);
    expect(handleLogoutMatch).toBeTruthy();

    // Should NOT use setTimeout hack
    expect(handleLogoutMatch[0]).not.toContain('setTimeout');
  });

  test('AdminLayout does not manually clear localStorage in handleLogout', () => {
    const fs = require('fs');
    const path = require('path');
    const source = fs.readFileSync(
      path.resolve(__dirname, '../pages/admin/AdminLayout.jsx'),
      'utf-8'
    );

    const handleLogoutMatch = source.match(/const handleLogout[\s\S]*?navigate\(/);
    expect(handleLogoutMatch).toBeTruthy();
    expect(handleLogoutMatch[0]).not.toContain('localStorage.removeItem');
  });
});
