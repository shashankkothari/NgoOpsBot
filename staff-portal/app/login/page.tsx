"use client";

import { signIn, useSession } from "next-auth/react";
import { useRouter, useSearchParams } from "next/navigation";
import { useEffect, useState } from "react";
import { Bot, ArrowRight, AlertCircle } from "lucide-react";
import { Suspense } from "react";

const ERROR_MESSAGES: Record<string, string> = {
  Unauthorized: "Your Google account is not registered as staff for that NGO. Contact your admin.",
  ServerError: "Something went wrong. Please try again.",
  OAuthCallback: "Google sign-in failed. Please try again.",
  OAuthSignin: "Could not start Google sign-in. Please try again.",
};

export default function LoginPage() {
  return (
    <Suspense>
      <LoginForm />
    </Suspense>
  );
}

function LoginForm() {
  const { status } = useSession();
  const router = useRouter();
  const searchParams = useSearchParams();

  const [ngoSlug, setNgoSlug] = useState("");
  const [step, setStep] = useState<"ngo" | "google">("ngo");
  const [loading, setLoading] = useState(false);
  // After 2 s of NextAuth "loading", show the form anyway so the user
  // isn't blocked by a spinner if the session check is slow.
  const [sessionTimedOut, setSessionTimedOut] = useState(false);

  const errorKey = searchParams.get("error") ?? "";
  const errorMessage =
    ERROR_MESSAGES[errorKey] ?? (errorKey ? "Sign-in failed. Please try again." : "");

  useEffect(() => {
    if (status === "authenticated") router.push("/chat");
  }, [status, router]);

  useEffect(() => {
    if (status !== "loading") return;
    const t = setTimeout(() => setSessionTimedOut(true), 2000);
    return () => clearTimeout(t);
  }, [status]);

  if (status === "loading" && !sessionTimedOut) {
    return (
      <div className="min-h-screen flex items-center justify-center">
        <div className="h-8 w-8 rounded-full border-4 border-indigo-600 border-t-transparent animate-spin" />
      </div>
    );
  }

  function handleContinue(e: React.FormEvent) {
    e.preventDefault();
    const slug = ngoSlug.trim().toLowerCase().replace(/\s+/g, "-");
    if (!slug) return;
    setNgoSlug(slug);
    setStep("google");
  }

  async function handleGoogleSignIn() {
    setLoading(true);
    // Store the NGO slug in a short-lived cookie so the server-side NextAuth
    // callback can read it and scope the staff lookup to this NGO only.
    document.cookie = `pending_ngo_slug=${encodeURIComponent(ngoSlug)}; path=/; max-age=300; SameSite=Lax`;
    await signIn("google", { callbackUrl: "/chat" });
  }

  return (
    <div className="min-h-screen bg-gradient-to-br from-indigo-50 via-white to-slate-50 flex items-center justify-center p-4">
      <div className="w-full max-w-sm">
        {/* Logo */}
        <div className="flex flex-col items-center mb-8 gap-3">
          <div className="h-16 w-16 rounded-2xl bg-indigo-600 flex items-center justify-center shadow-lg shadow-indigo-200">
            <Bot className="h-9 w-9 text-white" />
          </div>
          <div className="text-center">
            <h1 className="text-2xl font-bold text-slate-900">NGO OpsBot</h1>
            <p className="text-sm text-slate-500 mt-0.5">Staff Portal</p>
          </div>
        </div>

        {/* Card */}
        <div className="bg-white rounded-2xl border border-slate-200 shadow-sm p-8">
          {errorMessage && (
            <div className="flex items-start gap-2 text-sm text-red-600 bg-red-50 border border-red-100 rounded-lg px-3 py-2.5 mb-5">
              <AlertCircle className="h-4 w-4 mt-0.5 shrink-0" />
              <span>{errorMessage}</span>
            </div>
          )}

          {step === "ngo" ? (
            /* ── Step 1: enter NGO slug ── */
            <>
              <h2 className="text-lg font-semibold text-slate-900 mb-1">
                Find your organization
              </h2>
              <p className="text-sm text-slate-500 mb-5">
                Enter the ID your admin gave you to get started.
              </p>

              <form onSubmit={handleContinue} className="space-y-4">
                <div>
                  <label className="block text-xs font-medium text-slate-600 mb-1.5">
                    Organization ID
                  </label>
                  <input
                    type="text"
                    value={ngoSlug}
                    onChange={(e) => setNgoSlug(e.target.value)}
                    placeholder="e.g. green-future-ngo"
                    autoFocus
                    required
                    className="w-full rounded-lg border border-slate-200 bg-white px-3 py-2.5 text-sm text-slate-900 placeholder:text-slate-400 focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:border-transparent"
                  />
                  <p className="text-xs text-slate-400 mt-1.5">
                    Lowercase, hyphen-separated. Ask your admin if unsure.
                  </p>
                </div>
                <button
                  type="submit"
                  disabled={!ngoSlug.trim()}
                  className="w-full flex items-center justify-center gap-2 h-10 rounded-lg bg-indigo-600 hover:bg-indigo-700 disabled:opacity-40 disabled:cursor-not-allowed text-sm font-medium text-white transition-colors"
                >
                  Continue
                  <ArrowRight className="h-4 w-4" />
                </button>
              </form>
            </>
          ) : (
            /* ── Step 2: Google sign-in ── */
            <>
              <div className="flex items-center gap-2 mb-5">
                <button
                  onClick={() => { setStep("ngo"); setLoading(false); }}
                  className="text-xs text-indigo-600 hover:underline"
                >
                  ← Change
                </button>
                <span className="text-xs text-slate-400">Organization:</span>
                <span className="text-xs font-semibold text-slate-700 bg-slate-100 px-2 py-0.5 rounded">
                  {ngoSlug}
                </span>
              </div>

              <h2 className="text-lg font-semibold text-slate-900 mb-1">Sign in</h2>
              <p className="text-sm text-slate-500 mb-6">
                Use your organization Google account to continue.
              </p>

              <button
                onClick={handleGoogleSignIn}
                disabled={loading}
                className="w-full flex items-center justify-center gap-3 h-11 rounded-lg border border-slate-200 bg-white hover:bg-slate-50 disabled:opacity-60 transition-colors text-sm font-medium text-slate-700 shadow-sm"
              >
                {loading ? (
                  <div className="h-4 w-4 rounded-full border-2 border-slate-400 border-t-transparent animate-spin" />
                ) : (
                  <svg viewBox="0 0 24 24" className="h-4 w-4" aria-hidden>
                    <path d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92c-.26 1.37-1.04 2.53-2.21 3.31v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.09z" fill="#4285F4" />
                    <path d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z" fill="#34A853" />
                    <path d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.07H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.93l2.85-2.22.81-.62z" fill="#FBBC05" />
                    <path d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.07l3.66 2.84c.87-2.6 3.3-4.53 6.16-4.53z" fill="#EA4335" />
                  </svg>
                )}
                Continue with Google
              </button>

              <p className="text-xs text-slate-400 text-center mt-5">
                Access is limited to staff registered by your NGO admin.
              </p>
            </>
          )}
        </div>
      </div>
    </div>
  );
}
