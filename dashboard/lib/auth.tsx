"use client";

import { createContext, useContext, useEffect, useState, ReactNode } from "react";
import { useRouter } from "next/navigation";
import { api, User } from "./api";

interface AuthContextValue {
  user: User | null;
  loading: boolean;
  refresh: () => Promise<void>;
  logout: () => void;
}

const AuthContext = createContext<AuthContextValue | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [loading, setLoading] = useState(true);

  async function refresh() {
    // No client-visible token to check anymore — the httpOnly cookie is
    // invisible to JS by design, so we just ask the server via /auth/me
    // and treat any failure as "not logged in."
    try {
      const me = await api.me();
      setUser(me);
    } catch {
      setUser(null);
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    refresh();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  function logout() {
    api.logout();
    setUser(null);
  }

  return (
    <AuthContext.Provider value={{ user, loading, refresh, logout }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used within AuthProvider");
  return ctx;
}

/** Redirects to /login if there's no authenticated user once loading settles. */
export function useRequireAuth() {
  const { user, loading } = useAuth();
  const router = useRouter();

  useEffect(() => {
    if (!loading && !user) {
      router.replace("/login");
    }
  }, [loading, user, router]);

  return { user, loading };
}

/**
 * Same idea as useRequireAuth, but for /admin/* (spec section 23: admin
 * and user must be completely separate — separate routes AND separate
 * authorization, not the same "logged in" check with a nav link hidden).
 * A logged-out visitor goes to /login same as any other page; a logged-in
 * but non-admin user is bounced to /dashboard rather than /login, since
 * "you're not allowed here" is a different situation from "you're not
 * signed in" and shouldn't be presented as one.
 *
 * This is the UX layer only. The actual authorization boundary is the
 * backend's get_current_admin dependency (every /api/v1/admin/* call is
 * independently re-checked there) — this hook, and the edge middleware
 * in middleware.ts, exist so an unauthorized user never sees the admin
 * UI render at all, not because either one is trusted as the real gate.
 */
export function useRequireAdmin() {
  const { user, loading } = useAuth();
  const router = useRouter();

  const isAdmin = user?.role === "admin" || user?.role === "super_admin";

  useEffect(() => {
    if (loading) return;
    if (!user) {
      router.replace("/login");
    } else if (!isAdmin) {
      router.replace("/dashboard");
    }
  }, [loading, user, isAdmin, router]);

  return { user, loading: loading || (!!user && !isAdmin), isAdmin };
}
