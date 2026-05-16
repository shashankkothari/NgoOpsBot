"use client";

import { useState } from "react";
import { useSession } from "next-auth/react";
import useSWR, { mutate } from "swr";
import {
  HelpCircle,
  Plus,
  X,
  Loader2,
  ChevronDown,
  MessageSquare,
} from "lucide-react";
import { AppShell } from "@/app/components/layout/AppShell";
import { staffApi, apiFetcher } from "@/app/lib/api";
import { formatDate, cn } from "@/app/lib/utils";
import type { SupportTicket } from "@/app/lib/types";

const STATUS_LABELS: Record<string, string> = {
  open: "Open",
  in_progress: "In Progress",
  resolved: "Resolved",
  closed: "Closed",
};

const STATUS_COLORS: Record<string, string> = {
  open: "bg-blue-50 text-blue-700",
  in_progress: "bg-amber-50 text-amber-700",
  resolved: "bg-green-50 text-green-700",
  closed: "bg-slate-100 text-slate-500",
};

const PRIORITY_COLORS: Record<string, string> = {
  low: "bg-slate-100 text-slate-600",
  medium: "bg-amber-50 text-amber-700",
  high: "bg-orange-50 text-orange-700",
  urgent: "bg-red-50 text-red-700",
};

export default function SupportPage() {
  const { data: session } = useSession();
  const token = session?.backendToken ?? "";

  const { data, isLoading } = useSWR(
    token ? "/api/v1/staff/support" : null,
    apiFetcher(token)
  ) as { data: { items: SupportTicket[] } | undefined; isLoading: boolean };

  const tickets = data?.items ?? [];
  const [selected, setSelected] = useState<SupportTicket | null>(null);
  const [showCreate, setShowCreate] = useState(false);

  return (
    <AppShell>
      <div className="flex h-full overflow-hidden">
        {/* Ticket list */}
        <div className="flex-1 overflow-y-auto px-6 py-6">
          <div className="flex items-center justify-between mb-6">
            <div>
              <h1 className="text-xl font-bold text-slate-900">Help & Support</h1>
              <p className="text-sm text-slate-400 mt-0.5">
                {tickets.length} ticket{tickets.length !== 1 ? "s" : ""}
              </p>
            </div>
            <button
              onClick={() => setShowCreate(true)}
              className="flex items-center gap-2 h-9 px-4 rounded-lg bg-indigo-600 text-white text-sm font-medium hover:bg-indigo-700 transition-colors"
            >
              <Plus className="h-4 w-4" />
              New Request
            </button>
          </div>

          {isLoading ? (
            <div className="flex items-center justify-center py-20">
              <Loader2 className="h-6 w-6 animate-spin text-slate-300" />
            </div>
          ) : tickets.length === 0 ? (
            <div className="text-center py-20">
              <HelpCircle className="h-10 w-10 text-slate-200 mx-auto mb-3" />
              <p className="text-slate-400">No support requests yet</p>
              <p className="text-sm text-slate-400 mt-1">
                Submit a request if you need help from admin
              </p>
            </div>
          ) : (
            <div className="space-y-3">
              {tickets.map((t) => (
                <button
                  key={t.id}
                  onClick={() => setSelected(t)}
                  className={cn(
                    "w-full text-left bg-white rounded-xl border px-4 py-4 transition-colors",
                    selected?.id === t.id
                      ? "border-indigo-300 ring-1 ring-indigo-300"
                      : "border-slate-200 hover:border-slate-300"
                  )}
                >
                  <div className="flex items-start justify-between gap-3">
                    <div className="flex-1 min-w-0">
                      <p className="font-medium text-slate-900 text-sm truncate">
                        {t.title}
                      </p>
                      <p className="text-xs text-slate-500 mt-0.5 line-clamp-1">
                        {t.description}
                      </p>
                    </div>
                    <span
                      className={cn(
                        "text-xs font-medium px-2 py-0.5 rounded-full shrink-0",
                        STATUS_COLORS[t.status]
                      )}
                    >
                      {STATUS_LABELS[t.status]}
                    </span>
                  </div>
                  <div className="flex items-center gap-3 mt-2">
                    <span
                      className={cn(
                        "text-xs px-1.5 py-0.5 rounded",
                        PRIORITY_COLORS[t.priority]
                      )}
                    >
                      {t.priority}
                    </span>
                    <span className="text-xs text-slate-400">
                      {formatDate(t.created_at)}
                    </span>
                    {t.admin_reply && (
                      <span className="flex items-center gap-1 text-xs text-green-600">
                        <MessageSquare className="h-3 w-3" />
                        Reply received
                      </span>
                    )}
                  </div>
                </button>
              ))}
            </div>
          )}
        </div>

        {/* Detail panel */}
        {selected && (
          <TicketDetail ticket={selected} onClose={() => setSelected(null)} />
        )}

        {/* Create panel */}
        {showCreate && (
          <CreateTicketPanel
            token={token}
            onClose={() => setShowCreate(false)}
          />
        )}
      </div>
    </AppShell>
  );
}

function TicketDetail({
  ticket: t,
  onClose,
}: {
  ticket: SupportTicket;
  onClose: () => void;
}) {
  return (
    <aside className="w-96 border-l border-slate-200 bg-white flex flex-col overflow-hidden">
      <div className="flex items-center justify-between px-6 py-4 border-b border-slate-100">
        <h2 className="font-semibold text-slate-900 truncate">{t.title}</h2>
        <button
          onClick={onClose}
          className="h-8 w-8 flex items-center justify-center rounded-lg text-slate-400 hover:bg-slate-100 transition-colors ml-2 shrink-0"
        >
          <X className="h-4 w-4" />
        </button>
      </div>

      <div className="flex-1 overflow-y-auto p-6 space-y-5">
        <div className="flex gap-2">
          <span
            className={cn(
              "text-xs font-medium px-2 py-1 rounded-full",
              STATUS_COLORS[t.status]
            )}
          >
            {STATUS_LABELS[t.status]}
          </span>
          <span
            className={cn(
              "text-xs font-medium px-2 py-1 rounded-full capitalize",
              PRIORITY_COLORS[t.priority]
            )}
          >
            {t.priority} priority
          </span>
        </div>

        <div>
          <p className="text-xs font-medium text-slate-500 mb-1">Description</p>
          <p className="text-sm text-slate-700 whitespace-pre-wrap">{t.description}</p>
        </div>

        <div className="grid grid-cols-2 gap-4 text-xs">
          <div>
            <p className="text-slate-500">Category</p>
            <p className="font-medium text-slate-700 capitalize mt-0.5">{t.category}</p>
          </div>
          <div>
            <p className="text-slate-500">Submitted</p>
            <p className="font-medium text-slate-700 mt-0.5">{formatDate(t.created_at)}</p>
          </div>
        </div>

        {t.admin_reply ? (
          <div className="bg-green-50 rounded-xl p-4">
            <p className="text-xs font-semibold text-green-700 mb-2">
              Admin Reply
            </p>
            <p className="text-sm text-green-800 whitespace-pre-wrap">
              {t.admin_reply}
            </p>
          </div>
        ) : (
          <div className="bg-slate-50 rounded-xl p-4 text-center">
            <p className="text-sm text-slate-400">
              Awaiting admin response
            </p>
            <p className="text-xs text-slate-400 mt-1">
              You will receive a Telegram notification when replied.
            </p>
          </div>
        )}
      </div>
    </aside>
  );
}

function CreateTicketPanel({
  token,
  onClose,
}: {
  token: string;
  onClose: () => void;
}) {
  const [form, setForm] = useState({
    title: "",
    description: "",
    category: "other",
    priority: "medium",
  });
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    if (!form.title || !form.description) return;
    setSaving(true);
    setError("");
    try {
      await staffApi.createTicket(token, form);
      mutate("/api/v1/staff/support");
      onClose();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to submit ticket");
    } finally {
      setSaving(false);
    }
  }

  return (
    <aside className="w-96 border-l border-slate-200 bg-white flex flex-col overflow-hidden">
      <div className="flex items-center justify-between px-6 py-4 border-b border-slate-100">
        <h2 className="font-semibold text-slate-900">New Support Request</h2>
        <button
          onClick={onClose}
          className="h-8 w-8 flex items-center justify-center rounded-lg text-slate-400 hover:bg-slate-100 transition-colors"
        >
          <X className="h-4 w-4" />
        </button>
      </div>

      <form onSubmit={submit} className="flex-1 overflow-y-auto p-6 space-y-4">
        <div>
          <label className="block text-xs font-medium text-slate-700 mb-1.5">
            Subject *
          </label>
          <input
            value={form.title}
            onChange={(e) => setForm({ ...form, title: e.target.value })}
            placeholder="Brief description of your issue"
            className="w-full rounded-lg border border-slate-200 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500"
            required
          />
        </div>

        <div>
          <label className="block text-xs font-medium text-slate-700 mb-1.5">
            Details *
          </label>
          <textarea
            value={form.description}
            onChange={(e) => setForm({ ...form, description: e.target.value })}
            placeholder="Describe your issue in detail…"
            rows={5}
            className="w-full rounded-lg border border-slate-200 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500 resize-none"
            required
          />
        </div>

        <div className="grid grid-cols-2 gap-3">
          <div>
            <label className="block text-xs font-medium text-slate-700 mb-1.5">
              Category
            </label>
            <div className="relative">
              <select
                value={form.category}
                onChange={(e) => setForm({ ...form, category: e.target.value })}
                className="w-full appearance-none rounded-lg border border-slate-200 px-3 py-2 pr-8 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500"
              >
                <option value="access_request">Access Request</option>
                <option value="technical">Technical</option>
                <option value="agent_behaviour">Agent Behaviour</option>
                <option value="other">Other</option>
              </select>
              <ChevronDown className="pointer-events-none absolute right-2.5 top-1/2 -translate-y-1/2 h-4 w-4 text-slate-400" />
            </div>
          </div>
          <div>
            <label className="block text-xs font-medium text-slate-700 mb-1.5">
              Priority
            </label>
            <div className="relative">
              <select
                value={form.priority}
                onChange={(e) => setForm({ ...form, priority: e.target.value })}
                className="w-full appearance-none rounded-lg border border-slate-200 px-3 py-2 pr-8 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500"
              >
                <option value="low">Low</option>
                <option value="medium">Medium</option>
                <option value="high">High</option>
              </select>
              <ChevronDown className="pointer-events-none absolute right-2.5 top-1/2 -translate-y-1/2 h-4 w-4 text-slate-400" />
            </div>
          </div>
        </div>

        {error && (
          <p className="text-sm text-red-600 bg-red-50 rounded-lg px-3 py-2">
            {error}
          </p>
        )}

        <div className="pt-2 flex gap-2">
          <button
            type="button"
            onClick={onClose}
            className="flex-1 h-9 rounded-lg border border-slate-200 text-sm text-slate-700 hover:bg-slate-50 transition-colors"
          >
            Cancel
          </button>
          <button
            type="submit"
            disabled={saving}
            className="flex-1 h-9 rounded-lg bg-indigo-600 text-white text-sm font-medium hover:bg-indigo-700 disabled:opacity-50 transition-colors flex items-center justify-center gap-2"
          >
            {saving && <Loader2 className="h-4 w-4 animate-spin" />}
            Submit
          </button>
        </div>
      </form>
    </aside>
  );
}
