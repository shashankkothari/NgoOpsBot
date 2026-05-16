"use client";

import { useState } from "react";
import { useParams, useRouter } from "next/navigation";
import Link from "next/link";
import useSWR from "swr";
import {
  ArrowLeft,
  Edit,
  CheckCircle2,
  XCircle,
  Globe,
  Users,
  MessageSquare,
  Bell,
  Loader2,
  Clock,
  Copy,
  RefreshCw,
  AlertTriangle,
  Link2,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
  CardDescription,
} from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import {
  Sheet,
  SheetContent,
  SheetHeader,
  SheetTitle,
  SheetDescription,
} from "@/components/ui/sheet";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import {
  ngoApi,
  staffApi,
  reminderApi,
  swrKeys,
  type NGO,
  type NGOStats,
  type Staff,
  type StaffCreate,
  type Reminder,
} from "@/lib/api";
import { formatDate, formatDateTime, AGENT_LABELS } from "@/lib/utils";
import { NGOForm } from "@/components/ngos/ngo-form";
import { StaffForm } from "@/components/ngos/staff-form";
import { AgentSettingsPanel } from "@/components/ngos/agent-settings";
import { useToast } from "@/components/ui/use-toast";
import { Switch } from "@/components/ui/switch";

// ─── Staff Tab ────────────────────────────────────────────────────────────────

function StaffTab({ ngoId }: { ngoId: string }) {
  const { toast } = useToast();
  const [addOpen, setAddOpen] = useState(false);
  const [editStaff, setEditStaff] = useState<Staff | null>(null);

  const { data, isLoading, mutate } = useSWR(
    swrKeys.staff(ngoId),
    () => staffApi.list(ngoId)
  );

  const handleAdd = async (formData: StaffCreate) => {
    try {
      await staffApi.create(ngoId, formData);
      await mutate();
      setAddOpen(false);
      toast({ title: "Staff member added" });
    } catch (err) {
      toast({
        title: "Failed to add staff",
        description: err instanceof Error ? err.message : "Unknown error",
        variant: "destructive",
      });
    }
  };

  const handleEdit = async (formData: Parameters<typeof staffApi.update>[2]) => {
    if (!editStaff) return;
    try {
      await staffApi.update(ngoId, editStaff.id, formData);
      await mutate();
      setEditStaff(null);
      toast({ title: "Staff updated" });
    } catch (err) {
      toast({
        title: "Failed to update staff",
        description: err instanceof Error ? err.message : "Unknown error",
        variant: "destructive",
      });
    }
  };

  const handleToggleActive = async (staff: Staff) => {
    try {
      await staffApi.toggleActive(ngoId, staff.id, !staff.is_active);
      await mutate();
    } catch {
      toast({ title: "Failed to update status", variant: "destructive" });
    }
  };

  return (
    <>
      <div className="flex items-center justify-between mb-4">
        <p className="text-sm text-muted-foreground">
          {data?.total ?? 0} staff members
        </p>
        <Button size="sm" onClick={() => setAddOpen(true)}>
          <Users className="mr-1.5 h-3.5 w-3.5" />
          Add Staff
        </Button>
      </div>

      <Card>
        <CardContent className="p-0">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Name</TableHead>
                <TableHead>Telegram ID</TableHead>
                <TableHead>Role</TableHead>
                <TableHead>Agents</TableHead>
                <TableHead>Active</TableHead>
                <TableHead className="w-10" />
              </TableRow>
            </TableHeader>
            <TableBody>
              {isLoading ? (
                Array.from({ length: 4 }).map((_, i) => (
                  <TableRow key={i}>
                    {Array.from({ length: 6 }).map((_, j) => (
                      <TableCell key={j}>
                        <Skeleton className="h-4 w-full" />
                      </TableCell>
                    ))}
                  </TableRow>
                ))
              ) : data?.items.length ? (
                data.items.map((member) => (
                  <TableRow key={member.id}>
                    <TableCell className="font-medium">{member.name}</TableCell>
                    <TableCell>
                      <code className="text-xs bg-muted px-1.5 py-0.5 rounded">
                        {member.telegram_user_id}
                      </code>
                    </TableCell>
                    <TableCell>
                      <Badge variant="secondary" className="capitalize">
                        {member.role}
                      </Badge>
                    </TableCell>
                    <TableCell>
                      <div className="flex flex-wrap gap-1">
                        {member.allowed_agents.length ? (
                          member.allowed_agents.map((a) => (
                            <Badge key={a} variant="outline" className="text-xs">
                              {AGENT_LABELS[a]}
                            </Badge>
                          ))
                        ) : (
                          <span className="text-xs text-muted-foreground">None</span>
                        )}
                      </div>
                    </TableCell>
                    <TableCell>
                      <Switch
                        checked={member.is_active}
                        onCheckedChange={() => handleToggleActive(member)}
                      />
                    </TableCell>
                    <TableCell>
                      <Button
                        variant="ghost"
                        size="icon"
                        className="h-8 w-8"
                        onClick={() => setEditStaff(member)}
                      >
                        <Edit className="h-3.5 w-3.5" />
                      </Button>
                    </TableCell>
                  </TableRow>
                ))
              ) : (
                <TableRow>
                  <TableCell colSpan={6} className="text-center py-10">
                    <p className="text-sm text-muted-foreground">
                      No staff members yet
                    </p>
                  </TableCell>
                </TableRow>
              )}
            </TableBody>
          </Table>
        </CardContent>
      </Card>

      {/* Add Staff Sheet */}
      <Sheet open={addOpen} onOpenChange={setAddOpen}>
        <SheetContent className="overflow-y-auto">
          <SheetHeader>
            <SheetTitle>Add Staff Member</SheetTitle>
            <SheetDescription>
              Add a new staff member to this NGO.
            </SheetDescription>
          </SheetHeader>
          <div className="mt-6">
            <StaffForm
              onSubmit={handleAdd}
              onCancel={() => setAddOpen(false)}
            />
          </div>
        </SheetContent>
      </Sheet>

      {/* Edit Staff Sheet */}
      <Sheet open={!!editStaff} onOpenChange={(o) => !o && setEditStaff(null)}>
        <SheetContent className="overflow-y-auto">
          <SheetHeader>
            <SheetTitle>Edit Staff Member</SheetTitle>
            <SheetDescription>Update staff details and access.</SheetDescription>
          </SheetHeader>
          <div className="mt-6">
            {editStaff && (
              <StaffForm
                staff={editStaff}
                onSubmit={handleEdit}
                onCancel={() => setEditStaff(null)}
                isEdit
              />
            )}
          </div>
        </SheetContent>
      </Sheet>
    </>
  );
}

// ─── Reminders Tab ────────────────────────────────────────────────────────────

function RemindersTab({ ngoId }: { ngoId: string }) {
  const { data, isLoading } = useSWR<Reminder[]>(
    swrKeys.reminders(ngoId),
    () => reminderApi.list(ngoId)
  );

  return (
    <div className="space-y-3">
      {isLoading ? (
        Array.from({ length: 3 }).map((_, i) => (
          <Skeleton key={i} className="h-20 w-full rounded-xl" />
        ))
      ) : data?.length ? (
        data.map((reminder) => (
          <Card key={reminder.id}>
            <CardContent className="p-4">
              <div className="flex items-start justify-between gap-3">
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2 mb-1">
                    <p className="font-medium text-sm">{reminder.title}</p>
                    <Badge variant="secondary" className="text-xs capitalize">
                      {reminder.reminder_type}
                    </Badge>
                    <Badge variant={reminder.is_active ? "success" : "outline"}>
                      {reminder.is_active ? "Active" : "Paused"}
                    </Badge>
                  </div>
                  <p className="text-xs text-muted-foreground">
                    Agent: {AGENT_LABELS[reminder.agent_name]} · {reminder.target_audience}
                  </p>
                  <div className="flex items-center gap-3 mt-2">
                    {reminder.next_fire_at && (
                      <div className="flex items-center gap-1 text-xs text-muted-foreground">
                        <Clock className="h-3 w-3" />
                        Next: {formatDateTime(reminder.next_fire_at)}
                      </div>
                    )}
                    {reminder.last_fired_at && (
                      <p className="text-xs text-muted-foreground">
                        Last: {formatDateTime(reminder.last_fired_at)}
                      </p>
                    )}
                  </div>
                </div>
              </div>
            </CardContent>
          </Card>
        ))
      ) : (
        <div className="text-center py-10">
          <Bell className="h-8 w-8 text-muted-foreground/40 mx-auto mb-2" />
          <p className="text-sm text-muted-foreground">No reminders configured</p>
        </div>
      )}
    </div>
  );
}

// ─── Main Page ────────────────────────────────────────────────────────────────

export default function NGODetailPage() {
  const params = useParams();
  const router = useRouter();
  const { toast } = useToast();
  const ngoId = params.id as string;
  const [editOpen, setEditOpen] = useState(false);
  const [refreshingWebhook, setRefreshingWebhook] = useState(false);
  const [deactivating, setDeactivating] = useState(false);
  const [copied, setCopied] = useState(false);

  const { data: ngo, isLoading, mutate } = useSWR<NGO>(
    swrKeys.ngo(ngoId),
    () => ngoApi.get(ngoId)
  );

  const { data: stats } = useSWR<NGOStats>(
    swrKeys.ngoStats(ngoId),
    () => ngoApi.stats(ngoId),
    { refreshInterval: 60000 }
  );

  const [webhookUrl, setWebhookUrl] = useState<string>("");

  const copyWebhook = (url: string) => {
    navigator.clipboard.writeText(url);
    setCopied(true);
    setTimeout(() => setCopied(false), 1500);
  };

  const handleRefreshWebhook = async () => {
    setRefreshingWebhook(true);
    try {
      const result = await ngoApi.refreshWebhook(ngoId);
      const url = result.webhook_url ?? Object.values(result)[0] ?? "";
      setWebhookUrl(url);
      await mutate();
      toast({ title: "Webhook refreshed and re-registered with Telegram" });
    } catch (err) {
      toast({
        title: "Failed to refresh webhook",
        description: err instanceof Error ? err.message : "Unknown error",
        variant: "destructive",
      });
    } finally {
      setRefreshingWebhook(false);
    }
  };

  const handleDeactivate = async () => {
    if (!confirm(`Deactivate ${ngo?.name}? This will stop all bot messages.`)) return;
    setDeactivating(true);
    try {
      await ngoApi.deactivate(ngoId);
      await mutate();
      toast({ title: "NGO deactivated" });
    } catch (err) {
      toast({
        title: "Failed to deactivate NGO",
        description: err instanceof Error ? err.message : "Unknown error",
        variant: "destructive",
      });
    } finally {
      setDeactivating(false);
    }
  };

  const handleEdit = async (formData: Parameters<typeof ngoApi.update>[1]) => {
    try {
      await ngoApi.update(ngoId, formData);
      await mutate();
      setEditOpen(false);
      toast({ title: "NGO updated successfully" });
    } catch (err) {
      toast({
        title: "Failed to update NGO",
        description: err instanceof Error ? err.message : "Unknown error",
        variant: "destructive",
      });
    }
  };

  if (isLoading) {
    return (
      <div className="space-y-6">
        <Skeleton className="h-8 w-64" />
        <Skeleton className="h-32 w-full rounded-xl" />
        <Skeleton className="h-80 w-full rounded-xl" />
      </div>
    );
  }

  if (!ngo) {
    return (
      <div className="text-center py-20">
        <p className="text-muted-foreground">NGO not found</p>
        <Button variant="outline" className="mt-4" onClick={() => router.back()}>
          Go back
        </Button>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* Back + Header */}
      <div>
        <Link href="/dashboard/ngos">
          <Button variant="ghost" size="sm" className="gap-1.5 -ml-2 mb-3 text-muted-foreground">
            <ArrowLeft className="h-3.5 w-3.5" />
            All NGOs
          </Button>
        </Link>
        <div className="flex items-start justify-between gap-4">
          <div>
            <h1 className="text-2xl font-bold text-foreground flex items-center gap-3">
              {ngo.name}
              {ngo.is_active ? (
                <Badge variant="success" className="text-xs">Active</Badge>
              ) : (
                <Badge variant="outline" className="text-xs">Inactive</Badge>
              )}
            </h1>
            <p className="text-muted-foreground mt-1 font-mono text-sm">
              {ngo.slug}
            </p>
          </div>
          <Button variant="outline" size="sm" onClick={() => setEditOpen(true)}>
            <Edit className="mr-1.5 h-3.5 w-3.5" />
            Edit NGO
          </Button>
        </div>
      </div>

      {/* Info cards */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-4">
        <Card>
          <CardContent className="p-4">
            <div className="flex items-center gap-2 mb-1">
              <Globe className="h-3.5 w-3.5 text-muted-foreground" />
              <p className="text-xs text-muted-foreground">Timezone</p>
            </div>
            <p className="text-sm font-medium">{ngo.timezone}</p>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="p-4">
            <div className="flex items-center gap-2 mb-1">
              <Globe className="h-3.5 w-3.5 text-muted-foreground" />
              <p className="text-xs text-muted-foreground">Language</p>
            </div>
            <p className="text-sm font-medium uppercase">{ngo.language}</p>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="p-4">
            <div className="flex items-center gap-2 mb-1">
              <Users className="h-3.5 w-3.5 text-muted-foreground" />
              <p className="text-xs text-muted-foreground">Staff</p>
            </div>
            <p className="text-sm font-medium">{stats?.active_staff_count ?? "—"}</p>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="p-4">
            <div className="flex items-center gap-2 mb-1">
              <Clock className="h-3.5 w-3.5 text-muted-foreground" />
              <p className="text-xs text-muted-foreground">Created</p>
            </div>
            <p className="text-sm font-medium">{formatDate(ngo.created_at)}</p>
          </CardContent>
        </Card>
      </div>

      {/* Activity stats */}
      {stats && (
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-4">
          <Card>
            <CardContent className="p-4">
              <div className="flex items-center gap-2 mb-1">
                <MessageSquare className="h-3.5 w-3.5 text-muted-foreground" />
                <p className="text-xs text-muted-foreground">Total Messages</p>
              </div>
              <p className="text-2xl font-bold">{stats.total_messages.toLocaleString()}</p>
            </CardContent>
          </Card>
          <Card>
            <CardContent className="p-4">
              <div className="flex items-center gap-2 mb-1">
                <MessageSquare className="h-3.5 w-3.5 text-muted-foreground" />
                <p className="text-xs text-muted-foreground">Total Tokens</p>
              </div>
              <p className="text-2xl font-bold">{stats.total_tokens.toLocaleString()}</p>
            </CardContent>
          </Card>
          <Card>
            <CardContent className="p-4">
              <div className="flex items-center gap-2 mb-1">
                <Users className="h-3.5 w-3.5 text-muted-foreground" />
                <p className="text-xs text-muted-foreground">Active Staff</p>
              </div>
              <p className="text-2xl font-bold">{stats.active_staff_count}</p>
            </CardContent>
          </Card>
          <Card>
            <CardContent className="p-4">
              <div className="flex items-center gap-2 mb-1">
                <Bell className="h-3.5 w-3.5 text-muted-foreground" />
                <p className="text-xs text-muted-foreground">Reminders</p>
              </div>
              <p className="text-2xl font-bold">{stats.reminder_count}</p>
            </CardContent>
          </Card>
        </div>
      )}

      {/* Webhook URL — shown after refresh */}
      {webhookUrl && (
        <Card>
          <CardHeader className="pb-3">
            <div className="flex items-center gap-2">
              <Link2 className="h-4 w-4 text-primary" />
              <CardTitle className="text-base">Webhook URL</CardTitle>
            </div>
            <CardDescription>
              Registered with Telegram — bot receives messages via this URL.
            </CardDescription>
          </CardHeader>
          <CardContent>
            <div className="flex gap-2">
              <input
                readOnly
                value={webhookUrl}
                className="flex-1 h-9 rounded-md border border-input bg-muted px-3 py-1 text-xs font-mono text-muted-foreground focus:outline-none"
              />
              <button
                type="button"
                onClick={() => copyWebhook(webhookUrl)}
                className="inline-flex items-center gap-1.5 px-3 h-9 rounded-md border border-input bg-background text-sm font-medium hover:bg-accent transition-colors"
              >
                <Copy className="h-3.5 w-3.5" />
                {copied ? "Copied!" : "Copy"}
              </button>
            </div>
          </CardContent>
        </Card>
      )}

      {/* Tabs */}
      <Tabs defaultValue="staff">
        <TabsList>
          <TabsTrigger value="staff">Staff</TabsTrigger>
          <TabsTrigger value="agents">Agent Settings</TabsTrigger>
          <TabsTrigger value="reminders">Reminders</TabsTrigger>
        </TabsList>

        <TabsContent value="staff">
          <StaffTab ngoId={ngoId} />
        </TabsContent>

        <TabsContent value="agents">
          <AgentSettingsPanel ngoId={ngoId} />
        </TabsContent>

        <TabsContent value="reminders">
          <RemindersTab ngoId={ngoId} />
        </TabsContent>
      </Tabs>

      {/* Danger zone */}
      <Card className="border-destructive/30">
        <CardHeader className="pb-3">
          <div className="flex items-center gap-2">
            <AlertTriangle className="h-4 w-4 text-destructive" />
            <CardTitle className="text-base text-destructive">Danger Zone</CardTitle>
          </div>
          <CardDescription>Irreversible or high-impact actions.</CardDescription>
        </CardHeader>
        <CardContent className="space-y-3">
          <div className="flex items-center justify-between rounded-lg border border-border p-3">
            <div>
              <p className="text-sm font-medium">Refresh Webhook</p>
              <p className="text-xs text-muted-foreground">
                Generates a new secret and re-registers the webhook with Telegram.
              </p>
            </div>
            <Button
              variant="outline"
              size="sm"
              onClick={handleRefreshWebhook}
              disabled={refreshingWebhook}
            >
              {refreshingWebhook ? (
                <Loader2 className="mr-1.5 h-3.5 w-3.5 animate-spin" />
              ) : (
                <RefreshCw className="mr-1.5 h-3.5 w-3.5" />
              )}
              Refresh
            </Button>
          </div>
          {ngo.is_active && (
            <div className="flex items-center justify-between rounded-lg border border-destructive/30 p-3 bg-destructive/5">
              <div>
                <p className="text-sm font-medium text-destructive">Deactivate NGO</p>
                <p className="text-xs text-muted-foreground">
                  Stops the bot from processing messages. Staff can no longer use the bot.
                </p>
              </div>
              <Button
                variant="destructive"
                size="sm"
                onClick={handleDeactivate}
                disabled={deactivating}
              >
                {deactivating ? (
                  <Loader2 className="mr-1.5 h-3.5 w-3.5 animate-spin" />
                ) : (
                  <XCircle className="mr-1.5 h-3.5 w-3.5" />
                )}
                Deactivate
              </Button>
            </div>
          )}
        </CardContent>
      </Card>

      {/* Edit NGO Sheet */}
      <Sheet open={editOpen} onOpenChange={setEditOpen}>
        <SheetContent className="overflow-y-auto">
          <SheetHeader>
            <SheetTitle>Edit NGO</SheetTitle>
            <SheetDescription>Update organization settings.</SheetDescription>
          </SheetHeader>
          <div className="mt-6">
            <NGOForm
              ngo={ngo}
              onSubmit={handleEdit}
              onCancel={() => setEditOpen(false)}
              isEdit
            />
          </div>
        </SheetContent>
      </Sheet>
    </div>
  );
}
