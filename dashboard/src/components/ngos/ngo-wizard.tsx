"use client";

import { useState } from "react";
import {
  Check,
  ChevronRight,
  ChevronLeft,
  Loader2,
  CheckCircle2,
  XCircle,
  Copy,
  ExternalLink,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Switch } from "@/components/ui/switch";
import { Badge } from "@/components/ui/badge";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { type NGO, type NGOCreate, type AgentType, ngoApi, agentApi } from "@/lib/api";
import { TIMEZONES, LANGUAGES, AGENT_LABELS } from "@/lib/utils";

// ─── Step data ────────────────────────────────────────────────────────────────

const STEPS = [
  { id: 1, label: "Basic Info" },
  { id: 2, label: "Telegram" },
  { id: 3, label: "Anthropic Key" },
  { id: 4, label: "Agents" },
  { id: 5, label: "Confirm" },
] as const;

const ALL_AGENTS: AgentType[] = [
  "fundraising",
  "finance",
  "marketing",
  "hr",
  "compliance",
];

const AGENT_DESCRIPTIONS: Record<AgentType, string> = {
  fundraising: "Campaign tracking, donor outreach, grant management",
  finance: "Budget queries, expense tracking, financial summaries",
  marketing: "Content scheduling, outreach analytics, campaign reports",
  hr: "Volunteer management, onboarding, leave tracking",
  compliance: "Policy queries, regulatory filings, audit support",
};

// ─── Wizard state ─────────────────────────────────────────────────────────────

interface WizardData {
  name: string;
  timezone: string;
  language: string;
  telegram_bot_token: string;
  anthropic_api_key: string;
  enabled_agents: AgentType[];
}

const DEFAULT_DATA: WizardData = {
  name: "",
  timezone: "UTC",
  language: "en",
  telegram_bot_token: "",
  anthropic_api_key: "",
  enabled_agents: [...ALL_AGENTS],
};

// ─── Sub-steps ────────────────────────────────────────────────────────────────

function StepBasicInfo({
  data,
  onChange,
}: {
  data: WizardData;
  onChange: (patch: Partial<WizardData>) => void;
}) {
  return (
    <div className="space-y-4">
      <div className="space-y-1.5">
        <Label htmlFor="wiz-name">
          Organization Name <span className="text-destructive">*</span>
        </Label>
        <Input
          id="wiz-name"
          placeholder="Green Future NGO"
          value={data.name}
          onChange={(e) => onChange({ name: e.target.value })}
        />
        <p className="text-xs text-muted-foreground">
          A unique slug will be auto-generated from the name.
        </p>
      </div>

      <div className="grid grid-cols-2 gap-4">
        <div className="space-y-1.5">
          <Label>
            Timezone <span className="text-destructive">*</span>
          </Label>
          <Select
            value={data.timezone}
            onValueChange={(v) => onChange({ timezone: v })}
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
        </div>

        <div className="space-y-1.5">
          <Label>
            Language <span className="text-destructive">*</span>
          </Label>
          <Select
            value={data.language}
            onValueChange={(v) => onChange({ language: v })}
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
        </div>
      </div>
    </div>
  );
}

type TelegramStatus = "idle" | "checking" | "ok" | "error";

function StepTelegram({
  data,
  onChange,
}: {
  data: WizardData;
  onChange: (patch: Partial<WizardData>) => void;
}) {
  const [status, setStatus] = useState<TelegramStatus>("idle");
  const [botName, setBotName] = useState<string>("");
  const [errorMsg, setErrorMsg] = useState<string>("");

  const verify = async () => {
    if (!data.telegram_bot_token.trim()) return;
    setStatus("checking");
    setErrorMsg("");
    setBotName("");
    try {
      const resp = await fetch(
        `https://api.telegram.org/bot${data.telegram_bot_token.trim()}/getMe`
      );
      const json = await resp.json();
      if (json.ok) {
        setBotName(`@${json.result.username}`);
        setStatus("ok");
      } else {
        setErrorMsg(json.description || "Invalid token");
        setStatus("error");
      }
    } catch {
      setErrorMsg("Network error — check token and try again");
      setStatus("error");
    }
  };

  return (
    <div className="space-y-4">
      <div className="rounded-xl border border-border bg-muted/30 p-4">
        <p className="text-sm text-muted-foreground">
          Create a new bot via{" "}
          <a
            href="https://t.me/BotFather"
            target="_blank"
            rel="noopener noreferrer"
            className="text-primary underline underline-offset-2 inline-flex items-center gap-0.5"
          >
            @BotFather <ExternalLink className="h-3 w-3" />
          </a>{" "}
          and paste the token below.
        </p>
      </div>

      <div className="space-y-1.5">
        <Label htmlFor="wiz-token">
          Bot Token <span className="text-destructive">*</span>
        </Label>
        <div className="flex gap-2">
          <Input
            id="wiz-token"
            type="password"
            placeholder="123456789:AAH5YL..."
            className="font-mono flex-1"
            value={data.telegram_bot_token}
            onChange={(e) => {
              onChange({ telegram_bot_token: e.target.value });
              setStatus("idle");
            }}
          />
          <Button
            type="button"
            variant="outline"
            onClick={verify}
            disabled={!data.telegram_bot_token.trim() || status === "checking"}
          >
            {status === "checking" ? (
              <Loader2 className="h-4 w-4 animate-spin" />
            ) : (
              "Verify"
            )}
          </Button>
        </div>
      </div>

      {status === "ok" && (
        <div className="flex items-center gap-2 text-emerald-600 dark:text-emerald-400 text-sm">
          <CheckCircle2 className="h-4 w-4" />
          Token verified — bot is <span className="font-medium">{botName}</span>
        </div>
      )}
      {status === "error" && (
        <div className="flex items-center gap-2 text-destructive text-sm">
          <XCircle className="h-4 w-4" />
          {errorMsg}
        </div>
      )}
    </div>
  );
}

function StepAnthropicKey({
  data,
  onChange,
}: {
  data: WizardData;
  onChange: (patch: Partial<WizardData>) => void;
}) {
  const usePlatformKey = !data.anthropic_api_key;

  return (
    <div className="space-y-4">
      <div className="rounded-xl border border-border bg-muted/30 p-4 space-y-1">
        <p className="text-sm font-medium">Platform key available</p>
        <p className="text-xs text-muted-foreground">
          You can leave this blank to use the platform-level Anthropic key.
          Providing an NGO-specific key isolates token billing to this
          organization.
        </p>
      </div>

      <div className="space-y-1.5">
        <Label htmlFor="wiz-ant-key">Anthropic API Key (optional)</Label>
        <Input
          id="wiz-ant-key"
          type="password"
          placeholder="sk-ant-api03-..."
          className="font-mono"
          value={data.anthropic_api_key}
          onChange={(e) => onChange({ anthropic_api_key: e.target.value })}
        />
      </div>

      <div className="flex items-center gap-2 text-sm text-muted-foreground">
        {usePlatformKey ? (
          <>
            <CheckCircle2 className="h-4 w-4 text-emerald-500" />
            Will use platform Anthropic key
          </>
        ) : (
          <>
            <CheckCircle2 className="h-4 w-4 text-emerald-500" />
            Will use NGO-specific key
          </>
        )}
      </div>
    </div>
  );
}

function StepAgents({
  data,
  onChange,
}: {
  data: WizardData;
  onChange: (patch: Partial<WizardData>) => void;
}) {
  const toggle = (agent: AgentType) => {
    const current = data.enabled_agents;
    const next = current.includes(agent)
      ? current.filter((a) => a !== agent)
      : [...current, agent];
    onChange({ enabled_agents: next });
  };

  return (
    <div className="space-y-3">
      <p className="text-sm text-muted-foreground">
        All agents are enabled by default. You can change this after onboarding
        from the NGO settings.
      </p>
      {ALL_AGENTS.map((agent) => {
        const enabled = data.enabled_agents.includes(agent);
        return (
          <div
            key={agent}
            className={`flex items-center justify-between rounded-xl border p-4 transition-colors ${
              enabled
                ? "border-primary/30 bg-primary/5"
                : "border-border bg-background"
            }`}
          >
            <div className="flex-1 min-w-0 pr-4">
              <div className="flex items-center gap-2">
                <p className="text-sm font-medium">{AGENT_LABELS[agent]}</p>
                {enabled && (
                  <Badge variant="success" className="text-xs">
                    Enabled
                  </Badge>
                )}
              </div>
              <p className="text-xs text-muted-foreground mt-0.5">
                {AGENT_DESCRIPTIONS[agent]}
              </p>
            </div>
            <Switch checked={enabled} onCheckedChange={() => toggle(agent)} />
          </div>
        );
      })}
    </div>
  );
}

function StepConfirm({
  data,
  createdNgo,
  webhookUrl,
  onCopy,
}: {
  data: WizardData;
  createdNgo: NGO | null;
  webhookUrl: string | null;
  onCopy: (text: string) => void;
}) {
  if (createdNgo) {
    return (
      <div className="space-y-4">
        <div className="flex items-center gap-3 p-4 rounded-xl border border-emerald-500/30 bg-emerald-500/5">
          <CheckCircle2 className="h-6 w-6 text-emerald-500 flex-shrink-0" />
          <div>
            <p className="font-medium text-emerald-700 dark:text-emerald-400">
              NGO created successfully!
            </p>
            <p className="text-xs text-muted-foreground mt-0.5">
              The webhook has been registered with Telegram automatically.
            </p>
          </div>
        </div>

        {webhookUrl && (
          <div className="space-y-1.5">
            <Label>Webhook URL</Label>
            <div className="flex gap-2">
              <Input
                readOnly
                value={webhookUrl}
                className="font-mono text-xs"
              />
              <Button
                type="button"
                variant="outline"
                size="icon"
                onClick={() => onCopy(webhookUrl)}
              >
                <Copy className="h-4 w-4" />
              </Button>
            </div>
            <p className="text-xs text-muted-foreground">
              This URL is automatically registered with Telegram.
            </p>
          </div>
        )}

        <div className="rounded-xl border border-border p-4 space-y-2 text-sm">
          <div className="flex justify-between">
            <span className="text-muted-foreground">Name</span>
            <span className="font-medium">{createdNgo.name}</span>
          </div>
          <div className="flex justify-between">
            <span className="text-muted-foreground">Slug</span>
            <code className="text-xs bg-muted px-1.5 py-0.5 rounded">{createdNgo.slug}</code>
          </div>
          <div className="flex justify-between">
            <span className="text-muted-foreground">Agents enabled</span>
            <span className="font-medium">{data.enabled_agents.length}</span>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-4">
      <p className="text-sm text-muted-foreground">
        Review the configuration before creating the NGO.
      </p>

      <div className="rounded-xl border border-border divide-y divide-border text-sm">
        <div className="flex justify-between px-4 py-3">
          <span className="text-muted-foreground">Name</span>
          <span className="font-medium">{data.name || "—"}</span>
        </div>
        <div className="flex justify-between px-4 py-3">
          <span className="text-muted-foreground">Slug</span>
          <span className="text-xs text-muted-foreground italic">auto-generated</span>
        </div>
        <div className="flex justify-between px-4 py-3">
          <span className="text-muted-foreground">Timezone</span>
          <span>{data.timezone}</span>
        </div>
        <div className="flex justify-between px-4 py-3">
          <span className="text-muted-foreground">Language</span>
          <span>
            {LANGUAGES.find((l) => l.value === data.language)?.label ||
              data.language}
          </span>
        </div>
        <div className="flex justify-between px-4 py-3">
          <span className="text-muted-foreground">Telegram bot</span>
          <span>{data.telegram_bot_token ? "Configured" : "—"}</span>
        </div>
        <div className="flex justify-between px-4 py-3">
          <span className="text-muted-foreground">Anthropic key</span>
          <span>
            {data.anthropic_api_key ? "NGO-specific" : "Platform key"}
          </span>
        </div>
        <div className="flex justify-between px-4 py-3">
          <span className="text-muted-foreground">Agents</span>
          <div className="flex flex-wrap gap-1 justify-end max-w-[60%]">
            {data.enabled_agents.length === ALL_AGENTS.length ? (
              <Badge variant="secondary" className="text-xs">
                All ({ALL_AGENTS.length})
              </Badge>
            ) : data.enabled_agents.length === 0 ? (
              <span className="text-muted-foreground">None</span>
            ) : (
              data.enabled_agents.map((a) => (
                <Badge key={a} variant="outline" className="text-xs">
                  {AGENT_LABELS[a]}
                </Badge>
              ))
            )}
          </div>
        </div>
      </div>
    </div>
  );
}

// ─── Wizard root ──────────────────────────────────────────────────────────────

interface NGOWizardProps {
  onComplete: (ngo: NGO) => void;
  onCancel: () => void;
  onCreate: (payload: NGOCreate) => Promise<NGO>;
}

export function NGOWizard({ onComplete, onCancel, onCreate }: NGOWizardProps) {
  const [step, setStep] = useState(1);
  const [data, setData] = useState<WizardData>(DEFAULT_DATA);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [submitError, setSubmitError] = useState<string>("");
  const [createdNgo, setCreatedNgo] = useState<NGO | null>(null);
  const [webhookUrl, setWebhookUrl] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);

  const patch = (p: Partial<WizardData>) => setData((d) => ({ ...d, ...p }));

  const canAdvance = (): boolean => {
    switch (step) {
      case 1:
        return data.name.trim().length >= 2;
      case 2:
        return data.telegram_bot_token.trim().length > 10;
      case 3:
        return true;
      case 4:
        return true;
      case 5:
        return createdNgo !== null;
      default:
        return false;
    }
  };

  const handleSubmit = async () => {
    setIsSubmitting(true);
    setSubmitError("");
    try {
      const payload: NGOCreate = {
        name: data.name,
        telegram_bot_token: data.telegram_bot_token,
        anthropic_api_key: data.anthropic_api_key || null,
        timezone: data.timezone,
        language: data.language,
      };
      const ngo = await onCreate(payload);
      setCreatedNgo(ngo);

      // Persist the agent selections made in Step 4.
      // Run all upserts in parallel; failures are non-fatal.
      await Promise.allSettled(
        ALL_AGENTS.map((agent) =>
          agentApi.upsert(ngo.id, {
            agent_name: agent,
            is_enabled: data.enabled_agents.includes(agent),
          })
        )
      );

      try {
        const result = await ngoApi.refreshWebhook(ngo.id);
        setWebhookUrl(result.webhook_url ?? null);
      } catch {
        // non-fatal: webhook registration failed but NGO was created
      }
    } catch (err) {
      setSubmitError(err instanceof Error ? err.message : "Failed to create NGO");
    } finally {
      setIsSubmitting(false);
    }
  };

  const handleCopy = (text: string) => {
    navigator.clipboard.writeText(text);
    setCopied(true);
    setTimeout(() => setCopied(false), 1500);
  };

  return (
    <div className="flex flex-col h-full">
      {/* Step indicator */}
      <div className="flex items-center gap-0 mb-6">
        {STEPS.map((s, i) => (
          <div key={s.id} className="flex items-center flex-1 last:flex-none">
            <div className="flex flex-col items-center">
              <div
                className={`h-7 w-7 rounded-full flex items-center justify-center text-xs font-semibold transition-colors ${
                  step > s.id
                    ? "bg-primary text-primary-foreground"
                    : step === s.id
                    ? "bg-primary/20 text-primary border-2 border-primary"
                    : "bg-muted text-muted-foreground"
                }`}
              >
                {step > s.id ? <Check className="h-3.5 w-3.5" /> : s.id}
              </div>
              <span
                className={`text-[10px] mt-1 whitespace-nowrap ${
                  step === s.id
                    ? "text-foreground font-medium"
                    : "text-muted-foreground"
                }`}
              >
                {s.label}
              </span>
            </div>
            {i < STEPS.length - 1 && (
              <div
                className={`h-px flex-1 mx-1 mb-4 transition-colors ${
                  step > s.id ? "bg-primary" : "bg-border"
                }`}
              />
            )}
          </div>
        ))}
      </div>

      {/* Step content */}
      <div className="flex-1 overflow-y-auto">
        {step === 1 && <StepBasicInfo data={data} onChange={patch} />}
        {step === 2 && <StepTelegram data={data} onChange={patch} />}
        {step === 3 && <StepAnthropicKey data={data} onChange={patch} />}
        {step === 4 && <StepAgents data={data} onChange={patch} />}
        {step === 5 && (
          <StepConfirm
            data={data}
            createdNgo={createdNgo}
            webhookUrl={webhookUrl}
            onCopy={handleCopy}
          />
        )}
      </div>

      {submitError && (
        <p className="text-sm text-destructive mt-3">{submitError}</p>
      )}

      {/* Navigation */}
      <div className="flex justify-between pt-4 mt-4 border-t border-border">
        {step > 1 && !createdNgo ? (
          <Button
            type="button"
            variant="ghost"
            onClick={() => setStep((s) => s - 1)}
          >
            <ChevronLeft className="mr-1.5 h-4 w-4" />
            Back
          </Button>
        ) : (
          <div />
        )}

        {createdNgo ? (
          <Button onClick={() => onComplete(createdNgo)}>
            <Check className="mr-1.5 h-4 w-4" />
            Done
          </Button>
        ) : step === 5 ? (
          <Button onClick={handleSubmit} disabled={isSubmitting}>
            {isSubmitting ? (
              <Loader2 className="mr-2 h-4 w-4 animate-spin" />
            ) : null}
            Create NGO
          </Button>
        ) : step === 1 ? (
          <div className="flex gap-2">
            <Button type="button" variant="outline" onClick={onCancel}>
              Cancel
            </Button>
            <Button
              onClick={() => setStep((s) => s + 1)}
              disabled={!canAdvance()}
            >
              Next
              <ChevronRight className="ml-1.5 h-4 w-4" />
            </Button>
          </div>
        ) : (
          <Button
            onClick={() => setStep((s) => s + 1)}
            disabled={!canAdvance()}
          >
            {step === 4 ? "Review" : "Next"}
            <ChevronRight className="ml-1.5 h-4 w-4" />
          </Button>
        )}
      </div>

      {copied && (
        <p className="text-xs text-emerald-600 text-center mt-2">
          Copied to clipboard!
        </p>
      )}
    </div>
  );
}
