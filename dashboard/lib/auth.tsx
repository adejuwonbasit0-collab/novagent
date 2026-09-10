"use client";

import { createContext, useContext, useEffect, useState, ReactNode } from "react";
import { useRouter } from "next/navigation";
import { api, User } from "./api";

interface AuthContextValue {
  user: User | null;
  loading: boolean;
  refresh: () => Promise<User | null>;
  logout: () => void;
}

const AuthContext = createContext<AuthContextValue | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [loading, setLoading] = useState(true);

  // BUG FIX: this used to be `async function refresh(): Promise<void>` —
  // it set `user` state but told no caller whether that succeeded. The
  // login page called `await refresh(); router.push("/dashboard")`
  // unconditionally, so ANY reason /auth/me failed right after a
  // successful login (expired-immediately token, cookie not actually
  // persisted by the browser, a backend hiccup) sent the user to
  // /dashboard anyway — which then bounced them straight back to
  // /login via useRequireAuth, with no error ever shown. From the
  // outside that looks exactly like "the login page just refreshes
  // itself and does nothing." Returning the result lets the login page
  // actually tell the two situations apart.
  async function refresh(): Promise<User | null> {
    try {
      const me = await api.me();
      setUser(me);
      return me;
    } catch {
      setUser(null);
      return null;
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
