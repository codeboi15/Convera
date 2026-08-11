from __future__ import annotations

import uuid
from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, ConfigDict, Field

from app.models.enums import ArticleStatus


class CategoryCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    position: int = 0


class CategoryUpdate(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=255)
    position: Optional[int] = None


class CategoryOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    name: str
    slug: str
    position: int
    article_count: int = 0


class ArticleCreate(BaseModel):
    title: str = Field(min_length=1, max_length=500)
    body_html: str = ""
    category_id: Optional[uuid.UUID] = None
    status: ArticleStatus = ArticleStatus.draft


class ArticleUpdate(BaseModel):
    title: Optional[str] = Field(default=None, min_length=1, max_length=500)
    body_html: Optional[str] = None
    category_id: Optional[uuid.UUID] = None
    status: Optional[ArticleStatus] = None


class ArticleOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    title: str
    slug: str
    body_html: str
    body_text: str
    status: ArticleStatus
    category_id: Optional[uuid.UUID] = None
    category_name: Optional[str] = None
    published_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime


class ArticleSummary(BaseModel):
    """Lightweight shape for lists, search results, and widget suggestions."""

    id: uuid.UUID
    title: str
    slug: str
    excerpt: str
    category_name: Optional[str] = None


class PublicArticle(BaseModel):
    id: uuid.UUID
    title: str
    slug: str
    body_html: str
    category_name: Optional[str] = None
    published_at: Optional[datetime] = None


class PublicCategory(BaseModel):
    name: str
    slug: str
    articles: List[ArticleSummary] = []


class PublicKnowledgeBase(BaseModel):
    workspace_name: str
    workspace_slug: str
    categories: List[PublicCategory] = []
    uncategorized: List[ArticleSummary] = []
