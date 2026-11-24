import { useEffect, useState } from "react";
import { useLocation, useNavigate } from "react-router";

import { fetchAuth } from "~/lib/api";

export function RequireAuth({ children }: { children: React.ReactNode }) {
  const [ready, setReady] = useState(false);
  const location = useLocation();
  const navigate = useNavigate();

  useEffect(() => {
    let live = true;
    const next = `${location.pathname}${location.search}`;
    fetchAuth()
      .then((auth) => {
        if (!live) return;
        if (auth.authenticated) {
          setReady(true);
          return;
        }
        navigate(`/login?next=${encodeURIComponent(next)}`, { replace: true });
      })
      .catch(() => {
        if (!live) return;
        navigate(`/login?next=${encodeURIComponent(next)}`, { replace: true });
      });
    return () => {
      live = false;
    };
    // Re-check only when the shell mounts. Expired calls redirect from the API client.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  if (!ready) {
    return (
      <div className="grid min-h-screen place-items-center">
        <div className="flex items-center gap-3 font-mono text-[11px] uppercase tracking-[0.22em] text-[var(--desk-ink-faint)]">
          <span className="h-1.5 w-1.5 rounded-full bg-[var(--desk-success)] tech-pulse" />
          Checking token
        </div>
      </div>
    );
  }

  return children;
}
