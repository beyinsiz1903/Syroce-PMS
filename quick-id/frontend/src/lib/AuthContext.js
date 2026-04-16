import { createContext, useContext, useState, useEffect, useCallback, useRef } from 'react';

const AuthContext = createContext(null);

// JWT token'dan expiry süresini çıkar
function getTokenExpiry(token) {
  if (!token) return null;
  try {
    const payload = JSON.parse(atob(token.split('.')[1]));
    return payload.exp ? payload.exp * 1000 : null; // ms cinsinden
  } catch {
    return null;
  }
}

const SESSION_WARNING_MINUTES = 5; // Son 5 dakikada uyarı göster

export function AuthProvider({ children }) {
  const [user, setUser] = useState(() => {
    try {
      const stored = localStorage.getItem('quickid_user');
      return stored ? JSON.parse(stored) : null;
    } catch { return null; }
  });
  const [token, setToken] = useState(() => localStorage.getItem('quickid_token'));
  const [loading, setLoading] = useState(false);
  const [sessionExpiry, setSessionExpiry] = useState(null);
  const [sessionWarning, setSessionWarning] = useState(false);
  const [sessionRemainingMinutes, setSessionRemainingMinutes] = useState(null);
  const timerRef = useRef(null);

  const login = useCallback((tokenStr, userData) => {
    localStorage.setItem('quickid_token', tokenStr);
    localStorage.setItem('quickid_user', JSON.stringify(userData));
    setToken(tokenStr);
    setUser(userData);
    setSessionWarning(false);

    const expiry = getTokenExpiry(tokenStr);
    setSessionExpiry(expiry);
  }, []);

  const logout = useCallback(() => {
    localStorage.removeItem('quickid_token');
    localStorage.removeItem('quickid_user');
    setToken(null);
    setUser(null);
    setSessionExpiry(null);
    setSessionWarning(false);
    setSessionRemainingMinutes(null);
    if (timerRef.current) clearInterval(timerRef.current);
  }, []);

  const extendSession = useCallback(() => {
    // Token yenileme yapılamaz (JWT stateless), sadece uyarıyı kapat
    setSessionWarning(false);
  }, []);

  // Oturum süresini kontrol et
  useEffect(() => {
    if (!token) {
      if (timerRef.current) clearInterval(timerRef.current);
      return;
    }

    const expiry = getTokenExpiry(token);
    setSessionExpiry(expiry);

    if (!expiry) return;

    const checkSession = () => {
      const now = Date.now();
      const remaining = expiry - now;
      const remainingMinutes = Math.ceil(remaining / 60000);

      setSessionRemainingMinutes(remainingMinutes);

      if (remaining <= 0) {
        // Oturum süresi doldu
        logout();
        window.location.href = '/login';
        return;
      }

      if (remaining <= SESSION_WARNING_MINUTES * 60 * 1000) {
        setSessionWarning(true);
      }
    };

    checkSession();
    timerRef.current = setInterval(checkSession, 30000); // Her 30 saniyede kontrol

    return () => {
      if (timerRef.current) clearInterval(timerRef.current);
    };
  }, [token, logout]);

  const isAdmin = user?.role === 'admin';
  const isAuthenticated = !!token && !!user;

  return (
    <AuthContext.Provider value={{
      user, token, login, logout, isAdmin, isAuthenticated, loading,
      sessionExpiry, sessionWarning, sessionRemainingMinutes, extendSession,
    }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error('useAuth must be used within AuthProvider');
  return ctx;
}
