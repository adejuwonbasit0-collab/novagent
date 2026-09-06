import { NextRequest, NextResponse } from "next/server";

// Mirrors ACCESS_COOKIE in lib/server-auth.ts. Not imported directly —
// server-auth.ts pulls in next/headers, which isn't meant for the edge
// middleware runtime — but this needs to stay in sync with that value.
const ACCESS_COOKIE = "nova_access_token";

/**
 * This is the outermost of three layers protecting /admin (spec section
 * 23's "a normal user must never be able to access admin functionality
 * by changing a URL"):
 *   1. This middleware — no cookie at all -> redirected before any page
 *      code runs, cheapest possible check, edge-fast.
 *   2. app/admin/layout.tsx's useRequireAdmin() — cookie present but the
 *      user isn't an admin -> redirected client-side once /auth/me
 *      resolves the actual role.
 *   3. The backend's get_current_admin dependency on every
 *      /api/v1/admin/* route — the only layer that's actually
 *      authoritative; 1 and 2 exist to make the UI behave correctly, not
 *      because either is trusted as the real boundary. A logged-in
 *      non-admin who somehow got real admin page content client-side
 *      couldn't get real admin data back from any API call, because
 *      this layer doesn't know their role — only whether they're logged
 *      in at all.
 */
export function middleware(request: NextRequest) {
  const hasSession = request.cookies.has(ACCESS_COOKIE);

  if (!hasSession) {
    const loginUrl = new URL("/login", request.url);
    return NextResponse.redirect(loginUrl);
  }

  return NextResponse.next();
}

export const config = {
  matcher: ["/admin/:path*"],
};
