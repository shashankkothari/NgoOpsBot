"use client";

import useSWR from "swr";
import {
  Building2,
  Users,
  CheckCircle2,
  AlertCircle,
  XCircle,
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
import { ngoApi, systemApi, swrKeys, type NGO, type PaginatedResponse, type SystemHealth } from "@/lib/api";
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

type HealthStatus = "ok" | "error";

function ServiceRow({ label, status }: { label: string; status: HealthStatus | undefined }) {
  if (!status) return (
    <div className="flex items-center justify-between py-2 border-b border-border last:border-0">
      <p className="text-sm font-medium">{label}</p>
      <Skeleton className="h-5 w-16" />
    </div>
  );
  const ok = status === "ok";
  return (
    <div className="flex items-center justify-between py-2 border-b border-border last:border-0">
      <p className="text-sm font-medium">{label}</p>
      <div className="flex items-center gap-1.5">
        {ok
          ? <CheckCircle2 className="h-4 w-4 text-emerald-500" />
          : <XCircle className="h-4 w-4 text-destructive" />}
        <Badge variant={ok ? "success" : "destructive"}>{ok ? "Healthy" : "Error"}</Badge>
      </div>
    </div>
  );
}

export default function DashboardPage() {
  const { data: ngos, isLoading: ngosLoading } = useSWR<PaginatedResponse<NGO>>(
    swrKeys.ngos(),
    () => ngoApi.list({ page_size: 100 }),
    { refreshInterval: 60000 }
  );

  const { data: health, isLoading: healthLoading } = useSWR<SystemHealth>(
    swrKeys.health(),
    () => systemApi.health(),
    { refreshInterval: 15000 }
  );

  const totalNgos = ngos?.total;
  const activeNgos = ngos?.items.filter((n) => n.is_active).length;

  const overallOk = health?.database === "ok" && health?.redis === "ok";

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-foreground">Platform Overview</h1>
        <p className="text-muted-foreground mt-1">
          Monitor all NGO tenants and system health.
        </p>
      </div>

      {/* Stat cards */}
      <div className="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-4 gap-4">
        <StatCard
          title="Total NGOs"
          value={totalNgos}
          icon={Building2}
          loading={ngosLoading}
          description="Onboarded tenants"
        />
        <StatCard
          title="Active NGOs"
          value={activeNgos}
          icon={CheckCircle2}
          loading={ngosLoading}
          description="Currently active"
        />
        <StatCard
          title="Inactive NGOs"
          value={totalNgos !== undefined && activeNgos !== undefined ? totalNgos - activeNgos : undefined}
          icon={XCircle}
          loading={ngosLoading}
          description="Deactivated tenants"
        />
        <Card>
          <CardContent className="p-6">
            <div className="flex items-center justify-between">
              <div className="space-y-1">
                <p className="text-sm font-medium text-muted-foreground">System</p>
                {healthLoading ? (
                  <Skeleton className="h-8 w-20" />
                ) : (
                  <p className={`text-xl font-bold ${overallOk ? "text-emerald-600 dark:text-emerald-400" : "text-destructive"}`}>
                    {overallOk ? "All Good" : "Issues"}
                  </p>
                )}
                <p className="text-xs text-muted-foreground">Infrastructure</p>
              </div>
              <div className="h-12 w-12 rounded-xl bg-primary/10 flex items-center justify-center flex-shrink-0">
                <Activity className="h-6 w-6 text-primary" />
              </div>
            </div>
          </CardContent>
        </Card>
      </div>

      <div className="grid grid-cols-1 xl:grid-cols-3 gap-6">
        {/* NGO list preview */}
        <Card className="xl:col-span-2">
          <CardHeader className="pb-3">
            <div className="flex items-center gap-2">
              <Building2 className="h-4 w-4 text-primary" />
              <CardTitle className="text-base">NGO Tenants</CardTitle>
            </div>
            <CardDescription>Recently onboarded organizations</CardDescription>
          </CardHeader>
          <CardContent>
            {ngosLoading ? (
              <div className="space-y-3">
                {Array.from({ length: 5 }).map((_, i) => (
                  <div key={i} className="flex items-center gap-3">
                    <Skeleton className="h-8 w-8 rounded-lg" />
                    <div className="flex-1 space-y-1">
                      <Skeleton className="h-3.5 w-3/4" />
                      <Skeleton className="h-3 w-1/3" />
                    </div>
                  </div>
                ))}
              </div>
            ) : ngos?.items.length ? (
              <div className="space-y-0">
                {ngos.items.slice(0, 8).map((ngo, i) => (
                  <div
                    key={ngo.id}
                    className={`flex items-center gap-3 py-3 ${i < Math.min(ngos.items.length, 8) - 1 ? "border-b border-border" : ""}`}
                  >
                    <div className="h-8 w-8 rounded-lg bg-primary/10 flex items-center justify-center flex-shrink-0">
                      <Building2 className="h-3.5 w-3.5 text-primary" />
                    </div>
                    <div className="flex-1 min-w-0">
                      <p className="text-sm font-medium text-foreground">{ngo.name}</p>
                      <p className="text-xs text-muted-foreground mt-0.5">
                        <code className="bg-muted px-1 rounded">{ngo.slug}</code>
                        {" · "}
                        {formatRelativeTime(ngo.created_at)}
                      </p>
                    </div>
                    <Badge variant={ngo.is_active ? "success" : "outline"} className="flex-shrink-0">
                      {ngo.is_active ? "Active" : "Inactive"}
                    </Badge>
                  </div>
                ))}
              </div>
            ) : (
              <p className="text-sm text-muted-foreground py-6 text-center">
                No NGOs onboarded yet
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
          <CardContent>
            {healthLoading ? (
              <div className="space-y-3">
                {Array.from({ length: 3 }).map((_, i) => (
                  <div key={i} className="flex justify-between items-center py-2">
                    <Skeleton className="h-4 w-24" />
                    <Skeleton className="h-5 w-16" />
                  </div>
                ))}
              </div>
            ) : (
              <>
                <div className="flex items-center justify-between py-2 border-b border-border">
                  <p className="text-sm font-medium">Overall</p>
                  <div className="flex items-center gap-1.5">
                    {overallOk
                      ? <CheckCircle2 className="h-4 w-4 text-emerald-500" />
                      : <AlertCircle className="h-4 w-4 text-destructive" />}
                    <Badge variant={overallOk ? "success" : "destructive"}>
                      {health?.status === "ready" ? "Ready" : "Degraded"}
                    </Badge>
                  </div>
                </div>
                <ServiceRow label="Database" status={health?.database} />
                <ServiceRow label="Redis" status={health?.redis} />
              </>
            )}
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
