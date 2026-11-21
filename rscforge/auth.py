from __future__ import annotations

import base64
import secrets

from fastapi import Request
from fastapi.responses import Response

from .config import settings


def _challenge() -> Response:
    return Response(
        content="Authentication required",
        status_code=401,
        headers={"WWW-Authenticate": 'Basic realm="RscForge"'},
    )


async def auth_middleware(request: Request, call_next):
    if request.url.path in {"/healthz"}:
        return await call_next(request)

    if request.url.path == "/export.rsc" and settings.export_token:
        token = request.query_params.get("token", "")
        if secrets.compare_digest(token, settings.export_token):
            return await call_next(request)
        if not settings.password:
            return _challenge()

    if settings.password:
        header = request.headers.get("authorization", "")
        scheme, _, encoded = header.partition(" ")
        if scheme.lower() != "basic" or not encoded:
            return _challenge()
        try:
            decoded = base64.b64decode(encoded).decode("utf-8")
            username, _, password = decoded.partition(":")
        except Exception:
            return _challenge()
        user_ok = secrets.compare_digest(username, settings.username)
        password_ok = secrets.compare_digest(password, settings.password)
        if not (user_ok and password_ok):
            return _challenge()

    return await call_next(request)
