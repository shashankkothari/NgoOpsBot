"use client";

import { useState } from "react";
import useSWR from "swr";
import { MessageSquare, Bot, User, Filter, ChevronRight, ArrowLeft } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Label } from "@/components/ui/label";
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
  type ConversationThread,
  type ConversationMessage,
  type PaginatedResponse,
  type NGO,
  type AgentType,
} from "@/lib/api";
import { formatDateTime, formatRelativeTime, AGENT_LABELS } from "@/lib/utils";

const ALL_AGENTS: AgentType[] = ["fundraising", "finance", "marketing", "hr", "compliance"];

function MessageBubble({ message }: { message: ConversationMessage }) {
  const isUser = message.role === "user";
  return (
    <div className={`flex gap-3 ${isUser ? "flex-row" : "flex-row-reverse"}`}>
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
        <p className={`text-xs mt-1.5 ${isUser ? "text-muted-foreground" : "text-primary-foreground/70"}`}>
          {formatDateTime(message.created_at)}
        </p>
      </div>
    </div>
  );
}

function ThreadView({ threadId, onBack }: { threadId: string; onBack: () => void }) {
  const { data, isLoading } = useSWR(
    swrKeys.thread(threadId),
    () => conversationApi.getThread(threadId)
  );

  return (
    <Card className="flex flex-col h-[600px]">
      <CardHeader className="pb-3 border-b border-border flex-shrink-0">
        <div className="flex items-center gap-2">
          <Button variant="ghost" size="icon" className="h-8 w-8" onClick={onBack}>
            <ArrowLeft className="h-4 w-4" />
          </Button>
          <CardTitle className="text-base">Conversation Thread</CardTitle>
          {data && (
            <Badge variant="outline" className="ml-auto">
              {AGENT_LABELS[data.agent_name]}
            </Badge>
          )}
        </div>
      </CardHeader>
      <CardContent className="flex-1 overflow-y-auto p-4 space-y-4">
        {isLoading ? (
          Array.from({ length: 4 }).map((_, i) => (
            <div key={i} className={`flex gap-3 ${i % 2 === 0 ? "" : "flex-row-reverse"}`}>
              <Skeleton className="h-8 w-8 rounded-full flex-shrink-0" />
              <Skeleton className={`h-16 w-64 rounded-xl ${i % 2 === 0 ? "rounded-tl-none" : "rounded-tr-none"}`} />
            </div>
          ))
        ) : data?.messages?.length ? (
          data.messages.map((msg) => <MessageBubble key={msg.id} message={msg} />)
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
  const [ngoId, setNgoId] = useState("");
  const [agentName, setAgentName] = useState("");
  const [selectedThread, setSelectedThread] = useState<ConversationThread | null>(null);
  const [page, setPage] = useState(1);

  const { data: ngos } = useSWR<PaginatedResponse<NGO>>(
    swrKeys.ngos(),
    () => ngoApi.list({ page_size: 100 })
  );

  const { data, isLoading } = useSWR<PaginatedResponse<ConversationThread>>(
    swrKeys.conversations({ ngo_id: ngoId, agent_name: agentName }),
    () => conversationApi.listThreads({
      ngo_id: ngoId || undefined,
      agent_name: (agentName as AgentType) || undefined,
      page,
      page_size: 20,
    }),
    { keepPreviousData: true }
  );

  if (selectedThread) {
    return (
      <div className="space-y-4">
        <h1 className="text-2xl font-bold text-foreground">Conversations</h1>
        <ThreadView threadId={selectedThread.id} onBack={() => setSelectedThread(null)} />
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-foreground">Conversations</h1>
        <p className="text-muted-foreground mt-1">Browse conversation threads across all NGOs.</p>
      </div>

      {/* Filters */}
      <Card>
        <CardContent className="p-4">
          <div className="flex items-center gap-2 mb-3">
            <Filter className="h-4 w-4 text-muted-foreground" />
            <span className="text-sm font-medium">Filters</span>
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div className="space-y-1.5">
              <Label className="text-xs">NGO</Label>
              <Select value={ngoId} onValueChange={(v) => { setNgoId(v === "all" ? "" : v); setPage(1); }}>
                <SelectTrigger><SelectValue placeholder="All NGOs" /></SelectTrigger>
                <SelectContent>
                  <SelectItem value="all">All NGOs</SelectItem>
                  {ngos?.items.map((ngo) => (
                    <SelectItem key={ngo.id} value={ngo.id}>{ngo.name}</SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-1.5">
              <Label className="text-xs">Agent</Label>
              <Select value={agentName} onValueChange={(v) => { setAgentName(v === "all" ? "" : v); setPage(1); }}>
                <SelectTrigger><SelectValue placeholder="All Agents" /></SelectTrigger>
                <SelectContent>
                  <SelectItem value="all">All Agents</SelectItem>
                  {ALL_AGENTS.map((a) => (
                    <SelectItem key={a} value={a}>{AGENT_LABELS[a]}</SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
          </div>
        </CardContent>
      </Card>

      {/* Thread list */}
      <div className="space-y-3">
        {isLoading ? (
          Array.from({ length: 6 }).map((_, i) => (
            <Skeleton key={i} className="h-20 w-full rounded-xl" />
          ))
        ) : data?.items.length ? (
          data.items.map((thread) => (
            <Card
              key={thread.id}
              className="cursor-pointer hover:border-primary/50 transition-colors"
              onClick={() => setSelectedThread(thread)}
            >
              <CardContent className="p-4">
                <div className="flex items-center justify-between gap-4">
                  <div className="flex items-start gap-3 min-w-0">
                    <div className="h-9 w-9 rounded-lg bg-primary/10 flex items-center justify-center flex-shrink-0">
                      <MessageSquare className="h-4 w-4 text-primary" />
                    </div>
                    <div className="min-w-0">
                      <div className="flex items-center gap-2 flex-wrap">
                        <Badge variant="outline" className="text-xs">
                          {AGENT_LABELS[thread.agent_name]}
                        </Badge>
                        <Badge variant={thread.is_active ? "success" : "secondary"} className="text-xs">
                          {thread.is_active ? "Active" : "Closed"}
                        </Badge>
                      </div>
                      <div className="flex items-center gap-3 mt-0.5">
                        <p className="text-xs text-muted-foreground">
                          {thread.message_count} messages
                        </p>
                        <p className="text-xs text-muted-foreground">
                          {formatRelativeTime(thread.last_activity_at)}
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
            <p className="text-sm text-muted-foreground">No conversations found</p>
          </div>
        )}
      </div>

      {data && data.total > 20 && (
        <div className="flex items-center justify-center gap-2">
          <Button variant="outline" size="sm" disabled={page === 1} onClick={() => setPage((p) => p - 1)}>
            Previous
          </Button>
          <span className="text-sm text-muted-foreground">Page {page}</span>
          <Button variant="outline" size="sm" disabled={data.items.length < 20} onClick={() => setPage((p) => p + 1)}>
            Next
          </Button>
        </div>
      )}
    </div>
  );
}
