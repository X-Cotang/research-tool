import { useState } from "react";
import { Bot, ChevronDown, ChevronRight, Terminal, Wrench } from "lucide-react";

import { Markdown } from "~/components/Markdown";

type Block =
  | { kind: "status"; text: string }
  | { kind: "assistant"; text: string }
  | { kind: "tool"; name: string; state: "call" | "running" | "done"; detail: string }
  | { kind: "output"; lines: string[] }
  | { kind: "command"; text: string };

const TOOL_LINE =
  /^\[cli\] (?:tool (\S+)|running (.+)|finished (\S+))(?: · (.*))?$/i;

function previewJson(line: string): { name: string; detail: string } | null {
  const name = /"toolName"\s*:\s*"([^"]+)"/.exec(line)?.[1];
  const text = /"text"\s*:\s*"((?:\\.|[^"\\]){0,220})/.exec(line)?.[1];
  if (!name && !text) return null;
  const detail = (text || "")
    .replace(/\\n/g, " ")
    .replace(/\\"/g, '"')
    .replace(/\s+/g, " ")
    .trim();
  return { name: name || "tool", detail: detail.slice(0, 220) };
}

function pushOutput(blocks: Block[], line: string) {
  const last = blocks[blocks.length - 1];
  if (last?.kind === "output") last.lines.push(line);
  else blocks.push({ kind: "output", lines: [line] });
}

export function parseWorkerLog(lines: string[]): Block[] {
  const blocks: Block[] = [];
  for (const raw of lines) {
    const line = raw.trim();
    if (!line) continue;

    const step = /^\[step:([^\]]+)\]\s*(.*)$/i.exec(line);
    if (step) {
      const detail = step[2].replace(/\s+/g, " ").trim();
      blocks.push({
        kind: "status",
        text: detail ? `${step[1]} · ${detail.slice(0, 180)}` : step[1],
      });
      continue;
    }

    if (line.startsWith("$ ")) {
      blocks.push({ kind: "command", text: line.slice(2) });
      continue;
    }

    if (line.startsWith("[cli]")) {
      const body = line.slice(5).trim();
      if (/^still running/i.test(body)) {
        const last = blocks[blocks.length - 1];
        if (last?.kind === "status" && last.text.startsWith("Still running")) {
          last.text = body;
        } else {
          blocks.push({ kind: "status", text: body });
        }
        continue;
      }
      if (/^(started|model turn|run finished|finished \()/i.test(body)) {
        const last = blocks[blocks.length - 1];
        if (last?.kind === "status" && last.text === body) continue;
        blocks.push({ kind: "status", text: body });
        continue;
      }
      const tool = TOOL_LINE.exec(line);
      if (tool) {
        const name = tool[1] || tool[2] || tool[3] || "tool";
        const state = tool[1] ? "call" : tool[2] ? "running" : "done";
        blocks.push({ kind: "tool", name, state, detail: (tool[4] || "").trim() });
        continue;
      }
      const last = blocks[blocks.length - 1];
      if (last?.kind === "assistant") last.text = `${last.text}\n\n${body}`;
      else blocks.push({ kind: "assistant", text: body });
      continue;
    }

    if (line.startsWith("{")) {
      const found = previewJson(line);
      if (found) {
        blocks.push({ kind: "tool", name: found.name, state: "done", detail: found.detail });
      }
      continue;
    }

    pushOutput(blocks, line);
  }
  return blocks;
}

function OutputBlock({ lines }: { lines: string[] }) {
  const [open, setOpen] = useState(lines.length <= 6);
  const shown = open ? lines : lines.slice(-4);
  return (
    <div className="my-2 overflow-hidden rounded-md border border-[var(--desk-border)] bg-[#070709]">
      <button
        type="button"
        className="flex w-full items-center gap-2 px-3 py-2 text-left text-[11px] text-[var(--desk-ink-muted)] hover:bg-[var(--desk-surface-2)]"
        onClick={() => setOpen((value) => !value)}
      >
        {open ? <ChevronDown className="h-3.5 w-3.5" /> : <ChevronRight className="h-3.5 w-3.5" />}
        <Terminal className="h-3.5 w-3.5" />
        <span className="font-mono">Worker output · {lines.length} lines</span>
      </button>
      <pre className="max-h-64 overflow-auto border-t border-[var(--desk-border-subtle)] px-3 py-2 font-mono text-[11px] leading-relaxed text-zinc-400">
        {shown.join("\n")}
        {!open && lines.length > 4 ? "\n…" : ""}
      </pre>
    </div>
  );
}

function ToolRow({ block }: { block: Extract<Block, { kind: "tool" }> }) {
  const [open, setOpen] = useState(false);
  const long = block.detail.length > 140;
  const label = block.state === "call" ? "call" : block.state === "running" ? "running" : "done";
  return (
    <div className="my-1.5 overflow-hidden rounded-md border border-[var(--desk-border)] bg-[var(--desk-surface-2)]/70">
      <button
        type="button"
        className="flex w-full items-center gap-2 px-3 py-2 text-left"
        onClick={() => long && setOpen((value) => !value)}
      >
        <span className="flex h-5 w-5 items-center justify-center rounded border border-zinc-700 bg-zinc-800/60 text-zinc-300">
          <Wrench className="h-3 w-3" />
        </span>
        <span className="font-mono text-[11px] font-semibold text-[var(--desk-ink)]">{block.name}</span>
        {!open && block.detail ? (
          <span className="min-w-0 flex-1 truncate font-mono text-[11px] text-[var(--desk-ink-faint)]">
            {block.detail}
          </span>
        ) : (
          <span className="flex-1" />
        )}
        <span className="font-mono text-[10px] uppercase text-[var(--desk-ink-faint)]">{label}</span>
      </button>
      {open && block.detail ? (
        <pre className="max-h-64 overflow-auto whitespace-pre-wrap border-t border-[var(--desk-border-subtle)] bg-[#070709] px-3 py-2 font-mono text-[11px] leading-relaxed text-zinc-300">
          {block.detail}
        </pre>
      ) : null}
    </div>
  );
}

export function WorkerTranscript({ lines, active }: { lines: string[]; active: boolean }) {
  const blocks = parseWorkerLog(lines);
  if (blocks.length === 0) {
    return (
      <p className="text-xs text-[var(--desk-ink-faint)]">
        {active ? "Waiting for the worker to print its first step." : "No session output was captured."}
      </p>
    );
  }

  return (
    <div className="space-y-1">
      {blocks.map((block, index) => {
        if (block.kind === "status") {
          return (
            <p key={index} className="py-1 text-center font-mono text-[10px] text-[var(--desk-ink-faint)]">
              {block.text}
            </p>
          );
        }
        if (block.kind === "command") {
          return (
            <p key={index} className="truncate font-mono text-[10px] text-[var(--desk-ink-faint)]" title={block.text}>
              $ {block.text}
            </p>
          );
        }
        if (block.kind === "tool") return <ToolRow key={index} block={block} />;
        if (block.kind === "output") return <OutputBlock key={index} lines={block.lines} />;
        return (
          <div key={index} className="my-3 flex justify-start gap-2.5">
            <div className="relative flex h-7 w-7 shrink-0 items-center justify-center rounded-full border border-zinc-700 bg-[#121216] text-[var(--desk-accent)]">
              <Bot className="h-4 w-4" />
            </div>
            <div className="min-w-0 max-w-[90%]">
              <p className="mb-1 font-mono text-[11px] font-semibold text-[var(--desk-ink)]">Worker</p>
              <div className="desk-panel rounded-xl rounded-tl-sm border-[var(--desk-border)] bg-[var(--desk-surface)] p-4">
                <Markdown content={block.text} />
              </div>
            </div>
          </div>
        );
      })}
    </div>
  );
}
