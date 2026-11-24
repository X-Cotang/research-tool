import { useEffect, useState } from "react";
import {
  BookOpen,
  Code2,
  Cpu,
  Edit2,
  FileCode2,
  Plus,
  Save,
  Search,
  Sparkles,
  Trash2,
  X,
} from "lucide-react";

import {
  createSkill,
  deleteSkill,
  fetchSkills,
  updateSkill,
  type Skill,
} from "~/lib/api";
import { PageHeader, Panel, Spinner, StatCard } from "~/lib/ui";

const emptyForm = {
  slug: "",
  name: "",
  language: "",
  description: "",
  content: "",
};

export default function SkillsPage() {
  const [skills, setSkills] = useState<Skill[]>([]);
  const [loading, setLoading] = useState(true);
  const [form, setForm] = useState(emptyForm);
  const [editId, setEditId] = useState<number | null>(null);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [query, setQuery] = useState("");

  async function load() {
    setLoading(true);
    try {
      const r = await fetchSkills();
      setSkills(r.skills);
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    void load();
  }, []);

  function startEdit(skill: Skill) {
    setEditId(skill.id);
    setForm({
      slug: skill.slug,
      name: skill.name,
      language: skill.language ?? "",
      description: skill.description ?? "",
      content: skill.content,
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
      };
      if (editId) {
        await updateSkill(editId, body);
      } else {
        await createSkill(body);
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
    if (!confirm("Delete this skill?")) return;
    try {
      await deleteSkill(id);
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Delete failed");
    }
  }

  const filtered = skills.filter(
    (s) =>
      s.name.toLowerCase().includes(query.toLowerCase()) ||
      s.slug.toLowerCase().includes(query.toLowerCase()) ||
      (s.language || "").toLowerCase().includes(query.toLowerCase()),
  );

  return (
    <div className="space-y-6">
      <PageHeader
        title="Skill Packs & Review Guidance"
        subtitle="Language-focused defensive vulnerability guidance loaded by the AI Master during research planning"
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
        {/* Editor Form */}
        <div className="lg:col-span-5">
          <Panel>
            <div className="mb-4 flex items-center justify-between border-b border-[var(--desk-border-subtle)] pb-3">
              <div className="flex items-center gap-2">
                <Cpu className="h-4 w-4 text-[var(--desk-ink-muted)]" />
                <h2 className="font-display text-sm font-semibold text-[var(--desk-ink)]">
                  {editId ? "Edit Skill Pack" : "New Skill Pack"}
                </h2>
              </div>
              <span className="font-mono text-[10px] text-[var(--desk-ink-faint)]">
                SKILL.MD
              </span>
            </div>

            <form onSubmit={(e) => void onSubmit(e)} className="space-y-3.5">
              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="block font-mono text-[10px] uppercase text-[var(--desk-ink-faint)]">
                    Slug ID
                  </label>
                  <input
                    className="desk-input mt-1 font-mono text-xs"
                    value={form.slug}
                    onChange={(e) => setForm({ ...form, slug: e.target.value })}
                    placeholder="e.g. nodejs-review"
                    required
                  />
                </div>
                <div>
                  <label className="block font-mono text-[10px] uppercase text-[var(--desk-ink-faint)]">
                    Display Name
                  </label>
                  <input
                    className="desk-input mt-1 text-xs"
                    value={form.name}
                    onChange={(e) => setForm({ ...form, name: e.target.value })}
                    placeholder="Node.js Vulnerability Review"
                    required
                  />
                </div>
              </div>

              <div>
                <label className="block font-mono text-[10px] uppercase text-[var(--desk-ink-faint)]">
                  Language Target
                </label>
                <input
                  className="desk-input mt-1 font-mono text-xs"
                  value={form.language}
                  onChange={(e) => setForm({ ...form, language: e.target.value })}
                  placeholder="javascript, typescript, python, go, rust, etc."
                />
              </div>

              <div>
                <label className="block font-mono text-[10px] uppercase text-[var(--desk-ink-faint)]">
                  Short Description
                </label>
                <input
                  className="desk-input mt-1 text-xs"
                  value={form.description}
                  onChange={(e) => setForm({ ...form, description: e.target.value })}
                  placeholder="Summary of flaw types covered by this skill"
                />
              </div>

              <div>
                <label className="block font-mono text-[10px] uppercase text-[var(--desk-ink-faint)]">
                  Skill Instructions (Markdown)
                </label>
                <textarea
                  className="desk-input mt-1 min-h-[190px] font-mono text-xs leading-relaxed text-zinc-300"
                  value={form.content}
                  onChange={(e) => setForm({ ...form, content: e.target.value })}
                  placeholder="Vulnerability patterns, source-to-sink heuristics, critical AST queries..."
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
                  <span>{editId ? "Update Skill" : "Create Skill"}</span>
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

        {/* Skills Library List */}
        <div className="lg:col-span-7">
          <Panel>
            <div className="mb-4 flex items-center justify-between border-b border-[var(--desk-border-subtle)] pb-3">
              <div className="flex items-center gap-2">
                <BookOpen className="h-4 w-4 text-[var(--desk-ink-muted)]" />
                <h2 className="font-display text-sm font-semibold text-[var(--desk-ink)]">
                  Stored Skills Library ({skills.length})
                </h2>
              </div>
              <div className="relative max-w-xs">
                <Search className="absolute left-2.5 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-[var(--desk-ink-faint)]" />
                <input
                  className="desk-input pl-7 text-xs font-mono py-1"
                  placeholder="Filter skills…"
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
                No matching skills found in library.
              </p>
            ) : (
              <div className="space-y-2">
                {filtered.map((s) => (
                  <div
                    key={s.id}
                    className="flex items-start justify-between gap-3 rounded-lg border border-[var(--desk-border)] bg-[var(--desk-surface-2)]/50 p-3.5 transition-all hover:border-[var(--desk-border-accent)] hover:bg-[var(--desk-surface-2)]"
                  >
                    <div className="min-w-0 flex-1">
                      <div className="flex items-center gap-2">
                        <span className="font-display text-xs font-semibold text-[var(--desk-ink)]">
                          {s.name}
                        </span>
                        {s.language && (
                          <span className="rounded bg-zinc-800 px-1.5 py-0.5 font-mono text-[9px] uppercase text-zinc-300">
                            {s.language}
                          </span>
                        )}
                        {s.source === "builtin" && (
                          <span className="rounded border border-zinc-700 bg-zinc-800/80 px-1.5 py-0.5 font-mono text-[9px] text-[var(--desk-ink-faint)]">
                            BUILTIN
                          </span>
                        )}
                      </div>
                      <p className="font-mono text-[11px] text-[var(--desk-ink-faint)]">
                        slug: {s.slug}
                      </p>
                      {s.description && (
                        <p className="mt-1 text-xs text-[var(--desk-ink-muted)] line-clamp-2">
                          {s.description}
                        </p>
                      )}
                    </div>

                    <div className="flex shrink-0 items-center gap-1.5">
                      <button
                        type="button"
                        className="desk-btn desk-btn-ghost desk-btn-xs font-mono"
                        onClick={() => startEdit(s)}
                      >
                        <Edit2 className="h-3 w-3" />
                        <span>Edit</span>
                      </button>
                      {s.source !== "builtin" && (
                        <button
                          type="button"
                          className="desk-btn desk-btn-danger desk-btn-xs font-mono"
                          onClick={() => void onDelete(s.id)}
                        >
                          <Trash2 className="h-3 w-3" />
                        </button>
                      )}
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
