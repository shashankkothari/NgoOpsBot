"use client";

import { ScrollText } from "lucide-react";
import { Card, CardContent } from "@/components/ui/card";

export default function AuditPage() {
  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-foreground">Audit Logs</h1>
        <p className="text-muted-foreground mt-1">
          Track all administrative actions and changes across the platform.
        </p>
      </div>

      <Card>
        <CardContent className="py-20 text-center">
          <ScrollText className="h-10 w-10 text-muted-foreground/30 mx-auto mb-3" />
          <p className="text-sm font-medium text-muted-foreground">Audit log endpoint not yet available</p>
          <p className="text-xs text-muted-foreground mt-1">
            This screen will populate once <code className="bg-muted px-1 rounded">GET /api/v1/admin/audit</code> is implemented in the backend.
          </p>
        </CardContent>
      </Card>
    </div>
  );
}
