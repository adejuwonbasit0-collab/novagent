import { NextRequest, NextResponse } from "next/server";
import { BACKEND_URL, readAccessToken, readRefreshToken, setAuthCookies, clearAuthCookies } from "@/lib/server-auth";

/**
 * Every authenticated call the dashboard makes goes through here instead
 * of hitting the backend directly from the browser. The browser never
 * sees an access or refresh token — this route reads them from the
 * httpOnly cookies (set by /api/auth/login), attaches the bearer token
 * server-side, and forwards the request. On a 401 it attempts exactly one
 * silent refresh before giving up, matching the old client-side retry
 * logic but without ever exposing the refresh token to JS.
 *
 * Two things this has to get right beyond simple JSON-in/JSON-out:
 * - Multipart uploads (voice sample files): the original Content-Type
 *   (with its multipart boundary) must pass through unchanged — forcing
 *   application/json here would corrupt the upload.
 * - Binary responses (synthesized audio): the backend's response
 *   Content-Type decides whether we parse JSON or pass raw bytes through;
 *   always calling resp.json() would crash on an audio/wav response.
 */

async function forward(req: NextRequest, path: string[], accessToken: string | undefined) {
  const backendPath = `/api/v1/${path.join("/")}`;
  const url = new URL(req.url);

  const headers: Record<string, string> = {};
  if (accessToken) headers["Authorization"] = `Bearer ${accessToken}`;

  const method = req.method;
  const hasBody = method !== "GET" && method !== "HEAD" && method !== "DELETE";

  let body: ArrayBuffer | undefined;
  if (hasBody) {
    body = await req.arrayBuffer();
    const incomingContentType = req.headers.get("content-type");
    // Pass through the original Content-Type verbatim (this is what
    // carries a multipart boundary correctly); only default to JSON when
    // the caller didn't set one at all.
    headers["Content-Type"] = incomingContentType || "application/json";
  }

  return fetch(`${BACKEND_URL}${backendPath}${url.search}`, {
    method,
    headers,
    body: body && body.byteLength > 0 ? body : undefined,
  });
}

/** Builds the right kind of NextResponse depending on what the backend
 * actually sent back — JSON for ordinary API responses, raw bytes with
 * the original Content-Type for anything else (audio, etc.). */
async function passthroughResponse(resp: Response): Promise<NextResponse> {
  if (resp.status === 204) {
    return new NextResponse(null, { status: 204 });
  }

  const contentType = resp.headers.get("content-type") || "";
  if (contentType.includes("application/json")) {
    const body = await resp.json().catch(() => null);
    return NextResponse.json(body, { status: resp.status });
  }

  const bytes = await resp.arrayBuffer();
  return new NextResponse(bytes, { status: resp.status, headers: { "Content-Type": contentType } });
}

async function handle(req: NextRequest, { params }: { params: { path: string[] } }) {
  let accessToken = readAccessToken();
  let resp = await forward(req, params.path, accessToken);

  if (resp.status === 401) {
    const refreshToken = readRefreshToken();
    if (refreshToken) {
      const refreshResp = await fetch(`${BACKEND_URL}/api/v1/auth/refresh`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ refresh_token: refreshToken }),
      });

      if (refreshResp.ok) {
        const tokens = await refreshResp.json();
        accessToken = tokens.access_token;
        resp = await forward(req, params.path, accessToken);

        const response = await passthroughResponse(resp);
        setAuthCookies(response, tokens.access_token, tokens.refresh_token);
        return response;
      } else {
        const response = NextResponse.json({ detail: "Session expired" }, { status: 401 });
        clearAuthCookies(response);
        return response;
      }
    }
  }

  return passthroughResponse(resp);
}

export { handle as GET, handle as POST, handle as PATCH, handle as PUT, handle as DELETE };
