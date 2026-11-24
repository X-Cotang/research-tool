import { useEffect, useState } from "react";
import {
  BookOpen,
  Edit2,
  FileCode2,
  Plus,
  Save,
  Search,
  ShieldAlert,
  Sparkles,
  Trash2,
  X,
} from "lucide-react";

import {
  createPrompt,
  deletePrompt,
  fetchPrompts,
  updatePrompt,
  type Prompt,
} from "~/lib/api";
import { PageHeader, Panel, Spinner } from "~/lib/ui";

const emptyForm = {
  slug: "",
  name: "",
  language: "",
  vuln_class: "",
  description: "",
  content: "",
};

export default function PromptsPage() {
  const [prompts, setPrompts] = useState<Prompt[]>([]);
  const [loading, setLoading] = useState(true);
  const [form, setForm] = useState(emptyForm);
  const [editId, setEditId] = useState<number | null>(null);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [query, setQuery] = useState("");

  async function load() {
    setLoading(true);
    try {
      const r = await fetchPrompts();
      setPrompts(r.prompts);
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    void load();
  }, []);

  function startEdit(prompt: Prompt) {
    setEditId(prompt.id);
    setForm({
      slug: prompt.slug,
      name: prompt.name,
      language: prompt.language ?? "",
      vuln_class: prompt.vuln_class ?? "",
      description: prompt.description ?? "",
      content: prompt.content,
    });
  }

  function resetForm() {
    setEditId(null);
    setForm(emptyForm);
  }

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    setSaving(true);
    setError(null);
    try {
      const body = {
        ...form,
        language: form.language || null,
        vuln_class: form.vuln_class || null,
      };
      if (editId) {
        await updatePrompt(editId, body);
      } else {
        await createPrompt(body);
      }
      resetForm();
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Save failed");
    } finally {
      setSaving(false);
    }
  }

  async function onDelete(id: number) {
    if (!confirm("Delete this prompt?")) return;
    try {
      await deletePrompt(id);
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Delete failed");
    }
  }

  const filtered = prompts.filter(
    (p) =>
      p.name.toLowerCase().includes(query.toLowerCase()) ||
      p.slug.toLowerCase().includes(query.toLowerCase()) ||
      (p.vuln_class || "").toLowerCase().includes(query.toLowerCase()),
  );

  return (
    <div className="space-y-6">
      <PageHeader
        title="Vulnerability Prompt Templates"
        subtitle="Specialized prompts focusing external workers on RCE, Deserialization, SSRF, SQLi, and Authentication Bypass"
        actions={
          editId ? (
            <button
              type="button"
              className="desk-btn desk-btn-ghost text-xs"
              onClick={resetForm}
            >
              <X className="h-3.5 w-3.5" />
              <span>Cancel Edit</span>
            </button>
          ) : null
        }
      />

      {error ? <p className="mb-4 text-xs text-[var(--desk-danger)]">{error}</p> : null}

      <div className="grid gap-6 lg:grid-cols-12">
        {/* Editor */}
        <div className="lg:col-span-5">
          <Panel>
            <div className="mb-4 flex items-center justify-between border-b border-[var(--desk-border-subtle)] pb-3">
              <div className="flex items-center gap-2">
                <FileCode2 className="h-4 w-4 text-[var(--desk-ink-muted)]" />
                <h2 className="font-display text-sm font-semibold text-[var(--desk-ink)]">
                  {editId ? "Edit Prompt Template" : "New Prompt Template"}
                </h2>
              </div>
              <span className="font-mono text-[10px] text-[var(--desk-ink-faint)]">
                VULN-CLASS
              </span>
            </div>

            <form onSubmit={(e) => void onSubmit(e)} className="space-y-3.5">
              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="block font-mono text-[10px] uppercase text-[var(--desk-ink-faint)]">
                    Slug
                  </label>
                  <input
                    className="desk-input mt-1 font-mono text-xs"
                    value={form.slug}
                    onChange={(e) => setForm({ ...form, slug: e.target.value })}
                    placeholder="e.g. rce-fastapi"
                    required
                  />
                </div>
                <div>
                  <label className="block font-mono text-[10px] uppercase text-[var(--desk-ink-faint)]">
                    Name
                  </label>
                  <input
                    className="desk-input mt-1 text-xs"
                    value={form.name}
                    onChange={(e) => setForm({ ...form, name: e.target.value })}
                    placeholder="FastAPI Remote Code Execution"
                    required
                  />
                </div>
              </div>

              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="block font-mono text-[10px] uppercase text-[var(--desk-ink-faint)]">
                    Language Target
                  </label>
                  <input
                    className="desk-input mt-1 font-mono text-xs"
                    value={form.language}
                    onChange={(e) => setForm({ ...form, language: e.target.value })}
                    placeholder="python, javascript, go, etc."
                  />
                </div>
                <div>
                  <label className="block font-mono text-[10px] uppercase text-[var(--desk-ink-faint)]">
                    Vulnerability Class
                  </label>
                  <input
                    className="desk-input mt-1 font-mono text-xs"
                    value={form.vuln_class}
                    onChange={(e) => setForm({ ...form, vuln_class: e.target.value })}
                    placeholder="RCE, SSRF, Deserialization, SQLi"
                  />
                </div>
              </div>

              <div>
                <label className="block font-mono text-[10px] uppercase text-[var(--desk-ink-faint)]">
                  Description
                </label>
                <input
                  className="desk-input mt-1 text-xs"
                  value={form.description}
                  onChange={(e) => setForm({ ...form, description: e.target.value })}
                  placeholder="Targeting unsanitized input passed to subprocess/exec"
                />
              </div>

              <div>
                <label className="block font-mono text-[10px] uppercase text-[var(--desk-ink-faint)]">
                  Prompt Instructions
                </label>
                <textarea
                  className="desk-input mt-1 min-h-[190px] font-mono text-xs leading-relaxed text-zinc-300"
                  value={form.content}
                  onChange={(e) => setForm({ ...form, content: e.target.value })}
                  placeholder="Precise analysis directives passed to command-code/opencode/claude/qoder..."
                  required
                />
              </div>

              <div className="flex items-center gap-2 pt-2">
                <button
                  type="submit"
                  className="desk-btn desk-btn-primary"
                  disabled={saving}
                >
                  {saving ? <Spinner /> : <Save className="h-3.5 w-3.5" />}
                  <span>{editId ? "Update Prompt" : "Create Prompt"}</span>
                </button>
                {editId && (
                  <button
                    type="button"
                    className="desk-btn desk-btn-ghost"
                    onClick={resetForm}
                  >
                    Cancel
                  </button>
                )}
              </div>
            </form>
          </Panel>
        </div>

        {/* List */}
        <div className="lg:col-span-7">
          <Panel>
            <div className="mb-4 flex items-center justify-between border-b border-[var(--desk-border-subtle)] pb-3">
              <div className="flex items-center gap-2">
                <BookOpen className="h-4 w-4 text-[var(--desk-ink-muted)]" />
                <h2 className="font-display text-sm font-semibold text-[var(--desk-ink)]">
                  Prompt Templates ({prompts.length})
                </h2>
              </div>
              <div className="relative max-w-xs">
                <Search className="absolute left-2.5 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-[var(--desk-ink-faint)]" />
                <input
                  className="desk-input pl-7 text-xs font-mono py-1"
                  placeholder="Filter prompts…"
                  value={query}
                  onChange={(e) => setQuery(e.target.value)}
                />
              </div>
            </div>

            {loading ? (
              <div className="flex justify-center py-12">
                <Spinner />
              </div>
            ) : filtered.length === 0 ? (
              <p className="py-12 text-center font-mono text-xs text-[var(--desk-ink-muted)]">
                No matching prompts in library.
              </p>
            ) : (
              <div className="space-y-2">
                {filtered.map((p) => (
                  <div
                    key={p.id}
                    className="flex items-start justify-between gap-3 rounded-lg border border-[var(--desk-border)] bg-[var(--desk-surface-2)]/50 p-3.5 transition-all hover:border-[var(--desk-border-accent)] hover:bg-[var(--desk-surface-2)]"
                  >
                    <div className="min-w-0 flex-1">
                      <div className="flex items-center gap-2">
                        <span className="font-display text-xs font-semibold text-[var(--desk-ink)]">
                          {p.name}
                        </span>
                        {p.vuln_class && (
                          <span className="rounded border border-red-500/30 bg-red-500/10 px-1.5 py-0.5 font-mono text-[9px] font-semibold text-red-400">
                            {p.vuln_class}
                          </span>
                        )}
                        {p.language && (
                          <span className="rounded bg-zinc-800 px-1.5 py-0.5 font-mono text-[9px] uppercase text-zinc-300">
                            {p.language}
                          </span>
                        )}
                      </div>
                      <p className="font-mono text-[11px] text-[var(--desk-ink-faint)]">
                        slug: {p.slug}
                      </p>
                      {p.description && (
                        <p className="mt-1 text-xs text-[var(--desk-ink-muted)] line-clamp-2">
                          {p.description}
                        </p>
                      )}
                    </div>

                    <div className="flex shrink-0 items-center gap-1.5">
                      <button
                        type="button"
                        className="desk-btn desk-btn-ghost desk-btn-xs font-mono"
                        onClick={() => startEdit(p)}
                      >
                        <Edit2 className="h-3 w-3" />
                        <span>Edit</span>
                      </button>
                      <button
                        type="button"
                        className="desk-btn desk-btn-danger desk-btn-xs font-mono"
                        onClick={() => void onDelete(p.id)}
                      >
                        <Trash2 className="h-3 w-3" />
                      </button>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </Panel>
        </div>
      </div>
    </div>
  );
}
