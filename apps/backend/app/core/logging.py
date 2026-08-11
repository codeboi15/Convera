"""Logging with request tracing.

Every log line carries a request id, so one customer action can be followed
across process boundaries:

    HTTP request  ──▶  API log lines  ──▶  queued job  ──▶  worker log lines

The id lives in a :class:`~contextvars.ContextVar`, which asyncio propagates
into every task spawned from the request, so nothing has to thread it through
function signatures. A logging filter reads it back out at emit time.

Grep one id and you get the whole story:

    2026-08-12 09:14:02 INFO  [a3f1c2d4e5b60718] app.api: POST /api/... 201 42ms
    2026-08-12 09:14:02 INFO  [a3f1c2d4e5b60718] ...dispatch: queued send_email
    2026-08-12 09:14:03 INFO  [a3f1c2d4e5b60718] ...jobs: send_email START
    2026-08-12 09:14:04 INFO  [a3f1c2d4e5b60718] ...jobs: send_email OK
"""

from __future__ import annotations

import contextlib
import logging
import secrets
import sys
from contextvars import ContextVar
from typing import Iterator, Optional

from app.core.config import settings

#: Correlation id for the work currently in flight. "-" when there is none
#: (start-up, a cron tick before it assigns one).
_request_id: ContextVar[str] = ContextVar("request_id", default="-")

#: Header used to accept an id from upstream and to return it to the caller.
REQUEST_ID_HEADER = "x-request-id"

#: Ids are opaque; cap what we accept from outside so a hostile client cannot
#: write arbitrary-length junk into every log line.
MAX_REQUEST_ID_LENGTH = 64

_configured = False


def new_request_id() -> str:
    """A fresh id. Short enough to read, wide enough not to collide."""
    return secrets.token_hex(8)


def get_request_id() -> str:
    return _request_id.get()


def set_request_id(request_id: Optional[str]) -> str:
    """Bind an id to the current context, generating one if not supplied."""
    value = (request_id or "").strip()[:MAX_REQUEST_ID_LENGTH] or new_request_id()
    _request_id.set(value)
    return value


@contextlib.contextmanager
def request_context(request_id: Optional[str] = None) -> Iterator[str]:
    """Bind an id for the duration of a block, then restore the previous one.

    Used by Socket.IO handlers and worker jobs, which have no HTTP request to
    hang the id off but still need their log lines correlated.
    """
    value = (request_id or "").strip()[:MAX_REQUEST_ID_LENGTH] or new_request_id()
    token = _request_id.set(value)
    try:
        yield value
    finally:
        _request_id.reset(token)


class RequestIdFilter(logging.Filter):
    """Attach the current request id to every record.

    A filter rather than a custom logger: this way third-party log lines
    (uvicorn, sqlalchemy, arq) are correlated too, without them knowing.
    """

    def filter(self, record: logging.LogRecord) -> bool:
        record.request_id = get_request_id()
        return True


def configure_logging() -> None:
    """Idempotent stdout logging setup.

    stdout because every target platform (Railway, Docker, Kubernetes) treats
    the process's stdout as the log stream — writing to a file would mean the
    logs are only visible inside a container nobody can reach.
    """
    global _configured
    if _configured:
        return

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(
        logging.Formatter(
            "%(asctime)s %(levelname)-8s [%(request_id)s] %(name)s: %(message)s"
        )
    )
    handler.addFilter(RequestIdFilter())

    root = logging.getLogger()
    root.handlers = [handler]
    root.setLevel(logging.DEBUG if settings.debug else logging.INFO)

    # Access logs are re-emitted by our own middleware with the request id,
    # timing, and status attached — uvicorn's version would be a duplicate.
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
    _configured = True
