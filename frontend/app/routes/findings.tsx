import { useEffect, useState } from "react";
import { Link } from "react-router";
import {
  AlertTriangle,
  CheckCircle2,
  Filter,
  FolderGit2,
  Search,
  Shield,
  ShieldAlert,
  Sparkles,
} from "lucide-react";

import { fetchFindings, patchFinding, type Finding } from "~/lib/api";
import { PageHeader, Panel, SeverityBadge, Spinner, StatCard } from "~/lib/ui";

export default function FindingsPage() {
  const [findings, setFindings] = useState<Finding[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [filterSeverity, setFilterSeverity] = useState<string>("all");
  const [filterStatus, setFilterStatus] = useState<string>("all");
  const [search, setSearch] = useState("");

  useEffect(() => {
    fetchFindings()
      .then((r) => setFindings(r.findings))
      .catch((e) => setError(e instanceof Error ? e.message : "Load failed"))
      .finally(() => setLoading(false));
  }, []);

  async function onStatusChange(id: number, status: string) {
    const res = await patchFinding(id, { status });
    setFindings((prev) => prev.map((f) => (f.id === id ? res.finding : f)));
  }

  const criticalCount = findings.filter(
    (f) => (f.severity || "").toLowerCase() === "critical",
  ).length;
  const highCount = findings.filter(
    (f) => (f.severity || "").toLowerCase() === "high",
  ).length;
  const confirmedCount = findings.filter(
    (f) => (f.status || "").toLowerCase() === "confirmed",
  ).length;

  const filtered = findings.filter((f) => {
    if (
      filterSeverity !== "all" &&
      (f.severity || "").toLowerCase() !== filterSeverity
    )
      return false;
    if (filterStatus !== "all" && (f.status || "").toLowerCase() !== filterStatus)
      return false;
    if (search.trim()) {
      const q = search.toLowerCase();
      const matchTitle = (f.title || "").toLowerCase().includes(q);
      const matchProject = (f.full_name || "").toLowerCase().includes(q);
      if (!matchTitle && !matchProject) return false;
    }
    return true;
  });

  return (
    <div className="space-y-6">
      <PageHeader
        title="Vulnerability Findings"
        subtitle="Parsed security flaw candidates extracted from external CLI research notes across repositories"
      />

      {error ? <p className="mb-4 text-xs text-[var(--desk-danger)]">{error}</p> : null}

      {/* Metrics Row */}
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <StatCard
          label="Total Findings"
          value={findings.length}
          subtext="Vulnerabilities in triage database"
          icon={Shield}
        />
        <StatCard
          label="Critical Severity"
          value={criticalCount}
          subtext="Immediate RCE / Injection flaws"
          icon={ShieldAlert}
        />
        <StatCard
          label="High Severity"
          value={highCount}
          subtext="Significant exploitability"
          icon={AlertTriangle}
        />
        <StatCard
          label="Confirmed"
          value={confirmedCount}
          subtext="Verified authentic issues"
          icon={CheckCircle2}
        />
      </div>

      {/* Filters and Search Bar */}
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex flex-wrap items-center gap-2">
          <div className="relative">
            <Search className="absolute left-3 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-[var(--desk-ink-faint)]" />
            <input
              className="desk-input pl-8 text-xs font-mono max-w-xs"
              placeholder="Search findings or repos…"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
            />
          </div>

          <div className="flex items-center gap-1.5 rounded-md border border-[var(--desk-border)] bg-[var(--desk-surface-2)] px-2 py-1 text-xs">
            <span className="font-mono text-[10px] text-[var(--desk-ink-faint)] uppercase">
              Severity:
            </span>
            <select
              className="bg-transparent font-mono text-xs text-[var(--desk-ink)] focus:outline-none"
              value={filterSeverity}
              onChange={(e) => setFilterSeverity(e.target.value)}
            >
              <option value="all" className="bg-[#0e0e11]">All</option>
              <option value="critical" className="bg-[#0e0e11]">Critical</option>
              <option value="high" className="bg-[#0e0e11]">High</option>
              <option value="medium" className="bg-[#0e0e11]">Medium</option>
              <option value="low" className="bg-[#0e0e11]">Low</option>
            </select>
          </div>

          <div className="flex items-center gap-1.5 rounded-md border border-[var(--desk-border)] bg-[var(--desk-surface-2)] px-2 py-1 text-xs">
            <span className="font-mono text-[10px] text-[var(--desk-ink-faint)] uppercase">
              Status:
            </span>
            <select
              className="bg-transparent font-mono text-xs text-[var(--desk-ink)] focus:outline-none"
              value={filterStatus}
              onChange={(e) => setFilterStatus(e.target.value)}
            >
              <option value="all" className="bg-[#0e0e11]">All</option>
              <option value="open" className="bg-[#0e0e11]">Open</option>
              <option value="confirmed" className="bg-[#0e0e11]">Confirmed</option>
              <option value="false_positive" className="bg-[#0e0e11]">False Positive</option>
              <option value="fixed" className="bg-[#0e0e11]">Fixed</option>
            </select>
          </div>
        </div>

        <div className="font-mono text-xs text-[var(--desk-ink-faint)]">
          Showing {filtered.length} of {findings.length} findings
        </div>
      </div>

      {/* Findings Table */}
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
                  <th>Vulnerability Title</th>
                  <th>Severity</th>
                  <th>Triage Status</th>
                  <th>Target Project</th>
                  <th>Triage Action</th>
                </tr>
              </thead>
              <tbody>
                {filtered.length === 0 ? (
                  <tr>
                    <td colSpan={5} className="py-12 text-center text-xs text-[var(--desk-ink-muted)]">
                      <Shield className="mx-auto mb-2 h-6 w-6 text-zinc-600" />
                      <p className="font-mono">No findings match the current filters.</p>
                    </td>
                  </tr>
                ) : (
                  filtered.map((f) => (
                    <tr key={f.id}>
                      <td className="max-w-md">
                        <span className="font-mono text-xs font-medium text-[var(--desk-ink)] block truncate">
                          {f.title ?? "Untitled Vulnerability"}
                        </span>
                      </td>
                      <td>
                        <SeverityBadge severity={f.severity} />
                      </td>
                      <td>
                        <span className="badge badge-neutral font-mono text-[10px] uppercase">
                          {f.status ?? "open"}
                        </span>
                      </td>
                      <td>
                        <Link
                          to={`/projects/${f.project_id}`}
                          className="flex items-center gap-1.5 font-mono text-xs text-[var(--desk-ink-muted)] hover:text-[var(--desk-ink)] hover:underline"
                        >
                          <FolderGit2 className="h-3 w-3 text-[var(--desk-ink-faint)]" />
                          <span>#{f.project_id}</span>
                          {f.full_name ? <span className="text-zinc-400">· {f.full_name}</span> : ""}
                        </Link>
                      </td>
                      <td>
                        <select
                          className="desk-input w-auto py-1 font-mono text-xs"
                          value={f.status ?? "open"}
                          onChange={(e) => void onStatusChange(f.id, e.target.value)}
                        >
                          <option value="open">Open</option>
                          <option value="confirmed">Confirmed</option>
                          <option value="false_positive">False Positive</option>
                          <option value="fixed">Fixed</option>
                        </select>
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
