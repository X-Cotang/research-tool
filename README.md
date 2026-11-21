# Research Tool

Local security-research desk: discover GitHub targets, run CLI analysis workers, and chat with a built-in **AI Master** that can plan work, pick skills/prompts, and queue multi-project runs.

## Stack

| Layer | Tech |
|-------|------|
| Frontend | React Router 8, Tailwind 4, Vite |
| Backend | FastAPI, SQLite, httpx, MCP (Streamable HTTP) |
| Workers | External CLIs (`command-code`, `opencode`, `freebuff`, `claude`, `codex`, `qoder`) |
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

Hermes reaches the same process at `/mcp`. See below.

## Hermes MCP

The desk exposes eight tools over Streamable HTTP at `/mcp`. Hermes authenticates with the admin login JWT. There is no second API key. The tools list repos, scan an org, queue research, and poll jobs. They use the saved CLI preset and return as soon as the job is queued.

### 1. Desk login

Set `AUTH_USERNAME` and `AUTH_PASSWORD` in `.env` (see `.env.example`). Optional `AUTH_SECRET` is the JWT signing key. If you leave it empty, the key is derived from the username and password, so changing the password invalidates the Hermes token too.

Log in on the desk UI, or:

```bash
curl -s -X POST http://127.0.0.1:8765/api/auth/login \
  -H 'Content-Type: application/json' \
  -d '{"username":"YOUR_USER","password":"YOUR_PASSWORD"}'
```

Copy the `token` field only. Do not include the word `Bearer`. The token lasts 365 days.

To revoke it, rotate `AUTH_SECRET` (or change the password when `AUTH_SECRET` is unset), log in again, and update the Hermes env var.

### 2. Register the server on the Hermes machine

The research desk and Hermes can be different hosts. Hermes only needs outbound HTTPS to the desk.

```bash
hermes mcp add research --url https://desk.example/mcp
```

When asked for a bearer token, paste the login JWT. Hermes stores the header template in its config and the secret in the profile `.env`:

```yaml
mcp_servers:
  research:
    url: https://desk.example/mcp
    headers:
      Authorization: "Bearer ${MCP_RESEARCH_API_KEY}"
```

Then check the connection:

```bash
hermes mcp test research
```

You should see `research_whoami`, `research_list_repos`, `research_scan_org`, `research_create_task`, `research_create_batch`, `research_get_task`, `research_list_tasks`, and `research_list_findings`.

### 3. What to ask Hermes

A working request is: scan an org, list repos that are still idle, queue two of them, then check the jobs. Hermes should call `research_create_task` or `research_create_batch`, keep the `job_id`, and poll `research_get_task` until `status` is `done` or `error`. Findings come from `research_list_findings`.

### Network

Put TLS in front of the desk and point Hermes at that URL. Leave the app bound to loopback and do not publish port 8765. `/mcp` accepts the same `Authorization: Bearer` token as `/api`, so the Hermes env file is a copy of an admin session. The endpoint refuses a missing or expired token with HTTP 401.
