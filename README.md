# Research Tool

Local security-research desk: discover GitHub targets, run CLI analysis workers, and chat with a built-in **AI Master** that can plan work, pick skills/prompts, and queue multi-project runs.

## Stack

| Layer | Tech |
|-------|------|
| Frontend | React Router 8, Tailwind 4, Vite |
| Backend | FastAPI, SQLite, httpx |
| Workers | External CLIs (`command-code`, `opencode`, `freebuff`, `claude`, `codex`) |
| AI Master | Built-in OpenAI-compatible tool-calling agent (not a CLI) |

## Quick start

```bash
# Backend (port 8765)
cd backend
cp ../.env.example ../.env   # optional
uv sync
uv run backend

# Frontend (port 5173, proxies /api → backend)
cd frontend
npm install
npm run dev
```

Open http://127.0.0.1:5173

## Pages

- **Dashboard** — status, recent scans, quick org discover
- **Projects** — candidates / library, project detail, manual research + live job logs
- **Chat** — full AI Master conversation (also a floating mini chatbox on every page)
- **Runs** — multi-project batch progress
- **Skills / Prompts** — libraries the Master can select when planning research
- **Findings** — parsed candidates from research notes (verify / triage)
- **Settings** — GitHub token, AI Master credentials, research CLI presets, SAST

## Workflow

1. Configure GitHub + AI Master under **Settings**.
2. Discover an org from the Dashboard/Projects, or ask the Master to `scan_org`.
3. Run research manually on a project, or ask the Master to suggest a prompt / queue jobs.
4. For batches, the Master creates a **Run**; when jobs finish, a summary message is posted back to the conversation.
5. Parse **Findings** from `RESEARCH_NOTES.md` and triage status.

## On-disk layout

```text
research-tool/
  backend/          # FastAPI app (uv)
  frontend/         # React Router app
  skills/           # SKILL.md packs (seeded into SQLite)
  data/research.db  # SQLite (created at runtime)
  research/         # cloned targets + notes
```

## API

OpenAPI docs: http://127.0.0.1:8765/docs

Key groups: `/api/status`, `/api/settings/*`, `/api/scan`, `/api/projects`, `/api/jobs/{id}/stream`, `/api/chat/*`, `/api/skills`, `/api/prompts`, `/api/runs`, `/api/findings`.
