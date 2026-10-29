import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";
import { api, getToken, setToken } from "../api/client";
import type { User } from "../types";

type AuthState = {
  user: User | null;
  loading: boolean;
  needsBootstrap: boolean;
  refresh: () => Promise<void>;
  login: (email: string, password: string) => Promise<void>;
  logout: () => void;
  bootstrap: (email: string, password: string, displayName: string) => Promise<void>;
  register: (
    inviteCode: string,
    email: string,
    password: string,
    displayName: string,
  ) => Promise<void>;
};

const AuthContext = createContext<AuthState | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [loading, setLoading] = useState(true);
  const [needsBootstrap, setNeedsBootstrap] = useState(false);

  const refresh = useCallback(async () => {
    const status = await api<{ needs_bootstrap: boolean }>("/api/v1/auth/bootstrap-status");
    setNeedsBootstrap(status.needs_bootstrap);
    if (!getToken()) {
      setUser(null);
      return;
    }
    try {
      const me = await api<{ user: User }>("/api/v1/auth/me");
      setUser(me.user);
    } catch {
      setToken(null);
      setUser(null);
    }
  }, []);

  useEffect(() => {
    refresh().finally(() => setLoading(false));
  }, [refresh]);

  const login = useCallback(async (email: string, password: string) => {
    const data = await api<{ access_token: string; user: User }>("/api/v1/auth/login", {
      method: "POST",
      body: JSON.stringify({ email, password }),
    });
    setToken(data.access_token);
    setUser(data.user);
    setNeedsBootstrap(false);
  }, []);

  const bootstrap = useCallback(
    async (email: string, password: string, displayName: string) => {
      const data = await api<{ access_token: string; user: User }>("/api/v1/auth/bootstrap", {
        method: "POST",
        body: JSON.stringify({
          email,
          password,
          display_name: displayName,
        }),
      });
      setToken(data.access_token);
      setUser(data.user);
      setNeedsBootstrap(false);
    },
    [],
  );

  const register = useCallback(
    async (inviteCode: string, email: string, password: string, displayName: string) => {
      const data = await api<{ access_token: string; user: User }>("/api/v1/auth/register", {
        method: "POST",
        body: JSON.stringify({
          invite_code: inviteCode,
          email,
          password,
          display_name: displayName,
        }),
      });
      setToken(data.access_token);
      setUser(data.user);
    },
    [],
  );

  const logout = useCallback(() => {
    setToken(null);
    setUser(null);
  }, []);

  const value = useMemo(
    () => ({
      user,
      loading,
      needsBootstrap,
      refresh,
      login,
      logout,
      bootstrap,
      register,
    }),
    [user, loading, needsBootstrap, refresh, login, logout, bootstrap, register],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth outside provider");
  return ctx;
}
