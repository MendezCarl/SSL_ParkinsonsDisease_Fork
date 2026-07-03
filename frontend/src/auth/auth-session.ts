export interface AuthUser {
  username: string;
  fullName: string;
  email?: string | null;
  location: string;
  title: string;
  speciality: string;
}

export interface AuthSession {
  token: string;
  user: AuthUser;
}

const AUTH_SESSION_KEY = 'auth-session';

const isBrowser = typeof window !== 'undefined';

export const getStoredAuthSession = (): AuthSession | null => {
  if (!isBrowser) return null;

  const raw = window.localStorage.getItem(AUTH_SESSION_KEY);
  if (!raw) return null;

  try {
    return JSON.parse(raw) as AuthSession;
  } catch {
    window.localStorage.removeItem(AUTH_SESSION_KEY);
    return null;
  }
};

export const getStoredAuthToken = (): string | null => {
  return getStoredAuthSession()?.token ?? null;
};

export const setStoredAuthSession = (session: AuthSession): void => {
  if (!isBrowser) return;
  window.localStorage.setItem(AUTH_SESSION_KEY, JSON.stringify(session));
};

export const clearStoredAuthSession = (): void => {
  if (!isBrowser) return;
  window.localStorage.removeItem(AUTH_SESSION_KEY);
};
