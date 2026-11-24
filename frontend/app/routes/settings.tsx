import { useEffect, useState } from "react";
import {
  Bot,
  Check,
  CheckCircle2,
  Cpu,
  Key,
  Layers,
  Save,
  Search,
  Server,
  Shield,
  ShieldCheck,
  Terminal,
} from "lucide-react";

import { GithubIcon } from "~/components/GithubIcon";

import {
  fetchAiSettings,
  fetchGithubSettings,
  fetchSastSettings,
  fetchSettings,
  fetchStatus,
  testAiSettings,
  testGithubSettings,
  updateAiSettings,
  updateGithubSettings,
  updateSastSettings,
  updateSettings,
  type ResearchPreset,
  type SettingsResponse,
} from "~/lib/api";
import { PageHeader, Panel, Spinner } from "~/lib/ui";

export default function SettingsPage() {
  const [research, setResearch] = useState<SettingsResponse | null>(null);
  const [presets, setPresets] = useState<ResearchPreset[]>([]);
  const [command, setCommand] = useState("");
  const [preset, setPreset] = useState("");
  const [github, setGithub] = useState<Record<string, unknown>>({});
  const [githubToken, setGithubToken] = useState("");
  const [ai, setAi] = useState<Record<string, unknown>>({});
  const [aiForm, setAiForm] = useState({
    ai_base_url: "",
    ai_api_key: "",
    ai_model: "",
  });
  const [sast, setSast] = useState({
    sast_enabled: false,
    sast_tool: "semgrep",
    sast_timeout: 120,
  });
  const [loading, setLoading] = useState(true);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState<string | null>(null);

  useEffect(() => {
    Promise.all([
      fetchSettings(),
      fetchStatus(),
      fetchGithubSettings(),
      fetchAiSettings(),
      fetchSastSettings(),
    ])
      .then(([s, st, gh, aiRes, sastRes]) => {
        setResearch(s);
        setCommand(s.research_command);
        setPreset(s.research_preset);
        setPresets(st.research_presets);
        setGithub(gh);
        setAi(aiRes);
        setAiForm({
          ai_base_url: String(aiRes.ai_base_url ?? ""),
          ai_api_key: "",
          ai_model: String(aiRes.ai_model ?? ""),
        });
        setSast({
          sast_enabled: Boolean(sastRes.sast_enabled),
          sast_tool: sastRes.sast_tool ?? "semgrep",
          sast_timeout: sastRes.sast_timeout ?? 120,
        });
      })
      .catch((e) => setError(e instanceof Error ? e.message : "Load failed"))
      .finally(() => setLoading(false));
  }, []);

  function applyPreset(id: string) {
    setPreset(id);
    const p = presets.find((x) => x.id === id);
    if (p?.command) setCommand(p.command);
  }

  async function saveResearch(e: React.FormEvent) {
    e.preventDefault();
    setBusy("research");
    setMessage(null);
    try {
      const res = await updateSettings({ research_command: command, research_preset: preset });
      setResearch(res);
      setMessage("Research CLI worker configuration saved.");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Save failed");
    } finally {
      setBusy(null);
    }
  }

  async function saveGithub(e: React.FormEvent) {
    e.preventDefault();
    setBusy("github");
    setMessage(null);
    try {
      const body: Record<string, unknown> = {};
      if (githubToken.trim()) body.github_token = githubToken.trim();
      const res = await updateGithubSettings(body);
      setGithub(res);
      setGithubToken("");
      setMessage("GitHub token updated successfully.");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Save failed");
    } finally {
      setBusy(null);
    }
  }

  async function saveAi(e: React.FormEvent) {
    e.preventDefault();
    setBusy("ai");
    setMessage(null);
    try {
      const body: Record<string, unknown> = {};
      if (aiForm.ai_base_url) body.ai_base_url = aiForm.ai_base_url;
      if (aiForm.ai_model) body.ai_model = aiForm.ai_model;
      if (aiForm.ai_api_key) body.ai_api_key = aiForm.ai_api_key;
      const res = await updateAiSettings(body);
      setAi(res);
      setAiForm((f) => ({ ...f, ai_api_key: "" }));
      setMessage("AI Master LLM parameters saved.");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Save failed");
    } finally {
      setBusy(null);
    }
  }

  async function saveSast(e: React.FormEvent) {
    e.preventDefault();
    setBusy("sast");
    setMessage(null);
    try {
      const res = await updateSastSettings(sast);
      setSast({
        sast_enabled: Boolean(res.sast_enabled),
        sast_tool: res.sast_tool ?? "semgrep",
        sast_timeout: res.sast_timeout ?? 120,
      });
      setMessage("Static Application Security Testing (SAST) settings saved.");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Save failed");
    } finally {
      setBusy(null);
    }
  }

  if (loading) {
    return (
      <div className="flex justify-center py-24">
        <Spinner />
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <PageHeader
        title="Settings & Configuration"
        subtitle="Manage GitHub API credentials, AI Master endpoints, external CLI presets, and static analysis"
      />

      {message ? (
        <div className="flex items-center gap-2 rounded-md border border-emerald-500/30 bg-emerald-500/10 p-3 text-xs text-[var(--desk-success)]">
          <CheckCircle2 className="h-4 w-4 shrink-0" />
          <span>{message}</span>
        </div>
      ) : null}

      {error ? (
        <div className="rounded-md border border-red-500/30 bg-red-500/10 p-3 text-xs text-[var(--desk-danger)]">
          {error}
        </div>
      ) : null}

      <div className="grid gap-6">
        {/* GitHub Settings */}
        <Panel>
          <div className="mb-4 flex items-center justify-between border-b border-[var(--desk-border-subtle)] pb-3">
            <div className="flex items-center gap-2.5">
              <GithubIcon className="h-4 w-4 text-[var(--desk-ink-muted)]" />
              <h2 className="font-display text-sm font-semibold text-[var(--desk-ink)]">
                GitHub Authentication
              </h2>
            </div>
            <span
              className={`font-mono text-xs ${
                github.has_github_token ? "text-[var(--desk-success)]" : "text-amber-400"
              }`}
            >
              {github.has_github_token ? "● TOKEN ACTIVE" : "○ TOKEN MISSING"}
            </span>
          </div>

          <p className="mb-4 text-xs text-[var(--desk-ink-muted)]">
            Used for discovering organization repositories, reading repository metadata, stars, and language stats without rate limiting.
          </p>

          <form onSubmit={(e) => void saveGithub(e)} className="flex flex-wrap items-end gap-3">
            <div className="min-w-[280px] flex-1">
              <label className="block font-mono text-[11px] uppercase text-[var(--desk-ink-faint)]">
                Personal Access Token (classic or fine-grained)
              </label>
              <input
                type="password"
                className="desk-input mt-1 font-mono text-xs"
                value={githubToken}
                onChange={(e) => setGithubToken(e.target.value)}
                placeholder={github.has_github_token ? "ghp_••••••••••••••••" : "ghp_..."}
                autoComplete="off"
              />
            </div>
            <button
              type="submit"
              className="desk-btn desk-btn-primary"
              disabled={busy === "github"}
            >
              {busy === "github" ? <Spinner /> : <Save className="h-3.5 w-3.5" />}
              <span>Save Token</span>
            </button>
            <button
              type="button"
              className="desk-btn desk-btn-ghost"
              onClick={() =>
                void testGithubSettings().then((r) =>
                  setMessage(String(r.message ?? "GitHub API connection OK"))
                )
              }
            >
              Test Connection
            </button>
          </form>
        </Panel>

        {/* AI Master Credentials */}
        <Panel>
          <div className="mb-4 flex items-center justify-between border-b border-[var(--desk-border-subtle)] pb-3">
            <div className="flex items-center gap-2.5">
              <Bot className="h-4 w-4 text-[var(--desk-ink-muted)]" />
              <h2 className="font-display text-sm font-semibold text-[var(--desk-ink)]">
                AI Master Agent (OpenAI-Compatible Tool Calling)
              </h2>
            </div>
            <span className="font-mono text-xs text-zinc-400">
              {aiForm.ai_model || "gpt-4o"}
            </span>
          </div>

          <form onSubmit={(e) => void saveAi(e)} className="grid gap-4 sm:grid-cols-2">
            <div className="sm:col-span-2">
              <label className="block font-mono text-[11px] uppercase text-[var(--desk-ink-faint)]">
                OpenAI-Compatible Base URL
              </label>
              <input
                className="desk-input mt-1 font-mono text-xs"
                value={aiForm.ai_base_url}
                onChange={(e) => setAiForm({ ...aiForm, ai_base_url: e.target.value })}
                placeholder="https://api.openai.com/v1"
              />
            </div>
            <div>
              <label className="block font-mono text-[11px] uppercase text-[var(--desk-ink-faint)]">
                Model Name
              </label>
              <input
                className="desk-input mt-1 font-mono text-xs"
                value={aiForm.ai_model}
                onChange={(e) => setAiForm({ ...aiForm, ai_model: e.target.value })}
                placeholder="gpt-4o or claude-3-7-sonnet"
              />
            </div>
            <div>
              <label className="block font-mono text-[11px] uppercase text-[var(--desk-ink-faint)]">
                API Key
              </label>
              <input
                type="password"
                className="desk-input mt-1 font-mono text-xs"
                value={aiForm.ai_api_key}
                onChange={(e) => setAiForm({ ...aiForm, ai_api_key: e.target.value })}
                placeholder={ai.ai_api_key_set ? "•••••••••••• (Set - leave blank to keep)" : "sk-..."}
                autoComplete="off"
              />
            </div>
            <div className="flex gap-2 sm:col-span-2 pt-2">
              <button
                type="submit"
                className="desk-btn desk-btn-primary"
                disabled={busy === "ai"}
              >
                {busy === "ai" ? <Spinner /> : <Save className="h-3.5 w-3.5" />}
                <span>Save AI Settings</span>
              </button>
              <button
                type="button"
                className="desk-btn desk-btn-ghost"
                onClick={() =>
                  void testAiSettings().then((r) =>
                    setMessage(`AI Connection Test: ${JSON.stringify(r)}`)
                  )
                }
              >
                Test AI Endpoint
              </button>
            </div>
          </form>
        </Panel>

        {/* Research CLI Preset */}
        <Panel>
          <div className="mb-4 flex items-center justify-between border-b border-[var(--desk-border-subtle)] pb-3">
            <div className="flex items-center gap-2.5">
              <Terminal className="h-4 w-4 text-[var(--desk-ink-muted)]" />
              <h2 className="font-display text-sm font-semibold text-[var(--desk-ink)]">
                Vulnerability Research CLI Workers
              </h2>
            </div>
            <span className="font-mono text-xs text-[var(--desk-ink-faint)] uppercase">
              Preset: {preset}
            </span>
          </div>

          <form onSubmit={(e) => void saveResearch(e)} className="space-y-4">
            <div>
              <label className="block font-mono text-[11px] uppercase text-[var(--desk-ink-faint)]">
                Preset Selection
              </label>
              <div className="mt-2 flex flex-wrap gap-2">
                {presets.map((p) => (
                  <button
                    key={p.id}
                    type="button"
                    onClick={() => applyPreset(p.id)}
                    className={`rounded-md border px-3 py-1.5 font-mono text-xs transition-colors ${
                      preset === p.id
                        ? "border-[var(--desk-accent)] bg-[var(--desk-accent)] text-[#09090b] font-semibold"
                        : "border-[var(--desk-border)] bg-[var(--desk-surface-2)] text-[var(--desk-ink-muted)] hover:border-zinc-500 hover:text-[var(--desk-ink)]"
                    }`}
                  >
                    {p.label}
                    {p.available ? "" : " (Not installed)"}
                  </button>
                ))}
              </div>
            </div>

            <div>
              <label className="block font-mono text-[11px] uppercase text-[var(--desk-ink-faint)]">
                Command Template
              </label>
              <textarea
                className="desk-input mt-1.5 min-h-[110px] font-mono text-xs leading-relaxed text-zinc-300"
                value={command}
                onChange={(e) => setCommand(e.target.value)}
              />
              <p className="mt-1 font-mono text-[10px] text-[var(--desk-ink-faint)]">
                External CLI invoked during project research jobs. Retain logging flags for live drawer streaming.
              </p>
            </div>

            <button
              type="submit"
              className="desk-btn desk-btn-primary"
              disabled={busy === "research"}
            >
              {busy === "research" ? <Spinner /> : <Save className="h-3.5 w-3.5" />}
              <span>Save Worker Command</span>
            </button>
          </form>
        </Panel>

        {/* SAST Configuration */}
        <Panel>
          <div className="mb-4 flex items-center justify-between border-b border-[var(--desk-border-subtle)] pb-3">
            <div className="flex items-center gap-2.5">
              <ShieldCheck className="h-4 w-4 text-[var(--desk-ink-muted)]" />
              <h2 className="font-display text-sm font-semibold text-[var(--desk-ink)]">
                Static Application Security Testing (SAST)
              </h2>
            </div>
            <span className="font-mono text-xs text-[var(--desk-ink-faint)] uppercase">
              {sast.sast_enabled ? "ENABLED" : "DISABLED"}
            </span>
          </div>

          <form onSubmit={(e) => void saveSast(e)} className="flex flex-wrap items-end gap-4">
            <label className="flex items-center gap-2.5 text-xs font-medium text-[var(--desk-ink)] cursor-pointer">
              <input
                type="checkbox"
                className="h-4 w-4 rounded border-zinc-700 bg-zinc-800 text-white accent-zinc-100"
                checked={sast.sast_enabled}
                onChange={(e) => setSast({ ...sast, sast_enabled: e.target.checked })}
              />
              <span>Enable automated Semgrep scan on repository checkout</span>
            </label>

            <div>
              <label className="block font-mono text-[10px] uppercase text-[var(--desk-ink-faint)]">
                Engine
              </label>
              <select
                className="desk-input mt-1 w-auto font-mono text-xs"
                value={sast.sast_tool}
                onChange={(e) => setSast({ ...sast, sast_tool: e.target.value })}
              >
                <option value="semgrep">Semgrep</option>
                <option value="none">Disabled</option>
              </select>
            </div>

            <div>
              <label className="block font-mono text-[10px] uppercase text-[var(--desk-ink-faint)]">
                Timeout (seconds)
              </label>
              <input
                type="number"
                className="desk-input mt-1 w-24 font-mono text-xs"
                value={sast.sast_timeout}
                onChange={(e) =>
                  setSast({ ...sast, sast_timeout: Number(e.target.value) || 120 })
                }
              />
            </div>

            <button
              type="submit"
              className="desk-btn desk-btn-primary"
              disabled={busy === "sast"}
            >
              {busy === "sast" ? <Spinner /> : <Save className="h-3.5 w-3.5" />}
              <span>Save SAST</span>
            </button>
          </form>
        </Panel>
      </div>
    </div>
  );
}
