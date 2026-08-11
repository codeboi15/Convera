"""Reply drafting: retrieval inputs and grounding context.

Covers the pure logic that decides *what* the model is shown. The model call
itself is exercised by the integration scripts, not here — these must run
without a network or an API key.
"""

import uuid

import pytest

from app.models.conversation import Message
from app.models.enums import SenderType
from app.services.ai import (
    DRAFT_KB_CHARS_PER_ARTICLE,
    MAX_KEYWORDS,
    RETRIEVAL_MESSAGES,
    build_kb_context,
    extract_keywords,
    retrieval_text,
)


def message(body: str, sender: SenderType, seq: int) -> Message:
    return Message(
        id=uuid.uuid4(),
        workspace_id=uuid.uuid4(),
        conversation_id=uuid.uuid4(),
        seq=seq,
        sender_type=sender,
        body=body,
    )


# --------------------------------------------------------------------------
# Keyword extraction — the help centre search ANDs terms, so a whole sentence
# matches nothing. These keywords are what make retrieval work at all.
# --------------------------------------------------------------------------


def test_drops_stopwords_and_short_words():
    keywords = extract_keywords("Can I get my money back for the course?")
    assert "money" in keywords
    assert "course" in keywords
    for noise in ("can", "get", "for", "the", "my"):
        assert noise not in keywords


def test_prefers_longer_more_distinctive_words():
    keywords = extract_keywords("my subscription renewed but I wanted to cancel")
    assert keywords[0] == "subscription"


def test_deduplicates_and_caps_keyword_count():
    keywords = extract_keywords("refund refund refund " + " ".join(f"word{i}" for i in range(20)))
    assert keywords.count("refund") == 1
    assert len(keywords) <= MAX_KEYWORDS


def test_handles_empty_and_punctuation_only_input():
    assert extract_keywords("") == []
    assert extract_keywords("?!  ...") == []


# --------------------------------------------------------------------------
# Retrieval text
# --------------------------------------------------------------------------


def test_retrieves_against_recent_customer_messages_oldest_first():
    messages = [
        message("I bought your course last week", SenderType.contact, 1),
        message("Happy to help", SenderType.agent, 2),
        message("It wasn't what I expected", SenderType.contact, 3),
        message("Can I get my money back?", SenderType.contact, 4),
    ]
    text = retrieval_text(messages)

    assert text.splitlines() == [
        "I bought your course last week",
        "It wasn't what I expected",
        "Can I get my money back?",
    ]


def test_ignores_agent_messages():
    messages = [
        message("Our refund policy is generous", SenderType.agent, 1),
        message("ok thanks", SenderType.contact, 2),
    ]
    assert retrieval_text(messages) == "ok thanks"


def test_uses_at_most_the_configured_number_of_messages():
    messages = [
        message(f"msg{i}", SenderType.contact, i) for i in range(10)
    ]
    assert len(retrieval_text(messages).splitlines()) == RETRIEVAL_MESSAGES


def test_no_customer_message_yields_nothing_to_search():
    assert retrieval_text([message("hello?", SenderType.agent, 1)]) == ""
    assert retrieval_text([]) == ""


# --------------------------------------------------------------------------
# Grounding context
# --------------------------------------------------------------------------


def test_states_plainly_when_nothing_was_retrieved():
    """The model must be told there are no articles, not shown an empty block —
    that is what stops it inventing a policy."""
    context = build_kb_context([])
    assert "No help centre articles" in context


def test_labels_each_article_so_claims_are_traceable():
    context = build_kb_context(
        [("Refund policy", "Full refund within 14 days."), ("Billing", "Update your card.")]
    )
    assert "[Article 1: Refund policy]" in context
    assert "[Article 2: Billing]" in context
    assert "Full refund within 14 days." in context


def test_truncates_long_articles_to_bound_cost():
    context = build_kb_context([("Long one", "x" * (DRAFT_KB_CHARS_PER_ARTICLE * 3))])
    assert len(context) < DRAFT_KB_CHARS_PER_ARTICLE * 2
    assert context.endswith("…")


@pytest.mark.parametrize("body", ["", None])
def test_survives_articles_with_no_body(body):
    assert "[Article 1: Empty]" in build_kb_context([("Empty", body)])
