import { NextRequest, NextResponse } from "next/server";
import { BACKEND_URL } from "@/lib/server-auth";

export async function POST(req: NextRequest) {
  const body = await req.json();

  const backendResp = await fetch(`${BACKEND_URL}/api/v1/auth/register`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });

  const data = await backendResp.json().catch(() => ({}));
  return NextResponse.json(data, { status: backendResp.status });
}
