from __future__ import annotations

import logging
from typing import Dict, Optional

import httpx

from app.core.config import settings
from app.services.email.base import EmailProvider, OutboundEmail
from app.services.email.routing import normalize_message_id

logger = logging.getLogger(__name__)

MAILJET_SEND_URL = "https://api.mailjet.com/v3.1/send"


def _address(value: str) -> Dict[str, str]:
    """Turn ``Name <a@b.com>`` or ``a@b.com`` into Mailjet's {Email,Name} shape."""
    value = (value or "").strip()
    if "<" in value and value.endswith(">"):
        name, _, addr = value.partition("<")
        return {"Email": addr[:-1].strip(), "Name": name.strip().strip('"')}
    return {"Email": value}


class MailjetProvider(EmailProvider):
    """Outbound email over HTTPS via Mailjet.

    Used where the host blocks outbound SMTP — on Railway, connections to both
    587 and 465 fail with ``Network is unreachable``. Mailjet verifies a single
    sender address rather than a domain, and does not restrict calls by source
    IP, which matters because a platform's outbound IPs rotate between deploys.

    Authentication is HTTP Basic with an API key/secret pair, unlike the
    bearer-token providers.

    Outbound only: inbound still arrives over IMAP.
    """

    name = "mailjet"

    @property
    def supports_polling(self) -> bool:
        return False

    async def send(self, message: OutboundEmail) -> Optional[str]:
        key = settings.mailjet_api_key
        secret = settings.mailjet_api_secret
        sender = message.from_email or settings.mailjet_from_email
        if not key or not secret or not sender:
            logger.warning(
                "Mailjet not configured (key=%s secret=%s sender=%s); dropping email",
                bool(key),
                bool(secret),
                bool(sender),
            )
            return None

        payload_message: Dict[str, object] = {
            "From": {
                "Email": sender,
                **({"Name": message.from_name} if message.from_name else {}),
            },
            "To": [_address(message.to_email)],
            "Subject": message.subject,
            "TextPart": message.text_body or "",
        }
        if message.html_body:
            payload_message["HTMLPart"] = message.html_body
        if message.reply_to:
            payload_message["ReplyTo"] = _address(message.reply_to)

        # RFC 5322 threading — keeps the reply inside the customer's existing
        # mail thread rather than starting a new one.
        headers: Dict[str, str] = {}
        if message.in_reply_to:
            headers["In-Reply-To"] = message.in_reply_to
        if message.references:
            headers["References"] = " ".join(message.references)
        if headers:
            payload_message["Headers"] = headers

        try:
            async with httpx.AsyncClient(timeout=25) as client:
                res = await client.post(
                    MAILJET_SEND_URL,
                    json={"Messages": [payload_message]},
                    auth=(key, secret),
                    headers={"Content-Type": "application/json"},
                )
        except httpx.HTTPError:
            logger.exception("Mailjet request failed")
            return None

        if res.status_code >= 400:
            logger.error(
                "Mailjet rejected the message (%s): %s",
                res.status_code,
                res.text[:300],
            )
            return None

        try:
            body = res.json()
            sent = body.get("Messages", [{}])[0]
        except (ValueError, IndexError, AttributeError):
            return None

        # A 200 can still carry a per-message error, so check the status.
        if sent.get("Status") != "success":
            logger.error("Mailjet did not accept the message: %s", str(sent)[:300])
            return None

        to_entries = sent.get("To") or [{}]
        sent_id = to_entries[0].get("MessageID") or to_entries[0].get("MessageUUID")
        if not sent_id:
            return None
        return normalize_message_id(f"{sent_id}@mailjet.com")
