"use client";

import { useState } from "react";
import useSWR from "swr";
import { MessageSquare, User, Bot, Filter, ChevronRight, ArrowLeft } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import {
  conversationApi,
  ngoApi,
  swrKeys,
  type ConversationSession,
  type ConversationMessage,
  type PaginatedResponse,
  type NGO,
  type AgentType,
} from "@/lib/api";
import { formatDateTime, formatRelativeTime, AGENT_LABELS } from "@/lib/utils";

const ALL_AGENTS: AgentType[] = [
  "fundraising",
  "finance",
  "marketing",
  "hr",
  "compliance",
];

function MessageBubble({ message }: { message: ConversationMessage }) {
  const isUser = message.role === "user";
  return (
    <div
      className={`flex gap-3 ${isUser ? "flex-row" : "flex-row-reverse"}`}
    >
      <div
        className={`h-8 w-8 rounded-full flex items-center justify-center flex-shrink-0 ${
          isUser ? "bg-muted" : "bg-primary/10"
        }`}
      >
        {isUser ? (
          <User className="h-4 w-4 text-muted-foreground" />
        ) : (
          <Bot className="h-4 w-4 text-primary" />
        )}
      </div>
      <div
        className={`max-w-[75%] rounded-xl px-4 py-2.5 text-sm ${
          isUser
            ? "bg-muted text-foreground rounded-tl-none"
            : "bg-primary text-primary-foreground rounded-tr-none"
        }`}
      >
        <p className="whitespace-pre-wrap">{message.content}</p>
        <p
          className={`text-xs mt-1.5 ${
            isUser ? "text-muted-foreground" : "text-primary-foreground/70"
          }`}
        >
          {formatDateTime(message.timestamp)}
        </p>
      </div>
    </div>
  );
}

function ThreadView({
  sessionId,
  onBack,
}: {
  sessionId: string;
  onBack: () => void;
}) {
  const { data, isLoading } = useSWR<ConversationMessage[]>(
    swrKeys.messages(sessionId),
    () => conversationApi.getMessages(sessionId)
  );

  return (
    <Card className="flex flex-col h-[600px]">
      <CardHeader className="pb-3 border-b border-border">
        <div className="flex items-center gap-2">
          <Button
            variant="ghost"
            size="icon"
            className="h-8 w-8"
            onClick={onBack}
          >
            <ArrowLeft className="h-4 w-4" />
          </Button>
          <CardTitle className="text-base">Conversation Thread</CardTitle>
        </div>
      </CardHeader>
      <CardContent className="flex-1 overflow-y-auto p-4 space-y-4 scrollbar-thin">
        {isLoading ? (
          Array.from({ length: 4 }).map((_, i) => (
            <div
              key={i}
              className={`flex gap-3 ${i % 2 === 0 ? "" : "flex-row-reverse"}`}
            >
              <Skeleton className="h-8 w-8 rounded-full flex-shrink-0" />
              <Skeleton
                className={`h-16 w-64 rounded-xl ${
                  i % 2 === 0 ? "rounded-tl-none" : "rounded-tr-none"
                }`}
              />
            </div>
          ))
        ) : data?.length ? (
          data.map((msg) => <MessageBubble key={msg.id} message={msg} />)
        ) : (
          <div className="flex items-center justify-center h-full">
            <p className="text-sm text-muted-foreground">No messages</p>
          </div>
        )}
      </CardContent>
    </Card>
  );
}

export default function ConversationsPage() {
  const [ngoId, setNgoId] = useState<string>("");
  const [agentType, setAgentType] = useState<string>("");
  const [dateFrom, setDateFrom] = useState("");
  const [dateTo, setDateTo] = useState("");
  const [selectedSession, setSelectedSession] =
    useState<ConversationSession | null>(null);
  const [page, setPage] = useState(1);

  const { data: ngos } = useSWR<PaginatedResponse<NGO>>(
    swrKeys.ngos(),
    () => ngoApi.list({ page_size: 100 })
  );

  const filterParams = {
    ngo_id: ngoId || undefined,
    agent_type: (agentType as AgentType) || undefined,
    date_from: dateFrom || undefined,
    date_to: dateTo || undefined,
    page,
    page_size: 20,
  };

  const { data, isLoading } = useSWR<PaginatedResponse<ConversationSession>>(
    swrKeys.conversations({
      ngo_id: ngoId,
      agent_type: agentType,
      date_from: dateFrom,
      date_to: dateTo,
    }),
    () => conversationApi.listSessions(filterParams),
    { keepPreviousData: true }
  );

  if (selectedSession) {
    return (
      <div className="space-y-4">
        <div>
          <h1 className="text-2xl font-bold text-foreground">Conversations</h1>
        </div>
        <ThreadView
          sessionId={selectedSession.id}
          onBack={() => setSelectedSession(null)}
        />
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* Header */}
      <div>
        <h1 className="text-2xl font-bold text-foreground">Conversations</h1>
        <p className="text-muted-foreground mt-1">
          Browse and read conversation logs across all NGOs.
        </p>
      </div>

      {/* Filters */}
      <Card>
        <CardContent className="p-4">
          <div className="flex items-center gap-2 mb-3">
            <Filter className="h-4 w-4 text-muted-foreground" />
            <span className="text-sm font-medium">Filters</span>
          </div>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
            <div className="space-y-1.5">
              <Label className="text-xs">NGO</Label>
              <Select
                value={ngoId}
                onValueChange={(v) => {
                  setNgoId(v === "all" ? "" : v);
                  setPage(1);
                }}
              >
                <SelectTrigger>
                  <SelectValue placeholder="All NGOs" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="all">All NGOs</SelectItem>
                  {ngos?.items.map((ngo) => (
                    <SelectItem key={ngo.id} value={ngo.id}>
                      {ngo.name}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-1.5">
              <Label className="text-xs">Agent</Label>
              <Select
                value={agentType}
                onValueChange={(v) => {
                  setAgentType(v === "all" ? "" : v);
                  setPage(1);
                }}
              >
                <SelectTrigger>
                  <SelectValue placeholder="All Agents" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="all">All Agents</SelectItem>
                  {ALL_AGENTS.map((a) => (
                    <SelectItem key={a} value={a}>
                      {AGENT_LABELS[a]}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-1.5">
              <Label className="text-xs">From</Label>
              <Input
                type="date"
                value={dateFrom}
                onChange={(e) => {
                  setDateFrom(e.target.value);
                  setPage(1);
                }}
              />
            </div>
            <div className="space-y-1.5">
              <Label className="text-xs">To</Label>
              <Input
                type="date"
                value={dateTo}
                onChange={(e) => {
                  setDateTo(e.target.value);
                  setPage(1);
                }}
              />
            </div>
          </div>
        </CardContent>
      </Card>

      {/* Sessions list */}
      <div className="space-y-3">
        {isLoading ? (
          Array.from({ length: 6 }).map((_, i) => (
            <Skeleton key={i} className="h-20 w-full rounded-xl" />
          ))
        ) : data?.items.length ? (
          data.items.map((session) => (
            <Card
              key={session.id}
              className="cursor-pointer hover:border-primary/50 transition-colors"
              onClick={() => setSelectedSession(session)}
            >
              <CardContent className="p-4">
                <div className="flex items-center justify-between gap-4">
                  <div className="flex items-start gap-3 min-w-0">
                    <div className="h-9 w-9 rounded-lg bg-primary/10 flex items-center justify-center flex-shrink-0">
                      <MessageSquare className="h-4 w-4 text-primary" />
                    </div>
                    <div className="min-w-0">
                      <div className="flex items-center gap-2 flex-wrap">
                        <p className="text-sm font-medium">
                          {session.staff_name}
                        </p>
                        <Badge variant="outline" className="text-xs">
                          {AGENT_LABELS[session.agent_type]}
                        </Badge>
                      </div>
                      <div className="flex items-center gap-3 mt-0.5">
                        <p className="text-xs text-muted-foreground">
                          {session.message_count} messages
                        </p>
                        <p className="text-xs text-muted-foreground">
                          Started {formatRelativeTime(session.started_at)}
                        </p>
                      </div>
                    </div>
                  </div>
                  <ChevronRight className="h-4 w-4 text-muted-foreground flex-shrink-0" />
                </div>
              </CardContent>
            </Card>
          ))
        ) : (
          <div className="text-center py-16">
            <MessageSquare className="h-10 w-10 text-muted-foreground/30 mx-auto mb-3" />
            <p className="text-sm text-muted-foreground">
              No conversations found
            </p>
            <p className="text-xs text-muted-foreground mt-1">
              Try adjusting your filters
            </p>
          </div>
        )}
      </div>

      {/* Pagination */}
      {data && data.pages > 1 && (
        <div className="flex items-center justify-center gap-2">
          <Button
            variant="outline"
            size="sm"
            disabled={page === 1}
            onClick={() => setPage((p) => p - 1)}
          >
            Previous
          </Button>
          <span className="text-sm text-muted-foreground">
            Page {page} of {data.pages}
          </span>
          <Button
            variant="outline"
            size="sm"
            disabled={page === data.pages}
            onClick={() => setPage((p) => p + 1)}
          >
            Next
          </Button>
        </div>
      )}
    </div>
  );
}
