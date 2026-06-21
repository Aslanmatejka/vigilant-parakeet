import React, { createContext, useContext, useEffect, useMemo, useRef, useState } from 'react';
import authService from './authService.js';
import { geocodeAddress } from './geocoding';

const AuthContext = createContext({});

// Pre-bind singleton methods once so the context value identity is stable
// across renders and `useMemo` only needs to track real state changes.
const boundSignIn = authService.signIn.bind(authService);
const boundSignUp = authService.signUp.bind(authService);
const boundSignOut = authService.signOut.bind(authService);
const boundUpdateProfile = authService.updateProfile.bind(authService);
const boundUploadAvatar = authService.uploadAvatar.bind(authService);

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
  const inFlightRef = useRef(new Set());
  useEffect(() => {
    if (!user?.id || !user?.address) return;
    // Only backfill if coordinates are actually missing — don't overwrite
    // existing (possibly manually adjusted) coordinates.
    if (user?.latitude && user?.longitude) return;
    const addrKey = `${user.id}:${String(user.address).trim()}`;
    if (backfilledRef.current.get(user.id) === addrKey) return;
    // Guard against re-entry during an in-flight attempt for this address,
    // but DON'T mark it as backfilled — a transient failure should retry
    // on the next mount (or address change).
    if (inFlightRef.current.has(addrKey)) return;
    inFlightRef.current.add(addrKey);

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
        // Only record success — failures stay un-marked so they can retry.
        backfilledRef.current.set(user.id, addrKey);
      } catch (err) {
        console.debug('Address auto-geocode skipped:', err?.message);
      } finally {
        inFlightRef.current.delete(addrKey);
      }
    })();

    return () => { cancelled = true; };
  }, [user?.id, user?.address, user?.latitude, user?.longitude]);

  const value = useMemo(() => ({
    user,
    isAuthenticated,
    isAdmin,
    loading,
    initialized,
    signIn: boundSignIn,
    signUp: boundSignUp,
    signOut: boundSignOut,
    updateProfile: boundUpdateProfile,
    uploadAvatar: boundUploadAvatar,
  }), [user, isAuthenticated, isAdmin, loading, initialized]);

  return (
    <AuthContext.Provider value={value}>
      {children}
    </AuthContext.Provider>
  );
};

export default AuthContext;
