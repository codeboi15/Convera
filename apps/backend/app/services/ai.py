from __future__ import annotations

import logging
import re
import uuid
from datetime import datetime, timezone
from typing import TYPE_CHECKING, List, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.contact import Contact
from app.models.conversation import Conversation, Message
from app.models.enums import SenderType

if TYPE_CHECKING:  # pragma: no cover
    from app.schemas.kb import ArticleSummary

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


# ---------------------------------------------------------------------------
# Reply drafting
#
# Retrieval-augmented: the draft is grounded in the workspace's own published
# help-centre articles, so it answers with that tenant's actual policies rather
# than something plausible-sounding. An agent edits and sends it — nothing here
# reaches a customer on its own.
# ---------------------------------------------------------------------------

DRAFT_MAX_OUTPUT_TOKENS = 500
# Three articles is enough grounding for a support answer; more mostly adds
# cost and gives the model room to wander off the question.
DRAFT_KB_ARTICLES = 3
DRAFT_KB_CHARS_PER_ARTICLE = 1200

DRAFT_SYSTEM_PROMPT = """You draft replies for customer-support agents. An \
agent reviews and edits every draft before it is sent, so write a confident \
first version rather than a hedged one.

Write the agent's next reply to the customer:
- Answer what they actually asked, in the language they used.
- Ground every factual claim — policies, timelines, steps, amounts, eligibility \
— in the help centre articles provided. If the articles do not cover it, do not \
invent an answer: say what you can, then ask the one question that would let you \
help.
- Never promise a refund, discount, or deadline that is not in the articles or \
already agreed earlier in the conversation.
- Do not repeat an answer the customer has already been given in the transcript.
- Plain text only. No markdown, no subject line, no placeholders like [Name].
- Warm and direct. Two short paragraphs at most.
- Do not sign off — the agent's name is appended automatically."""


class ReplyDraft:
    """A generated draft plus the articles it was grounded in."""

    def __init__(self, text: str, sources: List["ArticleSummary"]) -> None:
        self.text = text
        self.sources = sources


# How many of the customer's recent messages to retrieve against. Only the last
# one is what they *asked*, but the topic word ("refund", "invoice") is often a
# message or two back — "can I get my money back?" on its own retrieves nothing.
RETRIEVAL_MESSAGES = 3


def retrieval_text(messages: List[Message]) -> str:
    """The customer's recent words, oldest first — what we search the KB with."""
    recent: List[str] = []
    for message in reversed(messages):
        if message.sender_type != SenderType.contact:
            continue
        body = (message.body or "").strip()
        if body:
            recent.append(body[:MAX_CHARS_PER_MESSAGE])
        if len(recent) >= RETRIEVAL_MESSAGES:
            break
    return "\n".join(reversed(recent))


# Retrieval keywords. The help-centre search is tuned for what a visitor types
# into a search box — a few words. A customer's actual message is a sentence,
# and ``websearch_to_tsquery`` ANDs its terms, so feeding it one whole matches
# nothing at all. Pull the distinctive words out first and search for those.
STOPWORDS = frozenset(
    """
    about after all also am an and any are as at back be because been before being but
    by can cant cannot could did didnt do does doesnt doing dont for from get gets
    getting got had has have having help hi hello how i id if im in into is isnt it its
    ive just me my need no not now of on one only or our out over please so some still
    such than that the their them then there these they this those to too try tried
    trying up us very was wasnt we were what when where which who why will with wont
    would you your yours
    """.split()
)
MIN_KEYWORD_LENGTH = 3
MAX_KEYWORDS = 6


def extract_keywords(text: str) -> List[str]:
    """Distinctive search terms from a customer message.

    Longest first: in support text the longer words ("refund", "subscription")
    carry the topic, while the short ones are mostly grammar.
    """
    words = re.findall(r"[a-z0-9']+", (text or "").lower())
    keywords: List[str] = []
    for word in words:
        word = word.strip("'")
        if len(word) < MIN_KEYWORD_LENGTH or word in STOPWORDS:
            continue
        if word not in keywords:
            keywords.append(word)
    keywords.sort(key=len, reverse=True)
    return keywords[:MAX_KEYWORDS]


async def retrieve_grounding(
    session: AsyncSession,
    workspace_id: uuid.UUID,
    question: str,
    limit: int = DRAFT_KB_ARTICLES,
) -> List["ArticleSummary"]:
    """Published articles relevant to a whole customer message.

    Searches the full message first (best when the customer wrote something
    short) and then each keyword, ranking articles by how many of those
    searches turned them up. Turns the underlying AND semantics into an OR
    without a second index or a second search implementation.
    """
    from app.services import kb as kb_service

    found: dict = {}
    hits: dict = {}
    for term in [question] + extract_keywords(question):
        for article in await kb_service.search_articles(
            session, workspace_id, term, published_only=True, limit=limit
        ):
            found.setdefault(article.id, article)
            hits[article.id] = hits.get(article.id, 0) + 1

    ranked = sorted(found.values(), key=lambda a: -hits[a.id])
    return ranked[:limit]


def build_kb_context(articles: List[tuple]) -> str:
    """Render retrieved articles as labelled grounding material."""
    if not articles:
        return "(No help centre articles matched this question.)"

    blocks = []
    for index, (title, body) in enumerate(articles, start=1):
        body = (body or "").strip()
        if len(body) > DRAFT_KB_CHARS_PER_ARTICLE:
            body = body[:DRAFT_KB_CHARS_PER_ARTICLE] + "…"
        blocks.append(f"[Article {index}: {title}]\n{body}")
    return "\n\n".join(blocks)


async def generate_draft_text(transcript: str, kb_context: str) -> Optional[str]:
    """Call Claude for a reply draft. Returns None on any failure.

    Same fail-soft contract as summarisation: the composer stays usable and the
    agent simply types the reply themselves.
    """
    if not settings.anthropic_api_key:
        logger.info("ANTHROPIC_API_KEY not configured; cannot draft a reply")
        return None

    try:
        from anthropic import AsyncAnthropic

        client = AsyncAnthropic(
            api_key=settings.anthropic_api_key, timeout=REQUEST_TIMEOUT_SECONDS
        )
        response = await client.messages.create(
            model=settings.anthropic_model,
            max_tokens=DRAFT_MAX_OUTPUT_TOKENS,
            system=DRAFT_SYSTEM_PROMPT,
            messages=[
                {
                    "role": "user",
                    "content": (
                        f"Help centre articles:\n\n{kb_context}\n\n"
                        f"Conversation so far:\n\n{transcript}\n\n"
                        "Write the agent's next reply."
                    ),
                }
            ],
        )
    except Exception:
        logger.exception("AI reply draft request failed")
        return None

    if getattr(response, "stop_reason", None) == "refusal":
        logger.warning("AI reply draft refused by safety classifier")
        return None

    parts = [
        block.text
        for block in response.content
        if getattr(block, "type", None) == "text"
    ]
    return "\n".join(parts).strip() or None


async def draft_reply(
    session: AsyncSession, conversation_id: uuid.UUID
) -> Optional[ReplyDraft]:
    """Draft the agent's next reply, grounded in the workspace's help centre."""
    from app.models.kb import KBArticle

    conversation = await session.get(Conversation, conversation_id)
    if conversation is None:
        return None

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

    question = retrieval_text(messages)
    if not question:
        # Nothing from the customer to answer yet.
        return None

    # Email threads carry a subject that usually names the topic outright
    # ("Refund request"), which is often more searchable than the message body.
    if conversation.subject:
        question = f"{conversation.subject}\n{question}"

    # Grounding comes from the same hybrid search that powers the public help
    # centre, so drafts and self-serve answers stay consistent.
    summaries = await retrieve_grounding(
        session, conversation.workspace_id, question, limit=DRAFT_KB_ARTICLES
    )

    bodies: List[tuple] = []
    if summaries:
        rows = (
            await session.scalars(
                select(KBArticle).where(
                    KBArticle.id.in_([a.id for a in summaries])
                )
            )
        ).all()
        by_id = {row.id: row for row in rows}
        # Preserve relevance order from the search.
        bodies = [
            (by_id[a.id].title, by_id[a.id].body_text)
            for a in summaries
            if a.id in by_id
        ]

    contact = await session.get(Contact, conversation.contact_id)
    contact_name = (contact.name or contact.email or "Customer") if contact else "Customer"

    text = await generate_draft_text(
        build_transcript(messages, contact_name), build_kb_context(bodies)
    )
    if text is None:
        return None
    return ReplyDraft(text=text, sources=summaries)


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
