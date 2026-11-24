import { useEffect, useState } from "react";
import { Link, NavLink, Outlet, useLocation } from "react-router";
import {
  Activity,
  Bot,
  Cpu,
  FileCode2,
  FolderGit2,
  LayoutDashboard,
  MessageSquare,
  PlaySquare,
  LogOut,
  Plus,
  Shield,
  ShieldAlert,
  SlidersHorizontal,
  Terminal,
} from "lucide-react";

import { MiniChat } from "~/components/MiniChat";
import {
  fetchLiveJobs,
  fetchAuth,
  fetchStatus,
  logout,
  type LiveJob,
  type StatusResponse,
} from "~/lib/api";

const navItems = [
  { to: "/", label: "Dashboard", icon: LayoutDashboard, end: true },
  { to: "/projects", label: "Projects", icon: FolderGit2 },
  { to: "/chat", label: "Master Chat", icon: Terminal },
  { to: "/runs", label: "Batch Runs", icon: PlaySquare },
  { to: "/skills", label: "Skills", icon: Cpu },
  { to: "/prompts", label: "Prompts", icon: FileCode2 },
  { to: "/findings", label: "Findings", icon: ShieldAlert },
  { to: "/agent", label: "Agent Memory", icon: Bot },
  { to: "/settings", label: "Settings", icon: SlidersHorizontal },
];

export function AppShell() {
  const [status, setStatus] = useState<StatusResponse | null>(null);
  const [liveJobs, setLiveJobs] = useState<LiveJob[]>([]);
  const [username, setUsername] = useState<string | null>(null);
  const location = useLocation();

  useEffect(() => {
    fetchStatus()
      .then((s) => setStatus(s))
      .catch(() => {});
    fetchAuth()
      .then((auth) => setUsername(auth.username))
      .catch(() => {});
  }, []);

  function onLogout() {
    logout();
    window.location.assign("/login");
  }

  useEffect(() => {
    let stopped = false;
    const tick = () => {
      fetchLiveJobs()
        .then((res) => {
          if (!stopped) setLiveJobs(res.jobs ?? []);
        })
        .catch(() => {});
    };
    tick();
    const timer = window.setInterval(tick, 3000);
    return () => {
      stopped = true;
      window.clearInterval(timer);
    };
  }, []);

  return (
    <div className="flex min-h-screen bg-[var(--desk-bg)] text-[var(--desk-ink)] selection:bg-zinc-100 selection:text-zinc-950">
      {/* Sidebar */}
      <aside className="sticky top-0 flex h-screen w-64 shrink-0 flex-col border-r border-[var(--desk-border)] bg-[#09090b]/95 backdrop-blur-md">
        {/* Brand Header */}
        <div className="flex flex-col border-b border-[var(--desk-border)] px-4 py-4">
          <div className="flex items-center justify-between">
            <span className="font-mono text-[9px] font-semibold uppercase tracking-[0.2em] text-[var(--desk-ink-faint)]">
              RESEARCH // DESK
            </span>
            <span className="flex items-center gap-1 font-mono text-[9px] text-[var(--desk-success)]">
              <span className="h-1.5 w-1.5 rounded-full bg-[var(--desk-success)] tech-pulse" />
              ONLINE
            </span>
          </div>
          <Link to="/" className="mt-1 flex items-center gap-2">
            <div className="flex h-6 w-6 items-center justify-center rounded-md border border-[var(--desk-border-accent)] bg-zinc-900 text-zinc-100">
              <Shield className="h-3.5 w-3.5" />
            </div>
            <span className="font-display text-sm font-semibold tracking-tight text-[var(--desk-ink)]">
              Security Tool
            </span>
            <span className="ml-auto rounded border border-[var(--desk-border)] bg-zinc-900/60 px-1 font-mono text-[9px] text-[var(--desk-ink-faint)]">
              v2.5
            </span>
          </Link>
        </div>

        {/* Navigation */}
        <nav className="flex-1 space-y-0.5 overflow-y-auto px-2 py-3">
          <div className="px-2 pb-1 font-mono text-[9px] font-semibold uppercase tracking-wider text-[var(--desk-ink-faint)]">
            Navigation
          </div>
          {navItems.map((item) => {
            const Icon = item.icon;
            return (
              <NavLink
                key={item.to}
                to={item.to}
                end={item.end}
                className={({ isActive }) =>
                  `flex items-center gap-2.5 rounded-md px-3 py-2 text-xs font-medium transition-all ${
                    isActive
                      ? "bg-[#fafafa] text-[#09090b] shadow-sm font-semibold"
                      : "text-[var(--desk-ink-muted)] hover:bg-[#141418] hover:text-[var(--desk-ink)]"
                  }`
                }
              >
                <Icon className="h-4 w-4 shrink-0" />
                <span className="truncate">{item.label}</span>
              </NavLink>
            );
          })}
        </nav>

        {/* Telemetry Footer */}
        <div className="border-t border-[var(--desk-border)] bg-[#0c0c0f] p-3 text-[11px]">
          <div className="mb-2 flex items-center justify-between font-mono text-[10px] text-[var(--desk-ink-faint)]">
            <span>TELEMETRY</span>
            <span>AUTO-SYNC</span>
          </div>
          <div className="space-y-1.5 rounded border border-[var(--desk-border)] bg-[#09090b] p-2 font-mono text-[10px]">
            <div className="flex items-center justify-between">
              <span className="text-[var(--desk-ink-faint)]">GitHub Token:</span>
              <span
                className={
                  status?.github_token
                    ? "text-[var(--desk-success)] font-medium"
                    : "text-amber-400"
                }
              >
                {status?.github_token ? "CONNECTED" : "NOT SET"}
              </span>
            </div>
            <div className="flex items-center justify-between">
              <span className="text-[var(--desk-ink-faint)]">CLI Worker:</span>
              <span className="text-zinc-300 truncate max-w-[90px]">
                {status?.research_preset || "command-code"}
              </span>
            </div>
            <div className="flex items-center justify-between">
              <span className="text-[var(--desk-ink-faint)]">Live CLIs:</span>
              <span className={liveJobs.length ? "text-sky-300" : "text-zinc-500"}>
                {liveJobs.length ? `${liveJobs.length} live` : "idle"}
              </span>
            </div>
            {liveJobs.map((job) => {
              const viewingRun = /^\/runs\/(\d+)/.exec(location.pathname);
              const runId = viewingRun ? Number(viewingRun[1]) : null;
              const outsideRun = runId != null && job.run_id !== runId;
              return (
                <Link
                  key={job.id}
                  to={`/jobs/${job.id}`}
                  className="block truncate text-sky-300 hover:underline"
                  title={job.cli_activity || job.status}
                >
                  {job.full_name.split("/")[1] || job.full_name}
                  {" · "}
                  {job.cli_activity || job.status}
                  {outsideRun ? " · not this batch" : ""}
                </Link>
              );
            })}
            <div className="flex items-center justify-between">
              <span className="text-[var(--desk-ink-faint)]">SAST:</span>
              <span className="text-zinc-300">
                {status?.sast?.binary_available ? "SEMGREP" : "NONE"}
              </span>
            </div>
          </div>
        </div>
      </aside>

      {/* Main Content Area */}
      <div className="flex min-w-0 flex-1 flex-col">
        {/* Top Command Bar */}
        <header className="sticky top-0 z-30 flex h-14 items-center justify-between border-b border-[var(--desk-border)] bg-[#09090b]/80 px-6 backdrop-blur-md">
          <div className="flex items-center gap-2 font-mono text-xs text-[var(--desk-ink-muted)]">
            <span>desk</span>
            <span>/</span>
            <span className="text-[var(--desk-ink)] font-medium">
              {location.pathname === "/"
                ? "dashboard"
                : location.pathname.slice(1).split("/")[0]}
            </span>
          </div>

          <div className="flex items-center gap-2">
            {username ? (
              <span className="hidden font-mono text-[10px] uppercase tracking-wider text-[var(--desk-ink-faint)] sm:inline">
                {username}
              </span>
            ) : null}
            <button type="button" onClick={onLogout} className="desk-btn desk-btn-ghost desk-btn-xs font-mono">
              <LogOut className="h-3 w-3" />
              <span>Sign out</span>
            </button>
            <Link
              to="/chat"
              className="desk-btn desk-btn-ghost desk-btn-xs font-mono"
            >
              <Terminal className="h-3 w-3" />
              <span>AI Master</span>
            </Link>
            <Link
              to="/projects"
              className="desk-btn desk-btn-primary desk-btn-xs font-mono"
            >
              <Plus className="h-3 w-3" />
              <span>Discover</span>
            </Link>
          </div>
        </header>

        <main className="min-w-0 flex-1 p-6 pb-24">
          <Outlet />
        </main>
      </div>

      <MiniChat />
    </div>
  );
}
