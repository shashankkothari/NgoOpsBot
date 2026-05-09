"use client";

import { useState } from "react";
import useSWR from "swr";
import { Bell, Building2, Clock, CalendarDays } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import { Card, CardContent } from "@/components/ui/card";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Label } from "@/components/ui/label";
import {
  ngoApi,
  reminderApi,
  swrKeys,
  type Reminder,
  type NGO,
  type PaginatedResponse,
} from "@/lib/api";
import { formatDateTime, AGENT_LABELS } from "@/lib/utils";

export default function RemindersPage() {
  const [selectedNgoId, setSelectedNgoId] = useState<string>("");

  const { data: ngos } = useSWR<PaginatedResponse<NGO>>(
    swrKeys.ngos(),
    () => ngoApi.list({ page_size: 100 })
  );

  const { data: reminders, isLoading } = useSWR<PaginatedResponse<Reminder>>(
    selectedNgoId ? swrKeys.reminders(selectedNgoId) : null,
    () => reminderApi.list(selectedNgoId),
    { keepPreviousData: true }
  );

  return (
    <div className="space-y-6">
      {/* Header */}
      <div>
        <h1 className="text-2xl font-bold text-foreground">Reminders</h1>
        <p className="text-muted-foreground mt-1">
          View scheduled reminders configured per NGO.
        </p>
      </div>

      {/* NGO selector */}
      <div className="max-w-xs space-y-1.5">
        <Label>Select NGO</Label>
        <Select
          value={selectedNgoId}
          onValueChange={(v) => setSelectedNgoId(v === "none" ? "" : v)}
        >
          <SelectTrigger>
            <SelectValue placeholder="Choose an NGO..." />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="none">Select an NGO</SelectItem>
            {ngos?.items.map((ngo) => (
              <SelectItem key={ngo.id} value={ngo.id}>
                {ngo.name}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>

      {/* Content */}
      {!selectedNgoId ? (
        <div className="text-center py-20">
          <Building2 className="h-10 w-10 text-muted-foreground/30 mx-auto mb-3" />
          <p className="text-sm text-muted-foreground">
            Select an NGO to view its reminders
          </p>
        </div>
      ) : isLoading ? (
        <div className="space-y-3">
          {Array.from({ length: 4 }).map((_, i) => (
            <Skeleton key={i} className="h-28 w-full rounded-xl" />
          ))}
        </div>
      ) : reminders?.items.length ? (
        <div className="space-y-3">
          {reminders.items.map((reminder) => (
            <Card key={reminder.id}>
              <CardContent className="p-5">
                <div className="flex items-start justify-between gap-4">
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2 mb-2 flex-wrap">
                      <p className="font-semibold text-foreground">
                        {reminder.title}
                      </p>
                      <Badge variant={reminder.is_active ? "success" : "outline"}>
                        {reminder.is_active ? "Active" : "Paused"}
                      </Badge>
                    </div>
                    <p className="text-sm text-muted-foreground line-clamp-2 mb-3">
                      {reminder.message}
                    </p>
                    <div className="flex flex-wrap items-center gap-4">
                      <div className="flex items-center gap-1.5 text-xs text-muted-foreground">
                        <CalendarDays className="h-3.5 w-3.5" />
                        <code className="bg-muted px-1.5 py-0.5 rounded">
                          {reminder.schedule_cron}
                        </code>
                      </div>
                      {reminder.next_run_at && (
                        <div className="flex items-center gap-1.5 text-xs text-muted-foreground">
                          <Clock className="h-3.5 w-3.5" />
                          Next: {formatDateTime(reminder.next_run_at)}
                        </div>
                      )}
                      {reminder.last_sent_at && (
                        <div className="flex items-center gap-1.5 text-xs text-muted-foreground">
                          <Bell className="h-3.5 w-3.5" />
                          Last sent: {formatDateTime(reminder.last_sent_at)}
                        </div>
                      )}
                    </div>
                    {reminder.target_agents.length > 0 && (
                      <div className="flex flex-wrap gap-1.5 mt-3">
                        {reminder.target_agents.map((a) => (
                          <Badge key={a} variant="secondary" className="text-xs">
                            {AGENT_LABELS[a]}
                          </Badge>
                        ))}
                      </div>
                    )}
                  </div>
                </div>
              </CardContent>
            </Card>
          ))}
        </div>
      ) : (
        <div className="text-center py-20">
          <Bell className="h-10 w-10 text-muted-foreground/30 mx-auto mb-3" />
          <p className="text-sm text-muted-foreground">
            No reminders configured for this NGO
          </p>
        </div>
      )}
    </div>
  );
}
