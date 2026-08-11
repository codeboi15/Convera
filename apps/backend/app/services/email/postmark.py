from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

import httpx

from app.core.config import settings
from app.services.email.base import EmailProvider, InboundEmail, OutboundEmail
from app.services.email.routing import normalize_message_id, parse_references

logger = logging.getLogger(__name__)

POSTMARK_SEND_URL = "https://api.postmarkapp.com/email"


def parse_webhook(payload: Dict[str, Any]) -> InboundEmail:
    """Normalise Postmark's inbound webhook JSON."""
    headers = {
        (h.get("Name") or "").lower(): h.get("Value")
        for h in payload.get("Headers", [])
    }

    def addresses(key: str) -> List[str]:
        full = payload.get(key + "Full") or []
        out = [item.get("Email") for item in full if item.get("Email")]
        if out:
            return out
        raw = payload.get(key) or ""
        return [a.strip() for a in raw.split(",") if a.strip()]

    return InboundEmail(
        message_id=normalize_message_id(payload.get("MessageID") or headers.get("message-id")) or "",
        from_email=(payload.get("From") or "").lower(),
        from_name=(payload.get("FromFull") or {}).get("Name") or None,
        to=addresses("To"),
        cc=addresses("Cc"),
        subject=payload.get("Subject") or "",
        text_body=payload.get("TextBody") or "",
        html_body=payload.get("HtmlBody") or None,
        in_reply_to=normalize_message_id(headers.get("in-reply-to")),
        references=parse_references(headers.get("references")),
        # OriginalRecipient preserves the plus-tag even when To: was rewritten.
        delivered_to=payload.get("OriginalRecipient"),
    )


class PostmarkProvider(EmailProvider):
    """Push-based transport: Postmark posts inbound mail to our webhook."""

    name = "postmark"

    async def send(self, message: OutboundEmail) -> Optional[str]:
        token = settings.postmark_server_token
        sender = message.from_email or settings.postmark_from_email
        if not token or not sender:
            logger.warning("Postmark not configured; dropping outbound email")
            return None

        headers: List[Dict[str, str]] = []
        if message.in_reply_to:
            headers.append({"Name": "In-Reply-To", "Value": message.in_reply_to})
        if message.references:
            headers.append(
                {"Name": "References", "Value": " ".join(message.references)}
            )

        body: Dict[str, Any] = {
            "From": (
                f"{message.from_name} <{sender}>" if message.from_name else sender
            ),
            "To": message.to_email,
            "Subject": message.subject,
            "TextBody": message.text_body,
            "MessageStream": "outbound",
        }
        if message.html_body:
            body["HtmlBody"] = message.html_body
        if message.reply_to:
            body["ReplyTo"] = message.reply_to
        if headers:
            body["Headers"] = headers

        try:
            async with httpx.AsyncClient(timeout=20) as client:
                res = await client.post(
                    POSTMARK_SEND_URL,
                    json=body,
                    headers={
                        "X-Postmark-Server-Token": token,
                        "Accept": "application/json",
                    },
                )
            if res.status_code >= 400:
                logger.error(
                    "Postmark send failed (%s): %s", res.status_code, res.text[:300]
                )
                return None
            return normalize_message_id(res.json().get("MessageID"))
        except httpx.HTTPError:
            logger.exception("Postmark request error")
            return None
