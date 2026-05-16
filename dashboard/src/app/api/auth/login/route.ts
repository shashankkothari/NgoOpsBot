import { NextResponse } from "next/server";
import { createHmac } from "crypto";

const AUTH_COOKIE = "ngo_admin_token";

function computeToken(secret: string): string {
  return createHmac("sha256", secret).update("admin").digest("hex");
}

export async function POST(request: Request) {
  let apiKey: string | undefined;
  try {
    const body = await request.json();
    apiKey = body.apiKey;
  } catch {
    return NextResponse.json({ error: "Invalid request" }, { status: 400 });
  }

  const adminKey = process.env.ADMIN_API_KEY;
  if (!adminKey || !apiKey || apiKey !== adminKey) {
    return NextResponse.json({ error: "Invalid API key" }, { status: 401 });
  }

  const secret = process.env.NEXTAUTH_SECRET!;
  const token = computeToken(secret);

  const response = NextResponse.json({ ok: true });
  response.cookies.set(AUTH_COOKIE, token, {
    httpOnly: true,
    secure: process.env.NODE_ENV === "production",
    sameSite: "lax",
    path: "/",
    maxAge: 24 * 60 * 60,
  });
  return response;
}
