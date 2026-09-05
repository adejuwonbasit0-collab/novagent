"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { api, APIError } from "@/lib/api";

export default function RegisterPage() {
  const [fullName, setFullName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const router = useRouter();

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    setSubmitting(true);
    try {
      await api.register(email, password, fullName || undefined);
      await api.login(email, password);
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
          <p className="text-muted text-sm">Create your account</p>
        </div>

        <form onSubmit={onSubmit} className="card space-y-4">
          {error && (
            <p className="text-danger text-sm border border-danger/40 bg-danger/10 rounded px-3 py-2">
              {error}
            </p>
          )}

          <div className="space-y-1">
            <label htmlFor="fullName" className="text-sm text-muted">
              Name
            </label>
            <input
              id="fullName"
              type="text"
              value={fullName}
              onChange={(e) => setFullName(e.target.value)}
              className="input-field w-full"
              autoComplete="name"
            />
          </div>

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
              minLength={8}
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              className="input-field w-full"
              autoComplete="new-password"
            />
            <p className="text-xs text-muted">At least 8 characters.</p>
          </div>

          <button type="submit" disabled={submitting} className="btn-primary w-full">
            {submitting ? "Creating account…" : "Create account"}
          </button>
        </form>

        <p className="text-center text-sm text-muted mt-4">
          Already have an account?{" "}
          <Link href="/login" className="text-accent hover:underline">
            Sign in
          </Link>
        </p>
      </div>
    </div>
  );
}
