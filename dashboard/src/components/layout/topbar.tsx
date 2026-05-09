"use client";

import { usePathname } from "next/navigation";
import { signOut, useSession } from "next-auth/react";
import {
  ChevronRight,
  LogOut,
  User,
  Home,
} from "lucide-react";
import { Button } from "@/components/ui/button";

const BREADCRUMB_MAP: Record<string, string> = {
  dashboard: "Dashboard",
  ngos: "NGOs",
  staff: "Staff",
  conversations: "Conversations",
  reminders: "Reminders",
  audit: "Audit Logs",
  system: "System Health",
};

function getBreadcrumbs(pathname: string) {
  const segments = pathname.split("/").filter(Boolean);
  const crumbs: { label: string; href: string }[] = [];

  let path = "";
  for (const segment of segments) {
    path += `/${segment}`;
    const label =
      BREADCRUMB_MAP[segment] ||
      (segment.length > 20
        ? `${segment.slice(0, 8)}…`
        : segment.charAt(0).toUpperCase() + segment.slice(1));
    crumbs.push({ label, href: path });
  }
  return crumbs;
}

export function Topbar() {
  const pathname = usePathname();
  const { data: session } = useSession();
  const breadcrumbs = getBreadcrumbs(pathname);

  return (
    <header className="sticky top-0 z-30 flex h-16 items-center justify-between border-b border-border bg-background/95 backdrop-blur px-6">
      {/* Breadcrumbs */}
      <nav className="flex items-center gap-1 text-sm text-muted-foreground">
        <Home className="h-3.5 w-3.5" />
        {breadcrumbs.map((crumb, i) => (
          <span key={crumb.href} className="flex items-center gap-1">
            <ChevronRight className="h-3.5 w-3.5" />
            <span
              className={
                i === breadcrumbs.length - 1
                  ? "text-foreground font-medium"
                  : "hover:text-foreground"
              }
            >
              {crumb.label}
            </span>
          </span>
        ))}
      </nav>

      {/* Right side */}
      <div className="flex items-center gap-3">
        <div className="flex items-center gap-2 text-sm">
          <div className="h-8 w-8 rounded-full bg-primary/10 flex items-center justify-center">
            <User className="h-4 w-4 text-primary" />
          </div>
          <span className="text-muted-foreground font-medium hidden sm:block">
            {session?.user?.name || "Admin"}
          </span>
        </div>
        <Button
          variant="ghost"
          size="sm"
          onClick={() => signOut({ callbackUrl: "/login" })}
          className="gap-1.5 text-muted-foreground hover:text-foreground"
        >
          <LogOut className="h-4 w-4" />
          <span className="hidden sm:inline">Sign out</span>
        </Button>
      </div>
    </header>
  );
}
