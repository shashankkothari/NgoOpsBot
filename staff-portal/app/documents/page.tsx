"use client";

import { useSession } from "next-auth/react";
import { FolderOpen, ExternalLink } from "lucide-react";
import { AppShell } from "@/app/components/layout/AppShell";

export default function DocumentsPage() {
  const { data: session } = useSession();

  return (
    <AppShell>
      <div className="flex flex-col h-full overflow-y-auto px-6 py-6">
        <div className="mb-6">
          <h1 className="text-xl font-bold text-slate-900">Documents</h1>
          <p className="text-sm text-slate-400 mt-0.5">
            Access your organization&apos;s shared files
          </p>
        </div>

        <div className="flex flex-col items-center justify-center flex-1 pb-20 gap-4">
          <div className="h-16 w-16 rounded-2xl bg-slate-100 flex items-center justify-center">
            <FolderOpen className="h-8 w-8 text-slate-400" />
          </div>
          <div className="text-center">
            <p className="font-medium text-slate-700">Google Drive</p>
            <p className="text-sm text-slate-400 mt-1 max-w-xs">
              Your admin manages document access from the admin portal.
              Click below to open your organization&apos;s shared folder.
            </p>
          </div>
          <a
            href="https://drive.google.com"
            target="_blank"
            rel="noopener noreferrer"
            className="flex items-center gap-2 h-10 px-5 rounded-lg bg-indigo-600 text-white text-sm font-medium hover:bg-indigo-700 transition-colors"
          >
            <ExternalLink className="h-4 w-4" />
            Open Google Drive
          </a>
          <p className="text-xs text-slate-400">
            Signed in as {session?.user?.email}
          </p>
        </div>
      </div>
    </AppShell>
  );
}
