"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import {
  Bot,
  Building2,
  Users,
  MessageSquare,
  Bell,
  ScrollText,
  Activity,
  LayoutDashboard,
  LifeBuoy,
} from "lucide-react";
import { cn } from "@/lib/utils";

const navItems = [
  {
    label: "Overview",
    href: "/dashboard",
    icon: LayoutDashboard,
    exact: true,
  },
  {
    label: "NGOs",
    href: "/dashboard/ngos",
    icon: Building2,
  },
  {
    label: "Staff",
    href: "/dashboard/staff",
    icon: Users,
  },
  {
    label: "Conversations",
    href: "/dashboard/conversations",
    icon: MessageSquare,
  },
  {
    label: "Reminders",
    href: "/dashboard/reminders",
    icon: Bell,
  },
  {
    label: "Support Queue",
    href: "/dashboard/support",
    icon: LifeBuoy,
  },
  {
    label: "Audit Logs",
    href: "/dashboard/audit",
    icon: ScrollText,
  },
  {
    label: "System Health",
    href: "/dashboard/system",
    icon: Activity,
  },
];

export function Sidebar() {
  const pathname = usePathname();

  const isActive = (href: string, exact?: boolean) => {
    if (exact) return pathname === href;
    return pathname.startsWith(href);
  };

  return (
    <aside className="fixed inset-y-0 left-0 z-40 flex w-60 flex-col bg-sidebar border-r border-sidebar-border">
      {/* Logo */}
      <div className="flex h-16 items-center gap-3 px-5 border-b border-sidebar-border">
        <div className="h-8 w-8 rounded-lg bg-sidebar-primary flex items-center justify-center flex-shrink-0">
          <Bot className="h-4.5 w-4.5 text-sidebar-primary-foreground" />
        </div>
        <div className="min-w-0">
          <p className="text-sm font-semibold text-sidebar-foreground truncate">
            NGO OpsBot
          </p>
          <p className="text-xs text-sidebar-foreground/50 truncate">
            Admin Console
          </p>
        </div>
      </div>

      {/* Nav */}
      <nav className="flex-1 overflow-y-auto py-4 px-3 space-y-0.5 scrollbar-thin">
        <p className="px-2 mb-2 text-xs font-medium text-sidebar-foreground/40 uppercase tracking-wider">
          Platform
        </p>
        {navItems.map((item) => {
          const Icon = item.icon;
          const active = isActive(item.href, item.exact);
          return (
            <Link
              key={item.href}
              href={item.href}
              className={cn(
                "group flex items-center gap-3 rounded-lg px-3 py-2 text-sm font-medium transition-all",
                active
                  ? "bg-sidebar-accent text-sidebar-foreground"
                  : "text-sidebar-foreground/60 hover:bg-sidebar-accent/60 hover:text-sidebar-foreground"
              )}
            >
              <Icon
                className={cn(
                  "h-4 w-4 flex-shrink-0 transition-colors",
                  active
                    ? "text-sidebar-primary"
                    : "text-sidebar-foreground/40 group-hover:text-sidebar-foreground/70"
                )}
              />
              {item.label}
            </Link>
          );
        })}
      </nav>

      {/* Footer */}
      <div className="p-4 border-t border-sidebar-border">
        <p className="text-xs text-sidebar-foreground/30 text-center">
          v0.1.0 · Platform Admin
        </p>
      </div>
    </aside>
  );
}
