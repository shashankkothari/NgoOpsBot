"use client";

import { useState } from "react";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import { Loader2, Check } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Switch } from "@/components/ui/switch";
import { Badge } from "@/components/ui/badge";
import { cn, AGENT_LABELS } from "@/lib/utils";
import {
  type Staff,
  type StaffCreate,
  type StaffUpdate,
  type AgentType,
} from "@/lib/api";

const ALL_AGENTS: AgentType[] = [
  "fundraising",
  "finance",
  "marketing",
  "hr",
  "compliance",
];

const staffSchema = z.object({
  name: z.string().min(2, "Name must be at least 2 characters"),
  telegram_id: z
    .string()
    .min(1, "Telegram ID is required")
    .regex(/^\d+$/, "Telegram ID must be numeric"),
  role: z.enum(["admin", "manager", "staff"]),
  is_active: z.boolean().optional(),
});

type StaffFormValues = z.infer<typeof staffSchema>;

interface StaffFormProps {
  staff?: Staff;
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  onSubmit: (data: any) => Promise<void>;
  onCancel: () => void;
  isEdit?: boolean;
}

export function StaffForm({
  staff,
  onSubmit,
  onCancel,
  isEdit = false,
}: StaffFormProps) {
  const [selectedAgents, setSelectedAgents] = useState<AgentType[]>(
    staff?.allowed_agents ?? []
  );

  const {
    register,
    handleSubmit,
    setValue,
    formState: { errors, isSubmitting },
  } = useForm<StaffFormValues>({
    resolver: zodResolver(staffSchema),
    defaultValues: {
      name: staff?.name ?? "",
      telegram_id: staff?.telegram_id ?? "",
      role: staff?.role ?? "staff",
      is_active: staff?.is_active ?? true,
    },
  });

  const toggleAgent = (agent: AgentType) => {
    setSelectedAgents((prev) =>
      prev.includes(agent) ? prev.filter((a) => a !== agent) : [...prev, agent]
    );
  };

  const handleFormSubmit = async (data: StaffFormValues) => {
    const payload: StaffCreate | StaffUpdate = {
      name: data.name,
      telegram_id: data.telegram_id,
      role: data.role,
      allowed_agents: selectedAgents,
      ...(isEdit ? { is_active: data.is_active } : {}),
    };
    await onSubmit(payload);
  };

  return (
    <form onSubmit={handleSubmit(handleFormSubmit)} className="space-y-4">
      {/* Name */}
      <div className="space-y-1.5">
        <Label htmlFor="staff-name">
          Full Name <span className="text-destructive">*</span>
        </Label>
        <Input
          id="staff-name"
          placeholder="Jane Doe"
          {...register("name")}
        />
        {errors.name && (
          <p className="text-xs text-destructive">{errors.name.message}</p>
        )}
      </div>

      {/* Telegram ID */}
      <div className="space-y-1.5">
        <Label htmlFor="telegram_id">
          Telegram User ID <span className="text-destructive">*</span>
        </Label>
        <Input
          id="telegram_id"
          placeholder="123456789"
          className="font-mono"
          {...register("telegram_id")}
        />
        {errors.telegram_id && (
          <p className="text-xs text-destructive">
            {errors.telegram_id.message}
          </p>
        )}
        <p className="text-xs text-muted-foreground">
          Numeric Telegram user ID (use @userinfobot to find it).
        </p>
      </div>

      {/* Role */}
      <div className="space-y-1.5">
        <Label>
          Role <span className="text-destructive">*</span>
        </Label>
        <Select
          defaultValue={staff?.role ?? "staff"}
          onValueChange={(v) => setValue("role", v as "admin" | "manager" | "staff")}
        >
          <SelectTrigger>
            <SelectValue placeholder="Select role" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="admin">Admin — Full access</SelectItem>
            <SelectItem value="manager">Manager — Manage staff & reports</SelectItem>
            <SelectItem value="staff">Staff — Bot access only</SelectItem>
          </SelectContent>
        </Select>
        {errors.role && (
          <p className="text-xs text-destructive">{errors.role.message}</p>
        )}
      </div>

      {/* Agent access */}
      <div className="space-y-2">
        <Label>Allowed Agents</Label>
        <div className="flex flex-wrap gap-2">
          {ALL_AGENTS.map((agent) => {
            const selected = selectedAgents.includes(agent);
            return (
              <button
                key={agent}
                type="button"
                onClick={() => toggleAgent(agent)}
                className={cn(
                  "inline-flex items-center gap-1.5 px-3 py-1.5 rounded-md text-sm font-medium border transition-all",
                  selected
                    ? "bg-primary text-primary-foreground border-primary"
                    : "bg-background text-muted-foreground border-border hover:border-primary/50 hover:text-foreground"
                )}
              >
                {selected && <Check className="h-3.5 w-3.5" />}
                {AGENT_LABELS[agent]}
              </button>
            );
          })}
        </div>
        <p className="text-xs text-muted-foreground">
          Select which AI agents this staff member can access.
        </p>
        {selectedAgents.length === 0 && (
          <p className="text-xs text-amber-500">
            No agents selected — staff will have no bot access.
          </p>
        )}
      </div>

      {/* Active toggle (edit only) */}
      {isEdit && (
        <div className="flex items-center justify-between rounded-lg border border-border p-3">
          <div>
            <p className="text-sm font-medium">Active</p>
            <p className="text-xs text-muted-foreground">
              Inactive staff cannot use the bot
            </p>
          </div>
          <Switch
            defaultChecked={staff?.is_active ?? true}
            onCheckedChange={(v) => setValue("is_active", v)}
          />
        </div>
      )}

      <div className="flex justify-end gap-2 pt-2">
        <Button type="button" variant="outline" onClick={onCancel}>
          Cancel
        </Button>
        <Button type="submit" disabled={isSubmitting}>
          {isSubmitting && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
          {isEdit ? "Save Changes" : "Add Staff Member"}
        </Button>
      </div>
    </form>
  );
}
