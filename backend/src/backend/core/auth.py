from __future__ import annotations

import base64
import hashlib
import hmac
import json
import time
from collections import defaultdict

from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Receive, Scope, Send

from backend.core import config

_PUBLIC = {
    ("POST", "/api/auth/login"),
    ("GET", "/api/auth/me"),
}
_FAILS: dict[str, list[float]] = defaultdict(list)
_FAIL_WINDOW = 60.0
_FAIL_LIMIT = 8


def auth_configured() -> bool:
    return bool(config.AUTH_USERNAME and config.AUTH_PASSWORD)


def _secret() -> bytes:
    if config.AUTH_SECRET:
        return config.AUTH_SECRET.encode()
    material = f"{config.AUTH_USERNAME}\0{config.AUTH_PASSWORD}".encode()
    return hashlib.sha256(material).digest()


def _eq(left: str, right: str) -> bool:
    return hmac.compare_digest(
        hashlib.sha256(left.encode()).digest(),
        hashlib.sha256(right.encode()).digest(),
    )


def credentials_match(username: str, password: str) -> bool:
    if not auth_configured():
        return False
    return _eq(username, config.AUTH_USERNAME) and _eq(password, config.AUTH_PASSWORD)


def _b64(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode().rstrip("=")


def _unb64(raw: str) -> bytes:
    return base64.urlsafe_b64decode(raw + "=" * (-len(raw) % 4))


def issue_token(username: str, now: float | None = None) -> tuple[str, int]:
    issued = int(now if now is not None else time.time())
    expires = issued + config.AUTH_TOKEN_TTL_SECONDS
    header = _b64(json.dumps({"alg": "HS256", "typ": "JWT"}, separators=(",", ":")).encode())
    payload = _b64(
        json.dumps(
            {"sub": username, "iat": issued, "exp": expires},
            separators=(",", ":"),
        ).encode()
    )
    signing_input = f"{header}.{payload}".encode()
    signature = _b64(hmac.new(_secret(), signing_input, hashlib.sha256).digest())
    return f"{header}.{payload}.{signature}", expires


def read_username(token: str | None, now: float | None = None) -> str | None:
    if not token or token.count(".") != 2 or not auth_configured():
        return None
    header_b64, payload_b64, signature = token.split(".")
    try:
        header = json.loads(_unb64(header_b64))
        if header.get("alg") != "HS256":
            return None
        payload = json.loads(_unb64(payload_b64))
        username = str(payload["sub"])
        expires = int(payload["exp"])
    except (KeyError, TypeError, ValueError, json.JSONDecodeError):
        return None
    expected = _b64(
        hmac.new(_secret(), f"{header_b64}.{payload_b64}".encode(), hashlib.sha256).digest()
    )
    if not hmac.compare_digest(signature, expected):
        return None
    if expires <= int(now if now is not None else time.time()):
        return None
    if not _eq(username, config.AUTH_USERNAME):
        return None
    return config.AUTH_USERNAME


def request_token(request: Request) -> str | None:
    header = request.headers.get("authorization", "").strip()
    if header.lower().startswith("bearer "):
        token = header[7:].strip()
        return token or None
    api_key = request.headers.get("x-api-key", "").strip()
    return api_key or None


def request_username(request: Request) -> str | None:
    return read_username(request_token(request))


def login_limited(ip: str, now: float | None = None) -> bool:
    current = now if now is not None else time.time()
    recent = [stamp for stamp in _FAILS[ip] if current - stamp < _FAIL_WINDOW]
    _FAILS[ip] = recent
    return len(recent) >= _FAIL_LIMIT


def record_login_failure(ip: str, now: float | None = None) -> None:
    _FAILS[ip].append(now if now is not None else time.time())


class AuthMiddleware:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        request = Request(scope)
        if request.method == "OPTIONS" or not request.url.path.startswith("/api"):
            await self.app(scope, receive, send)
            return
        if (request.method, request.url.path) in _PUBLIC:
            await self.app(scope, receive, send)
            return
        if not auth_configured():
            response = JSONResponse(
                status_code=503,
                content={
                    "detail": "Login is not configured. Set AUTH_USERNAME and AUTH_PASSWORD in .env."
                },
            )
            await response(scope, receive, send)
            return
        username = request_username(request)
        if not username:
            response = JSONResponse(status_code=401, content={"detail": "Not authenticated"})
            await response(scope, receive, send)
            return
        scope.setdefault("state", {})
        if isinstance(scope["state"], dict):
            scope["state"]["user"] = username
        await self.app(scope, receive, send)
