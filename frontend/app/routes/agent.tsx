import { useEffect, useState } from "react";
import {
  BookOpen,
  Bot,
  Brain,
  Check,
  ChevronRight,
  Copy,
  Cpu,
  History,
  Layers,
  RefreshCw,
  Sparkles,
} from "lucide-react";

import {
  adoptHarness,
  fetchAgentMemory,
  fetchExperiences,
  fetchHarness,
  rollbackHarness,
  type Experience,
  type HarnessComponent,
} from "~/lib/api";
import { PageHeader, Panel, Spinner, StatCard, StatusBadge } from "~/lib/ui";

export default function AgentPage() {
  const [memory, setMemory] = useState("");
  const [lessons, setLessons] = useState<Experience[]>([]);
  const [components, setComponents] = useState<HarnessComponent[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [copiedMemory, setCopiedMemory] = useState(false);

  async function load() {
    setLoading(true);
    setError(null);
    try {
      const [mem, exp, harness] = await Promise.all([
        fetchAgentMemory(),
        fetchExperiences(),
        fetchHarness(),
      ]);
      setMemory(mem.text);
      setLessons(exp.experiences);
      setComponents(harness.components);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load agent state");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    void load();
  }, []);

  async function onAdopt(id: number) {
    setMessage(null);
    try {
      const res = await adoptHarness(id);
      setMessage(`Adopted component ${res.component.name} v${res.component.version}.`);
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Adopt failed");
    }
  }

  async function onRollback(name: string) {
    setMessage(null);
    try {
      const res = await rollbackHarness(name);
      setMessage(`Restored component ${res.component.name} v${res.component.version}.`);
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Rollback failed");
    }
  }

  const onCopyMemory = async () => {
    try {
      await navigator.clipboard.writeText(memory);
      setCopiedMemory(true);
      setTimeout(() => setCopiedMemory(false), 2000);
    } catch {
      /* ignore */
    }
  };

  if (loading) {
    return (
      <div className="flex justify-center py-24">
        <Spinner />
      </div>
    );
  }

  const names = [...new Set(components.map((c) => c.name))];
  const candidatesCount = components.filter((c) => c.status === "candidate").length;

  return (
    <div className="space-y-6">
      <PageHeader
        title="AI Master Core & Memory"
        subtitle="Durable working memory, evidence-backed vulnerability lessons, and versioned harness architecture"
        actions={
          <button
            type="button"
            className="desk-btn desk-btn-ghost desk-btn-sm"
            onClick={() => void load()}
          >
            <RefreshCw className="h-3.5 w-3.5" />
            <span>Refresh State</span>
          </button>
        }
      />

      {error ? (
        <div className="rounded-md border border-red-500/30 bg-red-500/10 p-3 text-xs text-[var(--desk-danger)]">
          {error}
        </div>
      ) : null}

      {message ? (
        <div className="rounded-md border border-emerald-500/30 bg-emerald-500/10 p-3 text-xs text-[var(--desk-success)]">
          {message}
        </div>
      ) : null}

      {/* Metrics Row */}
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <StatCard
          label="Memory Size"
          value={`${memory.length} bytes`}
          subtext="Active working context"
          icon={Brain}
        />
        <StatCard
          label="Learned Lessons"
          value={lessons.length}
          subtext="Evidence-backed insights"
          icon={BookOpen}
        />
        <StatCard
          label="Harness Modules"
          value={names.length}
          subtext="Active components"
          icon={Layers}
        />
        <StatCard
          label="Pending Candidates"
          value={candidatesCount}
          subtext="Awaiting user adoption"
          icon={Sparkles}
        />
      </div>

      {/* Working Memory and Lessons */}
      <div className="grid gap-6 lg:grid-cols-2">
        <Panel className="flex flex-col">
          <div className="mb-3 flex items-center justify-between">
            <div className="flex items-center gap-2">
              <Brain className="h-4 w-4 text-[var(--desk-ink-faint)]" />
              <h2 className="font-mono text-xs font-semibold uppercase tracking-wider text-[var(--desk-ink-muted)]">
                Working Memory Snapshot
              </h2>
            </div>
            <button
              type="button"
              onClick={() => void onCopyMemory()}
              className="flex items-center gap-1 font-mono text-[11px] text-[var(--desk-ink-muted)] hover:text-[var(--desk-ink)]"
            >
              {copiedMemory ? (
                <>
                  <Check className="h-3 w-3 text-[var(--desk-success)]" />
                  <span className="text-[var(--desk-success)]">Copied</span>
                </>
              ) : (
                <>
                  <Copy className="h-3 w-3" />
                  <span>Copy</span>
                </>
              )}
            </button>
          </div>

          <pre className="flex-1 max-h-96 overflow-auto rounded-md border border-[var(--desk-border-subtle)] bg-[#070709] p-3 font-mono text-xs leading-relaxed text-[#d4d4d8] whitespace-pre-wrap">
            {memory || "Working memory is empty."}
          </pre>
        </Panel>

        <Panel className="flex flex-col">
          <div className="mb-3 flex items-center justify-between">
            <div className="flex items-center gap-2">
              <BookOpen className="h-4 w-4 text-[var(--desk-ink-faint)]" />
              <h2 className="font-mono text-xs font-semibold uppercase tracking-wider text-[var(--desk-ink-muted)]">
                Evidence-Backed Lessons ({lessons.length})
              </h2>
            </div>
          </div>

          <div className="flex-1 max-h-96 overflow-y-auto">
            {lessons.length === 0 ? (
              <p className="py-12 text-center font-mono text-xs text-[var(--desk-ink-muted)]">
                No lessons recorded yet. The Master records general lessons only after finished research jobs when backed by concrete evidence.
              </p>
            ) : (
              <ul className="divide-y divide-[var(--desk-border-subtle)]">
                {lessons.map((item) => (
                  <li key={item.id} className="py-3 text-xs space-y-1">
                    <div className="flex items-center justify-between font-mono text-[10px] text-[var(--desk-ink-faint)] uppercase">
                      <span>
                        Domain: {item.domain} · Confidence: {item.confidence}
                      </span>
                      <span>Job #{item.job_id ?? "—"}</span>
                    </div>
                    <p className="font-medium text-[var(--desk-ink)]">{item.cue}</p>
                    <p className="text-[var(--desk-ink-muted)] leading-relaxed">{item.lesson}</p>
                    <p className="font-mono text-[10px] text-zinc-500 truncate">
                      Evidence: {item.evidence}
                    </p>
                  </li>
                ))}
              </ul>
            )}
          </div>
        </Panel>
      </div>

      {/* Harness Versions */}
      <Panel>
        <div className="mb-4 flex items-center justify-between">
          <div>
            <h2 className="font-display text-sm font-semibold tracking-tight text-[var(--desk-ink)]">
              Harness Component Registry
            </h2>
            <p className="font-mono text-[11px] text-[var(--desk-ink-faint)]">
              Prompt, guardrail, and guidance modules that control the AI Master loop
            </p>
          </div>
          <span className="font-mono text-[10px] text-[var(--desk-ink-faint)]">
            HUMAN-IN-THE-LOOP SAFEGUARD
          </span>
        </div>

        <div className="space-y-6">
          {names.map((name) => (
            <div
              key={name}
              className="rounded-lg border border-[var(--desk-border)] bg-[var(--desk-surface-2)]/50 p-4"
            >
              <div className="mb-3 flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <Cpu className="h-4 w-4 text-[var(--desk-ink-faint)]" />
                  <h3 className="font-mono text-xs font-semibold uppercase text-[var(--desk-ink)]">
                    {name}
                  </h3>
                </div>
                <button
                  type="button"
                  className="desk-btn desk-btn-ghost desk-btn-xs font-mono"
                  onClick={() => void onRollback(name)}
                >
                  <History className="h-3 w-3" />
                  <span>Roll Back</span>
                </button>
              </div>

              <div className="space-y-2">
                {components
                  .filter((c) => c.name === name)
                  .map((c) => (
                    <div
                      key={c.id}
                      className="rounded border border-[var(--desk-border-subtle)] bg-[#070709] p-3 text-xs"
                    >
                      <div className="mb-2 flex items-center justify-between">
                        <div className="flex items-center gap-2">
                          <span className="font-mono text-[11px] font-semibold text-zinc-300">
                            v{c.version}
                          </span>
                          <StatusBadge status={c.status} />
                          {c.note ? (
                            <span className="font-mono text-[10px] text-[var(--desk-ink-faint)]">
                              · {c.note}
                            </span>
                          ) : null}
                        </div>
                        {c.status === "candidate" ? (
                          <button
                            type="button"
                            className="desk-btn desk-btn-primary desk-btn-xs font-mono"
                            onClick={() => void onAdopt(c.id)}
                          >
                            <Check className="h-3 w-3" />
                            <span>Adopt as Active</span>
                          </button>
                        ) : null}
                      </div>

                      <pre className="max-h-36 overflow-auto rounded border border-[var(--desk-border-subtle)] bg-[#0a0a0d] p-2.5 font-mono text-[11px] leading-relaxed text-zinc-300 whitespace-pre-wrap">
                        {c.content}
                      </pre>
                    </div>
                  ))}
              </div>
            </div>
          ))}
        </div>
      </Panel>
    </div>
  );
}
