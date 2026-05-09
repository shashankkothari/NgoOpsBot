"use client";

import useSWR from "swr";
import {
  CheckCircle2,
  AlertCircle,
  XCircle,
  Database,
  Zap,
  MessageSquare,
  Server,
  RefreshCw,
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
import { Separator } from "@/components/ui/separator";
import { systemApi, type SystemHealth } from "@/lib/api";

type HealthStatus = "healthy" | "degraded" | "down";

const STATUS_CONFIG: Record<
  HealthStatus,
  { icon: React.ElementType; label: string; colorClass: string; badgeVariant: "success" | "warning" | "destructive" }
> = {
  healthy: {
    icon: CheckCircle2,
    label: "Healthy",
    colorClass: "text-emerald-500",
    badgeVariant: "success",
  },
  degraded: {
    icon: AlertCircle,
    label: "Degraded",
    colorClass: "text-amber-500",
    badgeVariant: "warning",
  },
  down: {
    icon: XCircle,
    label: "Down",
    colorClass: "text-destructive",
    badgeVariant: "destructive",
  },
};

function ServiceCard({
  title,
  description,
  icon: Icon,
  status,
  details,
  loading,
}: {
  title: string;
  description: string;
  icon: React.ElementType;
  status: HealthStatus | undefined;
  details: React.ReactNode;
  loading: boolean;
}) {
  const cfg = status ? STATUS_CONFIG[status] : null;
  const StatusIcon = cfg?.icon;

  return (
    <Card>
      <CardHeader className="pb-3">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className="h-10 w-10 rounded-xl bg-primary/10 flex items-center justify-center">
              <Icon className="h-5 w-5 text-primary" />
            </div>
            <div>
              <CardTitle className="text-base">{title}</CardTitle>
              <CardDescription className="text-xs">{description}</CardDescription>
            </div>
          </div>
          {loading ? (
            <Skeleton className="h-6 w-20" />
          ) : cfg && StatusIcon ? (
            <div className="flex items-center gap-1.5">
              <StatusIcon className={`h-4 w-4 ${cfg.colorClass}`} />
              <Badge variant={cfg.badgeVariant}>{cfg.label}</Badge>
            </div>
          ) : null}
        </div>
      </CardHeader>
      <Separator />
      <CardContent className="pt-4">
        {loading ? (
          <div className="space-y-2">
            <Skeleton className="h-4 w-full" />
            <Skeleton className="h-4 w-2/3" />
          </div>
        ) : (
          details
        )}
      </CardContent>
    </Card>
  );
}

function MetricRow({
  label,
  value,
}: {
  label: string;
  value: string | number | undefined;
}) {
  return (
    <div className="flex items-center justify-between py-1.5">
      <p className="text-sm text-muted-foreground">{label}</p>
      <p className="text-sm font-medium text-foreground font-mono">
        {value ?? "—"}
      </p>
    </div>
  );
}

export default function SystemHealthPage() {
  const { data, isLoading, mutate, isValidating } = useSWR<SystemHealth>(
    "/api/v1/system/health",
    () => systemApi.health(),
    { refreshInterval: 30000 }
  );

  const uptime = data?.uptime_seconds;
  const uptimeFormatted = uptime
    ? `${Math.floor(uptime / 86400)}d ${Math.floor((uptime % 86400) / 3600)}h ${Math.floor(
        (uptime % 3600) / 60
      )}m`
    : "—";

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-foreground">System Health</h1>
          <p className="text-muted-foreground mt-1">
            Real-time infrastructure status and metrics.
          </p>
        </div>
        <Button
          variant="outline"
          size="sm"
          onClick={() => mutate()}
          disabled={isValidating}
        >
          <RefreshCw
            className={`mr-1.5 h-3.5 w-3.5 ${isValidating ? "animate-spin" : ""}`}
          />
          Refresh
        </Button>
      </div>

      {/* Overall status banner */}
      {isLoading ? (
        <Skeleton className="h-16 w-full rounded-xl" />
      ) : data ? (
        <Card
          className={
            data.status === "healthy"
              ? "border-emerald-500/30 bg-emerald-500/5"
              : data.status === "degraded"
              ? "border-amber-500/30 bg-amber-500/5"
              : "border-destructive/30 bg-destructive/5"
          }
        >
          <CardContent className="p-4">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-3">
                {data.status === "healthy" ? (
                  <CheckCircle2 className="h-6 w-6 text-emerald-500" />
                ) : data.status === "degraded" ? (
                  <AlertCircle className="h-6 w-6 text-amber-500" />
                ) : (
                  <XCircle className="h-6 w-6 text-destructive" />
                )}
                <div>
                  <p className="font-semibold text-foreground">
                    {data.status === "healthy"
                      ? "All Systems Operational"
                      : data.status === "degraded"
                      ? "Some Systems Degraded"
                      : "System Outage Detected"}
                  </p>
                  <p className="text-xs text-muted-foreground">
                    API v{data.version} · Uptime {uptimeFormatted}
                  </p>
                </div>
              </div>
              <Badge
                variant={STATUS_CONFIG[data.status]?.badgeVariant}
                className="text-sm px-3 py-1"
              >
                {STATUS_CONFIG[data.status]?.label}
              </Badge>
            </div>
          </CardContent>
        </Card>
      ) : null}

      {/* Service cards */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        <ServiceCard
          title="Database"
          description="PostgreSQL primary store"
          icon={Database}
          status={data?.database.status}
          loading={isLoading}
          details={
            <>
              <MetricRow
                label="Latency"
                value={
                  data?.database.latency_ms !== undefined
                    ? `${data.database.latency_ms}ms`
                    : undefined
                }
              />
              <MetricRow label="Status" value={data?.database.status} />
            </>
          }
        />
        <ServiceCard
          title="Redis"
          description="Cache & session store"
          icon={Zap}
          status={data?.redis.status}
          loading={isLoading}
          details={
            <>
              <MetricRow
                label="Latency"
                value={
                  data?.redis.latency_ms !== undefined
                    ? `${data.redis.latency_ms}ms`
                    : undefined
                }
              />
              <MetricRow label="Status" value={data?.redis.status} />
            </>
          }
        />
        <ServiceCard
          title="Telegram Webhooks"
          description="Bot webhook endpoints"
          icon={MessageSquare}
          status={data?.telegram_webhooks.status}
          loading={isLoading}
          details={
            <>
              <MetricRow
                label="Active webhooks"
                value={data?.telegram_webhooks.active_count}
              />
              <MetricRow
                label="Failed webhooks"
                value={data?.telegram_webhooks.failed_count}
              />
            </>
          }
        />
      </div>

      {/* Platform info */}
      <Card>
        <CardHeader className="pb-3">
          <div className="flex items-center gap-2">
            <Server className="h-4 w-4 text-primary" />
            <CardTitle className="text-base">Platform Information</CardTitle>
          </div>
        </CardHeader>
        <CardContent className="divide-y divide-border">
          {isLoading ? (
            <div className="space-y-2 py-2">
              <Skeleton className="h-4 w-full" />
              <Skeleton className="h-4 w-2/3" />
              <Skeleton className="h-4 w-1/2" />
            </div>
          ) : (
            <>
              <MetricRow label="API Version" value={data?.version} />
              <MetricRow label="Uptime" value={uptimeFormatted} />
              <MetricRow label="Overall Status" value={data?.status} />
            </>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
