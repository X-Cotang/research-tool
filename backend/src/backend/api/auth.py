from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from backend.core import config
from backend.core.auth import (
    auth_configured,
    credentials_match,
    issue_token,
    login_limited,
    record_login_failure,
    request_username,
)

router = APIRouter()


class LoginBody(BaseModel):
    username: str = Field(min_length=1, max_length=200)
    password: str = Field(min_length=1, max_length=500)


def _client_ip(request: Request) -> str:
    if request.client is None:
        return "local"
    return request.client.host


@router.get("/me")
def me(request: Request) -> dict:
    username = request_username(request)
    return {
        "authenticated": username is not None,
        "configured": auth_configured(),
        "username": username,
    }


@router.post("/login")
def login(body: LoginBody, request: Request) -> dict:
    if not auth_configured():
        raise HTTPException(
            status_code=503,
            detail="Login is not configured. Set AUTH_USERNAME and AUTH_PASSWORD in .env.",
        )
    ip = _client_ip(request)
    if login_limited(ip):
        raise HTTPException(status_code=429, detail="Too many attempts. Wait a minute and try again.")
    username = body.username.strip()
    if not credentials_match(username, body.password):
        record_login_failure(ip)
        raise HTTPException(status_code=401, detail="Invalid username or password")
    token, expires_at = issue_token(config.AUTH_USERNAME)
    return {
        "token": token,
        "token_type": "Bearer",
        "expires_at": expires_at,
        "username": config.AUTH_USERNAME,
    }
