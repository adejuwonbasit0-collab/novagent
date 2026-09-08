"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useRequireAdmin, useAuth } from "@/lib/auth";

const ADMIN_NAV = [
  { href: "/admin", label: "Overview" },
  { href: "/admin/branding", label: "Branding & CMS" },
  { href: "/admin/ai-provider", label: "AI Provider" },
  { href: "/admin/settings", label: "Assistant identity" },
  { href: "/admin/users", label: "User Management" },
  { href: "/admin/health", label: "System Health" },
];

/**
 * Deliberately does not reuse dashboard/layout.tsx or its <aside> — spec
 * section 23 asks for admin and user to be "completely separate," not
 * the same shell with an extra nav item shown conditionally, which is
 * exactly what this used to be (/dashboard/admin/* inside
 * DashboardLayout). A visibly different shell (dark red accent instead
 * of the product's normal accent color) also means an admin can never
 * mistake which context they're in mid-session.
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
      <aside className="w-56 border-r border-border flex flex-col bg-[#1a0f0f]">
        <div className="px-5 py-5 border-b border-border">
          <p className="font-display font-bold text-lg text-red-400">Nova Admin</p>
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
                  active ? "bg-red-500/15 text-red-300" : "text-muted hover:text-ink hover:bg-panel"
                }`}
              >
                {item.label}
              </Link>
            );
          })}
        </nav>

        <div className="px-4 py-4 border-t border-border space-y-2">
          <Link href="/dashboard" className="btn-secondary w-full text-sm block text-center">
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
