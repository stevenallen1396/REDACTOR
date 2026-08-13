"""HTTP Basic Auth gate, only active when REDACTOR_USERS is configured.

Locally (run.sh) that env var is never set, so the app stays open on
127.0.0.1 exactly as before - only localhost can reach it anyway. When
deployed publicly (see Dockerfile / render.yaml), REDACTOR_USERS is set and
every request - API and static frontend alike - requires a matching login.
"""

from __future__ import annotations

import base64
import os
import secrets

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response


def _load_users() -> dict[str, str]:
    raw = os.environ.get("REDACTOR_USERS", "")
    users = {}
    for pair in raw.split(","):
        pair = pair.strip()
        if not pair or ":" not in pair:
            continue
        username, password = pair.split(":", 1)
        if username and password:
            users[username] = password
    return users


class BasicAuthMiddleware(BaseHTTPMiddleware):
    def __init__(self, app):
        super().__init__(app)
        self._users = _load_users()

    async def dispatch(self, request: Request, call_next):
        if not self._users:
            return await call_next(request)

        if self._check(request.headers.get("authorization")):
            return await call_next(request)

        return Response(
            status_code=401,
            headers={"WWW-Authenticate": 'Basic realm="The REDACTOR"'},
        )

    def _check(self, header: str | None) -> bool:
        if not header or not header.startswith("Basic "):
            return False
        try:
            decoded = base64.b64decode(header[6:]).decode("utf-8")
            username, _, password = decoded.partition(":")
        except Exception:
            return False
        expected = self._users.get(username)
        return expected is not None and secrets.compare_digest(password, expected)
