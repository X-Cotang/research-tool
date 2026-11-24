import { useEffect, useRef, useState } from "react";
import { Link, useNavigate, useParams } from "react-router";
import {
  ArrowLeft,
  Bot,
  Brain,
  Check,
  ChevronDown,
  Copy,
  ExternalLink,
  Plus,
  RefreshCw,
  Send,
  Sparkles,
  Terminal,
  Trash2,
} from "lucide-react";

import {
  LiveBubble,
  MessageBubble,
  PromptSuggestions,
  type LiveBlock,
} from "~/components/ChatBlocks";
import {
  deleteConversation,
  fetchMessages,
  streamChatMessage,
  type ChatMessage,
  type ChatStreamEvent,
} from "~/lib/api";
import { PageHeader, Spinner } from "~/lib/ui";

export default function ChatDetailPage() {
  const { id } = useParams();
  const navigate = useNavigate();
  const conversationId = Number(id);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [live, setLive] = useState<LiveBlock[]>([]);
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);
  const scrollerRef = useRef<HTMLDivElement>(null);
  const stickToBottomRef = useRef(true);
  const abortRef = useRef<AbortController | null>(null);

  useEffect(() => {
    if (!conversationId) return;
    let stop = false;
    const pull = () => {
      fetchMessages(conversationId)
        .then((r) => {
          if (stop) return;
          setMessages((prev) => (sameTranscript(prev, r.messages) ? prev : r.messages));
        })
        .catch((e) => {
          if (!stop) setError(e instanceof Error ? e.message : "Load failed");
        });
    };
    pull();
    const timer = window.setInterval(pull, 5000);
    return () => {
      stop = true;
      window.clearInterval(timer);
    };
  }, [conversationId]);

  useEffect(() => {
    stickToBottomRef.current = true;
  }, [conversationId]);

  useEffect(() => {
    const el = scrollerRef.current;
    if (!el || !stickToBottomRef.current) return;
    el.scrollTop = el.scrollHeight;
  }, [messages, live]);

  async function send(customPrompt?: string) {
    const text = (customPrompt || input).trim();
    if (!text || busy || !conversationId) return;
    setError(null);
    setBusy(true);
    setInput("");
    stickToBottomRef.current = true;
    setMessages((prev) => [
      ...prev,
      {
        id: Date.now(),
        conversation_id: conversationId,
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
    try {
      await streamChatMessage(
        conversationId,
        text,
        (ev: ChatStreamEvent) => {
          if (ev.type === "token") {
            assistant += ev.content ?? "";
            setLive((prev) => {
              const withoutText = prev.filter((b) => b.kind !== "text");
              return [...withoutText, { kind: "text", content: assistant }];
            });
          } else if (ev.type === "thinking") {
            thinking += ev.content ?? "";
            setLive((prev) => {
              const rest = prev.filter((b) => b.kind !== "thinking");
              return [{ kind: "thinking", content: thinking }, ...rest];
            });
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
            fetchMessages(conversationId)
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

  async function onDelete() {
    if (!conversationId) return;
    if (!window.confirm("Delete this conversation and all tool logs?")) return;
    await deleteConversation(conversationId);
    navigate("/chat");
  }

  async function onCopyTranscript() {
    const text = messages
      .map((m) => `[${m.role.toUpperCase()}]\n${m.content}`)
      .join("\n\n---\n\n");
    try {
      await navigator.clipboard.writeText(text);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch {
      /* ignore */
    }
  }

  return (
    <div className="flex h-[calc(100dvh-11rem)] flex-col">
      {/* Top Header */}
      <div className="mb-4 flex flex-wrap items-center justify-between gap-3 border-b border-[var(--desk-border-subtle)] pb-3">
        <div className="flex items-center gap-3">
          <Link
            to="/chat"
            className="flex h-8 w-8 items-center justify-center rounded-md border border-[var(--desk-border)] bg-[var(--desk-surface-2)] text-[var(--desk-ink-muted)] transition-colors hover:text-[var(--desk-ink)]"
          >
            <ArrowLeft className="h-4 w-4" />
          </Link>
          <div>
            <div className="flex items-center gap-2">
              <h1 className="font-display text-base font-semibold tracking-tight text-[var(--desk-ink)]">
                AI Master Session #{conversationId}
              </h1>
              <span className="flex items-center gap-1 rounded-full border border-emerald-500/30 bg-emerald-500/10 px-2 py-0.5 font-mono text-[10px] text-emerald-400">
                <span className="h-1.5 w-1.5 rounded-full bg-emerald-400" />
                ONLINE
              </span>
            </div>
            <p className="font-mono text-[11px] text-[var(--desk-ink-faint)]">
              Integrated tool-calling agent with memory, skills, and prompt synthesis
            </p>
          </div>
        </div>

        <div className="flex items-center gap-2">
          <button
            type="button"
            className="desk-btn desk-btn-ghost desk-btn-sm"
            onClick={() => void onCopyTranscript()}
          >
            {copied ? (
              <>
                <Check className="h-3 w-3 text-[var(--desk-success)]" />
                <span className="text-[var(--desk-success)]">Copied</span>
              </>
            ) : (
              <>
                <Copy className="h-3 w-3" />
                <span>Copy Transcript</span>
              </>
            )}
          </button>
          <button
            type="button"
            className="desk-btn desk-btn-danger desk-btn-sm"
            onClick={() => void onDelete()}
          >
            <Trash2 className="h-3 w-3" />
            <span>Delete</span>
          </button>
        </div>
      </div>

      {/* Main Chat Panel */}
      <div className="desk-panel flex min-h-0 flex-1 flex-col overflow-hidden">
        {/* Messages Container */}
        <div
          ref={scrollerRef}
          className="min-h-0 flex-1 space-y-3 overflow-y-auto p-4 sm:p-6"
          onScroll={(e) => {
            stickToBottomRef.current = isNearBottom(e.currentTarget);
          }}
        >
          {messages.length === 0 && live.length === 0 ? (
            <div className="flex h-full flex-col items-center justify-center py-12 text-center">
              <div className="relative mb-4 flex h-16 w-16 items-center justify-center rounded-2xl border border-[var(--desk-border-accent)] bg-[var(--desk-surface-2)] text-[var(--desk-accent)] shadow-xl">
                <Bot className="h-8 w-8 text-zinc-100" />
                <span className="absolute -bottom-1 -right-1 h-3.5 w-3.5 rounded-full border-2 border-[#09090b] bg-[var(--desk-success)]" />
              </div>
              <h2 className="font-display text-lg font-semibold tracking-tight text-[var(--desk-ink)]">
                Autonomous Security Intelligence Master
              </h2>
              <p className="mt-1.5 max-w-md text-xs text-[var(--desk-ink-muted)]">
                Directly orchestrate reconnaissance, skill retrieval, prompt templates, and batch vulnerability research runs across targets.
              </p>

              <div className="mt-6 w-full max-w-xl">
                <PromptSuggestions onSelect={(p) => void send(p)} />
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

        {/* Error message */}
        {error ? (
          <div className="border-t border-red-500/20 bg-red-500/10 px-4 py-2 text-xs text-[var(--desk-danger)]">
            {error}
          </div>
        ) : null}

        {/* Prompt Suggestions Bar */}
        {messages.length > 0 && (
          <div className="border-t border-[var(--desk-border-subtle)] bg-[#09090c] px-4 py-1.5">
            <PromptSuggestions onSelect={(p) => void send(p)} />
          </div>
        )}

        {/* Input Bar */}
        <div className="border-t border-[var(--desk-border)] bg-[#0c0c0f] p-3 sm:p-4">
          <div className="flex items-end gap-3 rounded-xl border border-[var(--desk-border)] bg-[var(--desk-surface-2)] p-2 shadow-inner focus-within:border-zinc-500">
            <textarea
              className="max-h-36 min-h-[56px] flex-1 resize-none bg-transparent px-2 py-1 font-sans text-sm text-[var(--desk-ink)] placeholder:text-[var(--desk-ink-faint)] focus:outline-none"
              placeholder="Ask AI Master (e.g., 'Discover org repos', 'Compose plan for project #1', 'Check findings')…"
              value={input}
              onChange={(e) => setInput(e.target.value)}
              disabled={busy}
              rows={2}
              onKeyDown={(e) => {
                if (e.key === "Enter" && !e.shiftKey) {
                  e.preventDefault();
                  void send();
                }
              }}
            />
            <button
              type="button"
              className="desk-btn desk-btn-primary flex h-9 w-9 items-center justify-center rounded-lg p-0"
              disabled={busy || !input.trim()}
              onClick={() => void send()}
            >
              {busy ? <Spinner /> : <Send className="h-4 w-4" />}
            </button>
          </div>
          <div className="mt-2 flex items-center justify-between px-1 text-[11px] text-[var(--desk-ink-faint)] font-mono">
            <span>Press Enter to send · Shift+Enter for newline</span>
            <span>Tool Calling · Memory · Skills</span>
          </div>
        </div>
      </div>
    </div>
  );
}

const NEAR_BOTTOM_PX = 80;

function isNearBottom(el: HTMLElement) {
  return el.scrollHeight - el.scrollTop - el.clientHeight < NEAR_BOTTOM_PX;
}

function sameTranscript(prev: ChatMessage[], next: ChatMessage[]) {
  if (prev.length !== next.length) return false;
  for (let i = 0; i < prev.length; i += 1) {
    const a = prev[i];
    const b = next[i];
    if (a.id !== b.id || a.role !== b.role || a.type !== b.type || a.content !== b.content) {
      return false;
    }
  }
  return true;
}
