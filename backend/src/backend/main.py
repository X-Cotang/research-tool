from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.api import agent, chat, findings, jobs, library, orgs, projects, prompts, runs, settings, skills, status
from backend.core import config
from backend.core.db import init_db
from backend.domain.library import recover_stale_jobs, sync_research_dir
from backend.domain.logs import log_hub


@asynccontextmanager
async def lifespan(_app: FastAPI):
    log_hub.bind(asyncio.get_running_loop())
    config.ensure_dirs()
    init_db()
    recover_stale_jobs()
    sync_research_dir()
    from backend.domain.supervisor import supervise_forever

    supervisor_task = asyncio.create_task(supervise_forever())
    try:
        yield
    finally:
        supervisor_task.cancel()


app = FastAPI(title="Research Tool", version="0.2.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

_prefix = "/api"
app.include_router(status.router, prefix=_prefix, tags=["status"])
app.include_router(settings.router, prefix=_prefix, tags=["settings"])
app.include_router(orgs.router, prefix=_prefix, tags=["orgs"])
app.include_router(projects.router, prefix=_prefix, tags=["projects"])
app.include_router(library.router, prefix=_prefix, tags=["library"])
app.include_router(jobs.router, prefix=_prefix, tags=["jobs"])
app.include_router(chat.router, prefix=_prefix, tags=["chat"])
app.include_router(skills.router, prefix=_prefix, tags=["skills"])
app.include_router(prompts.router, prefix=_prefix, tags=["prompts"])
app.include_router(runs.router, prefix=_prefix, tags=["runs"])
app.include_router(findings.router, prefix=_prefix, tags=["findings"])
app.include_router(agent.router, prefix=_prefix, tags=["agent"])


def main() -> None:
    import uvicorn

    uvicorn.run("backend.main:app", host=config.HOST, port=config.PORT, reload=False)
