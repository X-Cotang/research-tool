import { useState } from "react";
import {
  AlertTriangle,
  Bot,
  Brain,
  Check,
  ChevronDown,
  ChevronRight,
  Copy,
  Cpu,
  Database,
  Search,
  Shield,
  Sliders,
  Sparkles,
  Terminal,
  User,
  Wrench,
} from "lucide-react";

import { Markdown } from "~/components/Markdown";
import type { ChatMessage } from "~/lib/api";

export type LiveBlock =
  | { kind: "text"; content: string }
  | { kind: "thinking"; content: string }
  | { kind: "tool_call"; name: string; arguments?: string }
  | { kind: "tool_result"; name: string; result?: string };

function tryParseJson(raw: string): Record<string, unknown> | null {
  try {
    const value = JSON.parse(raw) as unknown;
    return value && typeof value === "object" ? (value as Record<string, unknown>) : null;
  } catch {
    return null;
  }
}

function formatJsonOrText(raw: string): string {
  try {
    const parsed = JSON.parse(raw);
    return JSON.stringify(parsed, null, 2);
  } catch {
    return raw;
  }
}

function getToolIcon(name: string) {
  const n = name.toLowerCase();
  if (n.includes("scan")) return Search;
  if (n.includes("project") || n.includes("db")) return Database;
  if (n.includes("finding") || n.includes("sast")) return Shield;
  if (n.includes("queue") || n.includes("research") || n.includes("run")) return Terminal;
  if (n.includes("skill") || n.includes("harness")) return Cpu;
  if (n.includes("status") || n.includes("workspace")) return Sliders;
  return Wrench;
}

export function ToolBlock({
  kind,
  name,
  args,
  result,
  defaultOpen = false,
  isLive = false,
}: {
  kind: "call" | "result" | "combined";
  name: string;
  args?: string;
  result?: string;
  defaultOpen?: boolean;
  isLive?: boolean;
}) {
  const [open, setOpen] = useState(defaultOpen);
  const [copied, setCopied] = useState(false);
  const Icon = getToolIcon(name);

  const isRunning = isLive && !result && kind !== "result";
  const isError = Boolean(result && (result.includes("Error:") || result.includes("failed")));
  const isSuccess = Boolean(result && !isError);

  const displayArgs = args ? formatJsonOrText(args) : "";
  const displayResult = result ? formatJsonOrText(result) : "";

  // One line preview of args
  const preview = (args || "")
    .replace(/\s+/g, " ")
    .replace(/[{}"]/g, "")
    .trim();

  const copyDetails = async () => {
    const payload = [
      `Tool: ${name}`,
      displayArgs ? `Parameters:\n${displayArgs}` : "",
      displayResult ? `Result:\n${displayResult}` : "",
    ]
      .filter(Boolean)
      .join("\n\n");
    try {
      await navigator.clipboard.writeText(payload);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch {
      /* ignore */
    }
  };

  return (
    <div
      className={`my-1.5 overflow-hidden rounded-md border text-xs transition-colors ${
        open
          ? "border-[var(--desk-border-accent)] bg-[var(--desk-surface)]"
          : "border-[var(--desk-border)] bg-[var(--desk-surface-2)]/70 hover:border-[var(--desk-border-accent)]"
      }`}
    >
      <div className="flex items-center">
      <button
        type="button"
        onClick={() => setOpen(!open)}
        className="flex min-w-0 flex-1 items-center gap-2 px-3 py-2 text-left transition-colors hover:bg-[var(--desk-surface-2)]"
      >
        <span className="text-[var(--desk-ink-faint)]">
          {open ? <ChevronDown className="h-3.5 w-3.5" /> : <ChevronRight className="h-3.5 w-3.5" />}
        </span>

        <span
          className={`flex h-5 w-5 items-center justify-center rounded border ${
            isRunning
              ? "border-sky-500/40 bg-sky-500/10 text-sky-400"
              : isError
                ? "border-red-500/40 bg-red-500/10 text-red-400"
                : isSuccess
                  ? "border-emerald-500/40 bg-emerald-500/10 text-emerald-400"
                  : "border-zinc-700 bg-zinc-800/60 text-zinc-300"
          }`}
        >
          <Icon className="h-3 w-3" />
        </span>

        <span className="font-mono text-[11px] font-semibold text-[var(--desk-ink)]">
          {name}
        </span>

        {preview && !open ? (
          <span className="min-w-0 flex-1 truncate font-mono text-[11px] text-[var(--desk-ink-faint)]">
            {preview}
          </span>
        ) : (
          <span className="flex-1" />
        )}

        <div className="flex shrink-0 items-center gap-2">
          {isRunning ? (
            <span className="inline-flex items-center gap-1 font-mono text-[10px] text-sky-400">
              <span className="h-1.5 w-1.5 animate-ping rounded-full bg-sky-400" />
              EXECUTING
            </span>
          ) : isError ? (
            <span className="inline-flex items-center gap-1 font-mono text-[10px] text-[var(--desk-danger)]">
              FAILED
            </span>
          ) : isSuccess ? (
            <span className="inline-flex items-center gap-1 font-mono text-[10px] text-[var(--desk-success)]">
              SUCCESS
            </span>
          ) : (
            <span className="font-mono text-[10px] uppercase text-[var(--desk-ink-faint)]">
              {kind}
            </span>
          )}
        </div>
      </button>
      <CopyMessageButton
        text={[
          name,
          displayArgs ? displayArgs : "",
          displayResult ? displayResult : "",
        ]
          .filter(Boolean)
          .join("\n\n")}
      />
      </div>

      {open && (
        <div className="border-t border-[var(--desk-border-subtle)] bg-[#070709] p-3 text-xs">
          <div className="mb-2 flex items-center justify-between">
            <span className="font-mono text-[10px] uppercase tracking-wider text-[var(--desk-ink-faint)]">
              Execution Payload
            </span>
            <button
              type="button"
              onClick={() => void copyDetails()}
              className="flex items-center gap-1 rounded px-1.5 py-0.5 font-mono text-[10px] text-[var(--desk-ink-muted)] hover:bg-[var(--desk-surface-2)] hover:text-[var(--desk-ink)]"
            >
              {copied ? (
                <>
                  <Check className="h-3 w-3 text-[var(--desk-success)]" />
                  <span className="text-[var(--desk-success)]">Copied</span>
                </>
              ) : (
                <>
                  <Copy className="h-3 w-3" />
                  <span>Copy</span>
                </>
              )}
            </button>
          </div>

          {displayArgs && (
            <div className="mb-2">
              <p className="mb-1 font-mono text-[10px] font-medium text-[var(--desk-ink-faint)] uppercase">
                Arguments:
              </p>
              <pre className="overflow-x-auto rounded border border-[var(--desk-border-subtle)] bg-[#0a0a0d] p-2.5 font-mono text-[11px] leading-relaxed text-zinc-300">
                {displayArgs}
              </pre>
            </div>
          )}

          {displayResult && (
            <div>
              <p className="mb-1 font-mono text-[10px] font-medium text-[var(--desk-ink-faint)] uppercase">
                Result:
              </p>
              <pre className="max-h-72 overflow-x-auto rounded border border-[var(--desk-border-subtle)] bg-[#0a0a0d] p-2.5 font-mono text-[11px] leading-relaxed text-zinc-300">
                {displayResult}
              </pre>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

export function ThinkingBlock({
  content,
  defaultOpen = false,
}: {
  content: string;
  defaultOpen?: boolean;
}) {
  const [open, setOpen] = useState(defaultOpen);
  if (!content.trim()) return null;

  const preview = content.slice(0, 85).replace(/\s+/g, " ").trim();

  return (
    <div className="my-2 overflow-hidden rounded-md border border-[var(--desk-border)] bg-[var(--desk-surface-2)]/40 text-xs">
      <div className="flex items-center">
        <button
          type="button"
          onClick={() => setOpen(!open)}
          className="flex min-w-0 flex-1 items-center gap-2 px-3 py-1.5 text-left transition-colors hover:bg-[var(--desk-surface-2)]"
        >
          <span className="text-[var(--desk-ink-faint)]">
            {open ? <ChevronDown className="h-3.5 w-3.5" /> : <ChevronRight className="h-3.5 w-3.5" />}
          </span>
          <Brain className="h-3.5 w-3.5 text-purple-400" />
          <span className="font-mono text-[11px] font-medium text-[var(--desk-ink-muted)]">
            Reasoning Process
          </span>
          {!open && (
            <span className="min-w-0 flex-1 truncate font-mono text-[10px] text-[var(--desk-ink-faint)] italic">
              {preview}…
            </span>
          )}
        </button>
        <CopyMessageButton text={content} />
      </div>

      {open && (
        <div className="border-t border-[var(--desk-border-subtle)] bg-[#09090c] p-3 font-mono text-xs leading-relaxed text-[var(--desk-ink-muted)]">
          <div className="chat-thinking whitespace-pre-wrap">{content}</div>
        </div>
      )}
    </div>
  );
}

async function copyMessageText(text: string): Promise<boolean> {
  try {
    await navigator.clipboard.writeText(text);
    return true;
  } catch {
    const area = document.createElement("textarea");
    area.value = text;
    area.setAttribute("readonly", "true");
    area.style.position = "fixed";
    area.style.left = "-9999px";
    document.body.appendChild(area);
    area.select();
    const ok = document.execCommand("copy");
    area.remove();
    return ok;
  }
}

export function CopyMessageButton({ text, label = "Copy" }: { text: string; label?: string }) {
  const [copied, setCopied] = useState(false);

  return (
    <button
      type="button"
      className="inline-flex items-center gap-1 rounded px-1.5 py-0.5 font-mono text-[10px] text-[var(--desk-ink-faint)] hover:bg-[var(--desk-surface-2)] hover:text-[var(--desk-ink)]"
      onClick={(event) => {
        event.stopPropagation();
        void copyMessageText(text).then((ok) => {
          if (!ok) return;
          setCopied(true);
          window.setTimeout(() => setCopied(false), 1500);
        });
      }}
    >
      {copied ? <Check className="h-3 w-3 text-[var(--desk-success)]" /> : <Copy className="h-3 w-3" />}
      <span className={copied ? "text-[var(--desk-success)]" : undefined}>{copied ? "Copied" : label}</span>
    </button>
  );
}

export function MessageBubble({ message }: { message: ChatMessage }) {
  const type = message.type || "text";

  if (type === "thinking") {
    return <ThinkingBlock content={message.content} />;
  }

  if (type === "tool_call") {
    const parsed = tryParseJson(message.content);
    return (
      <ToolBlock
        kind="call"
        name={String(parsed?.name || "tool")}
        args={String(parsed?.arguments ?? message.content)}
      />
    );
  }

  if (type === "tool_result") {
    const parsed = tryParseJson(message.content);
    return (
      <ToolBlock
        kind="result"
        name={String(parsed?.name || "tool")}
        result={String(parsed?.result ?? message.content)}
      />
    );
  }

  const observation = type === "observation";
  const isUser = message.role === "user" && !observation;

  if (observation) {
    return (
      <div className="my-2 flex justify-start">
        <div className="flex max-w-[90%] items-start gap-2.5 rounded-lg border border-[var(--desk-border-accent)] bg-[var(--desk-surface-2)] p-3 shadow-sm">
          <div className="mt-0.5 flex h-5 w-5 shrink-0 items-center justify-center rounded-full bg-amber-500/10 text-amber-400">
            <AlertTriangle className="h-3 w-3" />
          </div>
          <div className="min-w-0 flex-1">
            <p className="font-mono text-[10px] font-semibold uppercase tracking-wider text-amber-400">
              System Observation / Job Event
            </p>
            <div className="mt-1 font-mono text-xs text-[var(--desk-ink)] whitespace-pre-wrap">
              {message.content}
            </div>
            <CopyMessageButton text={message.content} />
          </div>
        </div>
      </div>
    );
  }

  if (isUser) {
    return (
      <div className="my-3 flex justify-end gap-2.5">
        <div className="flex max-w-[85%] flex-col items-end">
          <div className="rounded-xl rounded-tr-sm bg-[#fafafa] px-4 py-2.5 text-sm font-medium text-[#09090b] shadow-md shadow-black/20">
            <p className="whitespace-pre-wrap leading-relaxed">{message.content}</p>
          </div>
          <span className="mt-1 flex items-center gap-2 font-mono text-[10px] text-[var(--desk-ink-faint)]">
            You
            <CopyMessageButton text={message.content} />
          </span>
        </div>
        <div className="flex h-7 w-7 shrink-0 items-center justify-center rounded-full border border-zinc-700 bg-zinc-800 text-zinc-200">
          <User className="h-3.5 w-3.5" />
        </div>
      </div>
    );
  }

  // Assistant Master
  return (
    <div className="my-3 flex justify-start gap-2.5">
      <div className="relative flex h-7 w-7 shrink-0 items-center justify-center rounded-full border border-zinc-700 bg-[#121216] text-[var(--desk-accent)] shadow-sm">
        <Bot className="h-4 w-4" />
        <span className="absolute -bottom-0.5 -right-0.5 h-2 w-2 rounded-full border border-[#09090b] bg-[var(--desk-success)]" />
      </div>
      <div className="flex max-w-[90%] flex-col items-start min-w-0">
        <div className="mb-1 flex items-center gap-2">
          <span className="font-mono text-[11px] font-semibold tracking-tight text-[var(--desk-ink)]">
            AI Master
          </span>
          <span className="rounded bg-[var(--desk-surface-2)] px-1.5 py-0.2 font-mono text-[9px] uppercase tracking-wider text-[var(--desk-ink-faint)]">
            Autonomous Cyber Desk
          </span>
        </div>
        <div className="desk-panel w-full rounded-xl rounded-tl-sm border-[var(--desk-border)] bg-[var(--desk-surface)] p-4 shadow-sm">
          <Markdown content={message.content} />
        </div>
        <CopyMessageButton text={message.content} />
      </div>
    </div>
  );
}

export function LiveBubble({ block }: { block: LiveBlock }) {
  if (block.kind === "text") {
    return (
      <div className="my-3 flex justify-start gap-2.5">
        <div className="relative flex h-7 w-7 shrink-0 items-center justify-center rounded-full border border-zinc-700 bg-[#121216] text-[var(--desk-accent)]">
          <Bot className="h-4 w-4" />
          <span className="absolute -bottom-0.5 -right-0.5 h-2 w-2 animate-ping rounded-full bg-sky-400" />
        </div>
        <div className="flex max-w-[90%] flex-col items-start min-w-0">
          <div className="mb-1 flex items-center gap-2">
            <span className="font-mono text-[11px] font-semibold text-[var(--desk-ink)]">
              AI Master
            </span>
            <span className="flex items-center gap-1 font-mono text-[9px] text-sky-400">
              <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-sky-400" />
              GENERATING…
            </span>
          </div>
          <div className="desk-panel w-full rounded-xl rounded-tl-sm border-[var(--desk-border)] bg-[var(--desk-surface)] p-4 shadow-sm">
            <Markdown content={block.content} />
            <span className="ml-1 inline-block h-3.5 w-1.5 animate-pulse bg-[var(--desk-accent)] align-middle" />
          </div>
          <CopyMessageButton text={block.content} />
        </div>
      </div>
    );
  }

  if (block.kind === "thinking") {
    return <ThinkingBlock content={block.content} defaultOpen />;
  }

  if (block.kind === "tool_call") {
    return (
      <ToolBlock
        kind="call"
        name={block.name}
        args={block.arguments}
        defaultOpen
        isLive
      />
    );
  }

  return (
    <ToolBlock
      kind="result"
      name={block.name}
      result={block.result}
      defaultOpen
    />
  );
}

export function PromptSuggestions({
  onSelect,
}: {
  onSelect: (prompt: string) => void;
}) {
  const suggestions = [
    {
      icon: Search,
      label: "Scan target org",
      prompt: "Scan GitHub organization https://github.com/expressjs to discover repositories and calculate research scores.",
    },
    {
      icon: Terminal,
      label: "Audit attack surface",
      prompt: "Analyze the attack surface of our top scored projects and identify potential critical vulnerabilities (RCE, SSRF, Deserialization).",
    },
    {
      icon: Sparkles,
      label: "Suggest 0-day prompt",
      prompt: "Suggest a tailored vulnerability research prompt template for project #1 focused on finding high-value flaws.",
    },
    {
      icon: Sliders,
      label: "Workspace status",
      prompt: "What is the current status of the workspace, running research jobs, and recent findings?",
    },
  ];

  return (
    <div className="flex flex-wrap items-center gap-1.5 py-1">
      <span className="font-mono text-[10px] uppercase text-[var(--desk-ink-faint)] mr-1">
        Quick Actions:
      </span>
      {suggestions.map((s, i) => {
        const Icon = s.icon;
        return (
          <button
            key={i}
            type="button"
            onClick={() => onSelect(s.prompt)}
            className="flex items-center gap-1.5 rounded-full border border-[var(--desk-border)] bg-[var(--desk-surface-2)]/80 px-2.5 py-1 text-xs text-[var(--desk-ink-muted)] transition-all hover:border-[var(--desk-border-accent)] hover:bg-[var(--desk-surface-2)] hover:text-[var(--desk-ink)]"
          >
            <Icon className="h-3 w-3 text-[var(--desk-ink-faint)]" />
            <span>{s.label}</span>
          </button>
        );
      })}
    </div>
  );
}
