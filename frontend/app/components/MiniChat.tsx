import { useCallback, useEffect, useRef, useState } from "react";
import { Link } from "react-router";
import {
  Bot,
  ExternalLink,
  Minus,
  RefreshCw,
  Send,
  Sparkles,
  Terminal,
  X,
} from "lucide-react";

import {
  LiveBubble,
  MessageBubble,
  PromptSuggestions,
  type LiveBlock,
} from "~/components/ChatBlocks";
import {
  createConversation,
  fetchMessages,
  streamChatMessage,
  type ChatMessage,
  type ChatStreamEvent,
} from "~/lib/api";
import { Spinner } from "~/lib/ui";

export function MiniChat() {
  const [open, setOpen] = useState(false);
  const [conversationId, setConversationId] = useState<number | null>(null);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [live, setLive] = useState<LiveBlock[]>([]);
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const scrollerRef = useRef<HTMLDivElement>(null);
  const stickToBottomRef = useRef(true);
  const abortRef = useRef<AbortController | null>(null);

  const ensureConversation = useCallback(async () => {
    if (conversationId) return conversationId;
    const { conversation } = await createConversation("Mini chat");
    setConversationId(conversation.id);
    return conversation.id;
  }, [conversationId]);

  useEffect(() => {
    if (!open || !conversationId) return;
    fetchMessages(conversationId)
      .then((r) => setMessages(r.messages))
      .catch(() => {});
  }, [open, conversationId]);

  useEffect(() => {
    stickToBottomRef.current = true;
  }, [open, conversationId]);

  useEffect(() => {
    const el = scrollerRef.current;
    if (!el || !open || !stickToBottomRef.current) return;
    el.scrollTop = el.scrollHeight;
  }, [messages, live, open]);

  async function handleSend(textToSend?: string) {
    const text = (textToSend || input).trim();
    if (!text || busy) return;
    setError(null);
    setBusy(true);
    setInput("");
    stickToBottomRef.current = true;
    try {
      const cid = await ensureConversation();
      setMessages((prev) => [
        ...prev,
        {
          id: Date.now(),
          conversation_id: cid,
          role: "user",
          type: "text",
          content: text,
        },
      ]);
      setLive([]);
      abortRef.current?.abort();
      const ac = new AbortController();
      abortRef.current = ac;
      let assistant = "";
      let thinking = "";
      await streamChatMessage(
        cid,
        text,
        (ev: ChatStreamEvent) => {
          if (ev.type === "token") {
            assistant += ev.content ?? "";
            setLive((prev) => [
              ...prev.filter((b) => b.kind !== "text"),
              { kind: "text", content: assistant },
            ]);
          } else if (ev.type === "thinking") {
            thinking += ev.content ?? "";
            setLive((prev) => [
              { kind: "thinking", content: thinking },
              ...prev.filter((b) => b.kind !== "thinking"),
            ]);
          } else if (ev.type === "tool_call") {
            setLive((prev) => [
              ...prev.filter((b) => b.kind !== "text"),
              ...(assistant ? [{ kind: "text" as const, content: assistant }] : []),
              {
                kind: "tool_call",
                name: ev.name ?? "tool",
                arguments: ev.arguments,
              },
            ]);
            assistant = "";
          } else if (ev.type === "tool_result") {
            setLive((prev) => [
              ...prev,
              { kind: "tool_result", name: ev.name ?? "tool", result: ev.result },
            ]);
          } else if (ev.type === "error") {
            setError(ev.message ?? "Stream error");
          } else if (ev.type === "done") {
            setLive([]);
            fetchMessages(cid)
              .then((r) => setMessages(r.messages))
              .catch(() => {});
          }
        },
        ac.signal,
      );
    } catch (e) {
      setError(e instanceof Error ? e.message : "Send failed");
    } finally {
      setBusy(false);
    }
  }

  async function resetConvo() {
    if (busy) return;
    setMessages([]);
    setLive([]);
    const { conversation } = await createConversation("Mini chat");
    setConversationId(conversation.id);
  }

  return (
    <>
      {!open ? (
        <button
          type="button"
          onClick={() => setOpen(true)}
          className="fixed bottom-6 right-6 z-50 flex items-center gap-2.5 rounded-full border border-[var(--desk-border-accent)] bg-[#09090b] px-4 py-2.5 font-mono text-xs font-semibold text-[var(--desk-ink)] shadow-2xl shadow-black/80 transition-all hover:scale-105 hover:border-zinc-500 hover:bg-[#141418]"
        >
          <div className="relative flex h-5 w-5 items-center justify-center rounded-full bg-zinc-800 text-[var(--desk-accent)]">
            <Bot className="h-3.5 w-3.5" />
            <span className="absolute -bottom-0.5 -right-0.5 h-1.5 w-1.5 rounded-full bg-[var(--desk-success)]" />
          </div>
          {/* <span>AI Master</span>
          <span className="rounded bg-zinc-800 px-1.5 py-0.5 text-[9px] font-mono text-[var(--desk-ink-muted)]">
            READY
          </span> */}
        </button>
      ) : (
        <div className="fixed bottom-6 right-6 z-50 flex h-[580px] w-[460px] flex-col overflow-hidden rounded-xl border border-[var(--desk-border-accent)] bg-[#09090b]/95 shadow-2xl shadow-black/80 backdrop-blur-xl">
          {/* Header */}
          <div className="flex items-center justify-between border-b border-[var(--desk-border)] bg-[#0d0d11] px-4 py-3">
            <div className="flex items-center gap-2.5">
              <div className="relative flex h-6 w-6 items-center justify-center rounded-full border border-zinc-700 bg-zinc-800 text-[var(--desk-accent)]">
                <Bot className="h-3.5 w-3.5" />
                <span className="absolute -bottom-0.5 -right-0.5 h-2 w-2 rounded-full bg-[var(--desk-success)] ring-2 ring-[#0d0d11]" />
              </div>
              <div>
                <div className="flex items-center gap-1.5">
                  <span className="font-mono text-xs font-semibold text-[var(--desk-ink)]">
                    AI Master
                  </span>
                  <span className="font-mono text-[9px] text-[var(--desk-ink-faint)]">
                    v2.5
                  </span>
                </div>
                <p className="font-mono text-[10px] text-[var(--desk-ink-faint)]">
                  Autonomous Security Desk
                </p>
              </div>
            </div>

            <div className="flex items-center gap-1 text-[var(--desk-ink-muted)]">
              <button
                type="button"
                onClick={() => void resetConvo()}
                title="New conversation"
                className="rounded p-1.5 hover:bg-[var(--desk-surface-2)] hover:text-[var(--desk-ink)]"
              >
                <RefreshCw className="h-3.5 w-3.5" />
              </button>
              {conversationId ? (
                <Link
                  to={`/chat/${conversationId}`}
                  title="Expand to full screen"
                  className="rounded p-1.5 hover:bg-[var(--desk-surface-2)] hover:text-[var(--desk-ink)]"
                >
                  <ExternalLink className="h-3.5 w-3.5" />
                </Link>
              ) : null}
              <button
                type="button"
                onClick={() => setOpen(false)}
                title="Close"
                className="rounded p-1.5 hover:bg-[var(--desk-surface-2)] hover:text-[var(--desk-ink)]"
              >
                <X className="h-4 w-4" />
              </button>
            </div>
          </div>

          {/* Messages Area */}
          <div
            ref={scrollerRef}
            className="min-h-0 flex-1 space-y-3 overflow-y-auto p-4 text-sm"
            onScroll={(e) => {
              stickToBottomRef.current = isNearBottom(e.currentTarget);
            }}
          >
            {messages.length === 0 && live.length === 0 ? (
              <div className="flex h-full flex-col justify-center py-6 text-center">
                <div className="mx-auto mb-3 flex h-12 w-12 items-center justify-center rounded-2xl border border-[var(--desk-border)] bg-[var(--desk-surface-2)] text-[var(--desk-accent)]">
                  <Terminal className="h-6 w-6 text-zinc-300" />
                </div>
                <h3 className="font-display text-sm font-semibold text-[var(--desk-ink)]">
                  Security Intelligence Master
                </h3>
                <p className="mx-auto mt-1 max-w-[280px] text-xs text-[var(--desk-ink-muted)]">
                  I can discover target repos, compose vulnerability research plans, queue CLI workers, and triage findings.
                </p>
                <div className="mt-4 px-2">
                  <PromptSuggestions onSelect={(p) => void handleSend(p)} />
                </div>
              </div>
            ) : (
              <>
                {messages.map((m) => (
                  <MessageBubble key={m.id} message={m} />
                ))}
                {live.map((block, i) => (
                  <LiveBubble key={`live-${i}`} block={block} />
                ))}
              </>
            )}
          </div>

          {/* Error Banner */}
          {error ? (
            <div className="border-t border-red-500/20 bg-red-500/10 px-3 py-1.5 text-xs text-[var(--desk-danger)]">
              {error}
            </div>
          ) : null}

          {/* Prompt Suggestions Bar */}
          {messages.length > 0 && (
            <div className="border-t border-[var(--desk-border-subtle)] bg-[#0c0c0f] px-3 py-1">
              <PromptSuggestions onSelect={(p) => void handleSend(p)} />
            </div>
          )}

          {/* Input Bar */}
          <div className="border-t border-[var(--desk-border)] bg-[#09090c] p-2.5">
            <div className="flex items-end gap-2 rounded-lg border border-[var(--desk-border)] bg-[var(--desk-surface-2)] p-1.5 focus-within:border-zinc-500">
              <textarea
                className="max-h-28 min-h-[38px] flex-1 resize-none bg-transparent px-2 py-1 font-sans text-xs text-[var(--desk-ink)] focus:outline-none"
                value={input}
                onChange={(e) => setInput(e.target.value)}
                placeholder="Ask AI Master (e.g. 'scan expressjs', 'suggest 0-day prompt')…"
                disabled={busy}
                rows={1}
                onKeyDown={(e) => {
                  if (e.key === "Enter" && !e.shiftKey) {
                    e.preventDefault();
                    void handleSend();
                  }
                }}
              />
              <button
                type="button"
                className="desk-btn desk-btn-primary flex h-8 w-8 items-center justify-center rounded-md p-0"
                disabled={busy || !input.trim()}
                onClick={() => void handleSend()}
              >
                {busy ? <Spinner /> : <Send className="h-3.5 w-3.5" />}
              </button>
            </div>
            <div className="mt-1 flex items-center justify-between px-1 text-[10px] text-[var(--desk-ink-faint)]">
              <span>Enter to send · Shift+Enter for new line</span>
              <span className="font-mono">AI Master 2.5</span>
            </div>
          </div>
        </div>
      )}
    </>
  );
}

function isNearBottom(el: HTMLElement) {
  return el.scrollHeight - el.scrollTop - el.clientHeight < 80;
}
