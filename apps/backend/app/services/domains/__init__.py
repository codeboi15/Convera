"""Custom domains for the public knowledge base.

Split into three concerns so none of them depends on a hosting vendor:

* :mod:`verification` — proving the workspace controls the domain (DNS TXT)
* :mod:`providers`    — issuing the TLS certificate (pluggable adapter)
* :mod:`service`      — the workspace-facing operations
"""

from app.services.domains.providers import get_domain_provider
from app.services.domains.verification import (
    RESERVED_TLDS,
    is_reserved_domain,
    normalize_domain,
    verify_dns_token,
)

__all__ = [
    "get_domain_provider",
    "normalize_domain",
    "is_reserved_domain",
    "verify_dns_token",
    "RESERVED_TLDS",
]
