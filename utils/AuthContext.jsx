import React, { createContext, useContext, useEffect, useState } from 'react';
import authService from './authService.js';

const AuthContext = createContext({});

export const useAuthContext = () => {
  const context = useContext(AuthContext);
  if (!context) {
    throw new Error('useAuthContext must be used within an AuthProvider');
  }
  return context;
};

export const AuthProvider = ({ children }) => {
  const [user, setUser] = useState(null);
  const [isAuthenticated, setIsAuthenticated] = useState(false);
  const [isAdmin, setIsAdmin] = useState(false);
  const [loading, setLoading] = useState(true);
  const [initialized, setInitialized] = useState(false);

      useEffect(() => {
        let isMounted = true;
        
        const initAuth = async () => {
            try {
                // Wait for auth service to initialize
                await authService.init();
                
                if (isMounted) {
                    // Set initial state
                    setUser(authService.getCurrentUser());
                    setIsAuthenticated(authService.isUserAuthenticated());
                    setIsAdmin(authService.isUserAdmin());
                    setInitialized(true);
                }
            } catch (error) {
                console.error('Auth initialization error:', error);
            } finally {
                if (isMounted) {
                    setLoading(false);
                }
            }
        };

        initAuth();

        // Listen for auth state changes
        const unsubscribe = authService.addListener(({ user, isAuthenticated, isAdmin }) => {
            if (isMounted) {
                setUser(user);
                setIsAuthenticated(isAuthenticated);
                setIsAdmin(isAdmin);
            }
        });

        return () => {
            isMounted = false;
            unsubscribe();
        };
    }, []);

    const value = {
    user,
    isAuthenticated,
    isAdmin,
    loading,
    initialized,
    signIn: authService.signIn.bind(authService),
    signUp: authService.signUp.bind(authService),
    signOut: authService.signOut.bind(authService),
    updateProfile: authService.updateProfile.bind(authService),
    uploadAvatar: authService.uploadAvatar.bind(authService),
  };

  return (
    <AuthContext.Provider value={value}>
      {children}
    </AuthContext.Provider>
  );
};

export default AuthContext;
