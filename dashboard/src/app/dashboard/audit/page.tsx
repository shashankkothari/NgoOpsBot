"use client";

import { useState } from "react";
import useSWR from "swr";
import { ScrollText, Filter, ChevronDown, ChevronUp } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
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
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import {
  auditApi,
  ngoApi,
  swrKeys,
  type AuditLog,
  type PaginatedResponse,
  type NGO,
} from "@/lib/api";
import { formatDateTime, formatRelativeTime } from "@/lib/utils";

const ACTION_COLORS: Record<
  string,
  "default" | "secondary" | "destructive" | "outline"
> = {
  create: "default",
  update: "secondary",
  delete: "destructive",
  login: "outline",
};

function getActionColor(
  action: string
): "default" | "secondary" | "destructive" | "outline" {
  for (const [key, color] of Object.entries(ACTION_COLORS)) {
    if (action.toLowerCase().includes(key)) return color;
  }
  return "outline";
}

function DetailsExpander({ details }: { details: Record<string, unknown> }) {
  const [open, setOpen] = useState(false);
  const hasDetails = Object.keys(details).length > 0;

  if (!hasDetails) return null;

  return (
    <div className="mt-2">
      <button
        onClick={() => setOpen(!open)}
        className="flex items-center gap-1 text-xs text-muted-foreground hover:text-foreground transition-colors"
      >
        {open ? (
          <ChevronUp className="h-3 w-3" />
        ) : (
          <ChevronDown className="h-3 w-3" />
        )}
        {open ? "Hide" : "Show"} details
      </button>
      {open && (
        <pre className="mt-2 text-xs bg-muted rounded-md p-3 overflow-auto max-h-40 text-muted-foreground">
          {JSON.stringify(details, null, 2)}
        </pre>
      )}
    </div>
  );
}

export default function AuditPage() {
  const [ngoId, setNgoId] = useState("");
  const [action, setAction] = useState("");
  const [resourceType, setResourceType] = useState("");
  const [dateFrom, setDateFrom] = useState("");
  const [dateTo, setDateTo] = useState("");
  const [page, setPage] = useState(1);

  const { data: ngos } = useSWR<PaginatedResponse<NGO>>(
    swrKeys.ngos(),
    () => ngoApi.list({ page_size: 100 })
  );

  const { data, isLoading } = useSWR<PaginatedResponse<AuditLog>>(
    swrKeys.audit({
      ngo_id: ngoId,
      action,
      resource_type: resourceType,
      date_from: dateFrom,
      date_to: dateTo,
    }),
    () =>
      auditApi.list({
        ngo_id: ngoId || undefined,
        action: action || undefined,
        resource_type: resourceType || undefined,
        date_from: dateFrom || undefined,
        date_to: dateTo || undefined,
        page,
        page_size: 25,
      }),
    { keepPreviousData: true }
  );

  return (
    <div className="space-y-6">
      {/* Header */}
      <div>
        <h1 className="text-2xl font-bold text-foreground">Audit Logs</h1>
        <p className="text-muted-foreground mt-1">
          Track all administrative actions and changes across the platform.
        </p>
      </div>

      {/* Filters */}
      <Card>
        <CardContent className="p-4">
          <div className="flex items-center gap-2 mb-3">
            <Filter className="h-4 w-4 text-muted-foreground" />
            <span className="text-sm font-medium">Filters</span>
          </div>
          <div className="grid grid-cols-2 md:grid-cols-5 gap-3">
            <div className="space-y-1.5">
              <Label className="text-xs">NGO</Label>
              <Select
                value={ngoId}
                onValueChange={(v) => {
                  setNgoId(v === "all" ? "" : v);
                  setPage(1);
                }}
              >
                <SelectTrigger>
                  <SelectValue placeholder="All NGOs" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="all">All NGOs</SelectItem>
                  {ngos?.items.map((ngo) => (
                    <SelectItem key={ngo.id} value={ngo.id}>
                      {ngo.name}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-1.5">
              <Label className="text-xs">Action</Label>
              <Input
                placeholder="e.g. create, update"
                value={action}
                onChange={(e) => {
                  setAction(e.target.value);
                  setPage(1);
                }}
              />
            </div>
            <div className="space-y-1.5">
              <Label className="text-xs">Resource Type</Label>
              <Input
                placeholder="e.g. ngo, staff"
                value={resourceType}
                onChange={(e) => {
                  setResourceType(e.target.value);
                  setPage(1);
                }}
              />
            </div>
            <div className="space-y-1.5">
              <Label className="text-xs">From</Label>
              <Input
                type="date"
                value={dateFrom}
                onChange={(e) => {
                  setDateFrom(e.target.value);
                  setPage(1);
                }}
              />
            </div>
            <div className="space-y-1.5">
              <Label className="text-xs">To</Label>
              <Input
                type="date"
                value={dateTo}
                onChange={(e) => {
                  setDateTo(e.target.value);
                  setPage(1);
                }}
              />
            </div>
          </div>
        </CardContent>
      </Card>

      {/* Log entries */}
      <Card>
        <CardContent className="p-0">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Timestamp</TableHead>
                <TableHead>Actor</TableHead>
                <TableHead>Action</TableHead>
                <TableHead>Resource</TableHead>
                <TableHead>NGO</TableHead>
                <TableHead>IP Address</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {isLoading ? (
                Array.from({ length: 8 }).map((_, i) => (
                  <TableRow key={i}>
                    {Array.from({ length: 6 }).map((_, j) => (
                      <TableCell key={j}>
                        <Skeleton className="h-4 w-full" />
                      </TableCell>
                    ))}
                  </TableRow>
                ))
              ) : data?.items.length ? (
                data.items.map((log) => (
                  <TableRow key={log.id} className="align-top">
                    <TableCell>
                      <p className="text-xs text-foreground whitespace-nowrap">
                        {formatRelativeTime(log.created_at)}
                      </p>
                      <p className="text-xs text-muted-foreground">
                        {formatDateTime(log.created_at)}
                      </p>
                    </TableCell>
                    <TableCell>
                      <p className="text-sm font-mono text-foreground">
                        {log.actor}
                      </p>
                    </TableCell>
                    <TableCell>
                      <Badge variant={getActionColor(log.action)}>
                        {log.action}
                      </Badge>
                    </TableCell>
                    <TableCell>
                      <p className="text-sm text-foreground">
                        {log.resource_type}
                      </p>
                      {log.resource_id && (
                        <p className="text-xs text-muted-foreground font-mono mt-0.5">
                          {log.resource_id.slice(0, 8)}…
                        </p>
                      )}
                      <DetailsExpander details={log.details} />
                    </TableCell>
                    <TableCell>
                      <p className="text-sm text-muted-foreground">
                        {log.ngo_name ?? "—"}
                      </p>
                    </TableCell>
                    <TableCell>
                      <p className="text-xs text-muted-foreground font-mono">
                        {log.ip_address ?? "—"}
                      </p>
                    </TableCell>
                  </TableRow>
                ))
              ) : (
                <TableRow>
                  <TableCell colSpan={6} className="text-center py-12">
                    <ScrollText className="h-8 w-8 text-muted-foreground/30 mx-auto mb-2" />
                    <p className="text-sm text-muted-foreground">
                      No audit logs found
                    </p>
                  </TableCell>
                </TableRow>
              )}
            </TableBody>
          </Table>
        </CardContent>
      </Card>

      {/* Pagination */}
      {data && data.pages > 1 && (
        <div className="flex items-center justify-center gap-2">
          <Button
            variant="outline"
            size="sm"
            disabled={page === 1}
            onClick={() => setPage((p) => p - 1)}
          >
            Previous
          </Button>
          <span className="text-sm text-muted-foreground">
            Page {page} of {data.pages}
          </span>
          <Button
            variant="outline"
            size="sm"
            disabled={page === data.pages}
            onClick={() => setPage((p) => p + 1)}
          >
            Next
          </Button>
        </div>
      )}
    </div>
  );
}
