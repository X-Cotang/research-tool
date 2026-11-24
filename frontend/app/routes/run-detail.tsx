import { useEffect, useState } from "react";
import { Link, useParams } from "react-router";
import {
  ArrowLeft,
  Calendar,
  CheckCircle2,
  Clock,
  FolderGit2,
  Layers,
  MessageSquare,
  PlaySquare,
  Terminal,
} from "lucide-react";

import { JobLogDrawer } from "~/components/JobLogDrawer";
import { fetchRun, type Run, type RunTask } from "~/lib/api";
import { PageHeader, Panel, Spinner, StatusBadge } from "~/lib/ui";

const columns = [
  { id: "queued", label: "Queued", color: "text-amber-400" },
  { id: "running", label: "Running", color: "text-sky-400" },
  { id: "done", label: "Completed", color: "text-emerald-400" },
  { id: "error", label: "Failed", color: "text-red-400" },
] as const;

export default function RunDetailPage() {
  const { id } = useParams();
  const runId = Number(id);
  const [run, setRun] = useState<Run | null>(null);
  const [loading, setLoading] = useState(true);
  const [jobDrawerId, setJobDrawerId] = useState<number | null>(null);

  useEffect(() => {
    if (!runId) return;
    fetchRun(runId)
      .then((r) => setRun(r.run))
      .finally(() => setLoading(false));
  }, [runId]);

  if (loading) {
    return (
      <div className="flex justify-center py-24">
        <Spinner />
      </div>
    );
  }

  if (!run) {
    return <p className="text-[var(--desk-danger)] font-mono">Run #{runId} not found.</p>;
  }

  const tasks = run.tasks ?? [];
  const taskState = (task: RunTask) =>
    (task.job_status || task.status || "queued").toLowerCase();
  const byStatus = (status: string) => tasks.filter((t) => taskState(t) === status);

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between border-b border-[var(--desk-border-subtle)] pb-4">
        <div className="flex items-center gap-3">
          <Link
            to="/runs"
            className="flex h-8 w-8 items-center justify-center rounded-md border border-[var(--desk-border)] bg-[var(--desk-surface-2)] text-[var(--desk-ink-muted)] hover:text-[var(--desk-ink)]"
          >
            <ArrowLeft className="h-4 w-4" />
          </Link>
          <div>
            <div className="flex items-center gap-2">
              <h1 className="font-display text-lg font-semibold tracking-tight text-[var(--desk-ink)]">
                Batch Run #{run.id}
              </h1>
              <StatusBadge status={run.status} />
            </div>
            <p className="font-mono text-[11px] text-[var(--desk-ink-faint)]">
              {tasks.length} targeted repositories in this research run
            </p>
          </div>
        </div>

        {run.conversation_id && (
          <Link
            to={`/chat/${run.conversation_id}`}
            className="desk-btn desk-btn-ghost desk-btn-sm font-mono text-xs"
          >
            <MessageSquare className="h-3.5 w-3.5" />
            <span>Open Origin Session #{run.conversation_id}</span>
          </Link>
        )}
      </div>

      {/* Plan Details Card */}
      <Panel>
        <div className="mb-3 font-mono text-xs font-semibold uppercase tracking-wider text-[var(--desk-ink-muted)]">
          Execution Parameters & Timestamps
        </div>
        <div className="grid grid-cols-2 gap-4 text-xs font-mono sm:grid-cols-4">
          <div className="rounded border border-[var(--desk-border-subtle)] bg-[#070709] p-3">
            <span className="text-[var(--desk-ink-faint)] block text-[10px] uppercase">Started</span>
            <span className="text-[var(--desk-ink)] font-medium mt-1 block">
              {run.created_at ? new Date(run.created_at).toLocaleString() : "—"}
            </span>
          </div>
          <div className="rounded border border-[var(--desk-border-subtle)] bg-[#070709] p-3">
            <span className="text-[var(--desk-ink-faint)] block text-[10px] uppercase">Finished</span>
            <span className="text-[var(--desk-ink)] font-medium mt-1 block">
              {run.finished_at ? new Date(run.finished_at).toLocaleString() : "Running or Pending"}
            </span>
          </div>
          <div className="rounded border border-[var(--desk-border-subtle)] bg-[#070709] p-3">
            <span className="text-[var(--desk-ink-faint)] block text-[10px] uppercase">Total Tasks</span>
            <span className="text-[var(--desk-ink)] font-medium mt-1 block">{tasks.length}</span>
          </div>
          <div className="rounded border border-[var(--desk-border-subtle)] bg-[#070709] p-3">
            <span className="text-[var(--desk-ink-faint)] block text-[10px] uppercase">State</span>
            <span className="text-[var(--desk-ink)] font-medium mt-1 block uppercase">
              {run.status}
            </span>
          </div>
        </div>

        {run.plan && typeof run.plan === "object" ? (
          <div className="mt-4">
            <span className="font-mono text-[10px] uppercase text-[var(--desk-ink-faint)] block mb-1">
              AI Master Plan Structure:
            </span>
            <pre className="max-h-40 overflow-auto rounded border border-[var(--desk-border-subtle)] bg-[#070709] p-3 text-xs font-mono text-zinc-300">
              {JSON.stringify(run.plan, null, 2)}
            </pre>
          </div>
        ) : null}
      </Panel>

      {/* Kanban Task Columns */}
      <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-4">
        {columns.map((col) => {
          const items = byStatus(col.id);
          return (
            <div
              key={col.id}
              className="flex min-h-[160px] flex-col rounded-lg border border-[var(--desk-border)] bg-[var(--desk-surface)] p-3.5"
            >
              <div className="mb-3 flex items-center justify-between border-b border-[var(--desk-border-subtle)] pb-2 font-mono text-xs">
                <span className={`font-semibold uppercase ${col.color}`}>
                  {col.label}
                </span>
                <span className="rounded bg-[var(--desk-surface-2)] px-1.5 py-0.5 text-[10px] text-[var(--desk-ink-muted)]">
                  {items.length}
                </span>
              </div>

              <div className="flex-1 space-y-2">
                {items.length === 0 ? (
                  <p className="py-6 text-center font-mono text-xs text-[var(--desk-ink-faint)]">
                    —
                  </p>
                ) : (
                  items.map((t) => (
                    <TaskCard key={t.id} task={t} onOpenJob={setJobDrawerId} />
                  ))
                )}
              </div>
            </div>
          );
        })}
      </div>
      <JobLogDrawer
        jobId={jobDrawerId}
        open={jobDrawerId !== null}
        onClose={() => setJobDrawerId(null)}
      />
    </div>
  );
}

function TaskCard({
  task,
  onOpenJob,
}: {
  task: RunTask;
  onOpenJob: (jobId: number) => void;
}) {
  return (
    <div className="rounded-md border border-[var(--desk-border-subtle)] bg-[#070709] p-3 text-xs transition-colors hover:border-zinc-700">
      <Link
        to={`/projects/${task.project_id}`}
        className="font-mono font-medium text-[var(--desk-ink)] hover:underline flex items-center gap-1.5"
      >
        <FolderGit2 className="h-3.5 w-3.5 text-[var(--desk-ink-faint)] shrink-0" />
        <span className="truncate">{task.full_name || `Project #${task.project_id}`}</span>
      </Link>
      {task.job_id ? (
        <div className="mt-2 flex items-center justify-between gap-2 font-mono text-[10px] text-[var(--desk-ink-faint)]">
          <button
            type="button"
            className="text-[var(--desk-accent)] hover:underline"
            onClick={() => onOpenJob(task.job_id as number)}
          >
            Job #{task.job_id} logs
          </button>
          <Link to={`/jobs/${task.job_id}`} className="text-[var(--desk-accent)] hover:underline">
            Session
          </Link>
          <StatusBadge status={task.job_status || task.status} />
        </div>
      ) : null}
      {task.job_error ? (
        <p className="mt-2 whitespace-pre-wrap break-words text-[11px] text-red-300">
          {task.job_error_step ? `Step ${task.job_error_step}: ` : ""}
          {task.job_error}
        </p>
      ) : null}
    </div>
  );
}
