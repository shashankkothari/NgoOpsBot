"use client";

import useSWR from "swr";
import {
  Building2,
  Users,
  MessageSquare,
  Bell,
  CheckCircle2,
  AlertCircle,
  XCircle,
  TrendingUp,
  Activity,
} from "lucide-react";
import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
  CardDescription,
} from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import { systemApi, type DashboardStats, type SystemHealth } from "@/lib/api";
import { formatRelativeTime } from "@/lib/utils";

function StatCard({
  title,
  value,
  icon: Icon,
  description,
  loading,
}: {
  title: string;
  value: number | undefined;
  icon: React.ElementType;
  description?: string;
  loading: boolean;
}) {
  return (
    <Card>
      <CardContent className="p-6">
        <div className="flex items-center justify-between">
          <div className="space-y-1">
            <p className="text-sm font-medium text-muted-foreground">{title}</p>
            {loading ? (
              <Skeleton className="h-8 w-20" />
            ) : (
              <p className="text-3xl font-bold text-foreground">
                {value?.toLocaleString() ?? "—"}
              </p>
            )}
            {description && (
              <p className="text-xs text-muted-foreground">{description}</p>
            )}
          </div>
          <div className="h-12 w-12 rounded-xl bg-primary/10 flex items-center justify-center flex-shrink-0">
            <Icon className="h-6 w-6 text-primary" />
          </div>
        </div>
      </CardContent>
    </Card>
  );
}

function StatusIndicator({
  status,
}: {
  status: "healthy" | "degraded" | "down" | undefined;
}) {
  if (!status) return <Skeleton className="h-5 w-16" />;
  const config = {
    healthy: {
      icon: CheckCircle2,
      label: "Healthy",
      class: "text-emerald-500",
      badge: "success" as const,
    },
    degraded: {
      icon: AlertCircle,
      label: "Degraded",
      class: "text-amber-500",
      badge: "warning" as const,
    },
    down: {
      icon: XCircle,
      label: "Down",
      class: "text-destructive",
      badge: "destructive" as const,
    },
  };
  const cfg = config[status];
  const Icon = cfg.icon;
  return (
    <div className="flex items-center gap-1.5">
      <Icon className={`h-4 w-4 ${cfg.class}`} />
      <Badge variant={cfg.badge}>{cfg.label}</Badge>
    </div>
  );
}

export default function DashboardPage() {
  const { data: stats, isLoading: statsLoading } = useSWR<DashboardStats>(
    "/api/v1/system/stats",
    () => systemApi.stats(),
    { refreshInterval: 30000 }
  );

  const { data: health, isLoading: healthLoading } = useSWR<SystemHealth>(
    "/api/v1/system/health",
    () => systemApi.health(),
    { refreshInterval: 15000 }
  );

  return (
    <div className="space-y-6">
      {/* Header */}
      <div>
        <h1 className="text-2xl font-bold text-foreground">
          Platform Overview
        </h1>
        <p className="text-muted-foreground mt-1">
          Monitor all NGO tenants, activity, and system health.
        </p>
      </div>

      {/* Stat cards */}
      <div className="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-4 gap-4">
        <StatCard
          title="Total NGOs"
          value={stats?.total_ngos}
          icon={Building2}
          loading={statsLoading}
          description="Onboarded tenants"
        />
        <StatCard
          title="Active Staff"
          value={stats?.active_staff}
          icon={Users}
          loading={statsLoading}
          description="Across all NGOs"
        />
        <StatCard
          title="Messages Today"
          value={stats?.messages_today}
          icon={MessageSquare}
          loading={statsLoading}
          description="Bot conversations"
        />
        <StatCard
          title="Reminders Sent"
          value={stats?.reminders_sent_today}
          icon={Bell}
          loading={statsLoading}
          description="Today"
        />
      </div>

      <div className="grid grid-cols-1 xl:grid-cols-3 gap-6">
        {/* Recent Activity */}
        <Card className="xl:col-span-2">
          <CardHeader className="pb-3">
            <div className="flex items-center gap-2">
              <TrendingUp className="h-4 w-4 text-primary" />
              <CardTitle className="text-base">Recent Activity</CardTitle>
            </div>
            <CardDescription>
              Latest actions across the platform
            </CardDescription>
          </CardHeader>
          <CardContent>
            {statsLoading ? (
              <div className="space-y-3">
                {Array.from({ length: 5 }).map((_, i) => (
                  <div key={i} className="flex items-center gap-3">
                    <Skeleton className="h-8 w-8 rounded-full" />
                    <div className="flex-1 space-y-1">
                      <Skeleton className="h-3.5 w-3/4" />
                      <Skeleton className="h-3 w-1/3" />
                    </div>
                  </div>
                ))}
              </div>
            ) : stats?.recent_activity?.length ? (
              <div className="space-y-0">
                {stats.recent_activity.map((item, i) => (
                  <div
                    key={item.id}
                    className={`flex items-start gap-3 py-3 ${
                      i < stats.recent_activity.length - 1
                        ? "border-b border-border"
                        : ""
                    }`}
                  >
                    <div className="h-8 w-8 rounded-full bg-primary/10 flex items-center justify-center flex-shrink-0 mt-0.5">
                      <Activity className="h-3.5 w-3.5 text-primary" />
                    </div>
                    <div className="flex-1 min-w-0">
                      <p className="text-sm text-foreground">
                        {item.description}
                      </p>
                      <p className="text-xs text-muted-foreground mt-0.5">
                        {item.ngo_name && (
                          <span className="font-medium">{item.ngo_name} · </span>
                        )}
                        {formatRelativeTime(item.timestamp)}
                      </p>
                    </div>
                  </div>
                ))}
              </div>
            ) : (
              <p className="text-sm text-muted-foreground py-6 text-center">
                No recent activity
              </p>
            )}
          </CardContent>
        </Card>

        {/* System Health */}
        <Card>
          <CardHeader className="pb-3">
            <div className="flex items-center gap-2">
              <Activity className="h-4 w-4 text-primary" />
              <CardTitle className="text-base">System Health</CardTitle>
            </div>
            <CardDescription>Infrastructure status</CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            {healthLoading ? (
              <div className="space-y-4">
                {Array.from({ length: 4 }).map((_, i) => (
                  <div key={i} className="flex justify-between items-center">
                    <Skeleton className="h-4 w-24" />
                    <Skeleton className="h-5 w-16" />
                  </div>
                ))}
              </div>
            ) : (
              <>
                <div className="flex items-center justify-between py-2 border-b border-border">
                  <div>
                    <p className="text-sm font-medium">Overall</p>
                    <p className="text-xs text-muted-foreground">
                      Platform status
                    </p>
                  </div>
                  <StatusIndicator status={health?.status} />
                </div>
                <div className="flex items-center justify-between py-2 border-b border-border">
                  <div>
                    <p className="text-sm font-medium">Database</p>
                    {health?.database.latency_ms !== undefined && (
                      <p className="text-xs text-muted-foreground">
                        {health.database.latency_ms}ms latency
                      </p>
                    )}
                  </div>
                  <StatusIndicator status={health?.database.status} />
                </div>
                <div className="flex items-center justify-between py-2 border-b border-border">
                  <div>
                    <p className="text-sm font-medium">Redis</p>
                    {health?.redis.latency_ms !== undefined && (
                      <p className="text-xs text-muted-foreground">
                        {health.redis.latency_ms}ms latency
                      </p>
                    )}
                  </div>
                  <StatusIndicator status={health?.redis.status} />
                </div>
                <div className="flex items-center justify-between py-2">
                  <div>
                    <p className="text-sm font-medium">Telegram Webhooks</p>
                    {health?.telegram_webhooks && (
                      <p className="text-xs text-muted-foreground">
                        {health.telegram_webhooks.active_count} active
                        {health.telegram_webhooks.failed_count > 0 &&
                          ` · ${health.telegram_webhooks.failed_count} failed`}
                      </p>
                    )}
                  </div>
                  <StatusIndicator status={health?.telegram_webhooks.status} />
                </div>

                {health?.uptime_seconds !== undefined && (
                  <div className="pt-2 border-t border-border">
                    <p className="text-xs text-muted-foreground">
                      Uptime:{" "}
                      <span className="text-foreground font-medium">
                        {Math.floor(health.uptime_seconds / 3600)}h{" "}
                        {Math.floor((health.uptime_seconds % 3600) / 60)}m
                      </span>
                    </p>
                    {health.version && (
                      <p className="text-xs text-muted-foreground mt-0.5">
                        API version:{" "}
                        <span className="font-mono">{health.version}</span>
                      </p>
                    )}
                  </div>
                )}
              </>
            )}
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
