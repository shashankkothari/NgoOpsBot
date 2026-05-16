import NextAuth from "next-auth";
import GoogleProvider from "next-auth/providers/google";
import { AsyncLocalStorage } from "node:async_hooks";
import type { NextRequest } from "next/server";

// AsyncLocalStorage lets us safely thread the NGO slug from the raw HTTP
// request cookie into the NextAuth signIn callback without relying on
// Next.js's cookies() helper (which loses context inside NextAuth's internals).
const ngoSlugStorage = new AsyncLocalStorage<string | null>();

function parseNgoSlug(cookieHeader: string | null): string | null {
  if (!cookieHeader) return null;
  const match = cookieHeader.match(/(?:^|;\s*)pending_ngo_slug=([^;]+)/);
  return match ? decodeURIComponent(match[1]) : null;
}

const handler = NextAuth({
  providers: [
    GoogleProvider({
      clientId: process.env.GOOGLE_CLIENT_ID!,
      clientSecret: process.env.GOOGLE_CLIENT_SECRET!,
    }),
  ],
  callbacks: {
    async signIn({ account }) {
      if (account?.provider !== "google" || !account.id_token) return false;

      // Read the NGO slug threaded in via AsyncLocalStorage from the route wrapper.
      const ngoSlug = ngoSlugStorage.getStore() ?? null;

      try {
        const body: Record<string, string> = { id_token: account.id_token };
        if (ngoSlug) body.ngo_slug = ngoSlug;

        const res = await fetch(
          `${process.env.NEXT_PUBLIC_API_URL}/api/v1/staff/auth/google`,
          {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(body),
          }
        );
        if (!res.ok) return "/login?error=Unauthorized";
        const data = await res.json();
        account.backendToken = data.access_token;
        account.staffProfile = data.staff;
        return true;
      } catch {
        return "/login?error=ServerError";
      }
    },

    async jwt({ token, account }) {
      if (account?.backendToken) {
        token.backendToken = account.backendToken as string;
        token.staffProfile = account.staffProfile;
      }
      return token;
    },

    async session({ session, token }) {
      session.backendToken = token.backendToken as string;
      session.staffProfile = token.staffProfile as {
        id: string;
        name: string;
        role: string;
        ngo_id: string;
        ngo_name: string;
        ngo_slug: string;
        allowed_agents: string[];
      };
      return session;
    },
  },
  pages: {
    signIn: "/login",
    error: "/login",
  },
});

// NextAuth v4 App Router route handlers receive (req, { params: { nextauth } }).
// We wrap them to extract the NGO slug from cookies before NextAuth takes over,
// then thread it into the signIn callback via AsyncLocalStorage.
type NextAuthCtx = { params: { nextauth: string[] } };

// eslint-disable-next-line @typescript-eslint/no-explicit-any
async function wrappedHandler(req: NextRequest, ctx: NextAuthCtx): Promise<any> {
  const ngoSlug = parseNgoSlug(req.headers.get("cookie"));
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  return ngoSlugStorage.run(ngoSlug, () => (handler as any)(req, ctx));
}

export const GET = wrappedHandler;
export const POST = wrappedHandler;
