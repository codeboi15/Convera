from __future__ import annotations

from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_session
from app.models.enums import ArticleStatus
from app.models.kb import KBArticle, KBCategory
from app.models.workspace import Workspace
from app.schemas.kb import (
    ArticleSummary,
    PublicArticle,
    PublicCategory,
    PublicKnowledgeBase,
)
from app.services import kb as kb_service

router = APIRouter()


async def _resolve_workspace(
    session: AsyncSession, identifier: str
) -> Workspace:
    """Look up a workspace by slug or by connected custom domain.

    Accepting both is what lets the same public pages serve
    ``/kb/acme`` and ``help.acme.com``.
    """
    workspace = await session.scalar(
        select(Workspace).where(
            or_(
                Workspace.slug == identifier.lower(),
                Workspace.custom_domain == identifier.lower(),
            )
        )
    )
    if workspace is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Knowledge base not found"
        )
    return workspace


@router.get("/{identifier}", response_model=PublicKnowledgeBase)
async def public_index(
    identifier: str, session: AsyncSession = Depends(get_session)
) -> PublicKnowledgeBase:
    """Published articles grouped by category — the public help centre index."""
    workspace = await _resolve_workspace(session, identifier)

    categories = (
        await session.scalars(
            select(KBCategory)
            .where(KBCategory.workspace_id == workspace.id)
            .order_by(KBCategory.position, KBCategory.name)
        )
    ).all()

    rows = (
        await session.execute(
            select(KBArticle)
            .where(
                KBArticle.workspace_id == workspace.id,
                KBArticle.status == ArticleStatus.published,
            )
            .order_by(KBArticle.title)
        )
    ).scalars().all()

    by_category: dict = {}
    uncategorized: List[ArticleSummary] = []
    for article in rows:
        summary = ArticleSummary(
            id=article.id,
            title=article.title,
            slug=article.slug,
            excerpt=kb_service.excerpt(article.body_text),
        )
        if article.category_id is None:
            uncategorized.append(summary)
        else:
            by_category.setdefault(article.category_id, []).append(summary)

    return PublicKnowledgeBase(
        workspace_name=workspace.name,
        workspace_slug=workspace.slug,
        categories=[
            PublicCategory(
                name=c.name, slug=c.slug, articles=by_category.get(c.id, [])
            )
            for c in categories
            if by_category.get(c.id)
        ],
        uncategorized=uncategorized,
    )


@router.get("/{identifier}/search", response_model=List[ArticleSummary])
async def public_search(
    identifier: str,
    q: str = Query(min_length=1, max_length=200),
    limit: int = Query(default=10, ge=1, le=25),
    session: AsyncSession = Depends(get_session),
) -> List[ArticleSummary]:
    """Search published articles. Also powers the chat widget's suggestions."""
    workspace = await _resolve_workspace(session, identifier)
    return await kb_service.search_articles(
        session, workspace.id, q, published_only=True, limit=limit
    )


@router.get("/{identifier}/articles/{slug}", response_model=PublicArticle)
async def public_article(
    identifier: str, slug: str, session: AsyncSession = Depends(get_session)
) -> PublicArticle:
    workspace = await _resolve_workspace(session, identifier)
    article = await session.scalar(
        select(KBArticle).where(
            KBArticle.workspace_id == workspace.id,
            KBArticle.slug == slug,
            KBArticle.status == ArticleStatus.published,
        )
    )
    if article is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Article not found"
        )

    category_name: Optional[str] = None
    if article.category_id:
        category_name = await session.scalar(
            select(KBCategory.name).where(KBCategory.id == article.category_id)
        )

    return PublicArticle(
        id=article.id,
        title=article.title,
        slug=article.slug,
        body_html=article.body_html,
        category_name=category_name,
        published_at=article.published_at,
    )
