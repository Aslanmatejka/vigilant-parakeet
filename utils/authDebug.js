// Add this to your authService.js file or create a new file
import supabase from './supabaseClient.js';

export async function checkSupabaseAuth() {
  try {
    // Get the current session
    const { data: { session }, error } = await supabase.auth.getSession();
    
    if (error) {
      console.error('Error checking auth session:', error.message);
      return { authenticated: false, error: error.message };
    }
    
    if (!session) {
      console.log('No active session found');
      return { authenticated: false };
    }
    
    // Check if the token is valid by making a simple request
    const { error: testError } = await supabase
      .from('users')
      .select('id')
      .limit(1);
    
    if (testError) {
      console.error('Auth token test failed:', testError.message);
      return { 
        authenticated: false, 
        session: session,
        error: testError.message 
      };
    }
    
    return { 
      authenticated: true, 
      user: session.user,
      session: session
    };
  } catch (error) {
    console.error('Authentication check failed:', error);
    return { authenticated: false, error: error.message };
  }
}

// Use this function to log detailed auth state for debugging
export async function debugAuthState() {
  const authState = await checkSupabaseAuth();
  console.log('===== Auth State Debug =====');
  console.log('Authenticated:', authState.authenticated);
  
  if (authState.user) {
    console.log('User ID:', authState.user.id);
    console.log('Email:', authState.user.email);
    console.log('Last Sign In:', authState.user.last_sign_in_at);
  } else {
    console.log('No user found in session');
  }
  
  if (authState.session) {
    console.log('Session expires at:', new Date(authState.session.expires_at * 1000).toLocaleString());
    console.log('Access Token (first 20 chars):', authState.session.access_token?.substring(0, 20) + '...');
  }
  
  if (authState.error) {
    console.log('Error:', authState.error);
  }
  
  console.log('============================');
  return authState;
}

// Helper to ensure authentication before making Supabase requests
export async function ensureAuthenticated() {
  const { data: { session } } = await supabase.auth.getSession();
  if (!session) {
    throw new Error('Not authenticated. Please sign in.');
  }
  return session;
}
