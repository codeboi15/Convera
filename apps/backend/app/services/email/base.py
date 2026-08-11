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


def _build(choice: str) -> EmailProvider:
    choice = (choice or "stub").lower()
    if choice == "imap":
        from app.services.email.imap_smtp import ImapSmtpProvider

        return ImapSmtpProvider()
    if choice == "postmark":
        from app.services.email.postmark import PostmarkProvider

        return PostmarkProvider()
    if choice == "brevo":
        from app.services.email.brevo import BrevoProvider

        return BrevoProvider()
    if choice == "resend":
        from app.services.email.resend import ResendProvider

        return ResendProvider()
    return StubProvider()


_provider: Optional[EmailProvider] = None
_outbound_provider: Optional[EmailProvider] = None


def get_provider() -> EmailProvider:
    """Provider used for *inbound* mail (and outbound when none is set)."""
    global _provider
    if _provider is None:
        _provider = _build(settings.email_provider)
        logger.info("email provider (inbound): %s", _provider.name)
    return _provider


def get_outbound_provider() -> EmailProvider:
    """Provider used for *sending*.

    Kept separate because the two directions have different constraints: some
    hosts block outbound SMTP while inbound IMAP still works, so mail has to
    leave over HTTPS even though it arrives over IMAP.
    """
    global _outbound_provider
    if _outbound_provider is None:
        choice = settings.email_outbound_provider or settings.email_provider
        _outbound_provider = _build(choice)
        logger.info("email provider (outbound): %s", _outbound_provider.name)
    return _outbound_provider


def reset_provider() -> None:
    """Clear the cached providers (used by tests)."""
    global _provider, _outbound_provider
    _provider = None
    _outbound_provider = None
