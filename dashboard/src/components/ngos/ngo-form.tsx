"use client";

import { useEffect } from "react";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import { Loader2 } from "lucide-react";
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
import { type NGO, type NGOCreate, type NGOUpdate } from "@/lib/api";
import { slugify, TIMEZONES, LANGUAGES } from "@/lib/utils";

const ngoSchema = z.object({
  name: z.string().min(2, "Name must be at least 2 characters"),
  slug: z
    .string()
    .min(2, "Slug must be at least 2 characters")
    .regex(/^[a-z0-9-]+$/, "Slug must be lowercase letters, numbers, hyphens only"),
  telegram_bot_token: z
    .string()
    .min(10, "Telegram bot token is required")
    .optional()
    .or(z.literal("")),
  anthropic_api_key: z
    .string()
    .min(10, "Anthropic API key is required")
    .optional()
    .or(z.literal("")),
  timezone: z.string().min(1, "Timezone is required"),
  language: z.string().min(1, "Language is required"),
  is_active: z.boolean().optional(),
});

type NGOFormValues = z.infer<typeof ngoSchema>;

interface NGOFormProps {
  ngo?: NGO;
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  onSubmit: (data: any) => Promise<void>;
  onCancel: () => void;
  isEdit?: boolean;
}

export function NGOForm({ ngo, onSubmit, onCancel, isEdit = false }: NGOFormProps) {
  const {
    register,
    handleSubmit,
    watch,
    setValue,
    formState: { errors, isSubmitting },
  } = useForm<NGOFormValues>({
    resolver: zodResolver(ngoSchema),
    defaultValues: {
      name: ngo?.name ?? "",
      slug: ngo?.slug ?? "",
      telegram_bot_token: ngo?.telegram_bot_token_decrypted ?? "",
      anthropic_api_key: ngo?.anthropic_api_key_decrypted ?? "",
      timezone: ngo?.timezone ?? "UTC",
      language: ngo?.language ?? "en",
      is_active: ngo?.is_active ?? true,
    },
  });

  const nameValue = watch("name");

  useEffect(() => {
    if (!isEdit && nameValue) {
      setValue("slug", slugify(nameValue), { shouldValidate: false });
    }
  }, [nameValue, isEdit, setValue]);

  const handleFormSubmit = async (data: NGOFormValues) => {
    const payload: NGOCreate | NGOUpdate = {
      name: data.name,
      timezone: data.timezone,
      language: data.language,
      ...(data.telegram_bot_token ? { telegram_bot_token: data.telegram_bot_token } : {}),
      ...(data.anthropic_api_key ? { anthropic_api_key: data.anthropic_api_key } : {}),
      ...(isEdit ? { is_active: data.is_active } : {}),
    };
    await onSubmit(payload);
  };

  return (
    <form onSubmit={handleSubmit(handleFormSubmit)} className="space-y-4">
      {/* Name */}
      <div className="space-y-1.5">
        <Label htmlFor="name">
          Organization Name <span className="text-destructive">*</span>
        </Label>
        <Input
          id="name"
          placeholder="Green Future NGO"
          {...register("name")}
        />
        {errors.name && (
          <p className="text-xs text-destructive">{errors.name.message}</p>
        )}
      </div>

      {/* Slug — read-only display in edit mode, hidden in create mode (auto-generated) */}
      {isEdit && ngo?.slug && (
        <div className="space-y-1.5">
          <Label>Slug</Label>
          <p className="text-sm font-mono text-muted-foreground bg-muted px-3 py-2 rounded-md">
            {ngo.slug}
          </p>
          <p className="text-xs text-muted-foreground">
            Slug cannot be changed after creation.
          </p>
        </div>
      )}

      {/* Telegram Bot Token */}
      <div className="space-y-1.5">
        <Label htmlFor="telegram_bot_token">
          Telegram Bot Token{" "}
          {!isEdit && <span className="text-destructive">*</span>}
        </Label>
        <Input
          id="telegram_bot_token"
          type="password"
          placeholder="123456789:AAAA..."
          className="font-mono"
          {...register("telegram_bot_token")}
        />
        {errors.telegram_bot_token && (
          <p className="text-xs text-destructive">
            {errors.telegram_bot_token.message}
          </p>
        )}
        {isEdit && (
          <p className="text-xs text-muted-foreground">
            Leave blank to keep current token.
          </p>
        )}
      </div>

      {/* Anthropic API Key */}
      <div className="space-y-1.5">
        <Label htmlFor="anthropic_api_key">
          Anthropic API Key{" "}
          {!isEdit && <span className="text-destructive">*</span>}
        </Label>
        <Input
          id="anthropic_api_key"
          type="password"
          placeholder="sk-ant-..."
          className="font-mono"
          {...register("anthropic_api_key")}
        />
        {errors.anthropic_api_key && (
          <p className="text-xs text-destructive">
            {errors.anthropic_api_key.message}
          </p>
        )}
        {isEdit && (
          <p className="text-xs text-muted-foreground">
            Leave blank to keep current key.
          </p>
        )}
      </div>

      <div className="grid grid-cols-2 gap-4">
        {/* Timezone */}
        <div className="space-y-1.5">
          <Label>
            Timezone <span className="text-destructive">*</span>
          </Label>
          <Select
            defaultValue={ngo?.timezone ?? "UTC"}
            onValueChange={(v) => setValue("timezone", v)}
          >
            <SelectTrigger>
              <SelectValue placeholder="Select timezone" />
            </SelectTrigger>
            <SelectContent>
              {TIMEZONES.map((tz) => (
                <SelectItem key={tz} value={tz}>
                  {tz}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
          {errors.timezone && (
            <p className="text-xs text-destructive">{errors.timezone.message}</p>
          )}
        </div>

        {/* Language */}
        <div className="space-y-1.5">
          <Label>
            Language <span className="text-destructive">*</span>
          </Label>
          <Select
            defaultValue={ngo?.language ?? "en"}
            onValueChange={(v) => setValue("language", v)}
          >
            <SelectTrigger>
              <SelectValue placeholder="Select language" />
            </SelectTrigger>
            <SelectContent>
              {LANGUAGES.map((lang) => (
                <SelectItem key={lang.value} value={lang.value}>
                  {lang.label}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
          {errors.language && (
            <p className="text-xs text-destructive">{errors.language.message}</p>
          )}
        </div>
      </div>

      {/* Active toggle (edit only) */}
      {isEdit && (
        <div className="flex items-center justify-between rounded-lg border border-border p-3">
          <div>
            <p className="text-sm font-medium">Active</p>
            <p className="text-xs text-muted-foreground">
              Inactive NGOs cannot receive messages
            </p>
          </div>
          <Switch
            defaultChecked={ngo?.is_active ?? true}
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
          {isEdit ? "Save Changes" : "Create NGO"}
        </Button>
      </div>
    </form>
  );
}
