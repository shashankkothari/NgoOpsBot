import { cookies } from "next/headers";
import { NextRequest, NextResponse } from "next/server";
import { createHmac } from "crypto";

const AUTH_COOKIE = "ngo_admin_token";
const API_BASE = process.env.API_URL || "http://127.0.0.1:8000";

function isAuthenticated(): boolean {
  const secret = process.env.NEXTAUTH_SECRET;
  if (!secret) return false;
  const token = cookies().get(AUTH_COOKIE)?.value;
  if (!token) return false;
  const expected = createHmac("sha256", secret).update("admin").digest("hex");
  return token === expected;
}

async function handler(request: NextRequest, { params }: { params: { path: string[] } }) {
  if (!isAuthenticated()) {
    return NextResponse.json({ detail: "Unauthorized" }, { status: 401 });
  }

  const path = params.path.join("/");
  const search = request.nextUrl.search;
  const targetUrl = path.startsWith("health")
    ? `${API_BASE}/${path}${search}`
    : `${API_BASE}/api/${path}${search}`;

  const headers: HeadersInit = {
    "Content-Type": "application/json",
    "X-Admin-API-Key": process.env.ADMIN_API_KEY || "",
  };

  const init: RequestInit = { method: request.method, headers, cache: "no-store" };

  if (!["GET", "HEAD", "DELETE"].includes(request.method)) {
    init.body = await request.text();
  }

  try {
    const upstream = await fetch(targetUrl, init);
    const body = await upstream.text();
    return new NextResponse(body, {
      status: upstream.status,
      headers: { "Content-Type": upstream.headers.get("Content-Type") || "application/json" },
    });
  } catch (err) {
    const message = err instanceof Error ? err.message : "Upstream unreachable";
    console.error(`[proxy] ${request.method} ${targetUrl} →`, message);
    return NextResponse.json({ detail: `Proxy error: ${message}` }, { status: 502 });
  }
}

export const GET = handler;
export const POST = handler;
export const PATCH = handler;
export const PUT = handler;
export const DELETE = handler;
