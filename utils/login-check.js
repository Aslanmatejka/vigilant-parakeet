// This file helps debug authentication issues
// To use, import it in your component:
// import { checkLoginStatus } from '../utils/login-check';
// 
// Then call it in a useEffect:
// useEffect(() => {
//   checkLoginStatus();
// }, []);

import supabase from './supabaseClient';

export async function checkLoginStatus() {
  console.group('🔐 Authentication Check');
  
  try {
    // Check if we have a session
    const { data: { session }, error: sessionError } = await supabase.auth.getSession();
    
    if (sessionError) {
      console.error('❌ Session error:', sessionError.message);
      console.groupEnd();
      return false;
    }
    
    if (!session) {
      console.warn('⚠️ No active session found - user is NOT logged in');
      console.groupEnd();
      return false;
    }
    
    console.log('✅ User is logged in');
    console.log('📝 Session details:');
    console.log('  User ID:', session.user?.id);
    console.log('  Email:', session.user?.email);
    console.log('  Expires:', new Date(session.expires_at * 1000).toLocaleString());
    
    // Test the session with a simple request
    const { data: userData, error: userError } = await supabase
      .from('users')
      .select('is_admin')
      .eq('id', session.user.id)
      .single();
    
    if (userError) {
      console.error('❌ Auth verification failed:', userError.message);
      console.log('⚠️ You may need to update your RLS policies');
      console.groupEnd();
      return false;
    }
    
    console.log('✅ Authentication verified with database');
    console.log('👑 Admin status:', userData?.is_admin ? 'Yes' : 'No');
    console.groupEnd();
    return true;
  } catch (error) {
    console.error('❌ Authentication check failed:', error.message);
    console.groupEnd();
    return false;
  }
}

// Helper to log out the current user
export async function forceLogout() {
  try {
    const { error } = await supabase.auth.signOut();
    if (error) {
      console.error('❌ Logout failed:', error.message);
      return false;
    }
    console.log('✅ Successfully logged out');
    return true;
  } catch (error) {
    console.error('❌ Logout failed:', error.message);
    return false;
  }
}
