"""ASGI middleware: request id and access logging."""

from __future__ import annotations

import logging
import time
from typing import Any, Callable, Dict

from app.core.logging import REQUEST_ID_HEADER, get_request_id, request_context

logger = logging.getLogger("app.access")

#: Health checks and asset requests would otherwise dominate the log.
QUIET_PATHS = frozenset({"/", "/health", "/favicon.ico"})


class RequestIdMiddleware:
    """Give every HTTP request an id, log its outcome, and echo the id back.

    Written as raw ASGI rather than Starlette's ``BaseHTTPMiddleware`` for two
    reasons: ``BaseHTTPMiddleware`` runs the downstream app in a separate task,
    which complicates context propagation, and it buffers the response body,
    which would break Socket.IO's long-lived connections.

    An inbound ``X-Request-ID`` is honoured so a trace can start at the client
    or an upstream proxy; otherwise one is generated.
    """

    def __init__(self, app: Callable) -> None:
        self.app = app

    async def __call__(self, scope: Dict[str, Any], receive: Callable, send: Callable):
        if scope["type"] != "http":
            # WebSocket frames are traced per event in the Socket.IO handlers,
            # since one connection carries many independent actions.
            return await self.app(scope, receive, send)

        headers = {k.lower(): v for k, v in scope.get("headers", [])}
        incoming = headers.get(REQUEST_ID_HEADER.encode(), b"").decode("latin-1")

        with request_context(incoming) as request_id:
            started = time.perf_counter()
            status_code = 500

            async def send_with_id(message: Dict[str, Any]) -> None:
                nonlocal status_code
                if message["type"] == "http.response.start":
                    status_code = message["status"]
                    message.setdefault("headers", []).append(
                        (REQUEST_ID_HEADER.encode(), request_id.encode())
                    )
                await send(message)

            try:
                await self.app(scope, receive, send_with_id)
            except Exception:
                # Log with the id attached before the exception handler turns
                # it into a 500 — otherwise the traceback is uncorrelated.
                logger.exception(
                    "%s %s failed", scope.get("method"), scope.get("path")
                )
                raise
            finally:
                path = scope.get("path", "")
                if path not in QUIET_PATHS:
                    logger.info(
                        "%s %s %s %.0fms",
                        scope.get("method"),
                        path,
                        status_code,
                        (time.perf_counter() - started) * 1000,
                    )


def current_request_id() -> str:
    """The id of the work in flight, for passing across a process boundary."""
    return get_request_id()
