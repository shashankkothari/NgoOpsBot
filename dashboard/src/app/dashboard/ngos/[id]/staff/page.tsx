"use client";

import { useState } from "react";
import { useParams } from "next/navigation";
import Link from "next/link";
import useSWR from "swr";
import { ArrowLeft, Plus, Edit, Trash2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import { Switch } from "@/components/ui/switch";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { Card, CardContent } from "@/components/ui/card";
import {
  Sheet,
  SheetContent,
  SheetHeader,
  SheetTitle,
  SheetDescription,
} from "@/components/ui/sheet";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import {
  staffApi,
  swrKeys,
  type Staff,
  type StaffCreate,
  type PaginatedResponse,
} from "@/lib/api";
import { AGENT_LABELS } from "@/lib/utils";
import { StaffForm } from "@/components/ngos/staff-form";
import { useToast } from "@/components/ui/use-toast";

export default function StaffManagementPage() {
  const params = useParams();
  const { toast } = useToast();
  const ngoId = params.id as string;

  const [addOpen, setAddOpen] = useState(false);
  const [editStaff, setEditStaff] = useState<Staff | null>(null);
  const [deleteStaff, setDeleteStaff] = useState<Staff | null>(null);
  const [deleting, setDeleting] = useState(false);

  const { data, isLoading, mutate } = useSWR<PaginatedResponse<Staff>>(
    swrKeys.staff(ngoId),
    () => staffApi.list(ngoId, { page_size: 50 })
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

  const handleDelete = async () => {
    if (!deleteStaff) return;
    setDeleting(true);
    try {
      await staffApi.delete(ngoId, deleteStaff.id);
      await mutate();
      setDeleteStaff(null);
      toast({ title: "Staff member removed" });
    } catch (err) {
      toast({
        title: "Failed to remove staff",
        description: err instanceof Error ? err.message : "Unknown error",
        variant: "destructive",
      });
    } finally {
      setDeleting(false);
    }
  };

  return (
    <div className="space-y-6">
      {/* Header */}
      <div>
        <Link href={`/dashboard/ngos/${ngoId}`}>
          <Button variant="ghost" size="sm" className="gap-1.5 -ml-2 mb-3 text-muted-foreground">
            <ArrowLeft className="h-3.5 w-3.5" />
            Back to NGO
          </Button>
        </Link>
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-2xl font-bold text-foreground">Staff Management</h1>
            <p className="text-muted-foreground mt-1">
              Add, edit, and manage NGO staff access.
            </p>
          </div>
          <Button onClick={() => setAddOpen(true)}>
            <Plus className="mr-2 h-4 w-4" />
            Add Staff
          </Button>
        </div>
      </div>

      {/* Table */}
      <Card>
        <CardContent className="p-0">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Name</TableHead>
                <TableHead>Telegram ID</TableHead>
                <TableHead>Role</TableHead>
                <TableHead>Allowed Agents</TableHead>
                <TableHead>Active</TableHead>
                <TableHead className="w-24" />
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
              ) : data?.items.length ? (
                data.items.map((member) => (
                  <TableRow key={member.id}>
                    <TableCell>
                      <p className="font-medium">{member.name}</p>
                    </TableCell>
                    <TableCell>
                      <code className="text-xs bg-muted px-1.5 py-0.5 rounded">
                        {member.telegram_user_id}
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
                            <Badge key={a} variant="outline" className="text-xs">
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
                      <div className="flex items-center gap-1">
                        <Button
                          variant="ghost"
                          size="icon"
                          className="h-8 w-8"
                          onClick={() => setEditStaff(member)}
                        >
                          <Edit className="h-3.5 w-3.5" />
                        </Button>
                        <Button
                          variant="ghost"
                          size="icon"
                          className="h-8 w-8 text-destructive hover:text-destructive"
                          onClick={() => setDeleteStaff(member)}
                        >
                          <Trash2 className="h-3.5 w-3.5" />
                        </Button>
                      </div>
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
              Add a new staff member with specific agent access.
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
            <SheetDescription>
              Update staff details and agent access.
            </SheetDescription>
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

      {/* Delete Confirm Dialog */}
      <Dialog
        open={!!deleteStaff}
        onOpenChange={(o) => !o && setDeleteStaff(null)}
      >
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Remove Staff Member</DialogTitle>
            <DialogDescription>
              Are you sure you want to remove{" "}
              <strong>{deleteStaff?.name}</strong>? They will immediately lose
              bot access.
            </DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button variant="outline" onClick={() => setDeleteStaff(null)}>
              Cancel
            </Button>
            <Button
              variant="destructive"
              onClick={handleDelete}
              disabled={deleting}
            >
              {deleting ? "Removing…" : "Remove"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
