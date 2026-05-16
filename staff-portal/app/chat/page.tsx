"use client";

import { useState, useRef, useEffect, useCallback } from "react";
import { useSession } from "next-auth/react";
import { Send, Loader2, RotateCcw } from "lucide-react";
import { AppShell } from "@/app/components/layout/AppShell";
import { staffApi } from "@/app/lib/api";
import { cn, relativeTime } from "@/app/lib/utils";
import { type AgentType, AGENT_ICONS, AGENT_LABELS } from "@/app/lib/types";

interface Message {
  id: string;
  role: "user" | "assistant";
  content: string;
  ts: string;
}

export default function ChatPage() {
  const { data: session } = useSession();
  const allowedAgents = (session?.staffProfile?.allowed_agents ?? []) as AgentType[];
  const firstAgent = allowedAgents[0] ?? null;

  const [activeAgent, setActiveAgent] = useState<AgentType | null>(firstAgent);
  // Per-agent message history and thread IDs so switching agents preserves each conversation.
  const [messagesByAgent, setMessagesByAgent] = useState<Partial<Record<AgentType, Message[]>>>({});
  const [threadIdByAgent, setThreadIdByAgent] = useState<Partial<Record<AgentType, string>>>({});
  const [input, setInput] = useState("");
  const [sending, setSending] = useState(false);
  const bottomRef = useRef<HTMLDivElement>(null);

  // Derive the current agent's slice of state.
  const messages: Message[] = activeAgent ? (messagesByAgent[activeAgent] ?? []) : [];
  const threadId: string | undefined = activeAgent ? threadIdByAgent[activeAgent] : undefined;

  const setMessages = useCallback(
    (updater: Message[] | ((prev: Message[]) => Message[])) => {
      if (!activeAgent) return;
      setMessagesByAgent((prev) => ({
        ...prev,
        [activeAgent]: typeof updater === "function"
          ? updater(prev[activeAgent] ?? [])
          : updater,
      }));
    },
    [activeAgent]
  );

  const setThreadId = useCallback(
    (id: string | undefined) => {
      if (!activeAgent) return;
      setThreadIdByAgent((prev) => ({ ...prev, [activeAgent]: id }));
    },
    [activeAgent]
  );

  useEffect(() => {
    if (firstAgent && !activeAgent) setActiveAgent(firstAgent);
  }, [firstAgent, activeAgent]);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  const handleAgentSelect = useCallback((agent: AgentType) => {
    setActiveAgent(agent);
  }, []);

  const send = async () => {
    if (!input.trim() || !activeAgent || !session?.backendToken || sending) return;
    const token = session.backendToken;
    const text = input.trim();
    setInput("");
    setSending(true);

    const userMsg: Message = {
      id: crypto.randomUUID(),
      role: "user",
      content: text,
      ts: new Date().toISOString(),
    };
    setMessages((m) => [...m, userMsg]);

    try {
      const res = await staffApi.chat(token, activeAgent, text, threadId);
      setThreadId(res.thread_id);
      setMessages((m) => [
        ...m,
        {
          id: crypto.randomUUID(),
          role: "assistant",
          content: res.reply,
          ts: new Date().toISOString(),
        },
      ]);
    } catch (err) {
      setMessages((m) => [
        ...m,
        {
          id: crypto.randomUUID(),
          role: "assistant",
          content: `Sorry, something went wrong. ${err instanceof Error ? err.message : ""}`,
          ts: new Date().toISOString(),
        },
      ]);
    } finally {
      setSending(false);
    }
  };

  return (
    <AppShell
      activeAgent={activeAgent}
      onAgentSelect={handleAgentSelect}
      showAgentSidebar
    >
      <div className="flex flex-col h-full">
        {/* Header */}
        <div className="flex items-center justify-between px-6 py-4 border-b border-slate-200 bg-white">
          {activeAgent ? (
            <div className="flex items-center gap-2">
              <span className="text-xl">{AGENT_ICONS[activeAgent]}</span>
              <div>
                <p className="font-semibold text-slate-900">
                  {AGENT_LABELS[activeAgent]} Agent
                </p>
                <p className="text-xs text-slate-400">Ask me anything</p>
              </div>
            </div>
          ) : (
            <p className="text-slate-400">Select an agent to start</p>
          )}
          <button
            onClick={() => { setMessages([]); setThreadId(undefined); setInput(""); }}
            title="New conversation"
            className="h-8 w-8 flex items-center justify-center rounded-lg text-slate-400 hover:bg-slate-100 transition-colors"
          >
            <RotateCcw className="h-4 w-4" />
          </button>
        </div>

        {/* Messages */}
        <div className="flex-1 overflow-y-auto px-6 py-4 space-y-4">
          {messages.length === 0 && activeAgent && (
            <div className="flex flex-col items-center justify-center h-full text-center gap-3 pb-20">
              <span className="text-5xl">{AGENT_ICONS[activeAgent]}</span>
              <div>
                <p className="font-medium text-slate-700">
                  {AGENT_LABELS[activeAgent]} Agent
                </p>
                <p className="text-sm text-slate-400 mt-1">
                  How can I help you today?
                </p>
              </div>
            </div>
          )}

          {messages.map((msg) => (
            <div
              key={msg.id}
              className={cn(
                "flex gap-3",
                msg.role === "user" ? "justify-end" : "justify-start"
              )}
            >
              {msg.role === "assistant" && activeAgent && (
                <div className="h-8 w-8 rounded-full bg-indigo-100 flex items-center justify-center text-base shrink-0 mt-0.5">
                  {AGENT_ICONS[activeAgent]}
                </div>
              )}
              <div
                className={cn(
                  "max-w-[70%] rounded-2xl px-4 py-3 text-sm",
                  msg.role === "user"
                    ? "bg-indigo-600 text-white rounded-tr-sm"
                    : "bg-white border border-slate-200 text-slate-800 rounded-tl-sm"
                )}
              >
                <p className="whitespace-pre-wrap leading-relaxed">{msg.content}</p>
                <p
                  className={cn(
                    "text-xs mt-1.5",
                    msg.role === "user" ? "text-indigo-200" : "text-slate-400"
                  )}
                >
                  {relativeTime(msg.ts)}
                </p>
              </div>
            </div>
          ))}

          {sending && (
            <div className="flex gap-3 justify-start">
              <div className="h-8 w-8 rounded-full bg-indigo-100 flex items-center justify-center text-base shrink-0">
                {activeAgent && AGENT_ICONS[activeAgent]}
              </div>
              <div className="bg-white border border-slate-200 rounded-2xl rounded-tl-sm px-4 py-3">
                <div className="flex gap-1 items-center h-5">
                  {[0, 1, 2].map((i) => (
                    <span
                      key={i}
                      className="h-2 w-2 rounded-full bg-slate-300 animate-bounce"
                      style={{ animationDelay: `${i * 0.15}s` }}
                    />
                  ))}
                </div>
              </div>
            </div>
          )}

          <div ref={bottomRef} />
        </div>

        {/* Input */}
        <div className="px-6 py-4 border-t border-slate-200 bg-white">
          <div className="flex gap-2 items-end">
            <textarea
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter" && !e.shiftKey) {
                  e.preventDefault();
                  send();
                }
              }}
              placeholder={
                activeAgent
                  ? `Message ${AGENT_LABELS[activeAgent]} agent…`
                  : "Select an agent first"
              }
              disabled={!activeAgent || sending}
              rows={1}
              className="flex-1 resize-none rounded-xl border border-slate-200 px-4 py-2.5 text-sm text-slate-900 placeholder:text-slate-400 focus:outline-none focus:ring-2 focus:ring-indigo-500 disabled:opacity-50"
              style={{ maxHeight: 120 }}
            />
            <button
              onClick={send}
              disabled={!activeAgent || !input.trim() || sending}
              className="h-10 w-10 rounded-xl bg-indigo-600 flex items-center justify-center text-white disabled:opacity-40 hover:bg-indigo-700 transition-colors shrink-0"
            >
              {sending ? (
                <Loader2 className="h-4 w-4 animate-spin" />
              ) : (
                <Send className="h-4 w-4" />
              )}
            </button>
          </div>
          <p className="text-xs text-slate-400 mt-2 text-center">
            Shift+Enter for new line · Enter to send
          </p>
        </div>
      </div>
    </AppShell>
  );
}
