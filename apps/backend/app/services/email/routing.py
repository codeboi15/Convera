from __future__ import annotations

import re
from email.utils import parseaddr
from typing import List, Optional

from app.core.config import settings

# local-part may carry the tenant tag: mailbox+<key>@domain
_PLUS_TAG = re.compile(r"^([^+]+)\+([^@]+)@(.+)$")


def extract_inbound_key(address: str) -> Optional[str]:
    """Pull the workspace routing key out of a plus-addressed recipient.

    ``support+acme@example.com`` -> ``acme``
    """
    if not address:
        return None
    _, addr = parseaddr(address)
    match = _PLUS_TAG.match((addr or address).strip().lower())
    if not match:
        return None
    key = match.group(2).strip()
    return key or None


def first_inbound_key(addresses: List[str]) -> Optional[str]:
    """First routable key across candidate recipients, in priority order."""
    for address in addresses:
        key = extract_inbound_key(address)
        if key:
            return key
    return None


def inbound_address_for(inbound_key: str) -> str:
    """The address a workspace publishes (or forwards its support mail to)."""
    base = settings.email_inbound_address or "support@example.com"
    local, _, domain = base.partition("@")
    local = local.split("+", 1)[0]
    return f"{local}+{inbound_key}@{domain}"


def normalize_message_id(value: Optional[str]) -> Optional[str]:
    """Message-IDs are compared verbatim, so normalise the angle brackets."""
    if not value:
        return None
    value = value.strip()
    if not value:
        return None
    if not value.startswith("<"):
        value = f"<{value}>"
    if not value.endswith(">"):
        value = f"{value}>"
    return value


def parse_references(raw: Optional[str]) -> List[str]:
    """Split a References header into individual Message-IDs."""
    if not raw:
        return []
    return [normalize_message_id(p) for p in re.findall(r"<[^>]+>", raw)]


def reply_subject(subject: Optional[str]) -> str:
    subject = (subject or "").strip() or "(no subject)"
    return subject if subject.lower().startswith("re:") else f"Re: {subject}"
