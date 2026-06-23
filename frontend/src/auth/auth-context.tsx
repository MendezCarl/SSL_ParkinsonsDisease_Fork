import { ReactNode, createContext, useContext, useEffect, useMemo, useState } from 'react';
import apiService from '@/services/api';
import {
  AuthSession,
  AuthUser,
  clearStoredAuthSession,
  getStoredAuthSession,
  setStoredAuthSession,
} from './auth-session';

type AuthContextValue = {
  user: AuthUser | null;
  token: string | null;
  isAuthenticated: boolean;
  isLoading: boolean;
  login: (username: string, password: string) => Promise<{ success: boolean; error?: string }>;
  logout: () => void;
  refreshUser: () => Promise<void>;
};

const AuthContext = createContext<AuthContextValue | undefined>(undefined);

export const AuthProvider = ({ children }: { children: ReactNode }) => {
  const [session, setSession] = useState<AuthSession | null>(() => getStoredAuthSession());
  const [isLoading, setIsLoading] = useState(true);

  const logout = () => {
    clearStoredAuthSession();
    setSession(null);
  };

  const refreshUser = async () => {
    const stored = getStoredAuthSession();
    if (!stored?.token) {
      setIsLoading(false);
      return;
    }

    const response = await apiService.getCurrentUser();
    if (response.success && response.data) {
      const nextSession = { token: stored.token, user: response.data };
      setStoredAuthSession(nextSession);
      setSession(nextSession);
    } else {
      logout();
    }
    setIsLoading(false);
  };

  useEffect(() => {
    refreshUser();
  }, []);

  const login = async (username: string, password: string) => {
    const loginResponse = await apiService.login(username, password);
    if (!loginResponse.success || !loginResponse.data) {
      return { success: false, error: loginResponse.error || 'Login failed' };
    }

    const userResponse = await apiService.getCurrentUser(loginResponse.data.accessToken);
    if (!userResponse.success || !userResponse.data) {
      clearStoredAuthSession();
      return { success: false, error: userResponse.error || 'Failed to load user profile' };
    }

    const nextSession = {
      token: loginResponse.data.accessToken,
      user: userResponse.data,
    };
    setStoredAuthSession(nextSession);
    setSession(nextSession);
    return { success: true };
  };

  const value = useMemo<AuthContextValue>(
    () => ({
      user: session?.user ?? null,
      token: session?.token ?? null,
      isAuthenticated: !!session?.token,
      isLoading,
      login,
      logout,
      refreshUser,
    }),
    [session, isLoading]
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
};

export const useAuth = () => {
  const context = useContext(AuthContext);
  if (!context) {
    throw new Error('useAuth must be used within an AuthProvider');
  }
  return context;
};
