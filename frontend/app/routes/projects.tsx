import { useCallback, useEffect, useMemo, useState } from "react";
import { Link, useSearchParams } from "react-router";

import { JobLogDrawer } from "~/components/JobLogDrawer";
import {
  deleteProject,
  fetchLatest,
  fetchLibrary,
  fetchOrgs,
  fetchProjects,
  patchProject,
  researchRepo,
  scanOrg,
  startResearch,
  type Organization,
  type Project,
  type SearchCursor,
} from "~/lib/api";
import {
  isFalsePositive,
  isReported,
  isResearched,
  isSkipped,
  projectStatus,
} from "~/lib/projectStatus";
import { PageHeader, Panel, ProjectStatusBadge, Spinner } from "~/lib/ui";

const PAGE_SIZE = 25;
const FILTER_KEY = "research-tool-filters";
const VIEW_KEY = "research-tool-projects-view";

type Stage = "candidates" | "library";
type LibraryView = "active" | "history" | "all";

type DiscoveryFilters = {
  min_stars: number;
  max_age_days: number;
  created_within_days: number;
  sort_by: "created" | "updated" | "stars";
  max_results: number;
  typeWeb: boolean;
  typeApi: boolean;
  filterFree: boolean;
};

const DEFAULT_FILTERS: DiscoveryFilters = {
  min_stars: 0,
  max_age_days: 180,
  created_within_days: 90,
  sort_by: "created",
  max_results: 40,
  typeWeb: true,
  typeApi: true,
  filterFree: false,
};

function canUseLocalStorage(): boolean {
  return typeof window !== "undefined" && typeof window.localStorage !== "undefined";
}

function readStorage(key: string): string | null {
  if (!canUseLocalStorage()) return null;
  try {
    return window.localStorage.getItem(key);
  } catch {
    return null;
  }
}

function writeStorage(key: string, value: string): void {
  if (!canUseLocalStorage()) return;
  try {
    window.localStorage.setItem(key, value);
  } catch {
    /* ignore quota / private mode */
  }
}

function loadSavedFilters(): DiscoveryFilters {
  try {
    const raw = JSON.parse(readStorage(FILTER_KEY) || "{}") as Partial<
      DiscoveryFilters & { hideResearched?: boolean; hideSkipped?: boolean }
    >;
    return { ...DEFAULT_FILTERS, ...raw };
  } catch {
    return DEFAULT_FILTERS;
  }
}

function projectTypesFrom(filters: DiscoveryFilters): string[] {
  if (filters.filterFree) return [];
  const types: string[] = [];
  if (filters.typeWeb) types.push("web");
  if (filters.typeApi) types.push("api");
  return types;
}

export default function ProjectsPage() {
  const [searchParams, setSearchParams] = useSearchParams();
  const [stage, setStage] = useState<Stage>(() => {
    const saved = readStorage(VIEW_KEY);
    return saved === "library" ? "library" : "candidates";
  });
  const [libraryView, setLibraryView] = useState<LibraryView>("active");
  const [filters, setFilters] = useState<DiscoveryFilters>(loadSavedFilters);
  const [orgUrl, setOrgUrl] = useState("");
  const [orgLogin, setOrgLogin] = useState("");
  const [orgs, setOrgs] = useState<Organization[]>([]);
  const [projects, setProjects] = useState<Project[]>([]);
  const [cursor, setCursor] = useState<SearchCursor | null>(null);
  const [counts, setCounts] = useState<{ all: number; active: number; history: number }>({
    all: 0,
    active: 0,
    history: 0,
  });
  const [query, setQuery] = useState("");
  const [language, setLanguage] = useState("");
  const [hideResearched, setHideResearched] = useState(() => {
    try {
      return Boolean(JSON.parse(readStorage(FILTER_KEY) || "{}").hideResearched);
    } catch {
      return false;
    }
  });
  const [hideSkipped, setHideSkipped] = useState(() => {
    try {
      const saved = JSON.parse(readStorage(FILTER_KEY) || "{}");
      if (typeof saved.hideSkipped === "boolean") return saved.hideSkipped;
      return true;
    } catch {
      return true;
    }
  });
  const [page, setPage] = useState(1);
  const [repoUrl, setRepoUrl] = useState("");
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [jobDrawerId, setJobDrawerId] = useState<number | null>(null);
  const [restored, setRestored] = useState(false);

  const persistFilters = useCallback(
    (next: DiscoveryFilters, hr = hideResearched, hs = hideSkipped) => {
      writeStorage(
        FILTER_KEY,
        JSON.stringify({ ...next, hideResearched: hr, hideSkipped: hs }),
      );
    },
    [hideResearched, hideSkipped],
  );

  const scanParams = useCallback(
    (mode: "fresh" | "continue") => ({
      org_url: orgUrl.trim() || orgLogin,
      min_stars: filters.min_stars,
      max_age_days: filters.max_age_days,
      created_within_days: filters.created_within_days,
      sort_by: filters.sort_by,
      max_results: filters.max_results,
      project_types: projectTypesFrom(filters),
      mode,
    }),
    [orgUrl, orgLogin, filters],
  );

  const loadCandidates = useCallback(
    async (login: string) => {
      if (!login) {
        setProjects([]);
        setCursor(null);
        return;
      }
      const types = projectTypesFrom(filters);
      const res = await fetchProjects({
        org: login,
        min_stars: filters.min_stars,
        max_age_days: filters.max_age_days,
        created_within_days: filters.created_within_days,
        sort_by: filters.sort_by,
        project_types: types.length ? types.join(",") : "",
      });
      setProjects(res.projects);
      setOrgs(res.organizations);
      setCursor((res.cursor as SearchCursor | null) ?? null);
      if (res.organization?.login) {
        setOrgLogin(res.organization.login);
        setOrgUrl(res.organization.html_url || `https://github.com/${res.organization.login}`);
      }
    },
    [filters],
  );

  const loadLibrary = useCallback(async (view: LibraryView) => {
    const res = await fetchLibrary(view);
    setProjects(res.projects);
    setCounts({
      all: res.counts?.all ?? res.projects.length,
      active: res.counts?.active ?? 0,
      history: res.counts?.history ?? 0,
    });
  }, []);

  const reload = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      if (stage === "library") {
        await loadLibrary(libraryView);
        const orgRes = await fetchOrgs();
        setOrgs(orgRes.organizations);
      } else {
        await loadCandidates(orgLogin);
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to load");
    } finally {
      setLoading(false);
    }
  }, [stage, libraryView, orgLogin, loadLibrary, loadCandidates]);

  useEffect(() => {
    writeStorage(VIEW_KEY, stage);
  }, [stage]);

  useEffect(() => {
    if (restored) return;
    const orgFromQuery = searchParams.get("org");
    void (async () => {
      try {
        if (orgFromQuery) {
          setStage("candidates");
          setOrgLogin(orgFromQuery);
          setOrgUrl(`https://github.com/${orgFromQuery}`);
        } else {
          const latest = await fetchLatest();
          setOrgs(latest.organizations);
          if (latest.organization?.login && stage === "candidates") {
            setOrgLogin(latest.organization.login);
            setOrgUrl(
              latest.organization.html_url ||
                `https://github.com/${latest.organization.login}`,
            );
            setProjects(latest.projects);
            setCursor(null);
          }
        }
      } catch {
        /* ignore restore errors */
      } finally {
        setRestored(true);
      }
    })();
  }, [restored, searchParams, stage]);

  useEffect(() => {
    if (!restored) return;
    void reload();
  }, [restored, stage, libraryView, orgLogin, filters, reload]);

  useEffect(() => {
    setPage(1);
  }, [stage, libraryView, orgLogin, query, language, hideResearched, hideSkipped, projects.length]);

  const languages = useMemo(() => {
    const set = new Set<string>();
    for (const p of projects) {
      if (p.language) set.add(p.language);
    }
    return [...set].sort((a, b) => a.localeCompare(b));
  }, [projects]);

  const visible = useMemo(() => {
    const q = query.trim().toLowerCase();
    return projects.filter((p) => {
      if (stage === "candidates") {
        if (hideResearched && isResearched(p)) return false;
        if (hideSkipped && isSkipped(p)) return false;
      }
      if (language && (p.language || "") !== language) return false;
      if (q) {
        const hay = `${p.full_name} ${p.description || ""} ${p.language || ""}`.toLowerCase();
        if (!hay.includes(q)) return false;
      }
      return true;
    });
  }, [projects, stage, hideResearched, hideSkipped, language, query]);

  const totalPages = Math.max(1, Math.ceil(visible.length / PAGE_SIZE));
  const pageItems = visible.slice((page - 1) * PAGE_SIZE, page * PAGE_SIZE);

  async function runScan(mode: "fresh" | "continue") {
    const target = orgUrl.trim() || orgLogin;
    if (!target) {
      setError("Enter a GitHub org or user URL.");
      return;
    }
    setBusy(true);
    setMessage(null);
    setError(null);
    try {
      const res = await scanOrg(scanParams(mode));
      setMessage(res.message ?? "Scan complete.");
      setOrgLogin(res.organization.login);
      setOrgUrl(res.organization.html_url || `https://github.com/${res.organization.login}`);
      setProjects(res.projects);
      setOrgs(res.organizations || []);
      setCursor(res.cursor ?? null);
      setStage("candidates");
      setSearchParams({ org: res.organization.login });
    } catch (err) {
      setError(err instanceof Error ? err.message : "Scan failed");
    } finally {
      setBusy(false);
    }
  }

  async function onResearchRepo(e: React.FormEvent) {
    e.preventDefault();
    if (!repoUrl.trim()) return;
    setBusy(true);
    setError(null);
    try {
      const res = await researchRepo(repoUrl.trim());
      setMessage(`Queued research for ${res.project.full_name}`);
      setJobDrawerId(res.job.id);
      setStage("library");
      setLibraryView("active");
      await loadLibrary("active");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Repo research failed");
    } finally {
      setBusy(false);
    }
  }

  async function onPatch(
    id: number,
    body: { skipped?: boolean; reported?: boolean; false_positive?: boolean },
  ) {
    setError(null);
    try {
      const res = await patchProject(id, body);
      setProjects((prev) => prev.map((p) => (p.id === id ? { ...p, ...res.project } : p)));
      if (res.organizations) setOrgs(res.organizations);
      if (stage === "library") await loadLibrary(libraryView);
      const bits: string[] = [];
      if (body.skipped !== undefined) bits.push(body.skipped ? "Skipped" : "Unskipped");
      if (body.reported) bits.push("Marked reported → History");
      if (body.false_positive) bits.push("Marked false positive → History");
      if (body.reported === false || body.false_positive === false) bits.push("Restored to Active");
      if (bits.length) setMessage(bits.join(". "));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Update failed");
    }
  }

  async function onDelete(id: number, mode: "clone" | "full") {
    const label = mode === "clone" ? "remove the local clone" : "permanently delete this project";
    if (!window.confirm(`Really ${label}?`)) return;
    setBusy(true);
    try {
      const res = await deleteProject(id, mode);
      setMessage(res.message ?? "Deleted.");
      if (mode === "full") {
        setProjects((prev) => prev.filter((p) => p.id !== id));
      } else {
        setProjects((prev) =>
          prev.map((p) =>
            p.id === id ? { ...p, ...res.project, local_path: null, on_disk: false } : p,
          ),
        );
      }
      if (res.organizations) setOrgs(res.organizations);
      if (stage === "library") await loadLibrary(libraryView);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Delete failed");
    } finally {
      setBusy(false);
    }
  }

  async function onQuickResearch(project: Project) {
    setBusy(true);
    setError(null);
    try {
      const res = await startResearch(project.id);
      setJobDrawerId(res.job.id);
      setMessage(`Research queued for ${project.full_name}`);
      await reload();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Research failed");
    } finally {
      setBusy(false);
    }
  }

  function selectOrg(login: string) {
    setStage("candidates");
    setOrgLogin(login);
    setOrgUrl(`https://github.com/${login}`);
    setSearchParams({ org: login });
  }

  return (
    <div>
      <PageHeader
        title="Projects"
        subtitle="Discover candidates, manage the research library, and mark outcomes"
        actions={
          <div className="flex gap-2">
            <button
              type="button"
              className={`desk-btn ${stage === "candidates" ? "desk-btn-primary" : "desk-btn-ghost"}`}
              onClick={() => setStage("candidates")}
            >
              Candidates
            </button>
            <button
              type="button"
              className={`desk-btn ${stage === "library" ? "desk-btn-primary" : "desk-btn-ghost"}`}
              onClick={() => setStage("library")}
            >
              Library
            </button>
          </div>
        }
      />

      {error ? <p className="mb-3 text-sm text-[var(--desk-danger)]">{error}</p> : null}
      {message ? <p className="mb-3 text-sm text-[var(--desk-success)]">{message}</p> : null}

      <div className="mb-6 grid gap-4 xl:grid-cols-[220px_1fr]">
        <Panel className="h-fit">
          <h2 className="mb-2 text-xs font-semibold uppercase tracking-wide text-[var(--desk-ink-muted)]">
            Organizations
          </h2>
          <ul className="max-h-[420px] space-y-1 overflow-y-auto text-sm">
            {orgs.length === 0 ? (
              <li className="text-[var(--desk-ink-faint)]">No orgs scanned yet.</li>
            ) : (
              orgs.map((o) => (
                <li key={o.login}>
                  <button
                    type="button"
                    onClick={() => selectOrg(o.login)}
                    className={`w-full rounded px-2 py-1.5 text-left hover:bg-[var(--desk-surface-2)] ${
                      orgLogin === o.login && stage === "candidates"
                        ? "bg-[var(--desk-accent-soft)] font-medium"
                        : ""
                    }`}
                  >
                    <div className="truncate">{o.login}</div>
                    <div className="text-xs text-[var(--desk-ink-faint)]">
                      {o.project_count ?? 0} projects
                      {o.researched_count != null ? ` · ${o.researched_count} done` : ""}
                      {o.skipped_count != null ? ` · ${o.skipped_count} skipped` : ""}
                    </div>
                  </button>
                </li>
              ))
            )}
          </ul>
        </Panel>

        <div className="space-y-4">
          {stage === "candidates" ? (
            <Panel>
              <form
                className="grid gap-3 md:grid-cols-2 lg:grid-cols-3"
                onSubmit={(e) => {
                  e.preventDefault();
                  void runScan("fresh");
                }}
              >
                <label className="text-sm md:col-span-2 lg:col-span-3">
                  GitHub org / user
                  <input
                    className="desk-input mt-1"
                    value={orgUrl}
                    onChange={(e) => setOrgUrl(e.target.value)}
                    placeholder="https://github.com/microsoft"
                  />
                </label>
                <label className="text-sm">
                  Min stars
                  <input
                    type="number"
                    min={0}
                    className="desk-input mt-1"
                    value={filters.min_stars}
                    onChange={(e) => {
                      const next = { ...filters, min_stars: Number(e.target.value) || 0 };
                      setFilters(next);
                      persistFilters(next);
                    }}
                  />
                </label>
                <label className="text-sm">
                  Pushed within (days)
                  <input
                    type="number"
                    min={1}
                    className="desk-input mt-1"
                    value={filters.max_age_days}
                    onChange={(e) => {
                      const next = { ...filters, max_age_days: Number(e.target.value) || 180 };
                      setFilters(next);
                      persistFilters(next);
                    }}
                  />
                </label>
                <label className="text-sm">
                  Created within (days)
                  <input
                    type="number"
                    min={0}
                    className="desk-input mt-1"
                    value={filters.created_within_days}
                    onChange={(e) => {
                      const next = {
                        ...filters,
                        created_within_days: Number(e.target.value) || 0,
                      };
                      setFilters(next);
                      persistFilters(next);
                    }}
                  />
                </label>
                <label className="text-sm">
                  Sort
                  <select
                    className="desk-input mt-1"
                    value={filters.sort_by}
                    onChange={(e) => {
                      const next = {
                        ...filters,
                        sort_by: e.target.value as DiscoveryFilters["sort_by"],
                      };
                      setFilters(next);
                      persistFilters(next);
                    }}
                  >
                    <option value="created">Created</option>
                    <option value="updated">Updated</option>
                    <option value="stars">Stars</option>
                  </select>
                </label>
                <label className="text-sm">
                  Batch size
                  <input
                    type="number"
                    min={5}
                    max={200}
                    className="desk-input mt-1"
                    value={filters.max_results}
                    onChange={(e) => {
                      const next = { ...filters, max_results: Number(e.target.value) || 40 };
                      setFilters(next);
                      persistFilters(next);
                    }}
                  />
                </label>
                <fieldset className="text-sm md:col-span-2">
                  <legend className="mb-1 text-[var(--desk-ink-muted)]">Project types</legend>
                  <div className="flex flex-wrap gap-3">
                    <label className="inline-flex items-center gap-1.5">
                      <input
                        type="checkbox"
                        checked={filters.typeWeb}
                        disabled={filters.filterFree}
                        onChange={(e) => {
                          const next = { ...filters, typeWeb: e.target.checked };
                          setFilters(next);
                          persistFilters(next);
                        }}
                      />
                      Web
                    </label>
                    <label className="inline-flex items-center gap-1.5">
                      <input
                        type="checkbox"
                        checked={filters.typeApi}
                        disabled={filters.filterFree}
                        onChange={(e) => {
                          const next = { ...filters, typeApi: e.target.checked };
                          setFilters(next);
                          persistFilters(next);
                        }}
                      />
                      API
                    </label>
                    <label className="inline-flex items-center gap-1.5">
                      <input
                        type="checkbox"
                        checked={filters.filterFree}
                        onChange={(e) => {
                          const next = { ...filters, filterFree: e.target.checked };
                          setFilters(next);
                          persistFilters(next);
                        }}
                      />
                      Filter-free
                    </label>
                  </div>
                </fieldset>
                <div className="flex flex-wrap items-end gap-2 md:col-span-2 lg:col-span-3">
                  <button type="submit" className="desk-btn desk-btn-primary" disabled={busy}>
                    {busy ? <Spinner /> : null}
                    Find projects
                  </button>
                  <button
                    type="button"
                    className="desk-btn desk-btn-ghost"
                    disabled={busy || !orgLogin}
                    onClick={() => void runScan("continue")}
                  >
                    {cursor?.exhausted ? "Check for new" : "Load more"}
                  </button>
                  {cursor ? (
                    <span className="text-xs text-[var(--desk-ink-faint)]">
                      Discovered {cursor.total_discovered ?? 0}
                      {cursor.exhausted ? " · older bands exhausted" : ""}
                    </span>
                  ) : null}
                </div>
              </form>
            </Panel>
          ) : null}

          <Panel>
            <form
              onSubmit={(e) => void onResearchRepo(e)}
              className="flex flex-wrap items-end gap-3"
            >
              <label className="min-w-[260px] flex-1 text-sm">
                Direct repo URL
                <input
                  className="desk-input mt-1"
                  value={repoUrl}
                  onChange={(e) => setRepoUrl(e.target.value)}
                  placeholder="https://github.com/org/repo"
                />
              </label>
              <button type="submit" className="desk-btn desk-btn-ghost" disabled={busy}>
                Clone & research
              </button>
            </form>
          </Panel>

          {stage === "library" ? (
            <div className="flex flex-wrap items-center gap-2">
              {(["active", "history", "all"] as LibraryView[]).map((v) => (
                <button
                  key={v}
                  type="button"
                  className={`desk-btn desk-btn-sm ${libraryView === v ? "desk-btn-primary" : "desk-btn-ghost"}`}
                  onClick={() => setLibraryView(v)}
                >
                  {v === "active"
                    ? `Active (${counts.active})`
                    : v === "history"
                      ? `History (${counts.history})`
                      : `All (${counts.all})`}
                </button>
              ))}
              <button
                type="button"
                className="desk-btn desk-btn-ghost desk-btn-sm ml-auto"
                onClick={() => void reload()}
              >
                Refresh
              </button>
            </div>
          ) : (
            <div className="flex flex-wrap items-end gap-3">
              <label className="min-w-[160px] flex-1 text-sm">
                Search
                <input
                  className="desk-input mt-1"
                  value={query}
                  onChange={(e) => setQuery(e.target.value)}
                  placeholder="Filter by name…"
                />
              </label>
              <label className="text-sm">
                Language
                <select
                  className="desk-input mt-1 w-auto min-w-[120px]"
                  value={language}
                  onChange={(e) => setLanguage(e.target.value)}
                >
                  <option value="">All</option>
                  {languages.map((lang) => (
                    <option key={lang} value={lang}>
                      {lang}
                    </option>
                  ))}
                </select>
              </label>
              <label className="inline-flex items-center gap-1.5 text-sm">
                <input
                  type="checkbox"
                  checked={hideResearched}
                  onChange={(e) => {
                    setHideResearched(e.target.checked);
                    persistFilters(filters, e.target.checked, hideSkipped);
                  }}
                />
                Hide researched
              </label>
              <label className="inline-flex items-center gap-1.5 text-sm">
                <input
                  type="checkbox"
                  checked={hideSkipped}
                  onChange={(e) => {
                    setHideSkipped(e.target.checked);
                    persistFilters(filters, hideResearched, e.target.checked);
                  }}
                />
                Hide skipped
              </label>
            </div>
          )}

          <Panel>
            {loading ? (
              <div className="flex justify-center py-10">
                <Spinner />
              </div>
            ) : (
              <>
                <div className="mb-2 text-xs text-[var(--desk-ink-faint)]">
                  Showing {pageItems.length} of {visible.length}
                  {visible.length !== projects.length ? ` (filtered from ${projects.length})` : ""}
                </div>
                <div className="overflow-x-auto">
                  <table className="desk-table">
                    <thead>
                      <tr>
                        <th>Name</th>
                        <th>Lang</th>
                        <th>Stars</th>
                        <th>Score</th>
                        <th>Status</th>
                        <th>Actions</th>
                      </tr>
                    </thead>
                    <tbody>
                      {pageItems.length === 0 ? (
                        <tr>
                          <td colSpan={6} className="py-8 text-center text-[var(--desk-ink-muted)]">
                            No projects in this view.
                          </td>
                        </tr>
                      ) : (
                        pageItems.map((p) => {
                          const st = projectStatus(p);
                          const muted =
                            isSkipped(p) ||
                            (stage === "candidates" && isResearched(p)) ||
                            isReported(p) ||
                            isFalsePositive(p);
                          const historyRow =
                            stage === "library" && (isReported(p) || isFalsePositive(p));
                          return (
                            <tr
                              key={p.id}
                              className={`${muted ? "row-muted" : ""} ${historyRow ? "row-history" : ""}`}
                            >
                              <td>
                                <Link
                                  to={`/projects/${p.id}`}
                                  className="font-medium text-[var(--desk-accent)] hover:underline"
                                >
                                  {p.full_name}
                                </Link>
                                {p.description ? (
                                  <div className="mt-0.5 line-clamp-1 text-xs text-[var(--desk-ink-faint)]">
                                    {p.description}
                                  </div>
                                ) : null}
                              </td>
                              <td>{p.language ?? "—"}</td>
                              <td>{p.stars ?? 0}</td>
                              <td>
                                {typeof p.research_score === "number"
                                  ? p.research_score.toFixed(1)
                                  : (p.research_score ?? "—")}
                              </td>
                              <td>
                                <ProjectStatusBadge statusKey={st.key} label={st.label} />
                              </td>
                              <td>
                                <div className="flex flex-wrap gap-1">
                                  <button
                                    type="button"
                                    className="desk-btn desk-btn-ghost desk-btn-sm"
                                    disabled={busy}
                                    onClick={() => void onQuickResearch(p)}
                                  >
                                    Research
                                  </button>
                                  <button
                                    type="button"
                                    className="desk-btn desk-btn-ghost desk-btn-sm"
                                    onClick={() =>
                                      void onPatch(p.id, { skipped: !isSkipped(p) })
                                    }
                                  >
                                    {isSkipped(p) ? "Unskip" : "Skip"}
                                  </button>
                                  {stage === "library" || isResearched(p) ? (
                                    <>
                                      <button
                                        type="button"
                                        className="desk-btn desk-btn-ghost desk-btn-sm"
                                        onClick={() =>
                                          void onPatch(p.id, {
                                            reported: !isReported(p),
                                          })
                                        }
                                      >
                                        {isReported(p) ? "Unreport" : "Reported"}
                                      </button>
                                      <button
                                        type="button"
                                        className="desk-btn desk-btn-ghost desk-btn-sm"
                                        onClick={() =>
                                          void onPatch(p.id, {
                                            false_positive: !isFalsePositive(p),
                                          })
                                        }
                                      >
                                        {isFalsePositive(p) ? "Clear FP" : "False +"}
                                      </button>
                                    </>
                                  ) : null}
                                  <button
                                    type="button"
                                    className="desk-btn desk-btn-danger desk-btn-sm"
                                    onClick={() => void onDelete(p.id, "clone")}
                                  >
                                    Drop clone
                                  </button>
                                  <button
                                    type="button"
                                    className="desk-btn desk-btn-danger desk-btn-sm"
                                    onClick={() => void onDelete(p.id, "full")}
                                  >
                                    Delete
                                  </button>
                                  {p.last_job_id ? (
                                    <>
                                      <Link
                                        to={`/jobs/${p.last_job_id}`}
                                        className="desk-btn desk-btn-ghost desk-btn-sm"
                                      >
                                        {["running", "queued"].includes(
                                          (p.research_status || "").toLowerCase(),
                                        )
                                          ? "Watch CLI"
                                          : "Session"}
                                      </Link>
                                      <button
                                        type="button"
                                        className="desk-btn desk-btn-ghost desk-btn-sm"
                                        onClick={() => setJobDrawerId(p.last_job_id!)}
                                      >
                                        Logs
                                      </button>
                                    </>
                                  ) : null}
                                </div>
                              </td>
                            </tr>
                          );
                        })
                      )}
                    </tbody>
                  </table>
                </div>
                {visible.length > PAGE_SIZE ? (
                  <div className="mt-3 flex items-center justify-between text-sm">
                    <button
                      type="button"
                      className="desk-btn desk-btn-ghost desk-btn-sm"
                      disabled={page <= 1}
                      onClick={() => setPage((p) => Math.max(1, p - 1))}
                    >
                      Previous
                    </button>
                    <span className="text-[var(--desk-ink-muted)]">
                      Page {page} / {totalPages}
                    </span>
                    <button
                      type="button"
                      className="desk-btn desk-btn-ghost desk-btn-sm"
                      disabled={page >= totalPages}
                      onClick={() => setPage((p) => Math.min(totalPages, p + 1))}
                    >
                      Next
                    </button>
                  </div>
                ) : null}
              </>
            )}
          </Panel>
        </div>
      </div>

      <JobLogDrawer
        jobId={jobDrawerId}
        open={jobDrawerId !== null}
        onClose={() => setJobDrawerId(null)}
      />
    </div>
  );
}
