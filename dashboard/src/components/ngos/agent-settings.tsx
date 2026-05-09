"use client";

import { useState } from "react";
import { Loader2, Sparkles, ChevronDown, ChevronUp } from "lucide-react";
import useSWR, { mutate } from "swr";
import { Switch } from "@/components/ui/switch";
import { Textarea } from "@/components/ui/textarea";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import { agentApi, swrKeys, type AgentSettings, type AgentType } from "@/lib/api";
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
  settings,
  onUpdate,
}: {
  ngoId: string;
  settings: AgentSettings | undefined;
  onUpdate: (updated: AgentSettings) => void;
}) {
  const { toast } = useToast();
  const [expanded, setExpanded] = useState(false);
  const [prompt, setPrompt] = useState(settings?.custom_prompt ?? "");
  const [saving, setSaving] = useState(false);

  if (!settings) {
    return <Skeleton className="h-20 w-full" />;
  }

  const agentType = settings.agent_type;

  const handleToggle = async (enabled: boolean) => {
    try {
      const updated = await agentApi.update(ngoId, agentType, {
        is_enabled: enabled,
      });
      onUpdate(updated);
      toast({
        title: `${AGENT_LABELS[agentType]} ${enabled ? "enabled" : "disabled"}`,
      });
    } catch {
      toast({
        title: "Failed to update agent",
        variant: "destructive",
      });
    }
  };

  const handleSavePrompt = async () => {
    setSaving(true);
    try {
      const updated = await agentApi.update(ngoId, agentType, {
        custom_prompt: prompt || null,
      });
      onUpdate(updated);
      toast({
        title: "Custom prompt saved",
        description: `${AGENT_LABELS[agentType]} agent prompt updated.`,
      });
    } catch {
      toast({
        title: "Failed to save prompt",
        variant: "destructive",
      });
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="rounded-xl border border-border bg-card overflow-hidden">
      {/* Header row */}
      <div className="flex items-center gap-4 p-4">
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2">
            <p className="text-sm font-semibold text-foreground">
              {AGENT_LABELS[agentType]}
            </p>
            <Badge variant={settings.is_enabled ? "success" : "outline"}>
              {settings.is_enabled ? "Enabled" : "Disabled"}
            </Badge>
          </div>
          <p className="text-xs text-muted-foreground mt-0.5">
            {AGENT_DESCRIPTIONS[agentType]}
          </p>
        </div>
        <div className="flex items-center gap-3">
          <Switch
            checked={settings.is_enabled}
            onCheckedChange={handleToggle}
          />
          <button
            onClick={() => setExpanded(!expanded)}
            className="text-muted-foreground hover:text-foreground transition-colors"
          >
            {expanded ? (
              <ChevronUp className="h-4 w-4" />
            ) : (
              <ChevronDown className="h-4 w-4" />
            )}
          </button>
        </div>
      </div>

      {/* Expanded custom prompt */}
      {expanded && (
        <div className="px-4 pb-4 border-t border-border pt-4 space-y-3">
          <div className="flex items-center gap-1.5">
            <Sparkles className="h-3.5 w-3.5 text-primary" />
            <p className="text-xs font-medium text-foreground">
              Custom System Prompt
            </p>
          </div>
          <Textarea
            value={prompt}
            onChange={(e) => setPrompt(e.target.value)}
            placeholder={`Override the default ${AGENT_LABELS[agentType]} agent prompt. Leave blank to use the default.`}
            className="min-h-[120px] text-sm font-mono resize-y"
          />
          <div className="flex items-center justify-between">
            <p className="text-xs text-muted-foreground">
              {prompt.length} characters
            </p>
            <div className="flex gap-2">
              {prompt !== (settings.custom_prompt ?? "") && (
                <Button
                  variant="ghost"
                  size="sm"
                  onClick={() => setPrompt(settings.custom_prompt ?? "")}
                >
                  Reset
                </Button>
              )}
              <Button
                size="sm"
                onClick={handleSavePrompt}
                disabled={saving || prompt === (settings.custom_prompt ?? "")}
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

interface AgentSettingsProps {
  ngoId: string;
}

export function AgentSettingsPanel({ ngoId }: AgentSettingsProps) {
  const { data, isLoading, mutate: mutateAgents } = useSWR<AgentSettings[]>(
    swrKeys.agents(ngoId),
    () => agentApi.list(ngoId)
  );

  const handleUpdate = (updated: AgentSettings) => {
    if (!data) return;
    mutateAgents(
      data.map((s) => (s.agent_type === updated.agent_type ? updated : s)),
      false
    );
  };

  if (isLoading) {
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
        Enable or disable individual AI agents and customize their system prompts
        for this NGO.
      </p>
      {ALL_AGENTS.map((agentType) => {
        const settings = data?.find((s) => s.agent_type === agentType) ?? {
          id: `placeholder-${agentType}`,
          ngo_id: ngoId,
          agent_type: agentType,
          is_enabled: false,
          custom_prompt: null,
          updated_at: new Date().toISOString(),
        };
        return (
          <AgentCard
            key={agentType}
            ngoId={ngoId}
            settings={settings}
            onUpdate={handleUpdate}
          />
        );
      })}
    </div>
  );
}
