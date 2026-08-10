"use client";

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
} from "react";
import { useRouter } from "next/navigation";
import { ApiError, apiFetch } from "@/lib/api";
import type {
  AuthResponse,
  MeResponse,
  User,
  WorkspaceMembership,
} from "@/lib/auth-types";
import type { Role } from "@/lib/types";

const ACCESS_KEY = "intercom_access_token";
const REFRESH_KEY = "intercom_refresh_token";

/** RequestInit with a JSON-serialisable body (the raw one types body as BodyInit). */
export type AuthFetchInit = Omit<RequestInit, "body"> & { body?: unknown };

interface AuthState {
  user: User | null;
  workspaces: WorkspaceMembership[];
  activeWorkspaceId: string | null;
  activeRole: Role | null;
  loading: boolean;
}

interface AuthContextValue extends AuthState {
  accessToken: string | null;
  isAdmin: boolean;
  activeWorkspace: WorkspaceMembership | null;
  login: (email: string, password: string) => Promise<void>;
  signup: (input: {
    email: string;
    password: string;
    name?: string;
    workspace_name: string;
  }) => Promise<void>;
  logout: () => void;
  switchWorkspace: (workspaceId: string) => Promise<void>;
  /** Authenticated fetch that transparently refreshes an expired access token. */
  authFetch: <T>(path: string, init?: AuthFetchInit) => Promise<T>;
  applyAuth: (data: AuthResponse) => void;
}

const AuthContext = createContext<AuthContextValue | null>(null);

function readToken(key: string): string | null {
  if (typeof window === "undefined") return null;
  return window.localStorage.getItem(key);
}

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const router = useRouter();
  const [state, setState] = useState<AuthState>({
    user: null,
    workspaces: [],
    activeWorkspaceId: null,
    activeRole: null,
    loading: true,
  });

  // Kept in a ref so authFetch always sees the latest token without re-binding.
  const accessRef = useRef<string | null>(null);
  const [accessToken, setAccessToken] = useState<string | null>(null);

  const persist = useCallback((access: string | null, refresh: string | null) => {
    accessRef.current = access;
    setAccessToken(access);
    if (typeof window === "undefined") return;
    if (access) window.localStorage.setItem(ACCESS_KEY, access);
    else window.localStorage.removeItem(ACCESS_KEY);
    if (refresh) window.localStorage.setItem(REFRESH_KEY, refresh);
    else if (refresh === null && !access) window.localStorage.removeItem(REFRESH_KEY);
  }, []);

  const applyAuth = useCallback(
    (data: AuthResponse) => {
      persist(data.access_token, data.refresh_token);
      setState({
        user: data.user,
        workspaces: data.workspaces,
        activeWorkspaceId: data.active_workspace_id ?? null,
        activeRole:
          data.workspaces.find((w) => w.id === data.active_workspace_id)?.role ??
          null,
        loading: false,
      });
    },
    [persist],
  );

  const logout = useCallback(() => {
    persist(null, null);
    if (typeof window !== "undefined") {
      window.localStorage.removeItem(REFRESH_KEY);
    }
    setState({
      user: null,
      workspaces: [],
      activeWorkspaceId: null,
      activeRole: null,
      loading: false,
    });
    router.push("/login");
  }, [persist, router]);

  /** Exchange the refresh token for a new access token. */
  const refresh = useCallback(async (): Promise<string | null> => {
    const refreshToken = readToken(REFRESH_KEY);
    if (!refreshToken) return null;
    try {
      const data = await apiFetch<AuthResponse>("/api/auth/refresh", {
        method: "POST",
        body: { refresh_token: refreshToken },
      });
      applyAuth(data);
      return data.access_token;
    } catch {
      return null;
    }
  }, [applyAuth]);

  const authFetch = useCallback(
    async <T,>(path: string, init?: AuthFetchInit): Promise<T> => {
      const run = (token: string | null) =>
        apiFetch<T>(path, { ...init, token });

      try {
        return await run(accessRef.current);
      } catch (err) {
        // A single retry after refresh covers ordinary access-token expiry.
        if (err instanceof ApiError && err.status === 401) {
          const fresh = await refresh();
          if (fresh) return run(fresh);
          logout();
        }
        throw err;
      }
    },
    [refresh, logout],
  );

  // Restore the session on first load.
  useEffect(() => {
    let cancelled = false;

    (async () => {
      const stored = readToken(ACCESS_KEY);
      accessRef.current = stored;
      setAccessToken(stored);

      if (!stored) {
        if (!cancelled) setState((s) => ({ ...s, loading: false }));
        return;
      }

      try {
        const me = await apiFetch<MeResponse>("/api/auth/me", { token: stored });
        if (cancelled) return;
        setState({
          user: me.user,
          workspaces: me.workspaces,
          activeWorkspaceId: me.active_workspace_id ?? null,
          activeRole: me.active_role ?? null,
          loading: false,
        });
      } catch {
        const fresh = await refresh();
        if (cancelled) return;
        if (!fresh) {
          persist(null, null);
          setState((s) => ({ ...s, loading: false }));
        }
      }
    })();

    return () => {
      cancelled = true;
    };
  }, [refresh, persist]);

  const login = useCallback(
    async (email: string, password: string) => {
      const data = await apiFetch<AuthResponse>("/api/auth/login", {
        method: "POST",
        body: { email, password },
      });
      applyAuth(data);
    },
    [applyAuth],
  );

  const signup = useCallback(
    async (input: {
      email: string;
      password: string;
      name?: string;
      workspace_name: string;
    }) => {
      const data = await apiFetch<AuthResponse>("/api/auth/signup", {
        method: "POST",
        body: input,
      });
      applyAuth(data);
    },
    [applyAuth],
  );

  const switchWorkspace = useCallback(
    async (workspaceId: string) => {
      const data = await authFetch<AuthResponse>("/api/auth/switch-workspace", {
        method: "POST",
        body: { workspace_id: workspaceId },
      });
      applyAuth(data);
    },
    [authFetch, applyAuth],
  );

  const value = useMemo<AuthContextValue>(
    () => ({
      ...state,
      accessToken,
      isAdmin: state.activeRole === "admin",
      activeWorkspace:
        state.workspaces.find((w) => w.id === state.activeWorkspaceId) ?? null,
      login,
      signup,
      logout,
      switchWorkspace,
      authFetch,
      applyAuth,
    }),
    [state, accessToken, login, signup, logout, switchWorkspace, authFetch, applyAuth],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used inside an AuthProvider");
  return ctx;
}
