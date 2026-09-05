import { NextRequest, NextResponse } from "next/server";
import { BACKEND_URL, setAuthCookies } from "@/lib/server-auth";

export async function POST(req: NextRequest) {
  const body = await req.json();

  const backendResp = await fetch(`${BACKEND_URL}/api/v1/auth/login`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });

  if (!backendResp.ok) {
    const errBody = await backendResp.json().catch(() => ({}));
    return NextResponse.json({ detail: errBody.detail || "Login failed" }, { status: backendResp.status });
  }

  const { access_token, refresh_token } = await backendResp.json();

  // The client only ever sees {ok: true} — tokens stay server-side.
  const response = NextResponse.json({ ok: true });
  setAuthCookies(response, access_token, refresh_token);
  return response;
}
