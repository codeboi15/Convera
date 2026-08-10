from __future__ import annotations

import re
import secrets

_slug_re = re.compile(r"[^a-z0-9]+")


def slugify(value: str) -> str:
    value = _slug_re.sub("-", value.strip().lower()).strip("-")
    return value or "workspace"


def random_suffix(n: int = 4) -> str:
    return secrets.token_hex(n)[:n]
