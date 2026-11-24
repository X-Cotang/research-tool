import { useEffect, useState } from "react";
import { Link, useNavigate } from "react-router";
import {
  Bot,
  Calendar,
  MessageSquare,
  Plus,
  Search,
  Sparkles,
  Terminal,
  Trash2,
} from "lucide-react";

import {
  createConversation,
  deleteConversation,
  fetchConversations,
  type Conversation,
} from "~/lib/api";
import { PageHeader, Panel, Spinner } from "~/lib/ui";

export default function ChatPage() {
  const [conversations, setConversations] = useState<Conversation[]>([]);
  const [loading, setLoading] = useState(true);
  const [creating, setCreating] = useState(false);
  const [query, setQuery] = useState("");
  const [error, setError] = useState<string | null>(null);
  const navigate = useNavigate();

  async function load() {
    setLoading(true);
    try {
      const r = await fetchConversations();
      setConversations(r.conversations);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to load");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    void load();
  }, []);

  async function newChat() {
    setCreating(true);
    try {
      const { conversation } = await createConversation();
      navigate(`/chat/${conversation.id}`);
    } finally {
      setCreating(false);
    }
  }

  async function onDelete(id: number, e: React.MouseEvent) {
    e.preventDefault();
    e.stopPropagation();
    if (!window.confirm("Delete this conversation and all logs?")) return;
    await deleteConversation(id);
    setConversations((prev) => prev.filter((c) => c.id !== id));
  }

  const filtered = conversations.filter((c) =>
    (c.title || "").toLowerCase().includes(query.toLowerCase()),
  );

  return (
    <div>
      <PageHeader
        title="Master Chat"
        subtitle="Autonomous AI planner conversations with tool execution logs, skills, and memory"
        actions={
          <button
            type="button"
            className="desk-btn desk-btn-primary"
            disabled={creating}
            onClick={() => void newChat()}
          >
            {creating ? <Spinner /> : <Plus className="h-4 w-4" />}
            New Session
          </button>
        }
      />

      {error ? <p className="mb-4 text-sm text-[var(--desk-danger)]">{error}</p> : null}

      <div className="mb-4 flex items-center justify-between gap-4">
        <div className="relative max-w-sm flex-1">
          <Search className="absolute left-3 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-[var(--desk-ink-faint)]" />
          <input
            className="desk-input pl-8 text-xs"
            placeholder="Search conversations…"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
          />
        </div>
        <div className="font-mono text-xs text-[var(--desk-ink-faint)]">
          {conversations.length} total sessions
        </div>
      </div>

      <Panel>
        {loading ? (
          <div className="flex justify-center py-12">
            <Spinner />
          </div>
        ) : filtered.length === 0 ? (
          <div className="py-12 text-center">
            <div className="mx-auto mb-3 flex h-12 w-12 items-center justify-center rounded-2xl border border-[var(--desk-border)] bg-[var(--desk-surface-2)] text-[var(--desk-ink-muted)]">
              <MessageSquare className="h-6 w-6" />
            </div>
            <p className="font-medium text-[var(--desk-ink)]">
              {query ? "No matching conversations" : "No conversations yet"}
            </p>
            <p className="mt-1 text-xs text-[var(--desk-ink-muted)]">
              {query
                ? "Try searching for a different keyword"
                : "Start a new session with the AI Master to plan vulnerability research"}
            </p>
            {!query && (
              <button
                type="button"
                className="desk-btn desk-btn-primary mt-4 text-xs"
                onClick={() => void newChat()}
              >
                <Plus className="h-3.5 w-3.5" />
                Start First Session
              </button>
            )}
          </div>
        ) : (
          <div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-3">
            {filtered.map((c) => (
              <Link
                key={c.id}
                to={`/chat/${c.id}`}
                className="group relative flex flex-col justify-between rounded-lg border border-[var(--desk-border)] bg-[var(--desk-surface-2)]/60 p-4 transition-all hover:border-[var(--desk-border-accent)] hover:bg-[var(--desk-surface-2)] hover:shadow-lg"
              >
                <div>
                  <div className="flex items-start justify-between gap-2">
                    <span className="font-mono text-[10px] uppercase text-[var(--desk-ink-faint)]">
                      Session #{c.id}
                    </span>
                    <button
                      type="button"
                      title="Delete conversation"
                      onClick={(e) => void onDelete(c.id, e)}
                      className="rounded p-1 text-[var(--desk-ink-faint)] opacity-0 transition-opacity hover:text-[var(--desk-danger)] group-hover:opacity-100"
                    >
                      <Trash2 className="h-3.5 w-3.5" />
                    </button>
                  </div>
                  <h3 className="mt-1 font-display text-sm font-medium text-[var(--desk-ink)] line-clamp-2 group-hover:text-[var(--desk-accent)]">
                    {c.title || "Untitled Session"}
                  </h3>
                </div>

                <div className="mt-4 flex items-center justify-between border-t border-[var(--desk-border-subtle)] pt-2 text-[10px] text-[var(--desk-ink-faint)]">
                  <span className="flex items-center gap-1 font-mono">
                    <Calendar className="h-3 w-3" />
                    {c.updated_at ? new Date(c.updated_at).toLocaleDateString() : "Just now"}
                  </span>
                  <span className="font-mono text-[var(--desk-ink-muted)] group-hover:underline">
                    Open →
                  </span>
                </div>
              </Link>
            ))}
          </div>
        )}
      </Panel>
    </div>
  );
}
