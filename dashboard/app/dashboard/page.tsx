"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { api, Device, Reminder } from "@/lib/api";
import { useAuth } from "@/lib/auth";

export default function OverviewPage() {
  const { user } = useAuth();
  const [devices, setDevices] = useState<Device[] | null>(null);
  const [reminders, setReminders] = useState<Reminder[] | null>(null);

  useEffect(() => {
    api.listDevices().then(setDevices).catch(() => setDevices([]));
    api.listReminders().then(setReminders).catch(() => setReminders([]));
  }, []);

  const activeDevices = devices?.filter((d) => d.is_active).length ?? 0;
  const pendingReminders = reminders?.filter((r) => r.status === "pending").length ?? 0;

  return (
    <div className="max-w-4xl">
      <h1 className="text-2xl font-bold mb-1">Welcome back{user?.full_name ? `, ${user.full_name}` : ""}</h1>
      <p className="text-muted mb-8">Here's what's happening with {user?.assistant_name || "Nova"}.</p>

      <div className="grid grid-cols-1 sm:grid-cols-2 gap-4 mb-8">
        <div className="card">
          <p className="text-muted text-sm mb-1">Connected devices</p>
          <p className="text-3xl font-display font-bold">
            {devices === null ? "—" : activeDevices}
          </p>
          <Link href="/dashboard/devices" className="text-accent text-sm hover:underline">
            Manage devices →
          </Link>
        </div>

        <div className="card">
          <p className="text-muted text-sm mb-1">Pending reminders</p>
          <p className="text-3xl font-display font-bold">
            {reminders === null ? "—" : pendingReminders}
          </p>
          <Link href="/dashboard/reminders" className="text-accent text-sm hover:underline">
            View reminders →
          </Link>
        </div>
      </div>

      <div className="card">
        <p className="font-medium mb-2">Talk to {user?.assistant_name || "Nova"}</p>
        <p className="text-muted text-sm mb-4">
          Ask it to set a reminder, check your schedule, or control a connected device.
        </p>
        <Link href="/dashboard/assistant" className="btn-primary inline-block">
          Open assistant
        </Link>
      </div>
    </div>
  );
}
