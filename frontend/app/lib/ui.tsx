import type { ReactNode } from "react";
import {
  AlertCircle,
  AlertTriangle,
  CheckCircle2,
  Clock,
  HelpCircle,
  Shield,
  ShieldAlert,
} from "lucide-react";

export function PageHeader({
  title,
  subtitle,
  actions,
}: {
  title: string;
  subtitle?: string;
  actions?: ReactNode;
}) {
  return (
    <div className="mb-6 flex flex-wrap items-start justify-between gap-4 border-b border-[var(--desk-border-subtle)] pb-5">
      <div>
        <div className="flex items-center gap-2">
          <h1 className="font-display text-xl font-semibold tracking-tight text-[var(--desk-ink)]">
            {title}
          </h1>
        </div>
        {subtitle ? (
          <p className="mt-1 font-sans text-xs text-[var(--desk-ink-muted)] leading-relaxed">
            {subtitle}
          </p>
        ) : null}
      </div>
      {actions ? <div className="flex flex-wrap items-center gap-2">{actions}</div> : null}
    </div>
  );
}

export function StatusBadge({ status }: { status?: string | null }) {
  const s = (status ?? "unknown").toLowerCase();
  let cls = "badge-neutral";
  let icon = <Clock className="h-3 w-3" />;

  if (s === "running" || s === "cloned") {
    cls = "badge-running";
    icon = <span className="h-1.5 w-1.5 rounded-full bg-zinc-300 animate-pulse" />;
  } else if (s === "done" || s === "researched" || s === "reported" || s === "active") {
    cls = "badge-done";
    icon = <CheckCircle2 className="h-3 w-3 text-emerald-400" />;
  } else if (s === "error" || s === "false-positive" || s === "false_positive") {
    cls = "badge-error";
    icon = <AlertCircle className="h-3 w-3 text-red-400" />;
  } else if (s === "queued" || s === "skipped" || s === "archived" || s === "candidate") {
    cls = "badge-queued";
    icon = <Clock className="h-3 w-3 text-amber-400" />;
  }

  return (
    <span className={`badge ${cls}`}>
      {icon}
      <span>{status ?? "—"}</span>
    </span>
  );
}

export function ProjectStatusBadge({
  statusKey,
  label,
}: {
  statusKey: string;
  label: string;
}) {
  const s = statusKey.toLowerCase();
  let cls = "badge-neutral";
  let dot = <span className="h-1.5 w-1.5 rounded-full bg-zinc-400" />;

  if (s === "running" || s === "cloned") {
    cls = "badge-running";
    dot = <span className="h-1.5 w-1.5 rounded-full bg-zinc-100 animate-pulse" />;
  } else if (s === "done" || s === "reported") {
    cls = "badge-done";
    dot = <span className="h-1.5 w-1.5 rounded-full bg-emerald-400" />;
  } else if (s === "error" || s === "false-positive") {
    cls = "badge-error";
    dot = <span className="h-1.5 w-1.5 rounded-full bg-red-400" />;
  } else if (s === "queued" || s === "skipped" || s === "archived") {
    cls = "badge-queued";
    dot = <span className="h-1.5 w-1.5 rounded-full bg-amber-400" />;
  }

  return (
    <span className={`badge ${cls}`}>
      {dot}
      <span>{label}</span>
    </span>
  );
}

export function SeverityBadge({ severity }: { severity?: string | null }) {
  const s = (severity ?? "").toLowerCase();
  let cls = "badge-neutral";
  let icon = <HelpCircle className="h-3 w-3 text-zinc-400" />;

  if (s === "critical") {
    cls = "badge-error bg-red-500/15 text-red-300 border-red-500/40";
    icon = <ShieldAlert className="h-3 w-3 text-red-400" />;
  } else if (s === "high") {
    cls = "badge-error";
    icon = <AlertTriangle className="h-3 w-3 text-red-400" />;
  } else if (s === "medium") {
    cls = "badge-queued";
    icon = <Clock className="h-3 w-3 text-amber-400" />;
  } else if (s === "low") {
    cls = "badge-done";
    icon = <Shield className="h-3 w-3 text-emerald-400" />;
  }

  return (
    <span className={`badge ${cls}`}>
      {icon}
      <span className="font-mono text-[10px] uppercase font-semibold">{severity || "—"}</span>
    </span>
  );
}

export function Panel({
  children,
  className = "",
}: {
  children: ReactNode;
  className?: string;
}) {
  return <div className={`desk-panel p-5 ${className}`}>{children}</div>;
}

export function StatCard({
  label,
  value,
  subtext,
  icon: Icon,
}: {
  label: string;
  value: string | number;
  subtext?: string;
  icon?: React.ComponentType<{ className?: string }>;
}) {
  return (
    <div className="desk-panel p-4 flex flex-col justify-between">
      <div className="flex items-center justify-between text-[var(--desk-ink-faint)]">
        <span className="font-mono text-[10px] font-semibold uppercase tracking-wider">
          {label}
        </span>
        {Icon ? <Icon className="h-4 w-4 text-[var(--desk-ink-muted)]" /> : null}
      </div>
      <div className="mt-2 flex items-baseline gap-2">
        <span className="font-display text-2xl font-semibold tracking-tight text-[var(--desk-ink)] tabular-nums">
          {value}
        </span>
      </div>
      {subtext ? (
        <span className="mt-1 font-mono text-[10px] text-[var(--desk-ink-faint)]">
          {subtext}
        </span>
      ) : null}
    </div>
  );
}

export function Spinner() {
  return (
    <span
      className="inline-block h-3.5 w-3.5 animate-spin rounded-full border-2 border-[var(--desk-border-accent)] border-t-[var(--desk-ink)]"
      aria-hidden
    />
  );
}
