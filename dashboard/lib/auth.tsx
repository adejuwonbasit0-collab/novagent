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
 * Redirects to /login if there's no authenticated user, and to /dashboard if
 * the authenticated user isn't an admin/super_admin. This is the client-side
 * gate for the entire /admin route group — it exists purely for UX (so a
 * non-admin never even sees an admin layout flash by). It is NOT the real
 * security boundary: every admin API route independently checks the role
 * server-side via get_current_admin and returns 403 regardless of what the
 * client does, so a normal user can never reach admin functionality by
 * hitting the API directly or editing the URL.
 */
export function useRequireAdmin() {
  const { user, loading } = useAuth();
  const router = useRouter();

  useEffect(() => {
    if (loading) return;
    if (!user) {
      router.replace("/login");
      return;
    }
    if (user.role !== "admin" && user.role !== "super_admin") {
      router.replace("/dashboard");
    }
  }, [loading, user, router]);

  return { user, loading, isAdmin: !!user && (user.role === "admin" || user.role === "super_admin") };
}
