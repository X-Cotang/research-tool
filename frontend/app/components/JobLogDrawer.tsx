import { useEffect, useRef, useState } from "react";
import { Link } from "react-router";
import {
  Check,
  Copy,
  ExternalLink,
  SquareTerminal,
  Terminal,
  X,
} from "lucide-react";

import {
  fetchJob,
  streamJobLogs,
  type Job,
  type JobStreamEvent,
  type Project,
} from "~/lib/api";
import { Markdown } from "~/components/Markdown";
import { Spinner, StatusBadge } from "~/lib/ui";

type Props = {
  jobId: number | null;
  open: boolean;
  onClose: () => void;
};

function logLines(log: string | undefined): string[] {
  if (!log) return [];
  return log.split("\n").filter((line) => line.trim().length > 0);
}

function lineTone(line: string): string {
  if (/^Error\b/i.test(line) || /\[step:interrupted\]/.test(line)) {
    return "text-red-300";
  }
  if (/^\[step:/.test(line)) return "text-sky-300";
  if (line.startsWith("$ ")) return "text-amber-200";
  return "";
}

export function JobLogDrawer({ jobId, open, onClose }: Props) {
  const [lines, setLines] = useState<string[]>([]);
  const [job, setJob] = useState<Job | null>(null);
  const [project, setProject] = useState<Project | null>(null);
  const [copied, setCopied] = useState(false);
  const [tab, setTab] = useState<"log" | "report">("log");
  const logRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open || !jobId) return;
    setLines([]);
    setJob(null);
    setProject(null);
    setTab("log");
    const ac = new AbortController();
    let stopped = false;

    fetchJob(jobId)
      .then((snap) => {
        if (stopped) return;
        setJob(snap.job);
        setProject(snap.project);
        setLines(logLines(snap.job.log));
      })
      .catch(() => {});

    const stopStream = streamJobLogs(
      jobId,
      (ev: JobStreamEvent) => {
        if (ev.type === "snapshot") {
          const next = ev.job as Job | undefined;
          if (next) {
            setJob(next);
            setLines(logLines(next.log));
          }
          if (ev.project) setProject(ev.project as Project);
          return;
        }
        if (ev.type === "log" && ev.line) {
          setLines((prev) => [...prev, ev.line as string]);
        } else if (ev.type === "status") {
          setJob((prev) =>
            prev
              ? {
                  ...prev,
                  status: typeof ev.status === "string" ? ev.status : prev.status,
                  error: typeof ev.error === "string" ? ev.error : prev.error,
                  error_step:
                    typeof ev.error_step === "string" ? ev.error_step : prev.error_step,
                }
              : prev,
          );
        } else if (ev.type === "done") {
          setJob((prev) =>
            prev
              ? {
                  ...prev,
                  status: typeof ev.status === "string" ? ev.status : prev.status,
                  error: typeof ev.error === "string" ? ev.error : prev.error,
                  error_step:
                    typeof ev.error_step === "string" ? ev.error_step : prev.error_step,
                  report: typeof ev.report === "string" ? ev.report : prev.report,
                }
              : prev,
          );
          if (ev.status === "error" || ev.status === "done") {
            setTab(ev.status === "error" ? "log" : "report");
          }
        } else if (ev.line) {
          setLines((prev) => [...prev, String(ev.line)]);
        }
      },
      ac.signal,
    );

    return () => {
      stopped = true;
      ac.abort();
      stopStream();
    };
  }, [open, jobId]);

  useEffect(() => {
    if (logRef.current) {
      logRef.current.scrollTop = logRef.current.scrollHeight;
    }
  }, [lines]);

  const onCopy = async () => {
    try {
      await navigator.clipboard.writeText(lines.join("\n"));
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch {
      /* ignore */
    }
  };

  if (!open || !jobId) return null;

  const report = job?.report || project?.last_report || "";
  const finished = job?.status === "done" || job?.status === "error";

  return (
    <div className="fixed inset-0 z-50 flex justify-end">
      <button
        type="button"
        className="log-drawer-backdrop absolute inset-0 cursor-default"
        aria-label="Close job logs"
        onClick={onClose}
      />
      <aside className="log-drawer-panel relative z-10 flex h-full w-full max-w-2xl flex-col border-l border-[var(--desk-border-accent)] bg-[#09090b] shadow-2xl">
        {/* Header */}
        <header className="flex items-center justify-between border-b border-[var(--desk-border)] bg-[#0d0d11] px-5 py-3.5">
          <div className="flex items-center gap-3">
            <div className="flex h-8 w-8 items-center justify-center rounded-lg border border-[var(--desk-border)] bg-[var(--desk-surface-2)] text-[var(--desk-accent)]">
              <Terminal className="h-4 w-4" />
            </div>
            <div>
              <div className="flex items-center gap-2">
                <span className="font-mono text-xs font-semibold text-[var(--desk-ink)]">
                  Job #{jobId}
                </span>
                {job ? <StatusBadge status={job.status} /> : <Spinner />}
              </div>
              <p className="font-mono text-[11px] text-[var(--desk-ink-faint)] truncate max-w-sm">
                {project?.full_name ?? "External Worker Stream"}
              </p>
            </div>
          </div>

          <div className="flex items-center gap-2">
            <Link to={`/jobs/${jobId}`} className="desk-btn desk-btn-ghost desk-btn-xs font-mono">
              Open session
            </Link>
            <button
              type="button"
              className="desk-btn desk-btn-ghost desk-btn-xs font-mono"
              onClick={() => void onCopy()}
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
            <button
              type="button"
              className="rounded p-1.5 text-[var(--desk-ink-muted)] hover:bg-[var(--desk-surface-2)] hover:text-[var(--desk-ink)]"
              onClick={onClose}
            >
              <X className="h-4 w-4" />
            </button>
          </div>
        </header>

        {job?.error ? (
          <div className="border-b border-red-500/30 bg-red-500/10 px-5 py-3 text-xs text-red-200">
            <p className="font-mono font-semibold uppercase tracking-wide text-red-300">
              Failed{job.error_step ? ` at step ${job.error_step}` : ""}
            </p>
            <p className="mt-1 whitespace-pre-wrap break-words font-mono">{job.error}</p>
          </div>
        ) : null}

        {job?.command ? (
          <div className="border-b border-[var(--desk-border-subtle)] bg-[#050508] px-5 py-2 font-mono text-[11px] text-[var(--desk-ink-muted)]">
            <span className="text-[var(--desk-ink-faint)]">Command: </span>
            <code className="text-zinc-300 break-all">{job.command}</code>
          </div>
        ) : null}

        <div className="flex gap-2 border-b border-[var(--desk-border-subtle)] px-5 py-2">
          <button
            type="button"
            className={`desk-btn desk-btn-ghost desk-btn-xs font-mono ${tab === "log" ? "text-[var(--desk-ink)]" : ""}`}
            onClick={() => setTab("log")}
          >
            Logs ({lines.length})
          </button>
          <button
            type="button"
            className={`desk-btn desk-btn-ghost desk-btn-xs font-mono ${tab === "report" ? "text-[var(--desk-ink)]" : ""}`}
            onClick={() => setTab("report")}
          >
            Result {report ? "" : "(empty)"}
          </button>
        </div>

        {tab === "report" ? (
          <div className="flex-1 overflow-auto bg-[#030304] p-4 text-xs text-[#d4d4d8]">
            {report ? (
              <Markdown content={report} />
            ) : (
              <p className="font-mono text-[var(--desk-ink-faint)]">
                This job has no research report yet.
              </p>
            )}
          </div>
        ) : (
        <div
          ref={logRef}
          className="flex-1 overflow-auto bg-[#030304] p-4 font-mono text-[11px] leading-relaxed text-[#d4d4d8]"
        >
          {lines.length === 0 ? (
            <div className="flex h-full flex-col items-center justify-center text-center text-[var(--desk-ink-faint)]">
              {finished ? null : <Spinner />}
              <p className="mt-2 font-mono text-xs">
                {finished
                  ? "No log lines were captured for this job."
                  : "Connecting to job output stream…"}
              </p>
            </div>
          ) : (
            lines.map((line, i) => (
              <div
                key={`${i}-${line.slice(0, 24)}`}
                className={`whitespace-pre-wrap break-all hover:bg-zinc-900/40 px-1 py-0.5 rounded font-mono ${lineTone(line)}`}
              >
                <span className="mr-3 select-none text-[var(--desk-ink-faint)] opacity-40">
                  {String(i + 1).padStart(3, " ")}
                </span>
                <span>{line}</span>
              </div>
            ))
          )}
        </div>
        )}
      </aside>
    </div>
  );
}
