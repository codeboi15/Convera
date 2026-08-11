from __future__ import annotations

import uuid
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import CurrentUser, get_workspace_context
from app.core.db import get_session
from app.models.enums import ArticleStatus
from app.models.kb import KBArticle, KBCategory
from app.schemas.kb import (
    ArticleCreate,
    ArticleOut,
    ArticleSummary,
    ArticleUpdate,
    CategoryCreate,
    CategoryOut,
    CategoryUpdate,
)
from app.services import kb as kb_service

router = APIRouter()


# ── Categories ──────────────────────────────────────────────────────────

@router.get("/categories", response_model=List[CategoryOut])
async def list_categories(
    current: CurrentUser = Depends(get_workspace_context),
    session: AsyncSession = Depends(get_session),
) -> List[CategoryOut]:
    categories = (
        await session.scalars(
            select(KBCategory)
            .where(KBCategory.workspace_id == current.workspace_id)
            .order_by(KBCategory.position, KBCategory.name)
        )
    ).all()
    counts = await kb_service.article_counts(session, [c.id for c in categories])
    return [
        CategoryOut(
            id=c.id,
            name=c.name,
            slug=c.slug,
            position=c.position,
            article_count=counts.get(c.id, 0),
        )
        for c in categories
    ]


@router.post(
    "/categories", response_model=CategoryOut, status_code=status.HTTP_201_CREATED
)
async def create_category(
    payload: CategoryCreate,
    current: CurrentUser = Depends(get_workspace_context),
    session: AsyncSession = Depends(get_session),
) -> CategoryOut:
    category = KBCategory(
        workspace_id=current.workspace_id,
        name=payload.name,
        slug=await kb_service.unique_category_slug(
            session, current.workspace_id, payload.name
        ),
        position=payload.position,
    )
    session.add(category)
    await session.commit()
    await session.refresh(category)
    return CategoryOut(
        id=category.id,
        name=category.name,
        slug=category.slug,
        position=category.position,
        article_count=0,
    )


async def _load_category(
    session: AsyncSession, current: CurrentUser, category_id: uuid.UUID
) -> KBCategory:
    category = await session.scalar(
        select(KBCategory).where(
            KBCategory.id == category_id,
            KBCategory.workspace_id == current.workspace_id,
        )
    )
    if category is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Category not found"
        )
    return category


@router.patch("/categories/{category_id}", response_model=CategoryOut)
async def update_category(
    category_id: uuid.UUID,
    payload: CategoryUpdate,
    current: CurrentUser = Depends(get_workspace_context),
    session: AsyncSession = Depends(get_session),
) -> CategoryOut:
    category = await _load_category(session, current, category_id)
    if payload.name is not None:
        category.name = payload.name
    if payload.position is not None:
        category.position = payload.position
    await session.commit()
    await session.refresh(category)
    counts = await kb_service.article_counts(session, [category.id])
    return CategoryOut(
        id=category.id,
        name=category.name,
        slug=category.slug,
        position=category.position,
        article_count=counts.get(category.id, 0),
    )


@router.delete(
    "/categories/{category_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
)
async def delete_category(
    category_id: uuid.UUID,
    current: CurrentUser = Depends(get_workspace_context),
    session: AsyncSession = Depends(get_session),
) -> Response:
    """Delete a category. Articles are kept and become uncategorized."""
    category = await _load_category(session, current, category_id)
    await session.delete(category)
    await session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# ── Articles ────────────────────────────────────────────────────────────

def _to_out(article: KBArticle, category_name: Optional[str] = None) -> ArticleOut:
    return ArticleOut(
        id=article.id,
        title=article.title,
        slug=article.slug,
        body_html=article.body_html,
        body_text=article.body_text,
        status=article.status,
        category_id=article.category_id,
        category_name=category_name,
        published_at=article.published_at,
        created_at=article.created_at,
        updated_at=article.updated_at,
    )


@router.get("/articles", response_model=List[ArticleOut])
async def list_articles(
    status_filter: Optional[ArticleStatus] = Query(default=None, alias="status"),
    category_id: Optional[uuid.UUID] = None,
    search: Optional[str] = Query(default=None, max_length=200),
    current: CurrentUser = Depends(get_workspace_context),
    session: AsyncSession = Depends(get_session),
) -> List[ArticleOut]:
    stmt = (
        select(KBArticle, KBCategory.name)
        .outerjoin(KBCategory, KBCategory.id == KBArticle.category_id)
        .where(KBArticle.workspace_id == current.workspace_id)
    )
    if status_filter is not None:
        stmt = stmt.where(KBArticle.status == status_filter)
    if category_id is not None:
        stmt = stmt.where(KBArticle.category_id == category_id)
    if search:
        term = f"%{search.lower()}%"
        stmt = stmt.where(func.lower(KBArticle.title).like(term))

    rows = (
        await session.execute(stmt.order_by(KBArticle.updated_at.desc()))
    ).all()
    return [_to_out(a, name) for a, name in rows]


@router.post(
    "/articles", response_model=ArticleOut, status_code=status.HTTP_201_CREATED
)
async def create_article(
    payload: ArticleCreate,
    current: CurrentUser = Depends(get_workspace_context),
    session: AsyncSession = Depends(get_session),
) -> ArticleOut:
    if payload.category_id is not None:
        await _load_category(session, current, payload.category_id)

    html = kb_service.sanitize_html(payload.body_html)
    article = KBArticle(
        workspace_id=current.workspace_id,
        category_id=payload.category_id,
        title=payload.title,
        slug=await kb_service.unique_article_slug(
            session, current.workspace_id, payload.title
        ),
        body_html=html,
        body_text=kb_service.to_plain_text(html),
    )
    kb_service.apply_status(article, payload.status)
    session.add(article)
    await session.commit()
    await session.refresh(article)
    return _to_out(article)


async def _load_article(
    session: AsyncSession, current: CurrentUser, article_id: uuid.UUID
) -> KBArticle:
    article = await session.scalar(
        select(KBArticle).where(
            KBArticle.id == article_id,
            KBArticle.workspace_id == current.workspace_id,
        )
    )
    if article is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Article not found"
        )
    return article


@router.get("/articles/{article_id}", response_model=ArticleOut)
async def get_article(
    article_id: uuid.UUID,
    current: CurrentUser = Depends(get_workspace_context),
    session: AsyncSession = Depends(get_session),
) -> ArticleOut:
    article = await _load_article(session, current, article_id)
    name = (
        await session.scalar(
            select(KBCategory.name).where(KBCategory.id == article.category_id)
        )
        if article.category_id
        else None
    )
    return _to_out(article, name)


@router.patch("/articles/{article_id}", response_model=ArticleOut)
async def update_article(
    article_id: uuid.UUID,
    payload: ArticleUpdate,
    current: CurrentUser = Depends(get_workspace_context),
    session: AsyncSession = Depends(get_session),
) -> ArticleOut:
    article = await _load_article(session, current, article_id)

    if payload.category_id is not None:
        await _load_category(session, current, payload.category_id)
        article.category_id = payload.category_id
    if payload.title is not None and payload.title != article.title:
        article.title = payload.title
        article.slug = await kb_service.unique_article_slug(
            session, current.workspace_id, payload.title, exclude_id=article.id
        )
    if payload.body_html is not None:
        article.body_html = kb_service.sanitize_html(payload.body_html)
        article.body_text = kb_service.to_plain_text(article.body_html)
    if payload.status is not None:
        kb_service.apply_status(article, payload.status)

    await session.commit()
    await session.refresh(article)
    return _to_out(article)


@router.delete(
    "/articles/{article_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
)
async def delete_article(
    article_id: uuid.UUID,
    current: CurrentUser = Depends(get_workspace_context),
    session: AsyncSession = Depends(get_session),
) -> Response:
    article = await _load_article(session, current, article_id)
    await session.delete(article)
    await session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/search", response_model=List[ArticleSummary])
async def search_kb(
    q: str = Query(min_length=1, max_length=200),
    limit: int = Query(default=10, ge=1, le=25),
    current: CurrentUser = Depends(get_workspace_context),
    session: AsyncSession = Depends(get_session),
) -> List[ArticleSummary]:
    return await kb_service.search_articles(
        session, current.workspace_id, q, published_only=False, limit=limit
    )
