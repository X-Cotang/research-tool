import type { Project } from "~/lib/api";

export function isTruthyFlag(value: unknown): boolean {
  return value === true || value === 1 || value === "1";
}

export function isSkipped(project: Project): boolean {
  return isTruthyFlag(project.skipped);
}

export function isReported(project: Project): boolean {
  return isTruthyFlag(project.reported);
}

export function isFalsePositive(project: Project): boolean {
  return isTruthyFlag(project.false_positive);
}

export function isResearched(project: Project): boolean {
  const status = (project.research_status || "").toLowerCase();
  return (
    status === "done" ||
    Boolean(project.researched) ||
    Boolean(project.researched_at) ||
    Boolean(project.last_report)
  );
}

export function isOnDisk(project: Project): boolean {
  if (typeof project.on_disk === "boolean") return project.on_disk;
  return Boolean(project.local_path);
}

export type ProjectStatusKey =
  | "running"
  | "queued"
  | "reported"
  | "false-positive"
  | "skipped"
  | "done"
  | "archived"
  | "error"
  | "cloned"
  | "idle";

export function projectStatus(project: Project): { key: ProjectStatusKey; label: string } {
  const status = (project.research_status || "idle").toLowerCase();
  if (status === "running") return { key: "running", label: "Running" };
  if (status === "queued") return { key: "queued", label: "Queued" };
  if (status === "error") return { key: "error", label: "Error" };
  if (isReported(project)) return { key: "reported", label: "Reported" };
  if (isFalsePositive(project)) return { key: "false-positive", label: "False positive" };
  if (isSkipped(project) && !isResearched(project)) {
    return { key: "skipped", label: "Skipped" };
  }
  if (status === "done" || isResearched(project)) {
    if (!isOnDisk(project)) return { key: "archived", label: "Clone removed" };
    return { key: "done", label: "Researched" };
  }
  if (status === "cloned" || isOnDisk(project)) return { key: "cloned", label: "Cloned" };
  return { key: "idle", label: "New" };
}
