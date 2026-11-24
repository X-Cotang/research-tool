import { useEffect, useState } from "react";
import { Link } from "react-router";
import {
  Calendar,
  Layers,
  MessageSquare,
  PlaySquare,
  Sparkles,
} from "lucide-react";

import { fetchRuns, type Run } from "~/lib/api";
import { PageHeader, Panel, Spinner, StatCard, StatusBadge } from "~/lib/ui";

export default function RunsPage() {
  const [runs, setRuns] = useState<Run[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    fetchRuns()
      .then((r) => setRuns(r.runs))
      .finally(() => setLoading(false));
  }, []);

  const activeRuns = runs.filter(
    (r) => ["running", "queued"].includes((r.status || "").toLowerCase()),
  ).length;

  return (
    <div className="space-y-6">
      <PageHeader
        title="Batch Research Runs"
        subtitle="Multi-project automated vulnerability assessment batches managed by the AI Master"
      />

      {/* Metrics Row */}
      <div className="grid gap-4 sm:grid-cols-3">
        <StatCard
          label="Total Runs"
          value={runs.length}
          subtext="Historical batch executions"
          icon={Layers}
        />
        <StatCard
          label="Active Runs"
          value={activeRuns}
          subtext="Currently processing targets"
          icon={PlaySquare}
        />
        <StatCard
          label="Master Sync"
          value="Automated"
          subtext="Summarizes directly into chat"
          icon={Sparkles}
        />
      </div>

      <Panel>
        {loading ? (
          <div className="flex justify-center py-12">
            <Spinner />
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="desk-table">
              <thead>
                <tr>
                  <th>Batch Run ID</th>
                  <th>Execution Status</th>
                  <th>Created At</th>
                  <th>Conversation Origin</th>
                  <th>Action</th>
                </tr>
              </thead>
              <tbody>
                {runs.length === 0 ? (
                  <tr>
                    <td colSpan={5} className="py-12 text-center text-xs text-[var(--desk-ink-muted)]">
                      <PlaySquare className="mx-auto mb-2 h-6 w-6 text-zinc-600" />
                      <p className="font-mono">No batch runs queued yet.</p>
                      <p className="mt-1 font-mono text-[11px] text-[var(--desk-ink-faint)]">
                        Ask the AI Master to "queue a research batch for top projects" to start a run.
                      </p>
                    </td>
                  </tr>
                ) : (
                  runs.map((run) => (
                    <tr key={run.id}>
                      <td>
                        <Link
                          to={`/runs/${run.id}`}
                          className="font-mono font-medium text-[var(--desk-ink)] hover:text-white hover:underline flex items-center gap-1.5"
                        >
                          <PlaySquare className="h-3.5 w-3.5 text-[var(--desk-ink-faint)]" />
                          <span>Run #{run.id}</span>
                        </Link>
                      </td>
                      <td>
                        <StatusBadge status={run.status} />
                      </td>
                      <td className="font-mono text-xs text-[var(--desk-ink-muted)]">
                        {run.created_at ? new Date(run.created_at).toLocaleString() : "—"}
                      </td>
                      <td>
                        {run.conversation_id ? (
                          <Link
                            to={`/chat/${run.conversation_id}`}
                            className="flex items-center gap-1.5 font-mono text-xs text-[var(--desk-ink-muted)] hover:text-[var(--desk-ink)] hover:underline"
                          >
                            <MessageSquare className="h-3 w-3 text-[var(--desk-ink-faint)]" />
                            <span>Session #{run.conversation_id}</span>
                          </Link>
                        ) : (
                          <span className="font-mono text-xs text-[var(--desk-ink-faint)]">Manual API</span>
                        )}
                      </td>
                      <td>
                        <Link
                          to={`/runs/${run.id}`}
                          className="desk-btn desk-btn-ghost desk-btn-xs font-mono"
                        >
                          View Details →
                        </Link>
                      </td>
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </div>
        )}
      </Panel>
    </div>
  );
}
