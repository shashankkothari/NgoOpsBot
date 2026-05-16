"use client";

import useSWR from "swr";
import {
  CheckCircle2,
  XCircle,
  Database,
  Zap,
  Server,
  RefreshCw,
  Activity,
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
import { systemApi, swrKeys, type SystemHealth } from "@/lib/api";

function ServiceCard({
  title,
  description,
  icon: Icon,
  status,
  loading,
}: {
  title: string;
  description: string;
  icon: React.ElementType;
  status: "ok" | "error" | undefined;
  loading: boolean;
}) {
  const ok = status === "ok";

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
          ) : status !== undefined ? (
            <div className="flex items-center gap-1.5">
              {ok
                ? <CheckCircle2 className="h-4 w-4 text-emerald-500" />
                : <XCircle className="h-4 w-4 text-destructive" />}
              <Badge variant={ok ? "success" : "destructive"}>
                {ok ? "Healthy" : "Error"}
              </Badge>
            </div>
          ) : null}
        </div>
      </CardHeader>
      <Separator />
      <CardContent className="pt-4">
        {loading ? (
          <Skeleton className="h-4 w-2/3" />
        ) : (
          <p className="text-sm text-muted-foreground">
            Status: <span className={`font-medium ${ok ? "text-emerald-600 dark:text-emerald-400" : "text-destructive"}`}>
              {status ?? "—"}
            </span>
          </p>
        )}
      </CardContent>
    </Card>
  );
}

export default function SystemHealthPage() {
  const { data, isLoading, mutate, isValidating } = useSWR<SystemHealth>(
    swrKeys.health(),
    () => systemApi.health(),
    { refreshInterval: 30000 }
  );

  const overallOk = data?.database === "ok" && data?.redis === "ok";

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-foreground">System Health</h1>
          <p className="text-muted-foreground mt-1">Real-time infrastructure status.</p>
        </div>
        <Button variant="outline" size="sm" onClick={() => mutate()} disabled={isValidating}>
          <RefreshCw className={`mr-1.5 h-3.5 w-3.5 ${isValidating ? "animate-spin" : ""}`} />
          Refresh
        </Button>
      </div>

      {/* Overall status banner */}
      {isLoading ? (
        <Skeleton className="h-16 w-full rounded-xl" />
      ) : data ? (
        <Card className={overallOk ? "border-emerald-500/30 bg-emerald-500/5" : "border-destructive/30 bg-destructive/5"}>
          <CardContent className="p-4">
            <div className="flex items-center gap-3">
              {overallOk
                ? <CheckCircle2 className="h-6 w-6 text-emerald-500" />
                : <XCircle className="h-6 w-6 text-destructive" />}
              <div>
                <p className="font-semibold text-foreground">
                  {overallOk ? "All Systems Operational" : "System Issues Detected"}
                </p>
                <p className="text-xs text-muted-foreground">
                  Status: <span className="font-mono">{data.status}</span>
                </p>
              </div>
              <Badge
                variant={overallOk ? "success" : "destructive"}
                className="ml-auto text-sm px-3 py-1"
              >
                {overallOk ? "Healthy" : "Degraded"}
              </Badge>
            </div>
          </CardContent>
        </Card>
      ) : null}

      {/* Service cards */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        <ServiceCard
          title="Database"
          description="PostgreSQL primary store"
          icon={Database}
          status={data?.database}
          loading={isLoading}
        />
        <ServiceCard
          title="Redis"
          description="Cache & session store"
          icon={Zap}
          status={data?.redis}
          loading={isLoading}
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
            </div>
          ) : (
            <>
              <div className="flex items-center justify-between py-2">
                <p className="text-sm text-muted-foreground">Overall Status</p>
                <p className="text-sm font-mono font-medium">{data?.status ?? "—"}</p>
              </div>
              <div className="flex items-center justify-between py-2">
                <p className="text-sm text-muted-foreground">Database</p>
                <p className="text-sm font-mono font-medium">{data?.database ?? "—"}</p>
              </div>
              <div className="flex items-center justify-between py-2">
                <p className="text-sm text-muted-foreground">Redis</p>
                <p className="text-sm font-mono font-medium">{data?.redis ?? "—"}</p>
              </div>
            </>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
