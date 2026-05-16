import "next-auth";

declare module "next-auth" {
  interface Session {
    backendToken: string;
    staffProfile: {
      id: string;
      name: string;
      role: string;
      ngo_id: string;
      ngo_name: string;
      allowed_agents: string[];
    };
  }
}

declare module "next-auth/jwt" {
  interface JWT {
    backendToken?: string;
    staffProfile?: unknown;
  }
}

export type AgentType =
  | "fundraising"
  | "finance"
  | "marketing"
  | "hr"
  | "compliance"
  | "helper";

export const AGENT_LABELS: Record<AgentType, string> = {
  fundraising: "Fundraising",
  finance: "Finance",
  marketing: "Marketing",
  hr: "HR",
  compliance: "Compliance",
  helper: "Platform Help",
};

export const AGENT_ICONS: Record<AgentType, string> = {
  fundraising: "💰",
  finance: "📊",
  marketing: "📣",
  hr: "👥",
  compliance: "⚖️",
  helper: "❓",
};

// Specialist agents — shown in the main agent list, require enablement
export const ALL_AGENTS: AgentType[] = [
  "fundraising",
  "finance",
  "marketing",
  "hr",
  "compliance",
];

// System agents — always available, shown separately in the sidebar
export const SYSTEM_AGENTS: AgentType[] = ["helper"];

export interface Message {
  id: string;
  role: "user" | "assistant";
  content: string;
  created_at: string;
}

export interface Thread {
  id: string;
  agent_name: AgentType;
  created_at: string;
  updated_at: string;
}

export interface Reminder {
  id: string;
  title: string;
  message: string;
  due_at: string;
  repeat_interval: string | null;
  assignee_ids: string[];
  agent_name: string | null;
  is_acknowledged: boolean;
  created_by_id: string;
  ngo_id: string;
}

export interface Staff {
  id: string;
  name: string;
  email: string;
  role: string;
  telegram_user_id: number | null;
}

export interface SupportTicket {
  id: string;
  title: string;
  description: string;
  category: string;
  priority: "low" | "medium" | "high" | "urgent";
  status: "open" | "in_progress" | "resolved" | "closed";
  admin_reply: string | null;
  created_by_id: string;
  created_by_name: string;
  ngo_id: string;
  ngo_name: string;
  created_at: string;
  updated_at: string;
}
