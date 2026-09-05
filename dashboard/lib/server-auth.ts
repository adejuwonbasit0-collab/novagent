import { cookies } from "next/headers";
import { NextResponse } from "next/server";

// This module only ever runs server-side (Route Handlers) — the whole
// point is that access/refresh tokens never reach browser JS. Cookie
// names are prefixed to avoid collisions with anything else on the host.
export const ACCESS_COOKIE = "nova_access_token";
export const REFRESH_COOKIE = "nova_refresh_token";

// BACKEND_URL (no NEXT_PUBLIC_ prefix) is intentional: since the browser
// now only ever talks to this app's own /api/* routes, the real backend
// URL never needs to ship in the client bundle at all.
export const BACKEND_URL = process.env.BACKEND_URL || "http://localhost:8000";

const isProd = process.env.NODE_ENV === "production";

// secure: true whenever NODE_ENV=production is the correct default — real
// deployments must be HTTPS, and this is what stops the cookie being sent
// over an accidental plain-HTTP connection. One thing worth knowing if
// you're testing the production build (`npm run build && npm run start`)
// locally over plain http: curl's cookie jar does NOT enforce the Secure
// attribute the way real browsers do, so curl-based testing can appear to
// work end-to-end even in a configuration a real browser would reject
// (browsers vary on this for `localhost` specifically vs `127.0.0.1` —
// don't rely on either working over plain http in production mode). For
// real local testing in an actual browser, use `npm run dev` (NODE_ENV
// is not "production", so Secure is off) or put the production build
// behind real HTTPS.
const baseCookieOptions = {
  httpOnly: true,
  secure: isProd,
  sameSite: "lax" as const,
  path: "/",
};

export function readAccessToken(): string | undefined {
  return cookies().get(ACCESS_COOKIE)?.value;
}

export function readRefreshToken(): string | undefined {
  return cookies().get(REFRESH_COOKIE)?.value;
}

/** Sets both cookies on an outgoing response. Access token is a session
 * cookie (no maxAge) since its real lifetime is enforced by the backend
 * and the proxy's refresh-on-401 logic covers renewal; refresh token gets
 * a longer maxAge matching the backend's default. */
export function setAuthCookies(response: NextResponse, accessToken: string, refreshToken: string): void {
  response.cookies.set(ACCESS_COOKIE, accessToken, baseCookieOptions);
  response.cookies.set(REFRESH_COOKIE, refreshToken, { ...baseCookieOptions, maxAge: 60 * 60 * 24 * 30 });
}

export function clearAuthCookies(response: NextResponse): void {
  response.cookies.set(ACCESS_COOKIE, "", { ...baseCookieOptions, maxAge: 0 });
  response.cookies.set(REFRESH_COOKIE, "", { ...baseCookieOptions, maxAge: 0 });
}
