from __future__ import annotations

import re
import uuid
from datetime import datetime, timezone
from typing import List, Optional, Sequence

import bleach
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.slug import random_suffix, slugify
from app.models.enums import ArticleStatus
from app.models.kb import KBArticle, KBCategory
from app.schemas.kb import ArticleSummary

# Article HTML comes from a rich-text editor, so it is untrusted input that will
# be rendered on a public page — sanitize before it ever reaches the database.
ALLOWED_TAGS = [
    "p", "br", "div", "span", "strong", "b", "em", "i", "u", "s", "a", "ul",
    "ol", "li", "blockquote", "pre", "code", "h1", "h2", "h3", "h4", "h5", "h6",
    "hr", "img", "table", "thead", "tbody", "tr", "td", "th",
]
ALLOWED_ATTRS = {
    "a": ["href", "title", "target", "rel"],
    "img": ["src", "alt", "width", "height"],
    "*": ["class"],
}

_TAG_RE = re.compile(r"<[^>]+>")
_WS_RE = re.compile(r"\s+")


def sanitize_html(html: str) -> str:
    return bleach.clean(
        html or "",
        tags=ALLOWED_TAGS,
        attributes=ALLOWED_ATTRS,
        protocols=["http", "https", "mailto"],
        strip=True,
    )


def to_plain_text(html: str) -> str:
    """Plain-text projection used for search indexing, excerpts, and AI context."""
    text = _TAG_RE.sub(" ", html or "")
    text = bleach.clean(text, tags=[], strip=True)
    return _WS_RE.sub(" ", text).strip()


def excerpt(text: str, limit: int = 180) -> str:
    text = (text or "").strip()
    if len(text) <= limit:
        return text
    return text[:limit].rsplit(" ", 1)[0] + "…"


async def unique_article_slug(
    session: AsyncSession,
    workspace_id: uuid.UUID,
    title: str,
    exclude_id: Optional[uuid.UUID] = None,
) -> str:
    base = slugify(title)[:150] or "article"
    slug = base
    while True:
        stmt = select(KBArticle.id).where(
            KBArticle.workspace_id == workspace_id, KBArticle.slug == slug
        )
        if exclude_id is not None:
            stmt = stmt.where(KBArticle.id != exclude_id)
        if await session.scalar(stmt) is None:
            return slug
        slug = f"{base}-{random_suffix()}"


async def unique_category_slug(
    session: AsyncSession, workspace_id: uuid.UUID, name: str
) -> str:
    base = slugify(name)[:120] or "category"
    slug = base
    while await session.scalar(
        select(KBCategory.id).where(
            KBCategory.workspace_id == workspace_id, KBCategory.slug == slug
        )
    ):
        slug = f"{base}-{random_suffix()}"
    return slug


def apply_status(article: KBArticle, status: ArticleStatus) -> None:
    """Publishing stamps a timestamp; unpublishing clears it."""
    article.status = status
    if status == ArticleStatus.published and article.published_at is None:
        article.published_at = datetime.now(timezone.utc)
    elif status == ArticleStatus.draft:
        article.published_at = None


async def search_articles(
    session: AsyncSession,
    workspace_id: uuid.UUID,
    query: str,
    *,
    published_only: bool = True,
    limit: int = 10,
) -> List[ArticleSummary]:
    """Full-text search over published articles.

    Uses the generated ``search_vector`` column (GIN-indexed) with
    ``websearch_to_tsquery`` so end users can type natural queries. Falls back
    to a prefix/ILIKE match when the query has no usable lexemes (e.g. a single
    short word mid-typing), which is what makes widget auto-suggest feel live.
    """
    query = (query or "").strip()
    if not query:
        return []

    stmt = (
        select(KBArticle, KBCategory.name)
        .outerjoin(KBCategory, KBCategory.id == KBArticle.category_id)
        .where(KBArticle.workspace_id == workspace_id)
    )
    if published_only:
        stmt = stmt.where(KBArticle.status == ArticleStatus.published)

    tsquery = func.websearch_to_tsquery("english", query)
    ranked = (
        stmt.where(KBArticle.search_vector.op("@@")(tsquery))
        .order_by(func.ts_rank(KBArticle.search_vector, tsquery).desc())
        .limit(limit)
    )
    rows = (await session.execute(ranked)).all()

    if not rows:
        term = f"%{query.lower()}%"
        fallback = stmt.where(
            or_(
                func.lower(KBArticle.title).like(term),
                func.lower(KBArticle.body_text).like(term),
            )
        ).limit(limit)
        rows = (await session.execute(fallback)).all()

    return [
        ArticleSummary(
            id=a.id,
            title=a.title,
            slug=a.slug,
            excerpt=excerpt(a.body_text),
            category_name=category_name,
        )
        for a, category_name in rows
    ]


async def article_counts(
    session: AsyncSession, category_ids: Sequence[uuid.UUID]
) -> dict:
    if not category_ids:
        return {}
    rows = (
        await session.execute(
            select(KBArticle.category_id, func.count())
            .where(KBArticle.category_id.in_(category_ids))
            .group_by(KBArticle.category_id)
        )
    ).all()
    return {cid: int(count) for cid, count in rows}
