from __future__ import annotations

import uuid
from typing import List, Optional

from pydantic import BaseModel, EmailStr, Field

from app.schemas.conversation import MessageOut


class WidgetInitRequest(BaseModel):
    workspace_slug: str = Field(min_length=1, max_length=120)
    # Stable anonymous id kept in the visitor's localStorage.
    visitor_id: Optional[str] = Field(default=None, max_length=128)
    name: Optional[str] = Field(default=None, max_length=255)
    email: Optional[EmailStr] = None


class WidgetSession(BaseModel):
    token: str
    visitor_id: str
    workspace_id: uuid.UUID
    workspace_name: str
    contact_id: uuid.UUID
    conversation_id: uuid.UUID
    messages: List[MessageOut] = []
    agents_online: bool = False
