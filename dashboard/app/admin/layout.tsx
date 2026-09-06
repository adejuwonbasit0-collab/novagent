"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useRequireAdmin, useAuth } from "@/lib/auth";

const ADMIN_NAV = [
  { href: "/admin", label: "Overview" },
  { href: "/admin/ai-provider", label: "AI Provider" },
  { href: "/admin/settings", label: "Assistant identity" },
];

/**
 * Root layout for the entire /admin route group. This is intentionally a
 * separate route/layout from /dashboard (not a tab hidden inside the user
 * dashboard) so a normal user changing the URL to /admin/whatever never even
 * renders the user-dashboard shell with admin controls in it — they get
 * redirected before any admin page mounts. The real security boundary is
 * still server-side: every /api/v1/admin/* route independently requires
 * admin/super_admin role and 403s otherwise, regardless of what this layout
 * does. This layout only controls what the *browser* shows.
 */
export default function AdminLayout({ children }: { children: React.ReactNode }) {
  const { user, loading, isAdmin } = useRequireAdmin();
  const { logout } = useAuth();
  const pathname = usePathname();

  if (loading || !user || !isAdmin) {
    return (
      <div className="min-h-screen flex items-center justify-center">
        <p className="text-muted font-mono text-sm">Loading…</p>
      </div>
    );
  }

  return (
    <div className="min-h-screen flex">
      <aside className="w-56 border-r border-border flex flex-col bg-panel/40">
        <div className="px-5 py-5 border-b border-border">
          <p className="font-display font-bold text-lg">Nova Admin</p>
          <p className="text-xs text-muted mt-1">Platform administration</p>
        </div>

        <nav className="flex-1 px-2 py-4 space-y-1">
          {ADMIN_NAV.map((item) => {
            const active = pathname === item.href;
            return (
              <Link
                key={item.href}
                href={item.href}
                className={`block px-3 py-2 rounded text-sm transition-colors ${
                  active ? "bg-accent/15 text-accent" : "text-muted hover:text-ink hover:bg-panel"
                }`}
              >
                {item.label}
              </Link>
            );
          })}
        </nav>

        <div className="px-4 py-4 border-t border-border space-y-2">
          <Link href="/dashboard" className="block text-xs text-muted hover:text-ink">
            ← Back to user dashboard
          </Link>
          <p className="text-xs text-muted truncate">{user.email}</p>
          <button onClick={logout} className="btn-secondary w-full text-sm">
            Sign out
          </button>
        </div>
      </aside>

      <main className="flex-1 p-8 overflow-y-auto">{children}</main>
    </div>
  );
}
