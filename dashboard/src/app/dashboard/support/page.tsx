"use client";

import { useState, useEffect } from "react";
import useSWR, { mutate } from "swr";
import {
  LifeBuoy,
  X,
  Loader2,
  MessageSquare,
  Check,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Label } from "@/components/ui/label";
import {
  supportApi,
  ngoApi,
  swrKeys,
  type SupportTicket,
  type PaginatedResponse,
  type NGO,
} from "@/lib/api";
import { formatDateTime } from "@/lib/utils";

const STATUS_COLORS: Record<string, string> = {
  open: "bg-blue-50 text-blue-700 border-blue-200",
  in_progress: "bg-amber-50 text-amber-700 border-amber-200",
  resolved: "bg-green-50 text-green-700 border-green-200",
  closed: "bg-slate-100 text-slate-600 border-slate-200",
};

const STATUS_LABELS: Record<string, string> = {
  open: "Open",
  in_progress: "In Progress",
  resolved: "Resolved",
  closed: "Closed",
};

const PRIORITY_COLORS: Record<string, string> = {
  low: "bg-slate-100 text-slate-600",
  medium: "bg-amber-50 text-amber-700",
  high: "bg-orange-50 text-orange-700",
  urgent: "bg-red-50 text-red-700",
};


export default function SupportQueuePage() {
  const [selectedTicket, setSelectedTicket] = useState<SupportTicket | null>(null);
  const [filterNgo, setFilterNgo] = useState<string>("all");
  const [filterStatus, setFilterStatus] = useState<string>("all");
  const [filterPriority, setFilterPriority] = useState<string>("all");

  const { data: ngosData } = useSWR(
    swrKeys.ngos(),
    () => ngoApi.list({ page_size: 100 })
  ) as { data: PaginatedResponse<NGO> | undefined };

  const ngoFilter = filterNgo === "all" ? undefined : filterNgo;
  const statusFilter = filterStatus === "all" ? undefined : filterStatus;
  const priorityFilter = filterPriority === "all" ? undefined : filterPriority;

  const swrKey = swrKeys.support({
    ngo_id: ngoFilter,
    status: statusFilter,
    priority: priorityFilter,
  });

  const { data, isLoading } = useSWR(swrKey, () =>
    supportApi.list({
      ngo_id: ngoFilter,
      status: statusFilter,
      priority: priorityFilter,
      page_size: 50,
    })
  ) as { data: PaginatedResponse<SupportTicket> | undefined; isLoading: boolean };

  const tickets = data?.items ?? [];

  function clearFilters() {
    setFilterNgo("all");
    setFilterStatus("all");
    setFilterPriority("all");
  }

  const hasFilters = filterNgo !== "all" || filterStatus !== "all" || filterPriority !== "all";

  return (
    <div className="flex h-full overflow-hidden">
      {/* Left: ticket list */}
      <div className="flex-1 overflow-y-auto p-6 min-w-0">
        {/* Header */}
        <div className="flex items-center justify-between mb-6">
          <div>
            <h1 className="text-2xl font-bold text-foreground flex items-center gap-2">
              <LifeBuoy className="h-6 w-6 text-primary" />
              Support Queue
            </h1>
            <p className="text-sm text-muted-foreground mt-0.5">
              {data?.total ?? 0} ticket{(data?.total ?? 0) !== 1 ? "s" : ""}
            </p>
          </div>
        </div>

        {/* Filters */}
        <div className="flex flex-wrap gap-3 mb-6">
          <div className="w-48">
            <Select value={filterNgo} onValueChange={setFilterNgo}>
              <SelectTrigger>
                <SelectValue placeholder="All NGOs" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="all">All NGOs</SelectItem>
                {ngosData?.items.map((ngo) => (
                  <SelectItem key={ngo.id} value={ngo.id}>
                    {ngo.name}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          <div className="w-40">
            <Select value={filterStatus} onValueChange={setFilterStatus}>
              <SelectTrigger>
                <SelectValue placeholder="All Statuses" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="all">All Statuses</SelectItem>
                <SelectItem value="open">Open</SelectItem>
                <SelectItem value="in_progress">In Progress</SelectItem>
                <SelectItem value="resolved">Resolved</SelectItem>
                <SelectItem value="closed">Closed</SelectItem>
              </SelectContent>
            </Select>
          </div>
          <div className="w-36">
            <Select value={filterPriority} onValueChange={setFilterPriority}>
              <SelectTrigger>
                <SelectValue placeholder="All Priorities" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="all">All Priorities</SelectItem>
                <SelectItem value="urgent">Urgent</SelectItem>
                <SelectItem value="high">High</SelectItem>
                <SelectItem value="medium">Medium</SelectItem>
                <SelectItem value="low">Low</SelectItem>
              </SelectContent>
            </Select>
          </div>
          {hasFilters && (
            <Button variant="ghost" size="sm" onClick={clearFilters} className="gap-1.5">
              <X className="h-3.5 w-3.5" />
              Clear
            </Button>
          )}
        </div>

        {/* Ticket list */}
        {isLoading ? (
          <div className="space-y-3">
            {Array.from({ length: 5 }).map((_, i) => (
              <Skeleton key={i} className="h-24 w-full rounded-xl" />
            ))}
          </div>
        ) : tickets.length === 0 ? (
          <div className="text-center py-20">
            <LifeBuoy className="h-10 w-10 text-muted-foreground/30 mx-auto mb-3" />
            <p className="text-muted-foreground">No tickets found</p>
          </div>
        ) : (
          <div className="space-y-3">
            {tickets.map((t) => (
              <button
                key={t.id}
                onClick={() => setSelectedTicket(t)}
                className={`w-full text-left rounded-xl border p-4 transition-colors hover:border-primary/30 hover:bg-accent/30 ${
                  selectedTicket?.id === t.id
                    ? "border-primary/50 bg-accent/50 ring-1 ring-primary/30"
                    : "border-border bg-card"
                }`}
              >
                <div className="flex items-start justify-between gap-3">
                  <div className="flex-1 min-w-0">
                    <p className="font-medium text-sm text-foreground truncate">
                      {t.title}
                    </p>
                    <p className="text-xs text-muted-foreground mt-0.5 line-clamp-1">
                      {t.description}
                    </p>
                  </div>
                  <Badge
                    variant="outline"
                    className={`shrink-0 text-xs ${STATUS_COLORS[t.status]}`}
                  >
                    {STATUS_LABELS[t.status]}
                  </Badge>
                </div>
                <div className="flex items-center gap-3 mt-2.5 flex-wrap">
                  <Badge
                    variant="outline"
                    className={`text-xs capitalize ${PRIORITY_COLORS[t.priority]}`}
                  >
                    {t.priority}
                  </Badge>
                  <span className="text-xs text-muted-foreground">
                    {t.ngo_name}
                  </span>
                  <span className="text-xs text-muted-foreground">
                    by {t.created_by_name}
                  </span>
                  <span className="text-xs text-muted-foreground ml-auto">
                    {formatDateTime(t.created_at)}
                  </span>
                </div>
              </button>
            ))}
          </div>
        )}
      </div>

      {/* Right: detail + reply panel */}
      {selectedTicket && (
        <TicketDetailPanel
          ticket={selectedTicket}
          onClose={() => setSelectedTicket(null)}
          onUpdated={(updated) => {
            setSelectedTicket(updated);
            mutate(swrKey);
          }}
        />
      )}
    </div>
  );
}

function TicketDetailPanel({
  ticket: t,
  onClose,
  onUpdated,
}: {
  ticket: SupportTicket;
  onClose: () => void;
  onUpdated: (updated: SupportTicket) => void;
}) {
  const [reply, setReply] = useState(t.admin_reply ?? "");
  const [status, setStatus] = useState<SupportTicket["status"]>(t.status);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const [saved, setSaved] = useState(false);

  useEffect(() => {
    setReply(t.admin_reply ?? "");
    setStatus(t.status);
    setError("");
    setSaved(false);
  }, [t.id]);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setSaving(true);
    setError("");
    try {
      const updated = await supportApi.update(t.id, {
        status,
        admin_reply: reply || undefined,
      });
      setSaved(true);
      setTimeout(() => setSaved(false), 2000);
      onUpdated(updated);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to save");
    } finally {
      setSaving(false);
    }
  }

  return (
    <aside className="w-[420px] border-l border-border bg-card flex flex-col overflow-hidden shrink-0">
      <div className="flex items-center justify-between px-6 py-4 border-b border-border">
        <h2 className="font-semibold text-foreground truncate pr-2">{t.title}</h2>
        <button
          onClick={onClose}
          className="h-8 w-8 flex items-center justify-center rounded-lg text-muted-foreground hover:bg-accent transition-colors shrink-0"
        >
          <X className="h-4 w-4" />
        </button>
      </div>

      <div className="flex-1 overflow-y-auto p-6 space-y-5">
        {/* Meta */}
        <div className="flex flex-wrap gap-2">
          <Badge variant="outline" className={`text-xs ${STATUS_COLORS[t.status]}`}>
            {STATUS_LABELS[t.status]}
          </Badge>
          <Badge
            variant="outline"
            className={`text-xs capitalize ${PRIORITY_COLORS[t.priority]}`}
          >
            {t.priority} priority
          </Badge>
        </div>

        <div className="grid grid-cols-2 gap-3 text-xs">
          <div>
            <p className="text-muted-foreground">NGO</p>
            <p className="font-medium text-foreground mt-0.5">{t.ngo_name}</p>
          </div>
          <div>
            <p className="text-muted-foreground">Submitted by</p>
            <p className="font-medium text-foreground mt-0.5">{t.created_by_name}</p>
          </div>
          <div>
            <p className="text-muted-foreground">Category</p>
            <p className="font-medium text-foreground capitalize mt-0.5">{t.category}</p>
          </div>
          <div>
            <p className="text-muted-foreground">Date</p>
            <p className="font-medium text-foreground mt-0.5">{formatDateTime(t.created_at)}</p>
          </div>
        </div>

        <div>
          <p className="text-xs font-medium text-muted-foreground mb-1.5">Description</p>
          <p className="text-sm text-foreground whitespace-pre-wrap bg-muted/40 rounded-lg px-3 py-3">
            {t.description}
          </p>
        </div>

        {/* Reply form */}
        <form onSubmit={submit} className="space-y-4">
          <div>
            <Label className="text-xs font-medium">Update Status</Label>
            <Select
              value={status}
              onValueChange={(v) => setStatus(v as SupportTicket["status"])}
            >
              <SelectTrigger className="mt-1.5">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="open">Open</SelectItem>
                <SelectItem value="in_progress">In Progress</SelectItem>
                <SelectItem value="resolved">Resolved</SelectItem>
                <SelectItem value="closed">Closed</SelectItem>
              </SelectContent>
            </Select>
          </div>

          <div>
            <Label className="text-xs font-medium">Reply to Staff</Label>
            <textarea
              value={reply}
              onChange={(e) => setReply(e.target.value)}
              placeholder="Type your reply here… Staff will be notified via Telegram."
              rows={5}
              className="mt-1.5 w-full rounded-lg border border-input bg-background px-3 py-2 text-sm placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-ring resize-none"
            />
          </div>

          {error && (
            <p className="text-xs text-destructive bg-destructive/10 rounded-lg px-3 py-2">
              {error}
            </p>
          )}

          <Button type="submit" disabled={saving} className="w-full gap-2">
            {saving ? (
              <Loader2 className="h-4 w-4 animate-spin" />
            ) : saved ? (
              <Check className="h-4 w-4" />
            ) : (
              <MessageSquare className="h-4 w-4" />
            )}
            {saved ? "Saved!" : "Save & Notify Staff"}
          </Button>
        </form>
      </div>
    </aside>
  );
}
