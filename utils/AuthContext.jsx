import React, { createContext, useContext, useEffect, useRef, useState } from 'react';
import authService from './authService.js';
import { geocodeAddress } from './geocoding';

const AuthContext = createContext({});

export const useAuthContext = () => {
  const context = useContext(AuthContext);
  if (!context) {
    throw new Error('useAuthContext must be used within an AuthProvider');
  }
  return context;
};

export const AuthProvider = ({ children }) => {
  // Initialize state from authService's localStorage-restored values
  // This prevents a flash where isAuthenticated=false before init() completes
  const [user, setUser] = useState(() => authService.getCurrentUser());
  const [isAuthenticated, setIsAuthenticated] = useState(() => authService.isUserAuthenticated());
  const [isAdmin, setIsAdmin] = useState(() => authService.isUserAdmin());
  const [loading, setLoading] = useState(true);
  const [initialized, setInitialized] = useState(false);

  useEffect(() => {
    let isMounted = true;

    const initAuth = async () => {
      try {
        // Wait for auth service to initialize (idempotent - only runs once)
        await authService.init();

        if (isMounted) {
          // Sync React state with authService after init completes
          setUser(authService.getCurrentUser());
          setIsAuthenticated(authService.isUserAuthenticated());
          setIsAdmin(authService.isUserAdmin());
        }
      } catch (error) {
        console.error('Auth initialization error:', error);
      } finally {
        if (isMounted) {
          setInitialized(true);
          setLoading(false);
        }
      }
    };

    initAuth();

    // Listen for auth state changes (login, logout, token refresh)
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

  // Self-heal: if the user has an address but no geocoded coords (e.g. saved
  // before geocoding was added), backfill them silently exactly once per
  // session so the map / AI distance features have a fallback location.
  const backfilledRef = useRef(new Map());
  useEffect(() => {
    if (!user?.id || !user?.address) return;
    const addrKey = `${user.id}:${String(user.address).trim()}`;
    if (backfilledRef.current.get(user.id) === addrKey) return;
    backfilledRef.current.set(user.id, addrKey);

    let cancelled = false;
    (async () => {
      try {
        const coords = await geocodeAddress(user.address);
        if (cancelled || !coords) return;
        await authService.updateProfile({
          latitude: coords.latitude,
          longitude: coords.longitude,
          address_geocoded_at: new Date().toISOString(),
        });
      } catch (err) {
        console.debug('Address auto-geocode skipped:', err?.message);
      }
    })();

    return () => { cancelled = true; };
  }, [user?.id, user?.address, user?.latitude, user?.longitude]);

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
