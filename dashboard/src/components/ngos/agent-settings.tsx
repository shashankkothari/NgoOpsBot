"use client";

import { useState } from "react";
import { Loader2, Sparkles, ChevronDown, ChevronUp } from "lucide-react";
import useSWR from "swr";
import { Switch } from "@/components/ui/switch";
import { Textarea } from "@/components/ui/textarea";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import { agentApi, ngoApi, swrKeys, type AgentSetting, type AgentType } from "@/lib/api";
import { AGENT_LABELS } from "@/lib/utils";
import { useToast } from "@/components/ui/use-toast";

const AGENT_DESCRIPTIONS: Record<AgentType, string> = {
  fundraising: "Helps staff draft proposals, track donors, and manage campaigns.",
  finance: "Assists with budgeting, expense tracking, and financial reports.",
  marketing: "Supports social media, content creation, and outreach strategies.",
  hr: "Handles staff queries, leave management, and onboarding.",
  compliance: "Answers regulatory questions and tracks compliance deadlines.",
};

const ALL_AGENTS: AgentType[] = [
  "fundraising",
  "finance",
  "marketing",
  "hr",
  "compliance",
];

function AgentCard({
  ngoId,
  setting,
  onUpdate,
}: {
  ngoId: string;
  setting: AgentSetting;
  onUpdate: (updated: AgentSetting) => void;
}) {
  const { toast } = useToast();
  const [expanded, setExpanded] = useState(false);
  const [prompt, setPrompt] = useState(setting.custom_prompt ?? "");
  const [saving, setSaving] = useState(false);

  const handleToggle = async (enabled: boolean) => {
    try {
      const updated = await agentApi.upsert(ngoId, {
        agent_name: setting.agent_name,
        is_enabled: enabled,
      });
      onUpdate(updated);
      toast({ title: `${AGENT_LABELS[setting.agent_name]} ${enabled ? "enabled" : "disabled"}` });
    } catch {
      toast({ title: "Failed to update agent", variant: "destructive" });
    }
  };

  const handleSavePrompt = async () => {
    setSaving(true);
    try {
      const updated = await agentApi.upsert(ngoId, {
        agent_name: setting.agent_name,
        custom_prompt: prompt || null,
      });
      onUpdate(updated);
      toast({ title: "Custom prompt saved" });
    } catch {
      toast({ title: "Failed to save prompt", variant: "destructive" });
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="rounded-xl border border-border bg-card overflow-hidden">
      <div className="flex items-center gap-4 p-4">
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2">
            <p className="text-sm font-semibold text-foreground">
              {AGENT_LABELS[setting.agent_name]}
            </p>
            <Badge variant={setting.is_enabled ? "success" : "outline"}>
              {setting.is_enabled ? "Enabled" : "Disabled"}
            </Badge>
          </div>
          <p className="text-xs text-muted-foreground mt-0.5">
            {AGENT_DESCRIPTIONS[setting.agent_name]}
          </p>
        </div>
        <div className="flex items-center gap-3">
          <Switch checked={setting.is_enabled} onCheckedChange={handleToggle} />
          <button
            onClick={() => setExpanded(!expanded)}
            className="text-muted-foreground hover:text-foreground transition-colors"
          >
            {expanded ? <ChevronUp className="h-4 w-4" /> : <ChevronDown className="h-4 w-4" />}
          </button>
        </div>
      </div>

      {expanded && (
        <div className="px-4 pb-4 border-t border-border pt-4 space-y-3">
          <div className="flex items-center gap-1.5">
            <Sparkles className="h-3.5 w-3.5 text-primary" />
            <p className="text-xs font-medium">Custom System Prompt</p>
          </div>
          <Textarea
            value={prompt}
            onChange={(e) => setPrompt(e.target.value)}
            placeholder={`Override the default ${AGENT_LABELS[setting.agent_name]} prompt. Leave blank to use default.`}
            className="min-h-[120px] text-sm font-mono resize-y"
          />
          <div className="flex items-center justify-between">
            <p className="text-xs text-muted-foreground">{prompt.length} characters</p>
            <div className="flex gap-2">
              {prompt !== (setting.custom_prompt ?? "") && (
                <Button variant="ghost" size="sm" onClick={() => setPrompt(setting.custom_prompt ?? "")}>
                  Reset
                </Button>
              )}
              <Button
                size="sm"
                onClick={handleSavePrompt}
                disabled={saving || prompt === (setting.custom_prompt ?? "")}
              >
                {saving && <Loader2 className="mr-1.5 h-3.5 w-3.5 animate-spin" />}
                Save Prompt
              </Button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

export function AgentSettingsPanel({ ngoId }: { ngoId: string }) {
  const { toast } = useToast();
  const { data: ngo, mutate } = useSWR(
    swrKeys.ngo(ngoId),
    () => ngoApi.get(ngoId)
  );

  const settings = ngo?.settings ?? [];

  const handleUpdate = async (updated: AgentSetting) => {
    if (!ngo) return;
    await mutate(
      { ...ngo, settings: settings.map((s) => (s.agent_name === updated.agent_name ? updated : s)) },
      false
    );
  };

  if (!ngo) {
    return (
      <div className="space-y-3">
        {Array.from({ length: 5 }).map((_, i) => (
          <Skeleton key={i} className="h-20 w-full rounded-xl" />
        ))}
      </div>
    );
  }

  return (
    <div className="space-y-3">
      <p className="text-sm text-muted-foreground">
        Enable or disable individual AI agents and customize their system prompts for this NGO.
      </p>
      {ALL_AGENTS.map((agentType) => {
        const setting: AgentSetting = settings.find((s) => s.agent_name === agentType) ?? {
          id: `placeholder-${agentType}`,
          agent_name: agentType,
          is_enabled: false,   // no DB row → actually disabled; user must explicitly enable
          custom_prompt: null,
          created_at: new Date().toISOString(),
          updated_at: new Date().toISOString(),
        };
        return (
          <AgentCard
            key={agentType}
            ngoId={ngoId}
            setting={setting}
            onUpdate={handleUpdate}
          />
        );
      })}
    </div>
  );
}
