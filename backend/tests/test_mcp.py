import asyncio
import json
import os
import tempfile

_root = tempfile.mkdtemp(prefix="research-mcp-")
os.environ["DATA_DIR"] = _root
os.environ["RESEARCH_DIR"] = os.path.join(_root, "research")
os.environ["SKILLS_DIR"] = os.path.join(_root, "skills")
os.environ["ROOT_DIR"] = _root
os.environ["AUTH_USERNAME"] = "mcp-admin"
os.environ["AUTH_PASSWORD"] = "mcp-secret"
os.environ["AUTH_SECRET"] = "mcp-test-secret"

import httpx2
import pytest
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client

from backend.core.auth import issue_token
from backend.core.db import db
from backend.main import app


def _seed() -> int:
    with db() as conn:
        conn.execute(
            "INSERT INTO organizations (login, name, html_url) VALUES (?, ?, ?)",
            ("acme", "acme", "https://github.com/acme"),
        )
        org_id = conn.execute("SELECT id FROM organizations WHERE login = ?", ("acme",)).fetchone()["id"]
        cur = conn.execute(
            """
            INSERT INTO projects (
                org_id, full_name, name, html_url, clone_url, stars, language, research_status
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                org_id,
                "acme/widget",
                "widget",
                "https://github.com/acme/widget",
                "https://github.com/acme/widget.git",
                12,
                "Python",
                "idle",
            ),
        )
        return int(cur.lastrowid)


async def _session(token: str | None):
    headers = {}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    client = httpx2.AsyncClient(
        transport=httpx2.ASGITransport(app=app),
        base_url="http://testserver",
        headers=headers,
    )
    streams = streamable_http_client("http://testserver/mcp", http_client=client)
    return client, streams


def test_mcp_requires_admin_token_and_queues_a_task(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("backend.mcp_desk.schedule_job", lambda *_a, **_k: True)

    async def run() -> None:
        async with app.router.lifespan_context(app):
            project_id = _seed()
            token, _expires = issue_token("mcp-admin")

            bare = httpx2.AsyncClient(
                transport=httpx2.ASGITransport(app=app),
                base_url="http://testserver",
            )
            async with bare:
                denied = await bare.post(
                    "/mcp",
                    json={"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}},
                    headers={"content-type": "application/json", "accept": "application/json, text/event-stream"},
                )
            assert denied.status_code == 401

            client, streams = await _session(token)
            async with client:
                async with streams as (read, write):
                    async with ClientSession(read, write) as session:
                        await session.initialize()
                        listed = await session.list_tools()
                        names = {tool.name for tool in listed.tools}
                        assert "research_create_task" in names
                        assert "research_get_task" in names

                        who = await session.call_tool("research_whoami", {})
                        who_body = json.loads(who.content[0].text)
                        assert who_body["ok"] is True
                        assert who_body["username"] == "mcp-admin"

                        repos = await session.call_tool("research_list_repos", {"org": "acme"})
                        repo_body = json.loads(repos.content[0].text)
                        assert repo_body["repos"][0]["full_name"] == "acme/widget"

                        created = await session.call_tool(
                            "research_create_task",
                            {"project_id": project_id},
                        )
                        created_body = json.loads(created.content[0].text)
                        assert created_body["created"] is True
                        job_id = created_body["job_id"]

                        again = await session.call_tool(
                            "research_create_task",
                            {"full_name": "acme/widget"},
                        )
                        again_body = json.loads(again.content[0].text)
                        assert again_body["created"] is False
                        assert again_body["job_id"] == job_id

                        task = await session.call_tool("research_get_task", {"job_id": job_id})
                        task_body = json.loads(task.content[0].text)
                        assert task_body["task"]["status"] == "queued"
                        assert task_body["task"]["full_name"] == "acme/widget"
                        assert "command" not in task_body["task"]

    asyncio.run(run())
