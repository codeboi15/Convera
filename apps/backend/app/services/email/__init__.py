"""Email channel: provider-agnostic inbound parsing and outbound delivery."""

from app.services.email.base import (
    EmailProvider,
    InboundEmail,
    OutboundEmail,
    get_outbound_provider,
    get_provider,
)

__all__ = [
    "EmailProvider",
    "InboundEmail",
    "OutboundEmail",
    "get_provider",
    "get_outbound_provider",
]
