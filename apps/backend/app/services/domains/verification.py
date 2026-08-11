from __future__ import annotations

import asyncio
import logging
import re
import secrets
from typing import List, Optional, Tuple
from urllib.parse import urlparse

from app.core.config import settings

logger = logging.getLogger(__name__)

# TXT record name we look for, prefixed to the domain being verified.
VERIFY_PREFIX = "_intercom-verify"
TOKEN_PREFIX = "intercom-verify="

# RFC 6761 / RFC 2606 reserved names. These can never be registered publicly,
# so there is no domain to hijack — safe to auto-verify, which is what makes a
# local demo possible without faking the production code path.
RESERVED_TLDS = (".test", ".localhost", ".local", ".example", ".invalid")

_DOMAIN_RE = re.compile(
    r"^(?=.{1,253}$)(?!-)[a-z0-9-]{1,63}(?<!-)(\.(?!-)[a-z0-9-]{1,63}(?<!-))+$"
)


def normalize_domain(value: str) -> str:
    """Reduce user input to a bare lowercase hostname.

    Accepts what people actually paste — ``https://help.acme.com/``,
    ``HELP.acme.com``, ``help.acme.com:443`` — and returns ``help.acme.com``.
    """
    raw = (value or "").strip().lower()
    if not raw:
        return ""
    if "//" in raw:
        raw = urlparse(raw).netloc or raw.split("//", 1)[1]
    raw = raw.split("/", 1)[0].split("@")[-1]
    if ":" in raw:
        raw = raw.split(":", 1)[0]
    return raw.strip(".")


def is_valid_domain(domain: str) -> bool:
    return bool(_DOMAIN_RE.match(domain or ""))


def is_reserved_domain(domain: str) -> bool:
    """True for names that can never be publicly registered (local demo use)."""
    return (domain or "").endswith(RESERVED_TLDS)


def platform_hostnames() -> List[str]:
    """Hostnames belonging to this deployment, which must not be claimable."""
    hosts = []
    for url in (settings.frontend_url, *settings.cors_origin_list):
        host = normalize_domain(url)
        if host:
            hosts.append(host)
    return hosts


def rejection_reason(domain: str) -> Optional[str]:
    """Why this domain may not be connected, or None if it is acceptable."""
    if not domain:
        return "Enter a domain, for example help.yourcompany.com"
    if not is_valid_domain(domain):
        return "That doesn't look like a valid domain name."
    if "." not in domain.rstrip("."):
        return "Use a fully qualified domain, for example help.yourcompany.com"
    # Claiming our own hostname would let a tenant serve content on the
    # platform's domain.
    for host in platform_hostnames():
        if domain == host or domain.endswith("." + host):
            return "That domain belongs to the platform and cannot be connected."
    if domain.endswith((".vercel.app", ".railway.app", ".up.railway.app")):
        return "Platform-owned domains cannot be connected."
    return None


def new_token() -> str:
    return secrets.token_urlsafe(24)


def txt_record_name(domain: str) -> str:
    return f"{VERIFY_PREFIX}.{domain}"


def txt_record_value(token: str) -> str:
    return f"{TOKEN_PREFIX}{token}"


def _lookup_txt_sync(name: str) -> List[str]:
    """Resolve TXT records for ``name``. Returns [] when it cannot be resolved."""
    try:
        import dns.resolver  # imported lazily so the API boots without dnspython
    except ImportError:  # pragma: no cover - dependency missing
        logger.warning("dnspython not installed; DNS verification unavailable")
        return []

    try:
        resolver = dns.resolver.Resolver()
        resolver.lifetime = 8.0
        resolver.timeout = 4.0
        answers = resolver.resolve(name, "TXT")
    except Exception:
        # NXDOMAIN / NoAnswer / timeout all mean "not verified yet".
        logger.debug("TXT lookup failed for %s", name, exc_info=True)
        return []

    values: List[str] = []
    for record in answers:
        # A TXT record is a sequence of strings; join and strip the quoting.
        text = b"".join(getattr(record, "strings", []) or []).decode(
            "utf-8", "replace"
        )
        values.append(text or str(record).strip('"'))
    return values


async def verify_dns_token(domain: str, token: str) -> Tuple[bool, str]:
    """Check the domain publishes our verification token.

    Returns ``(verified, detail)`` — detail is shown to the admin so a failed
    check explains itself rather than just saying "not verified".
    """
    if is_reserved_domain(domain):
        return True, "Reserved test domain — verified automatically."

    name = txt_record_name(domain)
    expected = txt_record_value(token)
    records = await asyncio.to_thread(_lookup_txt_sync, name)

    if not records:
        return False, f"No TXT record found at {name}. DNS changes can take a few minutes."
    if any(expected in r for r in records):
        return True, "DNS record verified."
    return False, f"Found a TXT record at {name}, but the value doesn't match."
