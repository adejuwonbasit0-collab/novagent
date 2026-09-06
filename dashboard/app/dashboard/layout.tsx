"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useRequireAuth, useAuth } from "@/lib/auth";
import { StateRing } from "@/components/StateRing";

const NAV = [
  { href: "/dashboard", label: "Overview" },
  { href: "/dashboard/downloads", label: "Get Nova" },
  { href: "/dashboard/devices", label: "Devices" },
  { href: "/dashboard/permissions", label: "Permissions" },
  { href: "/dashboard/reminders", label: "Reminders" },
  { href: "/dashboard/voice", label: "Voice" },
  { href: "/dashboard/assistant", label: "Assistant" },
];

export default function DashboardLayout({ children }: { children: React.ReactNode }) {
  const { user, loading } = useRequireAuth();
  const { logout } = useAuth();
  const pathname = usePathname();

  if (loading || !user) {
    return (
      <div className="min-h-screen flex items-center justify-center">
        <p className="text-muted font-mono text-sm">Loading…</p>
      </div>
    );
  }

  const isAdmin = user.role === "admin" || user.role === "super_admin";

  return (
    <div className="min-h-screen flex">
      <aside className="w-56 border-r border-border flex flex-col">
        <div className="px-5 py-5 border-b border-border">
          <p className="font-display font-bold text-lg">Nova</p>
          <div className="mt-2">
            <StateRing state="idle" />
          </div>
        </div>

        <nav className="flex-1 px-2 py-4 space-y-1">
          {NAV.map((item) => {
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
          {isAdmin && (
            // Deliberately not part of NAV above (spec section 23: a
            // separate destination, not a same-shell nav item) — this is
            // the one deliberate crossover link, styled distinctly so
            // it reads as "leave to a different area" rather than just
            // another page in this sidebar.
            <Link href="/admin" className="btn-secondary w-full text-sm block text-center border-red-500/30 text-red-300">
              Admin →
            </Link>
          )}
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
