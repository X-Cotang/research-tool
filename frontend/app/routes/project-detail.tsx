import { useEffect, useState } from "react";
import { Link, useNavigate, useParams } from "react-router";

import { JobLogDrawer } from "~/components/JobLogDrawer";
import { Markdown } from "~/components/Markdown";
import {
  deleteProject,
  fetchFindings,
  fetchProject,
  fetchStatus,
  parseProjectFindings,
  patchFinding,
  patchProject,
  startResearch,
  type Finding,
  type Job,
  type Project,
  type ResearchPreset,
} from "~/lib/api";
import {
  isFalsePositive,
  isOnDisk,
  isReported,
  isSkipped,
  projectStatus,
} from "~/lib/projectStatus";
import { PageHeader, Panel, ProjectStatusBadge, SeverityBadge, Spinner } from "~/lib/ui";

export default function ProjectDetailPage() {
  const { id } = useParams();
  const navigate = useNavigate();
  const projectId = Number(id);
  const [project, setProject] = useState<Project | null>(null);
  const [jobs, setJobs] = useState<Job[]>([]);
  const [findings, setFindings] = useState<Finding[]>([]);
  const [presets, setPresets] = useState<ResearchPreset[]>([]);
  const [preset, setPreset] = useState("");
  const [command, setCommand] = useState("");
  const [loading, setLoading] = useState(true);
  const [researching, setResearching] = useState(false);
  const [parsing, setParsing] = useState(false);
  const [busy, setBusy] = useState(false);
  const [jobDrawerId, setJobDrawerId] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);

  async function reload() {
    if (!projectId) return;
    const [detail, f, st] = await Promise.all([
      fetchProject(projectId),
      fetchFindings(projectId),
      fetchStatus(),
    ]);
    setProject(detail.project);
    setJobs(detail.jobs);
    setFindings(f.findings);
    setPresets(st.research_presets);
    setPreset(st.research_preset);
    setCommand((c) => c || st.research_command);
  }

  useEffect(() => {
    if (!projectId) return;
    setLoading(true);
    reload()
      .catch((e) => setError(e instanceof Error ? e.message : "Load failed"))
      .finally(() => setLoading(false));
  }, [projectId]);

  function applyPreset(presetId: string) {
    setPreset(presetId);
    const p = presets.find((x) => x.id === presetId);
    if (p?.command) setCommand(p.command);
  }

  async function onResearch(e: React.FormEvent) {
    e.preventDefault();
    setResearching(true);
    setError(null);
    try {
      const res = await startResearch(projectId, command);
      setJobDrawerId(res.job.id);
      setMessage("Research job started.");
      await reload();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Research failed");
    } finally {
      setResearching(false);
    }
  }

  async function onParseFindings() {
    setParsing(true);
    try {
      await parseProjectFindings(projectId);
      const f = await fetchFindings(projectId);
      setFindings(f.findings);
      setMessage("Findings parsed from research notes.");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Parse failed");
    } finally {
      setParsing(false);
    }
  }

  async function onFindingStatus(findingId: number, status: string) {
    const res = await patchFinding(findingId, { status });
    setFindings((prev) => prev.map((f) => (f.id === findingId ? res.finding : f)));
  }

  async function onPatch(body: {
    skipped?: boolean;
    reported?: boolean;
    false_positive?: boolean;
  }) {
    setBusy(true);
    setError(null);
    try {
      const res = await patchProject(projectId, body);
      setProject(res.project);
      if (body.skipped !== undefined) {
        setMessage(body.skipped ? "Marked skipped." : "Unskipped.");
      } else if (body.reported) {
        setMessage("Marked reported — moved to Library History.");
      } else if (body.false_positive) {
        setMessage("Marked false positive — moved to Library History.");
      } else {
        setMessage("Project flags updated.");
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Update failed");
    } finally {
      setBusy(false);
    }
  }

  async function onDelete(mode: "clone" | "full") {
    const label =
      mode === "clone"
        ? "Remove the local clone (keep library entry and reports)?"
        : "Permanently delete this project, clone, and reports?";
    if (!window.confirm(label)) return;
    setBusy(true);
    try {
      const res = await deleteProject(projectId, mode);
      setMessage(res.message ?? "Done.");
      if (mode === "full") {
        navigate("/projects");
        return;
      }
      await reload();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Delete failed");
    } finally {
      setBusy(false);
    }
  }

  if (loading) {
    return (
      <div className="flex justify-center py-16">
        <Spinner />
      </div>
    );
  }

  if (!project) {
    return <p className="text-[var(--desk-danger)]">Project not found.</p>;
  }

  const st = projectStatus(project);

  return (
    <div>
      <PageHeader
        title={project.full_name}
        subtitle={project.description ?? undefined}
        actions={
          <div className="flex flex-wrap gap-2">
            <Link
              to={`/projects?org=${encodeURIComponent(project.full_name.split("/")[0] || "")}`}
              className="desk-btn desk-btn-ghost text-sm"
            >
              ← Projects
            </Link>
            <ProjectStatusBadge statusKey={st.key} label={st.label} />
          </div>
        }
      />

      {error ? <p className="mb-4 text-sm text-[var(--desk-danger)]">{error}</p> : null}
      {message ? <p className="mb-4 text-sm text-[var(--desk-success)]">{message}</p> : null}

      <Panel className="mb-6">
        <h2 className="mb-3 text-sm font-semibold uppercase tracking-wide text-[var(--desk-ink-muted)]">
          Mark & manage
        </h2>
        <div className="flex flex-wrap gap-2">
          <button
            type="button"
            className="desk-btn desk-btn-ghost"
            disabled={busy}
            onClick={() => void onPatch({ skipped: !isSkipped(project) })}
          >
            {isSkipped(project) ? "Unskip" : "Skip"}
          </button>
          <button
            type="button"
            className="desk-btn desk-btn-ghost"
            disabled={busy}
            onClick={() => void onPatch({ reported: !isReported(project) })}
          >
            {isReported(project) ? "Clear reported" : "Mark reported"}
          </button>
          <button
            type="button"
            className="desk-btn desk-btn-ghost"
            disabled={busy}
            onClick={() => void onPatch({ false_positive: !isFalsePositive(project) })}
          >
            {isFalsePositive(project) ? "Clear false positive" : "Mark false positive"}
          </button>
          <button
            type="button"
            className="desk-btn desk-btn-danger"
            disabled={busy || !isOnDisk(project)}
            onClick={() => void onDelete("clone")}
          >
            Remove clone
          </button>
          <button
            type="button"
            className="desk-btn desk-btn-danger"
            disabled={busy}
            onClick={() => void onDelete("full")}
          >
            Delete project
          </button>
        </div>
        <p className="mt-2 text-xs text-[var(--desk-ink-faint)]">
          Reported / false positive move the project into Library History. Skip hides it from
          default candidate lists.
        </p>
      </Panel>

      <div className="mb-6 grid gap-4 lg:grid-cols-2">
        <Panel>
          <h2 className="mb-2 text-sm font-semibold text-[var(--desk-ink-muted)]">Metadata</h2>
          <dl className="grid grid-cols-2 gap-x-4 gap-y-2 text-sm">
            <dt className="text-[var(--desk-ink-faint)]">Language</dt>
            <dd>{project.language ?? "—"}</dd>
            <dt className="text-[var(--desk-ink-faint)]">Stars</dt>
            <dd>{project.stars ?? 0}</dd>
            <dt className="text-[var(--desk-ink-faint)]">Score</dt>
            <dd>{project.research_score ?? "—"}</dd>
            <dt className="text-[var(--desk-ink-faint)]">On disk</dt>
            <dd>{isOnDisk(project) ? "Yes" : "No"}</dd>
            <dt className="text-[var(--desk-ink-faint)]">Local path</dt>
            <dd className="truncate font-mono text-xs">{project.local_path || "—"}</dd>
          </dl>
          {project.html_url ? (
            <a
              href={project.html_url}
              target="_blank"
              rel="noreferrer"
              className="mt-3 inline-block text-sm text-[var(--desk-accent)] hover:underline"
            >
              Open on GitHub
            </a>
          ) : null}
        </Panel>

        <Panel>
          <h2 className="mb-2 text-sm font-semibold text-[var(--desk-ink-muted)]">Recent jobs</h2>
          <ul className="space-y-1 text-sm">
            {jobs.length === 0 ? (
              <li className="text-[var(--desk-ink-muted)]">No jobs yet.</li>
            ) : (
              jobs.map((j) => (
                <li key={j.id} className="space-y-1">
                  <div className="flex items-center justify-between gap-2">
                    <Link to={`/jobs/${j.id}`} className="text-[var(--desk-accent)] hover:underline">
                      Job #{j.id}
                    </Link>
                    <button
                      type="button"
                      className="text-[var(--desk-accent)] hover:underline"
                      onClick={() => setJobDrawerId(j.id)}
                    >
                      <StatusFromJob status={j.status} />
                    </button>
                  </div>
                  {j.error ? (
                    <p className="text-xs text-[var(--desk-danger)]">
                      {j.error_step ? `Step ${j.error_step}: ` : ""}
                      {j.error}
                    </p>
                  ) : null}
                </li>
              ))
            )}
          </ul>
        </Panel>
      </div>

      {(project.last_report || project.notes) && (
        <Panel className="mb-6">
          {project.last_report ? (
            <div className="mb-4">
              <h2 className="mb-3 font-mono text-xs font-semibold uppercase tracking-wider text-[var(--desk-ink-muted)]">
                Research Notes / Assessment Report
              </h2>
              <div className="max-h-[500px] overflow-auto rounded-lg border border-[var(--desk-border-subtle)] bg-[#070709] p-4 text-xs">
                <Markdown content={project.last_report} />
              </div>
            </div>
          ) : null}
          {project.notes ? (
            <div>
              <h2 className="mb-2 font-mono text-xs font-semibold uppercase tracking-wider text-[var(--desk-ink-muted)]">
                Target Notes
              </h2>
              <div className="rounded-lg border border-[var(--desk-border-subtle)] bg-[#070709] p-4 text-xs">
                <Markdown content={project.notes} />
              </div>
            </div>
          ) : null}
        </Panel>
      )}

      <Panel className="mb-6">
        <h2 className="mb-3 text-sm font-semibold uppercase tracking-wide text-[var(--desk-ink-muted)]">
          Run research
        </h2>
        <form onSubmit={(e) => void onResearch(e)} className="space-y-3">
          <label className="block text-sm">
            Preset
            <select
              className="desk-input mt-1"
              value={preset}
              onChange={(e) => applyPreset(e.target.value)}
            >
              {presets.map((p) => (
                <option key={p.id} value={p.id} disabled={!p.available}>
                  {p.label}
                  {!p.available ? " (unavailable)" : ""}
                </option>
              ))}
            </select>
          </label>
          <label className="block text-sm">
            Command
            <textarea
              className="desk-input mt-1 min-h-[100px] font-mono text-xs"
              value={command}
              onChange={(e) => setCommand(e.target.value)}
            />
          </label>
          <button type="submit" className="desk-btn desk-btn-primary" disabled={researching}>
            {researching ? <Spinner /> : null}
            Start research
          </button>
        </form>
      </Panel>

      <Panel>
        <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
          <h2 className="text-sm font-semibold uppercase tracking-wide text-[var(--desk-ink-muted)]">
            Findings
          </h2>
          <button
            type="button"
            className="desk-btn desk-btn-ghost text-sm"
            disabled={parsing}
            onClick={() => void onParseFindings()}
          >
            {parsing ? <Spinner /> : null}
            Parse from report
          </button>
        </div>
        <div className="overflow-x-auto">
          <table className="desk-table">
            <thead>
              <tr>
                <th>Title</th>
                <th>Severity</th>
                <th>Location</th>
                <th>Status</th>
                <th>Actions</th>
              </tr>
            </thead>
            <tbody>
              {findings.length === 0 ? (
                <tr>
                  <td colSpan={5} className="py-6 text-center text-[var(--desk-ink-muted)]">
                    No findings parsed yet.
                  </td>
                </tr>
              ) : (
                findings.map((f) => (
                  <tr key={f.id}>
                    <td>
                      <div className="font-medium">{f.title ?? "Untitled"}</div>
                      {f.cwe ? (
                        <div className="text-xs text-[var(--desk-ink-faint)]">{f.cwe}</div>
                      ) : null}
                      {f.evidence ? (
                        <details className="mt-1 text-xs text-[var(--desk-ink-muted)]">
                          <summary className="cursor-pointer">Evidence</summary>
                          <pre className="mt-1 max-h-40 overflow-auto whitespace-pre-wrap font-mono">
                            {f.evidence}
                          </pre>
                        </details>
                      ) : null}
                    </td>
                    <td>
                      <SeverityBadge severity={f.severity} />
                    </td>
                    <td className="font-mono text-xs">
                      {f.file_path
                        ? `${f.file_path}${f.line_start != null ? `:${f.line_start}` : ""}`
                        : "—"}
                    </td>
                    <td>{f.status ?? "candidate"}</td>
                    <td>
                      <select
                        className="desk-input w-auto py-1 text-xs"
                        value={f.status ?? "candidate"}
                        onChange={(e) => void onFindingStatus(f.id, e.target.value)}
                      >
                        <option value="candidate">candidate</option>
                        <option value="confirmed">confirmed</option>
                        <option value="false_positive">false_positive</option>
                        <option value="reported">reported</option>
                      </select>
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </Panel>

      <JobLogDrawer
        jobId={jobDrawerId}
        open={jobDrawerId !== null}
        onClose={() => setJobDrawerId(null)}
      />
    </div>
  );
}

function StatusFromJob({ status }: { status?: string }) {
  return <span className="text-xs underline-offset-2">{status ?? "—"}</span>;
}
