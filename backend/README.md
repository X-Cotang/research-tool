# Backend

FastAPI + SQLite research desk API.

```bash
uv sync
uv run backend
```

Listens on `127.0.0.1:8765` by default. See [../README.md](../README.md) for full setup.

## Migrate from research-tool-old

```bash
uv run python scripts/migrate_from_old.py --parse-findings
```

Copies legacy SQLite rows (orgs, projects, jobs, scans, cursors, settings), syncs clone trees from `research-tool-old/research` into `../research`, rewrites `local_path` values, keeps existing chats/skills/harness data, and re-adds any projects that only existed in the new DB.
