"use client";

import { useSession } from "next-auth/react";
import { Settings, User, Shield } from "lucide-react";
import { AppShell } from "@/app/components/layout/AppShell";
import { AGENT_ICONS, AGENT_LABELS, ALL_AGENTS } from "@/app/lib/types";

export default function SettingsPage() {
  const { data: session } = useSession();
  const allowedAgents = session?.staffProfile?.allowed_agents ?? [];

  return (
    <AppShell>
      <div className="overflow-y-auto h-full px-6 py-6 max-w-2xl">
        <div className="mb-6">
          <h1 className="text-xl font-bold text-slate-900">Settings</h1>
          <p className="text-sm text-slate-400 mt-0.5">Your account preferences</p>
        </div>

        {/* Profile */}
        <section className="bg-white rounded-2xl border border-slate-200 p-6 mb-4">
          <h2 className="flex items-center gap-2 text-sm font-semibold text-slate-900 mb-4">
            <User className="h-4 w-4" /> Profile
          </h2>
          <div className="space-y-3">
            <Row label="Name" value={session?.staffProfile?.name ?? session?.user?.name ?? "—"} />
            <Row label="Email" value={session?.user?.email ?? "—"} />
            <Row label="Role" value={session?.staffProfile?.role ?? "—"} />
            <Row label="Organization" value={session?.staffProfile?.ngo_name ?? "—"} />
          </div>
        </section>

        {/* Agents */}
        <section className="bg-white rounded-2xl border border-slate-200 p-6">
          <h2 className="flex items-center gap-2 text-sm font-semibold text-slate-900 mb-4">
            <Shield className="h-4 w-4" /> Agent Access
          </h2>
          <p className="text-xs text-slate-500 mb-4">
            Agent access is managed by your NGO admin. Contact them to enable
            additional agents.
          </p>
          <div className="space-y-2">
            {ALL_AGENTS.map((agent) => {
              const enabled = allowedAgents.includes(agent);
              return (
                <div
                  key={agent}
                  className="flex items-center justify-between py-2.5"
                >
                  <div className="flex items-center gap-3">
                    <span className="text-xl">{AGENT_ICONS[agent]}</span>
                    <span className="text-sm text-slate-700">
                      {AGENT_LABELS[agent]}
                    </span>
                  </div>
                  <span
                    className={
                      enabled
                        ? "text-xs font-medium text-green-700 bg-green-50 px-2 py-0.5 rounded-full"
                        : "text-xs font-medium text-slate-400 bg-slate-100 px-2 py-0.5 rounded-full"
                    }
                  >
                    {enabled ? "Enabled" : "Locked"}
                  </span>
                </div>
              );
            })}
          </div>
        </section>
      </div>
    </AppShell>
  );
}

function Row({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex items-center justify-between py-1">
      <span className="text-sm text-slate-500">{label}</span>
      <span className="text-sm font-medium text-slate-900">{value}</span>
    </div>
  );
}
