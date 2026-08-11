from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import List, Optional

from app.core.config import settings

logger = logging.getLogger(__name__)


@dataclass
class InboundEmail:
    """A received email, normalised across providers."""

    message_id: str
    from_email: str
    from_name: Optional[str]
    to: List[str]
    cc: List[str] = field(default_factory=list)
    subject: str = ""
    text_body: str = ""
    html_body: Optional[str] = None
    in_reply_to: Optional[str] = None
    references: List[str] = field(default_factory=list)
    # Address the mailbox actually delivered to — the most reliable place to
    # find the plus-tag, since To: can be rewritten by forwarders.
    delivered_to: Optional[str] = None

    def recipient_candidates(self) -> List[str]:
        """Every address that might carry the routing tag, best first."""
        out: List[str] = []
        if self.delivered_to:
            out.append(self.delivered_to)
        out.extend(self.to)
        out.extend(self.cc)
        return [a for a in out if a]


@dataclass
class OutboundEmail:
    to_email: str
    subject: str
    text_body: str
    html_body: Optional[str] = None
    from_name: Optional[str] = None
    from_email: Optional[str] = None
    reply_to: Optional[str] = None
    # RFC 5322 threading headers.
    in_reply_to: Optional[str] = None
    references: Optional[List[str]] = None


class EmailProvider(ABC):
    """Transport for the email channel.

    Inbound arrives either by polling (IMAP) or by webhook (Postmark); both
    normalise to :class:`InboundEmail`, so routing and threading logic is
    written once.
    """

    name = "base"

    @abstractmethod
    async def send(self, message: OutboundEmail) -> Optional[str]:
        """Deliver an email. Returns the sent Message-ID when known."""

    async def fetch(self) -> List[InboundEmail]:
        """Poll for new mail. Push-based providers return nothing."""
        return []

    @property
    def supports_polling(self) -> bool:
        return False


class StubProvider(EmailProvider):
    """Logs instead of sending. Used until real credentials are configured."""

    name = "stub"

    def __init__(self) -> None:
        self.sent: List[OutboundEmail] = []

    async def send(self, message: OutboundEmail) -> Optional[str]:
        self.sent.append(message)
        logger.info(
            "[stub email] to=%s subject=%r in_reply_to=%s",
            message.to_email,
            message.subject,
            message.in_reply_to,
        )
        return None


_provider: Optional[EmailProvider] = None


def get_provider() -> EmailProvider:
    """Return the configured provider (cached)."""
    global _provider
    if _provider is not None:
        return _provider

    choice = (settings.email_provider or "stub").lower()
    if choice == "imap":
        from app.services.email.imap_smtp import ImapSmtpProvider

        _provider = ImapSmtpProvider()
    elif choice == "postmark":
        from app.services.email.postmark import PostmarkProvider

        _provider = PostmarkProvider()
    else:
        _provider = StubProvider()

    logger.info("email provider: %s", _provider.name)
    return _provider


def reset_provider() -> None:
    """Clear the cached provider (used by tests)."""
    global _provider
    _provider = None
