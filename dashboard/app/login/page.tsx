"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { api, APIError } from "@/lib/api";
import { useAuth } from "@/lib/auth";

export default function LoginPage() {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const router = useRouter();
  const { refresh } = useAuth();

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    setSubmitting(true);
    try {
      await api.login(email, password);
      await refresh();
      router.push("/dashboard");
    } catch (err) {
      setError(err instanceof APIError ? err.message : "Something went wrong. Try again.");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="min-h-screen flex items-center justify-center px-4">
      <div className="w-full max-w-sm">
        <div className="mb-8 text-center">
          <h1 className="text-2xl font-bold mb-1">Nova</h1>
          <p className="text-muted text-sm">Sign in to your assistant</p>
        </div>

        <form onSubmit={onSubmit} className="card space-y-4">
          {error && (
            <p className="text-danger text-sm border border-danger/40 bg-danger/10 rounded px-3 py-2">
              {error}
            </p>
          )}

          <div className="space-y-1">
            <label htmlFor="email" className="text-sm text-muted">
              Email
            </label>
            <input
              id="email"
              type="email"
              required
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              className="input-field w-full"
              autoComplete="email"
            />
          </div>

          <div className="space-y-1">
            <label htmlFor="password" className="text-sm text-muted">
              Password
            </label>
            <input
              id="password"
              type="password"
              required
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              className="input-field w-full"
              autoComplete="current-password"
            />
          </div>

          <button type="submit" disabled={submitting} className="btn-primary w-full">
            {submitting ? "Signing in…" : "Sign in"}
          </button>
        </form>

        <p className="text-center text-sm text-muted mt-4">
          No account?{" "}
          <Link href="/register" className="text-accent hover:underline">
            Create one
          </Link>
        </p>
      </div>
    </div>
  );
}
