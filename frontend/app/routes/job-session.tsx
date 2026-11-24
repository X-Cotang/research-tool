import { useEffect, useRef, useState } from "react";
import { Link, useNavigate, useParams } from "react-router";

import { Markdown } from "~/components/Markdown";
import { WorkerTranscript } from "~/components/WorkerTranscript";
import {
  fetchJob,
  followUpJob,
  streamJobLogs,
  type Job,
  type JobFollowup,
  type JobStreamEvent,
  type Project,
} from "~/lib/api";
import { Spinner, StatusBadge } from "~/lib/ui";

function logLines(log: string | undefined): string[] {
  if (!log) return [];
  return log.split("\n").filter((line) => line.trim().length > 0);
}

function currentStep(lines: string[], job: Job | null): string {
  if (job?.status === "error" && job.error_step) return job.error_step;
  for (let i = lines.length - 1; i >= 0; i -= 1) {
    const match = /^\[step:([a-z0-9_-]+)\]/i.exec(lines[i]);
    if (match) return match[1];
  }
  if (job?.error_step) return job.error_step;
  return job?.status === "queued" ? "queued" : "starting";
}

function isNearBottom(el: HTMLElement) {
  return el.scrollHeight - el.scrollTop - el.clientHeight < 80;
}

export default function JobSessionPage() {
  const { id } = useParams();
  const navigate = useNavigate();
  const jobId = Number(id);
  const [job, setJob] = useState<Job | null>(null);
  const [project, setProject] = useState<Project | null>(null);
  const [followups, setFollowups] = useState<JobFollowup[]>([]);
  const [lines, setLines] = useState<string[]>([]);
  const [tab, setTab] = useState<"session" | "log" | "report">("session");
  const [note, setNote] = useState("");
  const [sending, setSending] = useState(false);
  const [notice, setNotice] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const scrollerRef = useRef<HTMLDivElement>(null);
  const stickRef = useRef(true);

  useEffect(() => {
    if (!jobId) return;
    stickRef.current = true;
    const ac = new AbortController();
    let stopped = false;

    const apply = (nextJob: Job, nextProject?: Project, nextFollowups?: JobFollowup[]) => {
      setJob(nextJob);
      if (nextProject) setProject(nextProject);
      if (nextFollowups) setFollowups(nextFollowups);
      setLines(logLines(nextJob.log));
    };

    fetchJob(jobId)
      .then((snap) => {
        if (!stopped) apply(snap.job, snap.project, snap.followups ?? []);
      })
      .catch((err) => {
        if (!stopped) setError(err instanceof Error ? err.message : "Could not load this job.");
      });

    const stopStream = streamJobLogs(
      jobId,
      (ev: JobStreamEvent) => {
        if (ev.type === "snapshot") {
          const next = ev.job as Job | undefined;
          if (next) apply(next, ev.project as Project | undefined, (ev.followups as JobFollowup[]) ?? undefined);
          return;
        }
        if (ev.type === "log" && ev.line) {
          setLines((prev) => [...prev, ev.line as string]);
        } else if (ev.type === "status" || ev.type === "done") {
          setJob((prev) =>
            prev
              ? {
                  ...prev,
                  status: typeof ev.status === "string" ? ev.status : prev.status,
                  error: typeof ev.error === "string" ? ev.error : prev.error,
                  error_step: typeof ev.error_step === "string" ? ev.error_step : prev.error_step,
                  cli_activity:
                    typeof ev.cli_activity === "string" ? ev.cli_activity : prev.cli_activity,
                  cli_session_id:
                    typeof ev.cli_session_id === "string" ? ev.cli_session_id : prev.cli_session_id,
                  report: typeof ev.report === "string" ? ev.report : prev.report,
                }
              : prev,
          );
          if (ev.type === "done") {
            fetchJob(jobId)
              .then((snap) => {
                if (!stopped) apply(snap.job, snap.project, snap.followups ?? []);
              })
              .catch(() => {});
          }
        }
      },
      ac.signal,
    );

    return () => {
      stopped = true;
      ac.abort();
      stopStream();
    };
  }, [jobId]);

  useEffect(() => {
    const el = scrollerRef.current;
    if (!el || tab === "report" || !stickRef.current) return;
    el.scrollTop = el.scrollHeight;
  }, [lines, tab]);

  async function onFollowUp(e: React.FormEvent) {
    e.preventDefault();
    const message = note.trim();
    if (!message || sending) return;
    setSending(true);
    setError(null);
    setNotice(null);
    try {
      const result = await followUpJob(jobId, message);
      setNote("");
      if (result.job_id && result.job_id !== jobId) {
        navigate(`/jobs/${result.job_id}`);
        return;
      }
      setNotice(
        result.detail ??
          "Queued. The running CLI cannot take this note until the current turn finishes.",
      );
      const snap = await fetchJob(jobId);
      setFollowups(snap.followups ?? []);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not send the follow-up.");
    } finally {
      setSending(false);
    }
  }

  const step = currentStep(lines, job);
  const report = job?.report || "";
  const active = job?.status === "queued" || job?.status === "running";

  return (
    <div className="flex flex-col gap-3">
      <div className="flex flex-wrap items-center justify-between gap-3 border-b border-[var(--desk-border-subtle)] pb-3">
        <div>
          <div className="flex items-center gap-2">
            <h1 className="font-display text-base font-semibold text-[var(--desk-ink)]">
              Worker session #{jobId || "—"}
            </h1>
            {job ? <StatusBadge status={job.status} /> : <Spinner />}
          </div>
          <p className="mt-1 font-mono text-[11px] text-[var(--desk-ink-faint)]">
            {project ? (
              <Link to={`/projects/${project.id}`} className="text-[var(--desk-accent)] hover:underline">
                {project.full_name}
              </Link>
            ) : (
              "Loading repository"
            )}
            {" · "}step {step}
            {job?.cli_activity ? ` · ${job.cli_activity}` : ""}
          </p>
          {job?.cli_session_id ? (
            <p className="mt-1 font-mono text-[11px] text-[var(--desk-ink-faint)]">
              session {job.cli_session_id}
            </p>
          ) : null}
        </div>
      </div>

      <div className="rounded-lg border border-[var(--desk-border)] bg-[var(--desk-surface)] px-4 py-3 text-xs text-[var(--desk-ink-muted)]">
        Session shows the worker the way a chat does: its writing, and each tool on its own row.
        Raw log keeps every line, including git and semgrep. The process still exits when the turn
        finishes. Next turn resumes the saved session.
      </div>

      {error ? <p className="text-xs text-[var(--desk-danger)]">{error}</p> : null}
      {notice ? <p className="text-xs text-[var(--desk-ink-muted)]">{notice}</p> : null}

      <div className="desk-panel flex h-[min(640px,calc(100dvh-22rem))] min-h-[280px] flex-col overflow-hidden">
        <div className="flex gap-2 border-b border-[var(--desk-border-subtle)] px-4 py-2">
          <button type="button" className="desk-btn desk-btn-ghost desk-btn-xs font-mono" onClick={() => setTab("session")}>
            Session
          </button>
          <button type="button" className="desk-btn desk-btn-ghost desk-btn-xs font-mono" onClick={() => setTab("log")}>
            Raw log ({lines.length})
          </button>
          <button type="button" className="desk-btn desk-btn-ghost desk-btn-xs font-mono" onClick={() => setTab("report")}>
            Result {report ? "" : "(empty)"}
          </button>
        </div>
        {tab === "report" ? (
          <div className="flex-1 overflow-auto p-4 text-xs">
            {report ? <Markdown content={report} /> : <p className="text-[var(--desk-ink-faint)]">No report yet.</p>}
          </div>
        ) : tab === "session" ? (
          <div
            ref={scrollerRef}
            className="min-h-0 flex-1 overflow-auto p-4"
            onScroll={(e) => {
              stickRef.current = isNearBottom(e.currentTarget);
            }}
          >
            <WorkerTranscript lines={lines} active={active} />
          </div>
        ) : (
          <div
            ref={scrollerRef}
            className="min-h-0 flex-1 overflow-auto bg-[#030304] p-4 font-mono text-[11px] leading-relaxed text-[#d4d4d8]"
            onScroll={(e) => {
              stickRef.current = isNearBottom(e.currentTarget);
            }}
          >
            {lines.length === 0 ? (
              <p className="text-[var(--desk-ink-faint)]">
                {active ? "Waiting for the worker to print its first step." : "No log lines were captured."}
              </p>
            ) : (
              lines.map((line, i) => (
                <div key={`${i}-${line.slice(0, 24)}`} className="whitespace-pre-wrap break-all py-0.5">
                  <span className="mr-3 select-none text-[var(--desk-ink-faint)] opacity-40">
                    {String(i + 1).padStart(3, " ")}
                  </span>
                  {line}
                </div>
              ))
            )}
          </div>
        )}
      </div>

      {followups.length > 0 ? (
        <ul className="space-y-1 text-xs text-[var(--desk-ink-muted)]">
          {followups.map((item) => (
            <li key={item.id}>Waiting for the next turn: {item.message}</li>
          ))}
        </ul>
      ) : null}

      <form onSubmit={(e) => void onFollowUp(e)} className="flex items-end gap-2">
        <textarea
          className="desk-input min-h-[64px] flex-1 font-sans text-sm"
          value={note}
          onChange={(e) => setNote(e.target.value)}
          placeholder="Ask the worker to look at a specific sink, file, or bug class on the next turn."
          disabled={sending}
        />
        <button type="submit" className="desk-btn desk-btn-primary" disabled={sending || !note.trim()}>
          {sending ? <Spinner /> : null}
          Next turn
        </button>
      </form>
    </div>
  );
}
