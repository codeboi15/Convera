from __future__ import annotations

import uuid
from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, ConfigDict, EmailStr, Field

from app.models.enums import Channel, ConversationStatus, SenderType


class ContactOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    name: Optional[str] = None
    email: Optional[EmailStr] = None
    last_seen_at: Optional[datetime] = None


class MessageOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    conversation_id: uuid.UUID
    seq: int
    sender_type: SenderType
    sender_user_id: Optional[uuid.UUID] = None
    sender_contact_id: Optional[uuid.UUID] = None
    body: str
    html: Optional[str] = None
    read_at: Optional[datetime] = None
    created_at: datetime


class AssigneeOut(BaseModel):
    id: uuid.UUID
    name: Optional[str] = None
    email: EmailStr


class ConversationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    channel: Channel
    status: ConversationStatus
    subject: Optional[str] = None
    contact: ContactOut
    assignee: Optional[AssigneeOut] = None
    last_message_at: Optional[datetime] = None
    snoozed_until: Optional[datetime] = None
    message_count: int
    ai_summary: Optional[str] = None
    ai_summary_updated_at: Optional[datetime] = None
    created_at: datetime
    last_message_preview: Optional[str] = None
    unread_count: int = 0


class ConversationDetail(ConversationOut):
    messages: List[MessageOut] = []


class ConversationListOut(BaseModel):
    items: List[ConversationOut]
    total: int
    limit: int
    offset: int


class SendMessageRequest(BaseModel):
    body: str = Field(min_length=1, max_length=20000)


class AssignRequest(BaseModel):
    # None clears the assignment.
    assignee_id: Optional[uuid.UUID] = None


class StatusRequest(BaseModel):
    status: ConversationStatus
    # Required when status is "snoozed".
    snoozed_until: Optional[datetime] = None
