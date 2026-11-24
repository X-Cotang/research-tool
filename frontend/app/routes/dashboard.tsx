import { useEffect, useState } from "react";
import { Link } from "react-router";
import {
  Activity,
  ArrowRight,
  Bot,
  Building2,
  FolderGit2,
  Play,
  Radar,
  Search,
  Sparkles,
  Star,
  Terminal,
} from "lucide-react";

import { GithubIcon } from "~/components/GithubIcon";

import {
  fetchLatest,
  fetchStatus,
  scanOrg,
  type LatestResponse,
  type StatusResponse,
} from "~/lib/api";
import { projectStatus } from "~/lib/projectStatus";
import { PageHeader, Panel, ProjectStatusBadge, Spinner, StatCard } from "~/lib/ui";

const sampleTargets = [
  "expressjs",
  "fastapi",
  "OWASP",
  "nestjs",
];

export default function Dashboard() {
  const [latest, setLatest] = useState<LatestResponse | null>(null);
  const [status, setStatus] = useState<StatusResponse | null>(null);
  const [orgUrl, setOrgUrl] = useState("");
  const [scanning, setScanning] = useState(false);
  const [scanMsg, setScanMsg] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    Promise.all([fetchLatest(), fetchStatus()])
      .then(([l, s]) => {
        setLatest(l);
        setStatus(s);
        if (l.organization?.html_url) setOrgUrl(l.organization.html_url);
        else if (l.organization?.login) setOrgUrl(`https://github.com/${l.organization.login}`);
      })
      .catch((e) => setError(e instanceof Error ? e.message : "Load failed"));
  }, []);

  const projects = latest?.projects ?? [];
  const runningJobs = projects.filter((p) =>
    ["running", "queued"].includes((p.research_status ?? "").toLowerCase()),
  ).length;

  async function onScan(e?: React.FormEvent, targetUrl?: string) {
    if (e) e.preventDefault();
    const target = (targetUrl || orgUrl).trim();
    if (!target) return;
    setScanning(true);
    setScanMsg(null);
    setError(null);
    try {
      const res = await scanOrg({ org_url: target, mode: "fresh" });
      setScanMsg(
        res.message ??
          `Added ${res.added_count ?? 0} projects for ${res.organization?.login || "target"}.`,
      );
      const l = await fetchLatest();
      setLatest(l);
      if (res.organization?.html_url) setOrgUrl(res.organization.html_url);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Scan failed");
    } finally {
      setScanning(false);
    }
  }

  return (
    <div className="space-y-6">
      <PageHeader
        title="Security Intelligence Desk"
        subtitle={
          status
            ? `Workspace: ${status.research_dir} · GitHub ${
                status.github_token ? "Token Active" : "Unauthenticated"
              } · CLI: ${status.research_preset || "command-code"}`
            : "Loading workspace status…"
        }
        actions={
          <div className="flex items-center gap-2">
            <Link to="/chat" className="desk-btn desk-btn-ghost">
              <Bot className="h-3.5 w-3.5 text-zinc-300" />
              <span>Ask AI Master</span>
            </Link>
            <Link to="/projects" className="desk-btn desk-btn-primary">
              <FolderGit2 className="h-3.5 w-3.5" />
              <span>View Library</span>
            </Link>
          </div>
        }
      />

      {error ? (
        <div className="rounded-md border border-red-500/30 bg-red-500/10 p-3 text-xs text-[var(--desk-danger)]">
          {error}
        </div>
      ) : null}

      {/* Metrics Row */}
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <StatCard
          label="Organizations"
          value={latest?.organizations.length ?? "—"}
          subtext="Target GitHub Orgs Scanned"
          icon={Building2}
        />
        <StatCard
          label="Target Repositories"
          value={projects.length}
          subtext="Current active organization"
          icon={FolderGit2}
        />
        <StatCard
          label="Active Research Jobs"
          value={runningJobs}
          subtext="CLI worker execution queue"
          icon={Activity}
        />
        <StatCard
          label="Total Scans Logged"
          value={latest?.scans.length ?? "—"}
          subtext="Historical discovery runs"
          icon={Radar}
        />
      </div>

      {/* Quick Scan & Recent Scans */}
      <div className="grid gap-6 lg:grid-cols-2">
        <Panel className="flex flex-col justify-between">
          <div>
            <div className="mb-3 flex items-center justify-between">
              <div className="flex items-center gap-2">
                <Radar className="h-4 w-4 text-[var(--desk-ink-faint)]" />
                <h2 className="font-mono text-xs font-semibold uppercase tracking-wider text-[var(--desk-ink-muted)]">
                  Target Reconnaissance
                </h2>
              </div>
              <span className="font-mono text-[10px] text-[var(--desk-ink-faint)]">
                GITHUB DISCOVERY
              </span>
            </div>

            <form onSubmit={(e) => void onScan(e)} className="space-y-3">
              <div>
                <label className="block text-xs font-medium text-[var(--desk-ink-muted)]">
                  Organization or User URL
                </label>
                <div className="mt-1 flex gap-2">
                  <div className="relative flex-1">
                    <Search className="absolute left-3 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-[var(--desk-ink-faint)]" />
                    <input
                      className="desk-input pl-8 text-xs font-mono"
                      value={orgUrl}
                      onChange={(e) => setOrgUrl(e.target.value)}
                      placeholder="https://github.com/expressjs or expressjs"
                      disabled={scanning}
                    />
                  </div>
                  <button
                    type="submit"
                    className="desk-btn desk-btn-primary shrink-0"
                    disabled={scanning || !orgUrl.trim()}
                  >
                    {scanning ? <Spinner /> : <Radar className="h-3.5 w-3.5" />}
                    <span>Scan Target</span>
                  </button>
                </div>
              </div>

              {/* Quick sample chips */}
              <div className="flex items-center gap-1.5 pt-1">
                <span className="font-mono text-[10px] text-[var(--desk-ink-faint)]">
                  Quick targets:
                </span>
                {sampleTargets.map((target) => (
                  <button
                    key={target}
                    type="button"
                    onClick={() => {
                      const url = `https://github.com/${target}`;
                      setOrgUrl(url);
                      void onScan(undefined, url);
                    }}
                    disabled={scanning}
                    className="rounded border border-[var(--desk-border)] bg-[var(--desk-surface-2)] px-2 py-0.5 font-mono text-[10px] text-[var(--desk-ink-muted)] transition-colors hover:border-[var(--desk-border-accent)] hover:text-[var(--desk-ink)]"
                  >
                    {target}
                  </button>
                ))}
              </div>

              {scanMsg ? (
                <div className="flex items-center justify-between rounded border border-emerald-500/30 bg-emerald-500/10 p-2 text-xs text-[var(--desk-success)]">
                  <span>{scanMsg}</span>
                  {latest?.organization?.login ? (
                    <Link
                      to={`/projects?org=${encodeURIComponent(latest.organization.login)}`}
                      className="font-medium underline hover:opacity-80"
                    >
                      Open Candidates →
                    </Link>
                  ) : null}
                </div>
              ) : null}
            </form>
          </div>

          <div className="mt-4 border-t border-[var(--desk-border-subtle)] pt-3 text-[11px] text-[var(--desk-ink-faint)]">
            <span className="font-mono">Tip:</span> AI Master can also scan orgs autonomously via prompt:{" "}
            <code className="rounded bg-[var(--desk-surface-2)] px-1 py-0.5 font-mono text-[10px] text-zinc-300">
              scan_org
            </code>
          </div>
        </Panel>

        {/* Recent Scans */}
        <Panel>
          <div className="mb-3 flex items-center justify-between">
            <div className="flex items-center gap-2">
              <Activity className="h-4 w-4 text-[var(--desk-ink-faint)]" />
              <h2 className="font-mono text-xs font-semibold uppercase tracking-wider text-[var(--desk-ink-muted)]">
                Recent Reconnaissance
              </h2>
            </div>
            <Link
              to={
                latest?.organization?.login
                  ? `/projects?org=${encodeURIComponent(latest.organization.login)}`
                  : "/projects"
              }
              className="flex items-center gap-1 font-mono text-xs text-[var(--desk-ink-muted)] transition-colors hover:text-[var(--desk-ink)]"
            >
              <span>All Candidates</span>
              <ArrowRight className="h-3 w-3" />
            </Link>
          </div>

          {!latest ? (
            <div className="flex justify-center py-8">
              <Spinner />
            </div>
          ) : latest.scans.length === 0 ? (
            <p className="py-8 text-center text-xs text-[var(--desk-ink-muted)] font-mono">
              No scans logged yet. Run a target scan above.
            </p>
          ) : (
            <ul className="divide-y divide-[var(--desk-border-subtle)]">
              {latest.scans.slice(0, 5).map((s) => (
                <li key={s.id} className="flex items-center justify-between py-2.5 text-xs">
                  <div className="flex items-center gap-2 min-w-0">
                    <GithubIcon className="h-3.5 w-3.5 shrink-0 text-[var(--desk-ink-faint)]" />
                    <span className="font-mono font-medium text-[var(--desk-ink)] truncate">
                      {s.org_login ?? s.org_url}
                    </span>
                  </div>
                  <div className="flex items-center gap-2 font-mono text-[11px]">
                    <span className="rounded bg-[var(--desk-surface-2)] px-1.5 py-0.5 text-[var(--desk-ink-muted)]">
                      +{s.added_count ?? s.result_count ?? 0} repos
                    </span>
                    <span className="text-[var(--desk-ink-faint)] uppercase">{s.mode}</span>
                  </div>
                </li>
              ))}
            </ul>
          )}
        </Panel>
      </div>

      {/* Top Projects Table */}
      <Panel>
        <div className="mb-4 flex items-center justify-between">
          <div>
            <h2 className="font-display text-sm font-semibold tracking-tight text-[var(--desk-ink)]">
              Top Scored Target Projects
            </h2>
            <p className="font-mono text-[11px] text-[var(--desk-ink-faint)]">
              Ranked by attack surface score, commit activity, language, and vulnerabilities
            </p>
          </div>
          <Link
            to="/projects"
            className="desk-btn desk-btn-ghost desk-btn-sm font-mono text-xs"
          >
            <span>View All ({projects.length})</span>
            <ArrowRight className="h-3 w-3" />
          </Link>
        </div>

        <div className="overflow-x-auto">
          <table className="desk-table">
            <thead>
              <tr>
                <th>Target Repository</th>
                <th>Language</th>
                <th>Stars</th>
                <th>Vulnerability Score</th>
                <th>Status</th>
                <th>Action</th>
              </tr>
            </thead>
            <tbody>
              {projects.length === 0 ? (
                <tr>
                  <td colSpan={6} className="py-8 text-center text-xs text-[var(--desk-ink-muted)]">
                    No repositories discovered in current organization.
                  </td>
                </tr>
              ) : (
                projects.slice(0, 10).map((p) => {
                  const st = projectStatus(p);
                  const score = p.research_score ?? 0;
                  const scorePct = Math.min(100, Math.round(score * 10));

                  return (
                    <tr key={p.id}>
                      <td>
                        <Link
                          to={`/projects/${p.id}`}
                          className="font-mono font-medium text-[var(--desk-ink)] hover:text-white hover:underline flex items-center gap-1.5"
                        >
                          <GithubIcon className="h-3.5 w-3.5 text-[var(--desk-ink-faint)]" />
                          <span>{p.full_name}</span>
                        </Link>
                      </td>
                      <td>
                        <span className="rounded bg-[var(--desk-surface-2)] px-2 py-0.5 font-mono text-[10px] text-zinc-300">
                          {p.language ?? "—"}
                        </span>
                      </td>
                      <td>
                        <span className="flex items-center gap-1 font-mono text-xs text-[var(--desk-ink-muted)]">
                          <Star className="h-3 w-3 text-amber-400" />
                          {p.stars ?? 0}
                        </span>
                      </td>
                      <td>
                        <div className="flex items-center gap-2">
                          <div className="h-1.5 w-16 overflow-hidden rounded-full bg-zinc-800">
                            <div
                              className="h-full rounded-full bg-zinc-200"
                              style={{ width: `${scorePct}%` }}
                            />
                          </div>
                          <span className="font-mono text-xs text-zinc-200">
                            {score.toFixed?.(1) ?? score}
                          </span>
                        </div>
                      </td>
                      <td>
                        <ProjectStatusBadge statusKey={st.key} label={st.label} />
                      </td>
                      <td>
                        <Link
                          to={`/projects/${p.id}`}
                          className="desk-btn desk-btn-ghost desk-btn-xs font-mono"
                        >
                          <Play className="h-2.5 w-2.5" />
                          <span>Inspect</span>
                        </Link>
                      </td>
                    </tr>
                  );
                })
              )}
            </tbody>
          </table>
        </div>
      </Panel>
    </div>
  );
}
