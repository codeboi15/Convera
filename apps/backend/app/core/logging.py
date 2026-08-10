from __future__ import annotations

import logging
import sys

from app.core.config import settings

_configured = False


def configure_logging() -> None:
    """Idempotent stdout logging setup. Swappable for JSON logs in production."""
    global _configured
    if _configured:
        return
    level = logging.DEBUG if settings.debug else logging.INFO
    logging.basicConfig(
        level=level,
        stream=sys.stdout,
        format="%(asctime)s %(levelname)-8s %(name)s: %(message)s",
    )
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
    _configured = True
