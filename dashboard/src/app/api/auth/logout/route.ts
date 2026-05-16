import { NextResponse } from "next/server";

const AUTH_COOKIE = "ngo_admin_token";

export async function POST() {
  const response = NextResponse.json({ ok: true });
  response.cookies.delete(AUTH_COOKIE);
  return response;
}
