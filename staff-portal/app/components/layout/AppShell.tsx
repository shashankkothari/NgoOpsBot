"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useSession, signOut } from "next-auth/react";
import {
  MessageSquare,
  Bell,
  HelpCircle,
  FolderOpen,
  Settings,
  LogOut,
  Bot,
} from "lucide-react";
import { cn } from "@/app/lib/utils";
import { ALL_AGENTS, SYSTEM_AGENTS, AGENT_ICONS, AGENT_LABELS, type AgentType } from "@/app/lib/types";

const NAV_ITEMS = [
  { href: "/chat", label: "Chat", icon: MessageSquare },
  { href: "/reminders", label: "Reminders", icon: Bell },
  { href: "/support", label: "Help & Support", icon: HelpCircle },
  { href: "/documents", label: "Documents", icon: FolderOpen },
  { href: "/settings", label: "Settings", icon: Settings },
];

interface AppShellProps {
  children: React.ReactNode;
  activeAgent?: AgentType | null;
  onAgentSelect?: (agent: AgentType) => void;
  showAgentSidebar?: boolean;
}

export function AppShell({
  children,
  activeAgent,
  onAgentSelect,
  showAgentSidebar = false,
}: AppShellProps) {
  const pathname = usePathname();
  const { data: session } = useSession();
  const allowedAgents = session?.staffProfile?.allowed_agents ?? [];

  return (
    <div className="flex h-screen bg-slate-50 overflow-hidden">
      {/* Left nav */}
      <aside className="w-16 flex flex-col items-center py-4 gap-1 bg-white border-r border-slate-200 z-20">
        <div className="h-9 w-9 rounded-xl bg-indigo-600 flex items-center justify-center mb-4">
          <Bot className="h-5 w-5 text-white" />
        </div>

        {NAV_ITEMS.map(({ href, label, icon: Icon }) => (
          <Link
            key={href}
            href={href}
            title={label}
            className={cn(
              "flex h-10 w-10 items-center justify-center rounded-lg transition-colors",
              pathname.startsWith(href)
                ? "bg-indigo-50 text-indigo-600"
                : "text-slate-500 hover:bg-slate-100 hover:text-slate-700"
            )}
          >
            <Icon className="h-5 w-5" />
          </Link>
        ))}

        <div className="flex-1" />
        <button
          onClick={() => signOut({ callbackUrl: "/login" })}
          title="Sign out"
          className="flex h-10 w-10 items-center justify-center rounded-lg text-slate-400 hover:bg-red-50 hover:text-red-500 transition-colors"
        >
          <LogOut className="h-5 w-5" />
        </button>
      </aside>

      {/* Agent sidebar (chat page only) */}
      {showAgentSidebar && (
        <aside className="w-56 bg-white border-r border-slate-200 flex flex-col overflow-hidden">
          <div className="px-4 py-3 border-b border-slate-100">
            <p className="text-xs font-semibold text-slate-400 uppercase tracking-wider">
              Agents
            </p>
          </div>
          <div className="flex-1 overflow-y-auto py-2">
            {ALL_AGENTS.map((agent) => {
              const enabled = allowedAgents.includes(agent);
              return (
                <button
                  key={agent}
                  disabled={!enabled}
                  onClick={() => enabled && onAgentSelect?.(agent)}
                  className={cn(
                    "w-full flex items-center gap-3 px-4 py-2.5 text-sm transition-colors text-left",
                    activeAgent === agent
                      ? "bg-indigo-50 text-indigo-700 font-medium"
                      : enabled
                      ? "text-slate-700 hover:bg-slate-50"
                      : "text-slate-300 cursor-not-allowed"
                  )}
                >
                  <span className="text-base">{AGENT_ICONS[agent]}</span>
                  <span>{AGENT_LABELS[agent]}</span>
                  {!enabled && (
                    <span className="ml-auto text-xs text-slate-300">
                      Locked
                    </span>
                  )}
                </button>
              );
            })}
          </div>

          {/* Platform Help — always available, pinned above the profile strip */}
          <div className="border-t border-slate-100 py-2">
            {SYSTEM_AGENTS.map((agent) => (
              <button
                key={agent}
                onClick={() => onAgentSelect?.(agent)}
                title="Ask questions about using this platform"
                className={cn(
                  "w-full flex items-center gap-3 px-4 py-2.5 text-sm transition-colors text-left",
                  activeAgent === agent
                    ? "bg-amber-50 text-amber-700 font-medium"
                    : "text-slate-500 hover:bg-slate-50 hover:text-slate-700"
                )}
              >
                <span className="text-base">{AGENT_ICONS[agent]}</span>
                <span>{AGENT_LABELS[agent]}</span>
              </button>
            ))}
          </div>

          {/* Profile strip */}
          <div className="border-t border-slate-100 px-4 py-3">
            <p className="text-xs font-medium text-slate-700 truncate">
              {session?.staffProfile?.name ?? session?.user?.name ?? "Staff"}
            </p>
            <p className="text-xs text-slate-400 truncate">
              {session?.staffProfile?.ngo_name ?? ""}
            </p>
          </div>
        </aside>
      )}

      {/* Main content */}
      <main className="flex-1 overflow-hidden">{children}</main>
    </div>
  );
}
