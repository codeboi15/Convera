from __future__ import annotations

import logging
from typing import Dict, List, Optional

import httpx

from app.core.config import settings
from app.services.email.base import EmailProvider, OutboundEmail
from app.services.email.routing import normalize_message_id

logger = logging.getLogger(__name__)

RESEND_SEND_URL = "https://api.resend.com/emails"


class ResendProvider(EmailProvider):
    """Outbound email over HTTPS via Resend.

    Exists because some hosts (Railway among them) block outbound SMTP ports
    entirely — connections to 587 and 465 fail with ``Network is unreachable``.
    An HTTPS API is unaffected by that, since port 443 is always open.

    Outbound only: inbound continues to arrive over IMAP or a webhook, so this
    provider is paired with a polling provider rather than replacing it.
    """

    name = "resend"

    @property
    def supports_polling(self) -> bool:
        # Resend does not deliver inbound mail to us; IMAP handles that.
        return False

    async def send(self, message: OutboundEmail) -> Optional[str]:
        token = settings.resend_api_key
        sender = message.from_email or settings.resend_from_email
        if not token or not sender:
            logger.warning(
                "Resend not configured (api_key=%s from=%s); dropping outbound email",
                bool(token),
                bool(sender),
            )
            return None

        # Threading headers are what keep the reply inside the customer's
        # existing mail thread rather than starting a new one.
        headers: Dict[str, str] = {}
        if message.in_reply_to:
            headers["In-Reply-To"] = message.in_reply_to
        if message.references:
            headers["References"] = " ".join(message.references)

        payload: Dict[str, object] = {
            "from": (
                f"{message.from_name} <{sender}>" if message.from_name else sender
            ),
            "to": [message.to_email],
            "subject": message.subject,
            "text": message.text_body or "",
        }
        if message.html_body:
            payload["html"] = message.html_body
        if message.reply_to:
            payload["reply_to"] = message.reply_to
        if headers:
            payload["headers"] = headers

        try:
            async with httpx.AsyncClient(timeout=25) as client:
                res = await client.post(
                    RESEND_SEND_URL,
                    json=payload,
                    headers={
                        "Authorization": f"Bearer {token}",
                        "Content-Type": "application/json",
                    },
                )
        except httpx.HTTPError:
            logger.exception("Resend request failed")
            return None

        if res.status_code >= 400:
            logger.error(
                "Resend rejected the message (%s): %s",
                res.status_code,
                res.text[:300],
            )
            return None

        # Resend returns its own id; store it so the customer's reply threads
        # back to this conversation.
        try:
            sent_id = res.json().get("id")
        except ValueError:
            sent_id = None
        if not sent_id:
            return None
        return normalize_message_id(f"{sent_id}@resend.dev")
