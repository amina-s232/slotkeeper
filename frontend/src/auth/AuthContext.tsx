import { useQueryClient } from "@tanstack/react-query";
import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from "react";
import * as api from "../api/endpoints";
import type { RegisterInput } from "../api/endpoints";
import { clearTokens, hasRefreshToken, refreshAccessToken, setSessionExpiredHandler, storeTokens } from "../api/client";
import type { User } from "../api/types";

export interface AuthValue {
  status: "loading" | "anonymous" | "authenticated";
  user: User | null;
  login: (email: string, password: string) => Promise<User>;
  register: (input: RegisterInput) => Promise<User>;
  logout: () => void;
}

export const AuthContext = createContext<AuthValue | null>(null);

export function useAuth(): AuthValue {
  const value = useContext(AuthContext);
  if (!value) throw new Error("useAuth must be used inside <AuthProvider>");
  return value;
}

type State = Pick<AuthValue, "status" | "user">;

export function AuthProvider({ children }: { children: ReactNode }) {
  const queryClient = useQueryClient();
  // With a stored refresh token we do not know yet who the user is, so start in "loading".
  const [state, setState] = useState<State>({ status: hasRefreshToken() ? "loading" : "anonymous", user: null });

  const logout = useCallback(() => {
    clearTokens();
    queryClient.clear(); // the next person on this browser must not see this person's cached data
    setState({ status: "anonymous", user: null });
  }, [queryClient]);

  useEffect(() => {
    setSessionExpiredHandler(logout);
    return () => setSessionExpiredHandler(null);
  }, [logout]);

  useEffect(() => {
    if (!hasRefreshToken()) return;
    let cancelled = false;
    (async () => {
      try {
        if (await refreshAccessToken()) {
          const user = await api.me();
          if (!cancelled) setState({ status: "authenticated", user });
          return;
        }
      } catch {
        /* fall through to anonymous */
      }
      if (!cancelled) {
        clearTokens();
        setState({ status: "anonymous", user: null });
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  const login = useCallback(async (email: string, password: string) => {
    const tokens = await api.login(email, password);
    storeTokens(tokens.access, tokens.refresh);
    const user = await api.me();
    setState({ status: "authenticated", user });
    return user;
  }, []);

  const register = useCallback(
    async (input: RegisterInput) => {
      await api.register(input);
      return login(input.email, input.password);
    },
    [login],
  );

  const value = useMemo<AuthValue>(() => ({ ...state, login, register, logout }), [state, login, register, logout]);
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export const homeFor = (role: User["role"]): string =>
  role === "provider" ? "/dashboard" : role === "admin" ? "/appointments" : "/providers";
