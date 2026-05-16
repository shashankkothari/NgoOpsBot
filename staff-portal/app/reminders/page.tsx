"use client";

import { useState } from "react";
import { useSession } from "next-auth/react";
import useSWR, { mutate } from "swr";
import {
  Bell,
  Plus,
  Check,
  Clock,
  X,
  Loader2,
  ChevronDown,
} from "lucide-react";
import { AppShell } from "@/app/components/layout/AppShell";
import { staffApi, apiFetcher } from "@/app/lib/api";
import { formatDateTime, cn } from "@/app/lib/utils";
import type { Reminder } from "@/app/lib/types";

const SNOOZE_OPTIONS = [
  { label: "1 hour", hours: 1 },
  { label: "4 hours", hours: 4 },
  { label: "1 day", hours: 24 },
  { label: "3 days", hours: 72 },
];

export default function RemindersPage() {
  const { data: session } = useSession();
  const token = session?.backendToken ?? "";

  const { data, isLoading } = useSWR(
    token ? "/api/v1/staff/reminders" : null,
    apiFetcher(token)
  ) as { data: { items: Reminder[] } | undefined; isLoading: boolean };

  const reminders = data?.items ?? [];
  const pending = reminders.filter((r) => !r.is_acknowledged);
  const done = reminders.filter((r) => r.is_acknowledged);

  const [showCreate, setShowCreate] = useState(false);
  const [snoozingId, setSnoozingId] = useState<string | null>(null);

  async function acknowledge(id: string) {
    await staffApi.acknowledgeReminder(token, id);
    mutate("/api/v1/staff/reminders");
  }

  async function snooze(id: string, hours: number) {
    await staffApi.snoozeReminder(token, id, hours);
    setSnoozingId(null);
    mutate("/api/v1/staff/reminders");
  }

  return (
    <AppShell>
      <div className="flex h-full overflow-hidden">
        {/* Reminder list */}
        <div className="flex-1 overflow-y-auto px-6 py-6">
          <div className="flex items-center justify-between mb-6">
            <div>
              <h1 className="text-xl font-bold text-slate-900">Reminders</h1>
              <p className="text-sm text-slate-400 mt-0.5">
                {pending.length} pending
              </p>
            </div>
            <button
              onClick={() => setShowCreate(true)}
              className="flex items-center gap-2 h-9 px-4 rounded-lg bg-indigo-600 text-white text-sm font-medium hover:bg-indigo-700 transition-colors"
            >
              <Plus className="h-4 w-4" />
              New Reminder
            </button>
          </div>

          {isLoading ? (
            <div className="flex items-center justify-center py-20">
              <Loader2 className="h-6 w-6 animate-spin text-slate-300" />
            </div>
          ) : pending.length === 0 ? (
            <div className="text-center py-20">
              <Bell className="h-10 w-10 text-slate-200 mx-auto mb-3" />
              <p className="text-slate-400">No pending reminders</p>
            </div>
          ) : (
            <div className="space-y-3">
              {pending.map((r) => (
                <ReminderCard
                  key={r.id}
                  reminder={r}
                  snoozingId={snoozingId}
                  setSnoozingId={setSnoozingId}
                  onAcknowledge={() => acknowledge(r.id)}
                  onSnooze={(hours) => snooze(r.id, hours)}
                />
              ))}
            </div>
          )}

          {done.length > 0 && (
            <div className="mt-8">
              <p className="text-xs font-semibold text-slate-400 uppercase tracking-wider mb-3">
                Completed
              </p>
              <div className="space-y-2">
                {done.map((r) => (
                  <div
                    key={r.id}
                    className="bg-white rounded-xl border border-slate-100 px-4 py-3 opacity-50"
                  >
                    <p className="text-sm text-slate-600 line-through">{r.title}</p>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>

        {/* Create panel */}
        {showCreate && (
          <CreateReminderPanel
            token={token}
            onClose={() => setShowCreate(false)}
          />
        )}
      </div>
    </AppShell>
  );
}

function ReminderCard({
  reminder: r,
  snoozingId,
  setSnoozingId,
  onAcknowledge,
  onSnooze,
}: {
  reminder: Reminder;
  snoozingId: string | null;
  setSnoozingId: (id: string | null) => void;
  onAcknowledge: () => void;
  onSnooze: (hours: number) => void;
}) {
  const isPast = new Date(r.due_at) < new Date();
  return (
    <div className="bg-white rounded-xl border border-slate-200 p-4 relative">
      <div className="flex items-start gap-3">
        <div
          className={cn(
            "h-9 w-9 rounded-lg flex items-center justify-center shrink-0",
            isPast ? "bg-red-50" : "bg-amber-50"
          )}
        >
          <Bell
            className={cn(
              "h-4 w-4",
              isPast ? "text-red-500" : "text-amber-500"
            )}
          />
        </div>
        <div className="flex-1 min-w-0">
          <p className="font-medium text-slate-900 text-sm">{r.title}</p>
          {r.message && (
            <p className="text-xs text-slate-500 mt-0.5 line-clamp-2">{r.message}</p>
          )}
          <p className={cn("text-xs mt-1.5", isPast ? "text-red-500" : "text-slate-400")}>
            {formatDateTime(r.due_at)}
            {isPast && " · Overdue"}
          </p>
        </div>
        <div className="flex items-center gap-1 shrink-0">
          <div className="relative">
            <button
              onClick={() => setSnoozingId(snoozingId === r.id ? null : r.id)}
              className="h-8 w-8 flex items-center justify-center rounded-lg text-slate-400 hover:bg-slate-100 transition-colors"
              title="Snooze"
            >
              <Clock className="h-4 w-4" />
            </button>
            {snoozingId === r.id && (
              <div className="absolute right-0 top-9 bg-white border border-slate-200 rounded-xl shadow-lg z-10 py-1 w-36">
                {SNOOZE_OPTIONS.map((opt) => (
                  <button
                    key={opt.hours}
                    onClick={() => onSnooze(opt.hours)}
                    className="w-full text-left px-4 py-2 text-sm text-slate-700 hover:bg-slate-50"
                  >
                    {opt.label}
                  </button>
                ))}
              </div>
            )}
          </div>
          <button
            onClick={onAcknowledge}
            className="h-8 w-8 flex items-center justify-center rounded-lg text-slate-400 hover:bg-green-50 hover:text-green-600 transition-colors"
            title="Mark done"
          >
            <Check className="h-4 w-4" />
          </button>
        </div>
      </div>
    </div>
  );
}

function CreateReminderPanel({
  token,
  onClose,
}: {
  token: string;
  onClose: () => void;
}) {
  const [form, setForm] = useState({
    title: "",
    message: "",
    scheduled_at: "",
    repeat: "one_time",
  });
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    if (!form.title || !form.scheduled_at || !form.message) return;
    setSaving(true);
    setError("");
    try {
      await staffApi.createReminder(token, {
        title: form.title,
        message: form.message,
        scheduled_at: new Date(form.scheduled_at).toISOString(),
        repeat: form.repeat,
        assignee_type: "all",
      });
      mutate("/api/v1/staff/reminders");
      onClose();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to create reminder");
    } finally {
      setSaving(false);
    }
  }

  return (
    <aside className="w-96 border-l border-slate-200 bg-white flex flex-col overflow-hidden">
      <div className="flex items-center justify-between px-6 py-4 border-b border-slate-100">
        <h2 className="font-semibold text-slate-900">New Reminder</h2>
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
            Title *
          </label>
          <input
            value={form.title}
            onChange={(e) => setForm({ ...form, title: e.target.value })}
            placeholder="e.g. Submit quarterly report"
            className="w-full rounded-lg border border-slate-200 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500"
            required
          />
        </div>

        <div>
          <label className="block text-xs font-medium text-slate-700 mb-1.5">
            Description *
          </label>
          <textarea
            value={form.message}
            onChange={(e) => setForm({ ...form, message: e.target.value })}
            placeholder="What needs to be done…"
            rows={3}
            className="w-full rounded-lg border border-slate-200 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500 resize-none"
            required
          />
        </div>

        <div>
          <label className="block text-xs font-medium text-slate-700 mb-1.5">
            Date & time *
          </label>
          <input
            type="datetime-local"
            value={form.scheduled_at}
            onChange={(e) => setForm({ ...form, scheduled_at: e.target.value })}
            className="w-full rounded-lg border border-slate-200 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500"
            required
          />
        </div>

        <div>
          <label className="block text-xs font-medium text-slate-700 mb-1.5">
            Repeat
          </label>
          <div className="relative">
            <select
              value={form.repeat}
              onChange={(e) => setForm({ ...form, repeat: e.target.value })}
              className="w-full appearance-none rounded-lg border border-slate-200 px-3 py-2 pr-8 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500"
            >
              <option value="one_time">No repeat</option>
              <option value="daily">Daily</option>
              <option value="weekly">Weekly</option>
              <option value="monthly">Monthly</option>
            </select>
            <ChevronDown className="pointer-events-none absolute right-2.5 top-1/2 -translate-y-1/2 h-4 w-4 text-slate-400" />
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
            Create
          </button>
        </div>
      </form>
    </aside>
  );
}
