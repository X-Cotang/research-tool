import { useEffect, useState, type FormEvent } from "react";
import { useNavigate, useSearchParams } from "react-router";
import { ArrowRight, Eye, EyeOff, LockKeyhole, Shield, UserRound } from "lucide-react";

import { ApiError, fetchAuth, login } from "~/lib/api";

function safeNext(raw: string | null): string {
  if (!raw || !raw.startsWith("/") || raw.startsWith("//") || raw.startsWith("/login")) return "/";
  return raw;
}

export default function LoginPage() {
  const navigate = useNavigate();
  const [params] = useSearchParams();
  const next = safeNext(params.get("next"));
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [error, setError] = useState("");
  const [configured, setConfigured] = useState(true);
  const [submitting, setSubmitting] = useState(false);

  useEffect(() => {
    let live = true;
    fetchAuth()
      .then((auth) => {
        if (!live) return;
        setConfigured(auth.configured);
        if (!auth.configured) {
          setError("Set AUTH_USERNAME and AUTH_PASSWORD in .env, then restart the backend.");
        }
        if (auth.authenticated) navigate(next, { replace: true });
      })
      .catch(() => {
        if (live) setError("Cannot reach the desk API. Start the backend and try again.");
      });
    return () => {
      live = false;
    };
  }, [navigate, next]);

  async function onSubmit(event: FormEvent) {
    event.preventDefault();
    setError("");
    setSubmitting(true);
    try {
      await login(username.trim(), password);
      navigate(next, { replace: true });
    } catch (err) {
      const message = err instanceof ApiError ? err.message : "Sign-in failed";
      setError(message);
      if (err instanceof ApiError && err.status === 503) setConfigured(false);
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <main className="relative min-h-screen overflow-hidden">
      <div className="login-aurora" />
      <div className="login-grid" />

      <div className="relative mx-auto grid min-h-screen w-full max-w-6xl items-center gap-12 px-6 py-12 lg:grid-cols-[1.15fr_0.85fr] lg:px-10">
        <section className="hidden lg:block">
          <div className="mb-8 flex items-center gap-3 font-mono text-[10px] uppercase tracking-[0.28em] text-[var(--desk-ink-faint)]">
            <span className="h-1.5 w-1.5 rounded-full bg-[var(--desk-success)] tech-pulse" />
            Research // Desk
            <span className="text-zinc-700">/</span>
            Access gate
          </div>

          <h1 className="max-w-xl font-display text-5xl font-semibold leading-[1.05] tracking-tight text-zinc-50">
            A local desk for the work that stays on this machine.
          </h1>
          <p className="mt-5 max-w-md text-sm leading-relaxed text-[var(--desk-ink-muted)]">
            One operator. One API token. Credentials live in the environment file and never pass through a third-party account.
          </p>

          <div className="mt-10 grid max-w-lg grid-cols-3 gap-3">
            {[
              ["01", "JWT", "Valid 1 year"],
              ["02", "Bearer key", "Authorization"],
              ["03", "Local only", "Env credentials"],
            ].map(([index, title, detail]) => (
              <div key={index} className="login-spec">
                <div className="font-mono text-[10px] text-[var(--desk-ink-faint)]">{index}</div>
                <div className="mt-3 text-sm font-medium text-zinc-100">{title}</div>
                <div className="mt-1 font-mono text-[10px] uppercase tracking-wider text-zinc-500">{detail}</div>
              </div>
            ))}
          </div>
        </section>

        <section className="login-card desk-panel mx-auto w-full max-w-md p-7 sm:p-8">
          <div className="mb-8 flex items-center justify-between">
            <div className="flex items-center gap-3">
              <div className="flex h-10 w-10 items-center justify-center rounded-lg border border-[var(--desk-border-accent)] bg-zinc-900 text-zinc-100">
                <Shield className="h-4 w-4" />
              </div>
              <div>
                <div className="font-display text-base font-semibold tracking-tight">Security Tool</div>
                <div className="font-mono text-[10px] uppercase tracking-[0.18em] text-[var(--desk-ink-faint)]">
                  Operator sign-in
                </div>
              </div>
            </div>
            <span className="rounded border border-[var(--desk-border)] bg-zinc-900/70 px-1.5 py-0.5 font-mono text-[10px] text-zinc-500">
              v2.5
            </span>
          </div>

          <form onSubmit={onSubmit} className="space-y-4">
            <label className="block">
              <span className="mb-1.5 flex items-center gap-1.5 font-mono text-[10px] uppercase tracking-[0.16em] text-[var(--desk-ink-faint)]">
                <UserRound className="h-3 w-3" />
                Username
              </span>
              <input
                className="desk-input h-11"
                autoComplete="username"
                autoFocus
                value={username}
                onChange={(event) => setUsername(event.target.value)}
                placeholder="env username"
                required
              />
            </label>

            <label className="block">
              <span className="mb-1.5 flex items-center gap-1.5 font-mono text-[10px] uppercase tracking-[0.16em] text-[var(--desk-ink-faint)]">
                <LockKeyhole className="h-3 w-3" />
                Password
              </span>
              <div className="relative">
                <input
                  className="desk-input h-11 pr-11"
                  type={showPassword ? "text" : "password"}
                  autoComplete="current-password"
                  value={password}
                  onChange={(event) => setPassword(event.target.value)}
                  placeholder="env password"
                  required
                />
                <button
                  type="button"
                  className="absolute top-1/2 right-2 grid h-7 w-7 -translate-y-1/2 place-items-center rounded text-zinc-500 hover:text-zinc-200"
                  onClick={() => setShowPassword((value) => !value)}
                  aria-label={showPassword ? "Hide password" : "Show password"}
                >
                  {showPassword ? <EyeOff className="h-3.5 w-3.5" /> : <Eye className="h-3.5 w-3.5" />}
                </button>
              </div>
            </label>

            {error ? (
              <div className="rounded-md border border-red-500/30 bg-red-500/10 px-3 py-2 text-xs leading-relaxed text-red-200">
                {error}
              </div>
            ) : null}

            <button
              type="submit"
              className="desk-btn desk-btn-primary mt-2 h-11 w-full text-sm"
              disabled={submitting || !configured}
            >
              {submitting ? "Verifying…" : "Enter the desk"}
              <ArrowRight className="h-3.5 w-3.5" />
            </button>
          </form>

          <p className="mt-6 font-mono text-[10px] leading-relaxed tracking-wide text-zinc-600">
            JWT · BEARER · 1 YEAR · LOCAL ENV
          </p>
        </section>
      </div>
    </main>
  );
}
