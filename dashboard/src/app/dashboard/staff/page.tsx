"use client";

import { useState } from "react";
import useSWR from "swr";
import Link from "next/link";
import { Users, ChevronRight, Search } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import { Switch } from "@/components/ui/switch";
import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import {
  ngoApi,
  staffApi,
  swrKeys,
  type Staff,
  type NGO,
  type PaginatedResponse,
} from "@/lib/api";
import { AGENT_LABELS } from "@/lib/utils";
import { useToast } from "@/components/ui/use-toast";

export default function StaffPage() {
  const { toast } = useToast();
  const [selectedNgoId, setSelectedNgoId] = useState<string>("");
  const [search, setSearch] = useState("");

  const { data: ngos } = useSWR<PaginatedResponse<NGO>>(
    swrKeys.ngos(),
    () => ngoApi.list({ page_size: 100 })
  );

  const { data, isLoading, mutate } = useSWR<PaginatedResponse<Staff>>(
    selectedNgoId ? swrKeys.staff(selectedNgoId) : null,
    () => staffApi.list(selectedNgoId, { page_size: 50 }),
    { keepPreviousData: true }
  );

  const filteredStaff = data?.items.filter(
    (s) =>
      !search ||
      s.name.toLowerCase().includes(search.toLowerCase()) ||
      s.telegram_id.includes(search)
  );

  const handleToggleActive = async (staff: Staff) => {
    if (!selectedNgoId) return;
    try {
      await staffApi.toggleActive(selectedNgoId, staff.id, !staff.is_active);
      await mutate();
    } catch {
      toast({ title: "Failed to update status", variant: "destructive" });
    }
  };

  return (
    <div className="space-y-6">
      {/* Header */}
      <div>
        <h1 className="text-2xl font-bold text-foreground">Staff</h1>
        <p className="text-muted-foreground mt-1">
          View and manage staff members across all NGO tenants.
        </p>
      </div>

      {/* Controls */}
      <div className="flex items-center gap-3 flex-wrap">
        <Select
          value={selectedNgoId}
          onValueChange={(v) => setSelectedNgoId(v === "none" ? "" : v)}
        >
          <SelectTrigger className="w-56">
            <SelectValue placeholder="Select NGO..." />
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

        {selectedNgoId && (
          <div className="relative flex-1 max-w-xs">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
            <Input
              placeholder="Search by name or Telegram ID..."
              className="pl-9"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
            />
          </div>
        )}

        {selectedNgoId && (
          <Link href={`/dashboard/ngos/${selectedNgoId}/staff`}>
            <Button variant="outline" size="sm">
              <Users className="mr-1.5 h-3.5 w-3.5" />
              Manage Staff
            </Button>
          </Link>
        )}
      </div>

      {/* Table */}
      {!selectedNgoId ? (
        <div className="text-center py-20">
          <Users className="h-10 w-10 text-muted-foreground/30 mx-auto mb-3" />
          <p className="text-sm text-muted-foreground">
            Select an NGO to view its staff
          </p>
        </div>
      ) : (
        <Card>
          <CardContent className="p-0">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Name</TableHead>
                  <TableHead>Telegram ID</TableHead>
                  <TableHead>Role</TableHead>
                  <TableHead>Allowed Agents</TableHead>
                  <TableHead>Status</TableHead>
                  <TableHead className="w-10" />
                </TableRow>
              </TableHeader>
              <TableBody>
                {isLoading ? (
                  Array.from({ length: 5 }).map((_, i) => (
                    <TableRow key={i}>
                      {Array.from({ length: 6 }).map((_, j) => (
                        <TableCell key={j}>
                          <Skeleton className="h-4 w-full" />
                        </TableCell>
                      ))}
                    </TableRow>
                  ))
                ) : filteredStaff?.length ? (
                  filteredStaff.map((member) => (
                    <TableRow key={member.id}>
                      <TableCell className="font-medium">{member.name}</TableCell>
                      <TableCell>
                        <code className="text-xs bg-muted px-1.5 py-0.5 rounded">
                          {member.telegram_id}
                        </code>
                      </TableCell>
                      <TableCell>
                        <Badge
                          variant={
                            member.role === "admin"
                              ? "default"
                              : member.role === "manager"
                              ? "secondary"
                              : "outline"
                          }
                          className="capitalize"
                        >
                          {member.role}
                        </Badge>
                      </TableCell>
                      <TableCell>
                        <div className="flex flex-wrap gap-1">
                          {member.allowed_agents.length ? (
                            member.allowed_agents.map((a) => (
                              <Badge
                                key={a}
                                variant="outline"
                                className="text-xs"
                              >
                                {AGENT_LABELS[a]}
                              </Badge>
                            ))
                          ) : (
                            <span className="text-xs text-muted-foreground italic">
                              No access
                            </span>
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
                        <Link
                          href={`/dashboard/ngos/${selectedNgoId}/staff`}
                        >
                          <Button variant="ghost" size="icon" className="h-8 w-8">
                            <ChevronRight className="h-4 w-4" />
                          </Button>
                        </Link>
                      </TableCell>
                    </TableRow>
                  ))
                ) : (
                  <TableRow>
                    <TableCell colSpan={6} className="text-center py-10">
                      <p className="text-sm text-muted-foreground">
                        {search ? "No staff match your search" : "No staff yet"}
                      </p>
                    </TableCell>
                  </TableRow>
                )}
              </TableBody>
            </Table>
          </CardContent>
        </Card>
      )}
    </div>
  );
}
