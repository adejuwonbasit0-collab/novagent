"use client";

import { useState, useRef, useEffect } from "react";
import { api, APIError, ToolCall } from "@/lib/api";
import { StateRing } from "@/components/StateRing";

interface Message {
  role: "user" | "assistant";
  text: string;
  toolCalls?: ToolCall[];
}

export default function AssistantPage() {
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState("");
  const [state, setState] = useState<"idle" | "thinking" | "executing">("idle");
  const [pendingConfirm, setPendingConfirm] = useState<ToolCall | null>(null);
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  async function send(e: React.FormEvent) {
    e.preventDefault();
    const text = input.trim();
    if (!text) return;

    setMessages((prev) => [...prev, { role: "user", text }]);
    setInput("");
    setState("thinking");

    try {
      const reply = await api.chat(text);
      setMessages((prev) => [...prev, { role: "assistant", text: reply.reply, toolCalls: reply.tool_calls }]);

      const needsConfirm = reply.tool_calls.find((tc) => tc.result === "REQUIRES_CONFIRMATION");
      if (needsConfirm) {
        setPendingConfirm(needsConfirm);
      }
    } catch (err) {
      const msg = err instanceof APIError ? err.message : "Something went wrong.";
      setMessages((prev) => [...prev, { role: "assistant", text: `⚠️ ${msg}` }]);
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
      setMessages((prev) => [...prev, { role: "assistant", text: "Okay, I won't do that." }]);
      setPendingConfirm(null);
      return;
    }

    setState("executing");
    try {
      const result = await api.confirmPending(pendingConfirm.pending_id);
      setMessages((prev) => [
        ...prev,
        { role: "assistant", text: result.message || `${result.tool_name}: ${result.result}` },
      ]);
    } catch (err) {
      const msg = err instanceof APIError ? err.message : "Confirmation failed.";
      setMessages((prev) => [...prev, { role: "assistant", text: `⚠️ ${msg}` }]);
    } finally {
      setState("idle");
      setPendingConfirm(null);
    }
  }

  return (
    <div className="max-w-2xl flex flex-col h-[calc(100vh-4rem)]">
      <div className="flex items-center justify-between mb-4">
        <h1 className="text-2xl font-bold">Assistant</h1>
        <StateRing state={state} />
      </div>

      <div className="flex-1 overflow-y-auto card mb-4 space-y-4">
        {messages.length === 0 && (
          <p className="text-muted text-sm">
            Ask Nova to set a reminder, check your schedule, or control a connected device.
          </p>
        )}

        {messages.map((m, i) => (
          <div key={i} className={m.role === "user" ? "text-right" : "text-left"}>
            <span
              className={`inline-block px-3 py-2 rounded max-w-[85%] text-sm ${
                m.role === "user" ? "bg-accent text-base" : "bg-base border border-border"
              }`}
            >
              {m.text}
            </span>
          </div>
        ))}
        <div ref={bottomRef} />
      </div>

      {pendingConfirm && (
        <div className="card border-pending mb-4">
          <p className="text-sm mb-3">
            <span className="text-pending font-medium">Confirmation needed:</span>{" "}
            {pendingConfirm.message || `Run ${pendingConfirm.tool_name}?`}
          </p>
          <div className="flex gap-2">
            <button onClick={() => confirm(true)} className="btn-primary text-sm">
              Confirm
            </button>
            <button onClick={() => confirm(false)} className="btn-secondary text-sm">
              Cancel
            </button>
          </div>
        </div>
      )}

      <form onSubmit={send} className="flex gap-2">
        <input
          value={input}
          onChange={(e) => setInput(e.target.value)}
          className="input-field flex-1"
          placeholder="Ask Nova anything…"
          disabled={state !== "idle" || !!pendingConfirm}
        />
        <button type="submit" disabled={state !== "idle" || !!pendingConfirm} className="btn-primary">
          Send
        </button>
      </form>
    </div>
  );
}
