"use client";

import { useState, useRef, useEffect } from "react";
import {
  api,
  APIError,
  ToolCall,
  ConversationItem,
  ChatMessage,
} from "@/lib/api";
import { StateRing } from "@/components/StateRing";

export default function AssistantPage() {
  const [conversations, setConversations] = useState<ConversationItem[]>([]);
  const [activeConversationId, setActiveConversationId] = useState<string | null>(null);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [input, setInput] = useState("");
  const [state, setState] = useState<"idle" | "thinking" | "executing">("idle");
  const [pendingConfirm, setPendingConfirm] = useState<ToolCall | null>(null);
  const [error, setError] = useState<string | null>(null);
  const bottomRef = useRef<HTMLDivElement>(null);

  // Load conversation list
  const loadConversations = async () => {
    try {
      const list = await api.listConversations();
      setConversations(list);
      if (list.length > 0 && !activeConversationId) {
        setActiveConversationId(list[0].id);
      }
    } catch {
      // Ignore if no conversations
    }
  };

  useEffect(() => {
    loadConversations();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Load messages when active conversation changes
  useEffect(() => {
    if (!activeConversationId) {
      setMessages([]);
      return;
    }
    const loadMessages = async () => {
      try {
        const msgs = await api.getConversationMessages(activeConversationId);
        setMessages(msgs);
      } catch (err) {
        setError(err instanceof APIError ? err.message : "Failed to load conversation history.");
      }
    };
    loadMessages();
  }, [activeConversationId]);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  const handleCreateNewChat = async () => {
    try {
      const conv = await api.createConversation("New Conversation");
      setConversations((prev) => [conv, ...prev]);
      setActiveConversationId(conv.id);
      setMessages([]);
    } catch (err) {
      setError(err instanceof APIError ? err.message : "Failed to create conversation.");
    }
  };

  const handleDeleteChat = async (id: string, e: React.MouseEvent) => {
    e.stopPropagation();
    try {
      await api.deleteConversation(id);
      const remaining = conversations.filter((c) => c.id !== id);
      setConversations(remaining);
      if (activeConversationId === id) {
        setActiveConversationId(remaining.length > 0 ? remaining[0].id : null);
      }
    } catch (err) {
      setError(err instanceof APIError ? err.message : "Failed to delete conversation.");
    }
  };

  async function send(e: React.FormEvent) {
    e.preventDefault();
    const text = input.trim();
    if (!text) return;

    setError(null);
    setInput("");
    setState("thinking");

    let convId = activeConversationId;
    if (!convId) {
      try {
        const newConv = await api.createConversation(text.slice(0, 30));
        convId = newConv.id;
        setConversations((prev) => [newConv, ...prev]);
        setActiveConversationId(convId);
      } catch {
        // Continue even if conversation save fails
      }
    }

    // Append optimistic user message
    const tempUserMsg: ChatMessage = {
      id: `temp-${Date.now()}`,
      conversation_id: convId || "default",
      role: "user",
      content: text,
      created_at: new Date().toISOString(),
    };
    setMessages((prev) => [...prev, tempUserMsg]);

    try {
      const reply = await api.chat(text, convId || undefined);

      const assistantMsg: ChatMessage = {
        id: `resp-${Date.now()}`,
        conversation_id: convId || "default",
        role: "assistant",
        content: reply.reply,
        tool_calls: reply.tool_calls,
        created_at: new Date().toISOString(),
      };
      setMessages((prev) => [...prev, assistantMsg]);

      // If title is "New Conversation", update it
      const currentConv = conversations.find((c) => c.id === convId);
      if (currentConv && currentConv.title === "New Conversation") {
        const summary = text.slice(0, 25);
        api.updateConversation(convId!, summary).then(() => loadConversations());
      }

      const needsConfirm = reply.tool_calls.find((tc) => tc.result === "REQUIRES_CONFIRMATION");
      if (needsConfirm) {
        setPendingConfirm(needsConfirm);
      }
    } catch (err) {
      const msg = err instanceof APIError ? err.message : "Something went wrong.";
      const errMsg: ChatMessage = {
        id: `err-${Date.now()}`,
        conversation_id: convId || "default",
        role: "assistant",
        content: `⚠️ ${msg}`,
        created_at: new Date().toISOString(),
      };
      setMessages((prev) => [...prev, errMsg]);
    } finally {
      setState("idle");
    }
  }

  async function confirm(approved: boolean) {
    if (!pendingConfirm?.pending_id) {
      setPendingConfirm(null);
      return;
    }
    if (!approved) {
      setMessages((prev) => [
        ...prev,
        {
          id: `declined-${Date.now()}`,
          conversation_id: activeConversationId || "default",
          role: "assistant",
          content: "Action cancelled.",
          created_at: new Date().toISOString(),
        },
      ]);
      setPendingConfirm(null);
      return;
    }

    setState("executing");
    try {
      const result = await api.confirmPending(pendingConfirm.pending_id);
      setMessages((prev) => [
        ...prev,
        {
          id: `confirmed-${Date.now()}`,
          conversation_id: activeConversationId || "default",
          role: "assistant",
          content: result.message || `${result.tool_name}: ${result.result}`,
          created_at: new Date().toISOString(),
        },
      ]);
    } catch (err) {
      const msg = err instanceof APIError ? err.message : "Confirmation failed.";
      setMessages((prev) => [
        ...prev,
        {
          id: `err-confirm-${Date.now()}`,
          conversation_id: activeConversationId || "default",
          role: "assistant",
          content: `⚠️ ${msg}`,
          created_at: new Date().toISOString(),
        },
      ]);
    } finally {
      setState("idle");
      setPendingConfirm(null);
    }
  }

  return (
    <div className="h-[calc(100vh-6rem)] flex gap-4">
      {/* Sidebar: Thread List */}
      <div className="w-64 card p-3 flex flex-col shrink-0">
        <button
          onClick={handleCreateNewChat}
          className="btn-primary w-full text-xs font-semibold py-2 mb-3 flex items-center justify-center gap-2"
        >
          <span>＋</span> New Conversation
        </button>

        <div className="flex-1 overflow-y-auto space-y-1">
          {conversations.map((c) => (
            <div
              key={c.id}
              onClick={() => setActiveConversationId(c.id)}
              className={`p-2 rounded text-xs cursor-pointer flex items-center justify-between group transition-colors ${
                activeConversationId === c.id
                  ? "bg-accent/15 text-accent font-medium"
                  : "text-muted hover:text-ink hover:bg-panel"
              }`}
            >
              <span className="truncate flex-1">{c.title || "Untitled Chat"}</span>
              <button
                onClick={(e) => handleDeleteChat(c.id, e)}
                className="opacity-0 group-hover:opacity-100 hover:text-danger p-1 text-xs"
                title="Delete Chat"
              >
                ✕
              </button>
            </div>
          ))}
          {conversations.length === 0 && (
            <p className="text-[11px] text-muted text-center pt-4">No active conversations</p>
          )}
        </div>
      </div>

      {/* Main Chat Interface */}
      <div className="flex-1 flex flex-col card p-4 min-w-0">
        <div className="flex items-center justify-between border-b border-border pb-3 mb-3">
          <div>
            <h1 className="text-lg font-bold font-display">Nova AI Assistant</h1>
            <p className="text-xs text-muted">Multi-turn conversation & autonomous OS control</p>
          </div>
          <StateRing state={state} />
        </div>

        {error && (
          <div className="p-2.5 rounded bg-danger/10 border border-danger/30 text-danger text-xs mb-3">
            {error}
          </div>
        )}

        <div className="flex-1 overflow-y-auto space-y-4 pr-2">
          {messages.length === 0 && (
            <div className="h-full flex flex-col items-center justify-center text-center p-6 text-muted space-y-3">
              <div className="w-12 h-12 rounded-full bg-accent/10 border border-accent/20 flex items-center justify-center text-accent text-xl font-bold">
                ⚡
              </div>
              <div>
                <p className="font-semibold text-ink text-sm">How can Nova assist you today?</p>
                <p className="text-xs max-w-sm mt-1">
                  Try asking to launch WordPad, take a screenshot, audit a suspicious IP address, analyze a phishing URL, or schedule a reminder.
                </p>
              </div>
            </div>
          )}

          {messages.map((m) => (
            <div key={m.id} className={`flex flex-col ${m.role === "user" ? "items-end" : "items-start"}`}>
              <div
                className={`max-w-[85%] rounded-lg px-4 py-2.5 text-sm ${
                  m.role === "user"
                    ? "bg-accent text-white"
                    : "bg-panel border border-border text-ink"
                }`}
              >
                <p className="whitespace-pre-wrap leading-relaxed">{m.content}</p>

                {m.tool_calls && m.tool_calls.length > 0 && (
                  <div className="mt-2.5 pt-2 border-t border-border/50 space-y-1.5 font-mono text-xs">
                    {m.tool_calls.map((tc, idx) => (
                      <div
                        key={idx}
                        className="bg-black/30 p-2 rounded flex items-center justify-between gap-2 border border-white/5"
                      >
                        <div className="flex items-center gap-1.5 truncate">
                          <span className="text-accent">⚙</span>
                          <span className="font-semibold text-ink">{tc.tool_name}</span>
                          {tc.arguments && (
                            <span className="text-muted truncate">
                              ({JSON.stringify(tc.arguments)})
                            </span>
                          )}
                        </div>
                        <span
                          className={`text-[10px] px-1.5 py-0.5 rounded font-bold uppercase shrink-0 ${
                            tc.result === "SUCCESS"
                              ? "bg-active/20 text-active"
                              : tc.result === "REQUIRES_CONFIRMATION"
                              ? "bg-warning/20 text-warning"
                              : "bg-danger/20 text-danger"
                          }`}
                        >
                          {tc.result}
                        </span>
                      </div>
                    ))}
                  </div>
                )}
              </div>
              <span className="text-[10px] text-muted mt-1 px-1 font-mono">
                {m.created_at ? new Date(m.created_at).toLocaleTimeString() : ""}
              </span>
            </div>
          ))}
          <div ref={bottomRef} />
        </div>

        {/* Sensitive Action Human Confirmation Modal */}
        {pendingConfirm && (
          <div className="mt-3 p-3 rounded bg-warning/10 border border-warning/30 space-y-2">
            <div className="flex items-center gap-2 text-warning text-xs font-bold uppercase">
              <span>⚠️</span> Confirmation Required
            </div>
            <p className="text-xs text-ink">
              {pendingConfirm.message || `Nova is requesting permission to execute: ${pendingConfirm.tool_name}`}
            </p>
            <div className="flex gap-2">
              <button onClick={() => confirm(true)} className="btn-primary text-xs px-3 py-1">
                Approve & Execute
              </button>
              <button onClick={() => confirm(false)} className="btn-secondary text-xs px-3 py-1">
                Deny Action
              </button>
            </div>
          </div>
        )}

        {/* Input Bar */}
        <form onSubmit={send} className="mt-3 flex gap-2">
          <input
            value={input}
            onChange={(e) => setInput(e.target.value)}
            className="input flex-1 text-sm"
            placeholder="Type a request, system instruction, or query…"
            disabled={state !== "idle" || !!pendingConfirm}
          />
          <button
            type="submit"
            disabled={state !== "idle" || !!pendingConfirm || !input.trim()}
            className="btn-primary px-5 text-sm"
          >
            {state === "thinking" ? "Thinking…" : state === "executing" ? "Running…" : "Send"}
          </button>
        </form>
      </div>
    </div>
  );
}
