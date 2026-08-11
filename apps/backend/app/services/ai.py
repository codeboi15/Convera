from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import List, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.contact import Contact
from app.models.conversation import Conversation, Message
from app.models.enums import SenderType

logger = logging.getLogger(__name__)

# Summaries are only worth generating once a thread is long enough to be
# worth catching up on.
MIN_MESSAGES_FOR_SUMMARY = 4
# Regenerate once this many new messages have landed since the last summary.
REFRESH_AFTER_NEW_MESSAGES = 4

# Context windowing: keep the opening messages (which frame the problem) and
# the most recent ones (which carry current state), dropping the middle. This
# bounds cost on very long threads without losing the two ends that matter.
HEAD_MESSAGES = 6
TAIL_MESSAGES = 20
MAX_CHARS_PER_MESSAGE = 1500

REQUEST_TIMEOUT_SECONDS = 30.0
MAX_OUTPUT_TOKENS = 400

SYSTEM_PROMPT = """You write briefings for customer-support agents who are \
picking up an ongoing conversation.

Summarise the conversation in three short labelled sections:
What they want: the customer's goal or problem, in one or two sentences.
What's been tried: steps already taken by the customer or previous agents.
Current status: where things stand right now and what the next action is.

Rules:
- Be specific. Include order numbers, error messages, dates, and amounts.
- Only state facts present in the transcript. Never invent details.
- If a section has nothing to report, write "Nothing yet".
- Plain text, no markdown, under 150 words total."""


def build_transcript(messages: List[Message], contact_name: str) -> str:
    """Render a windowed transcript for the model."""
    if len(messages) > HEAD_MESSAGES + TAIL_MESSAGES:
        head = messages[:HEAD_MESSAGES]
        tail = messages[-TAIL_MESSAGES:]
        skipped = len(messages) - len(head) - len(tail)
        selected = head + tail
        marker_at = len(head)
    else:
        selected = messages
        skipped = 0
        marker_at = -1

    lines: List[str] = []
    for index, message in enumerate(selected):
        if index == marker_at and skipped:
            lines.append(f"[... {skipped} earlier messages omitted ...]")
        speaker = contact_name if message.sender_type == SenderType.contact else "Agent"
        body = (message.body or "").strip()
        if len(body) > MAX_CHARS_PER_MESSAGE:
            body = body[:MAX_CHARS_PER_MESSAGE] + "…"
        lines.append(f"{speaker}: {body}")
    return "\n".join(lines)


def should_summarize(conversation: Conversation) -> bool:
    """Whether a (re)summary is worth the API call."""
    if conversation.message_count < MIN_MESSAGES_FOR_SUMMARY:
        return False
    if conversation.ai_summary is None:
        return True
    new_messages = conversation.message_count - conversation.ai_summary_message_count
    return new_messages >= REFRESH_AFTER_NEW_MESSAGES


async def generate_summary_text(transcript: str) -> Optional[str]:
    """Call Claude for a summary. Returns None on any failure.

    Deliberately fail-soft: the dashboard renders without a summary rather
    than erroring when the model is slow, rate-limited, or unconfigured.
    """
    if not settings.anthropic_api_key:
        logger.info("ANTHROPIC_API_KEY not configured; skipping summary")
        return None

    try:
        from anthropic import AsyncAnthropic

        client = AsyncAnthropic(
            api_key=settings.anthropic_api_key, timeout=REQUEST_TIMEOUT_SECONDS
        )
        response = await client.messages.create(
            model=settings.anthropic_model,
            max_tokens=MAX_OUTPUT_TOKENS,
            system=SYSTEM_PROMPT,
            messages=[
                {
                    "role": "user",
                    "content": f"Summarise this support conversation:\n\n{transcript}",
                }
            ],
        )
    except Exception:
        # Timeouts, rate limits, network errors, bad keys — all fail soft.
        logger.exception("AI summary request failed")
        return None

    if getattr(response, "stop_reason", None) == "refusal":
        logger.warning("AI summary refused by safety classifier")
        return None

    parts = [
        block.text
        for block in response.content
        if getattr(block, "type", None) == "text"
    ]
    summary = "\n".join(parts).strip()
    return summary or None


async def summarize_conversation(
    session: AsyncSession, conversation_id: uuid.UUID, force: bool = False
) -> Optional[str]:
    """Generate and persist a summary for a conversation."""
    conversation = await session.get(Conversation, conversation_id)
    if conversation is None:
        return None
    if not force and not should_summarize(conversation):
        return conversation.ai_summary

    messages = list(
        (
            await session.scalars(
                select(Message)
                .where(Message.conversation_id == conversation.id)
                .order_by(Message.seq)
            )
        ).all()
    )
    if not messages:
        return None

    contact = await session.get(Contact, conversation.contact_id)
    contact_name = (contact.name or contact.email or "Customer") if contact else "Customer"

    summary = await generate_summary_text(
        build_transcript(messages, contact_name)
    )
    if summary is None:
        return conversation.ai_summary

    conversation.ai_summary = summary
    conversation.ai_summary_updated_at = datetime.now(timezone.utc)
    conversation.ai_summary_message_count = conversation.message_count
    await session.commit()
    return summary
